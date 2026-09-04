"""Tabbed "Add reference" picker dialog.

Consolidates the reference-add entry points into one dialog: source tabs
(Library / Community / My observations / Enter manually) sharing a single
:class:`ReferencePreviewPane`, docked beside the tab widget in a top-level
splitter so every tab's selection populates the same preview instance
instead of each tab owning its own. Library, Community, and My observations
are wired; Enter manually shows an honest, visibly-stubbed placeholder.

The Community tab embeds :class:`~ui.cloud_reference_dialog.CommunityResultsPane`,
which relocates ``CloudReferenceDialog``'s browse/select flow (its search
workers and payload builders, reused rather than duplicated) into the
picker. Unlike that legacy dialog, genus/species are fixed by the picker's
working taxon, so results load automatically instead of behind a search
button, and the dialog's two footer buttons ("Import summary as reference" /
"Use raw points for plot") become a radio the tab exposes instead
("Range summary" / "Raw points (n=X)"). A cloud entry has no measurement-set
or observation identity, so "Add to plot" routes through a dedicated
``cloud_attach_callback(dict)`` rather than the string-identifier
``attach_callback`` the other tabs use, straight to the same
``_add_reference_series_entry`` path the legacy dialog already calls
directly -- no new persistence. ``CloudReferenceDialog`` itself stays
reachable for now; stage 6 removes that dead entry point.

The Library tab does not fork any add/attach logic: selecting a result and
clicking "Add to plot" calls the ``attach_callback`` supplied by the host
(MainWindow), which is expected to be
``MainWindow._attach_normalized_reference_to_active_observation`` — the
exact path the (soon to be retired) ``ReferenceLibraryAttachDialog`` uses.
Color assignment is not touched here: it happens automatically, keyed by
list position, inside ``MainWindow._resolved_reference_series_entries``.

The My observations tab lists previous observations of the working taxon —
the same query (``ObservationDB.get_personal_observations_for_species``)
that populates the legacy Source dropdown's "My data <date>" entries — and
routes "Add to plot" through the same ``attach_callback``, but with an
``"observation:<id>"``-prefixed identifier: a personal observation has no
normalized measurement-set identity, so the host dispatches that prefix to
the legacy ``source_kind == "observation"`` comparison-series path instead
of the measurement-set attach path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from database.models import MeasurementDB, ObservationDB
from database.reference_library import (
    MeasurementSet,
    MeasurementSetCandidate,
    MeasurementSetRepository,
)

from .cloud_reference_dialog import CommunityResultsPane
from .reference_preview_pane import ReferencePreviewPane
from .two_line_row import TwoLineRow

_NEW_PUBLICATION_ROLE = "new_publication"

_USABLE_MEASUREMENT_TYPES = (None, "", "manual", "spore", "spores")


def filter_library_candidates(
    candidates: Iterable[MeasurementSetCandidate],
    *,
    taxon_id: str | None,
    only_this_taxon: bool,
    query: str = "",
) -> list[MeasurementSetCandidate]:
    """Pure taxon+search filter for the Library tab's results list.

    Mirrors ``ReferenceLibraryAttachDialog._filtered_candidates``'s taxon
    scope and text-search semantics (search matches short label, published
    taxon name, and raw expression; taxon scope and search AND together) so
    both dialogs behave identically without sharing dialog state.
    """
    result = list(candidates)
    if taxon_id is not None and only_this_taxon:
        target = str(taxon_id)
        result = [c for c in result if str(getattr(c, "taxon_id", "") or "") == target]
    normalized_query = (query or "").strip().casefold()
    if normalized_query:
        def _match(c: MeasurementSetCandidate) -> bool:
            for field_value in (c.short_label, c.name_as_published, c.raw_text):
                if field_value and normalized_query in str(field_value).casefold():
                    return True
            return False

        result = [c for c in result if _match(c)]
    return result


@dataclass
class PersonalObservationCandidate:
    """One row in the My observations tab: a different personal observation
    of the working taxon, with spore measurements usable as a comparison
    series."""

    observation_id: int
    date: str
    author: str
    location: str
    points: list[dict]

    @property
    def n(self) -> int:
        return len(self.points)


def default_my_observation_candidates(
    genus: str, species: str, *, exclude_observation_id: int | None = None
) -> list[PersonalObservationCandidate]:
    """Load My-observations candidates from the same query that populates
    the legacy Source dropdown's "My data <date>" entries.

    Only observations with at least one usable spore measurement are
    returned (mirrors the point-filtering in
    ``MainWindow._maybe_load_reference_panel_reference``'s observation
    branch), since an entry with no points cannot be plotted.
    """
    if not genus or not species:
        return []
    rows = ObservationDB.get_personal_observations_for_species(
        genus, species, exclude_observation_id=exclude_observation_id
    )
    result: list[PersonalObservationCandidate] = []
    for row in rows:
        try:
            obs_id = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue
        raw = MeasurementDB.get_measurements_for_observation(obs_id)
        points = [
            m for m in raw
            if m.get("length_um") is not None
            and m.get("width_um") is not None
            and m.get("measurement_type") in _USABLE_MEASUREMENT_TYPES
        ]
        if not points:
            continue
        obs = ObservationDB.get_observation(obs_id) or {}
        date_str = (row.get("date") or "").split(" ")[0].split("T")[0]
        result.append(
            PersonalObservationCandidate(
                observation_id=obs_id,
                date=date_str,
                author=(row.get("author") or "").strip(),
                location=(obs.get("location") or "").strip(),
                points=points,
            )
        )
    return result


class _StubTabPane(QWidget):
    """Honest placeholder for a not-yet-wired source tab."""

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(message, self)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addWidget(label)


class AddReferenceDialog(QDialog):
    """Tabbed picker for adding a reference dataset to the comparison plot.

    "Library", "Community", and "My observations" are functional; "Enter
    manually" shows a stub pane (wired in a later stage per the plan).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        taxon_label: str = "",
        taxon_id: int | str | None = None,
        genus: str = "",
        species: str = "",
        exclude_observation_id: int | None = None,
        exclude_measurement_set_ids: Iterable[str] | None = None,
        attach_callback: Callable[[str, str], None] | None = None,
        cloud_attach_callback: Callable[[dict], None] | None = None,
        candidates: list[MeasurementSetCandidate] | None = None,
        my_observations: list[PersonalObservationCandidate] | None = None,
        community_results: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self._taxon_id: str | None = str(taxon_id).strip() or None if taxon_id is not None else None
        self._genus = genus
        self._species = species
        self._exclude_observation_id = exclude_observation_id
        self._exclude_ids = {str(x) for x in (exclude_measurement_set_ids or [])}
        self._attach_callback = attach_callback
        self._cloud_attach_callback = cloud_attach_callback
        # Optional injected candidate list, mirroring
        # ReferenceLibraryAttachDialog's testability convention: when
        # provided, skips the repository query so tests/scenarios can run
        # against deterministic fixtures without a real reference DB.
        self._injected_candidates = (
            [c for c in candidates if str(c.measurement_set_id) not in self._exclude_ids]
            if candidates is not None
            else None
        )
        self._injected_my_observations = my_observations
        self._injected_community_results = community_results
        self._candidates: list[MeasurementSetCandidate] = []
        self._selected_candidate: MeasurementSetCandidate | None = None
        self._my_observations: list[PersonalObservationCandidate] = []
        self._selected_observation: PersonalObservationCandidate | None = None

        title = self.tr("Add reference")
        if taxon_label:
            title = self.tr("Add reference — {taxon}").format(taxon=taxon_label)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(820, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        body_splitter = QSplitter(Qt.Horizontal, self)
        self.tabs = QTabWidget(body_splitter)
        body_splitter.addWidget(self.tabs)
        # Single shared preview pane (reused from Stage 1 — never rebuilt):
        # every tab's selection populates this one instance.
        self.preview_pane = ReferencePreviewPane(body_splitter)
        body_splitter.addWidget(self.preview_pane)
        body_splitter.setStretchFactor(0, 1)
        body_splitter.setStretchFactor(1, 2)
        root.addWidget(body_splitter, 1)

        self._build_library_tab()
        self.tabs.addTab(self._library_tab, self.tr("Library"))
        self._build_community_tab()
        self._community_tab_index = self.tabs.addTab(self._community_tab, self.tr("Community"))
        self._build_my_observations_tab()
        self._my_observations_tab_index = self.tabs.addTab(
            self._my_observations_tab, self.tr("My observations")
        )
        self.tabs.addTab(
            _StubTabPane(self.tr("Coming in a later stage")),
            self.tr("Enter manually"),
        )
        self.tabs.currentChanged.connect(self._on_tab_changed)

        footer = QHBoxLayout()
        self.status_hint_label = QLabel("", self)
        self.status_hint_label.setStyleSheet("color: #7f8c8d;")
        footer.addWidget(self.status_hint_label, 1)
        self.cancel_btn = QPushButton(self.tr("Cancel"), self)
        self.cancel_btn.clicked.connect(self.reject)
        footer.addWidget(self.cancel_btn)
        self.add_to_plot_btn = QPushButton(self.tr("Add to plot"), self)
        self.add_to_plot_btn.setEnabled(False)
        self.add_to_plot_btn.setDefault(True)
        self.add_to_plot_btn.clicked.connect(self._on_add_to_plot_clicked)
        footer.addWidget(self.add_to_plot_btn)
        root.addLayout(footer)

        self.preview_pane.clear()
        self._refresh_candidates()
        self._refresh_my_observations()

    def _on_tab_changed(self, _index: int) -> None:
        self._update_footer_state()
        if self.tabs.currentIndex() == self._my_observations_tab_index:
            self._populate_observation_preview(self._selected_observation)
        elif self.tabs.currentIndex() == self._community_tab_index:
            self._community_pane.sync_preview()
        elif self.tabs.currentWidget() is self._library_tab:
            self._populate_preview(self._selected_candidate)
        else:
            self.preview_pane.clear()

    # ------------------------------------------------------------------
    # Library tab
    # ------------------------------------------------------------------

    def _build_library_tab(self) -> None:
        self._library_tab = QWidget(self)
        layout = QVBoxLayout(self._library_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.search_input = QLineEdit(self._library_tab)
        self.search_input.setPlaceholderText(
            self.tr("Filter by publication, taxon, or raw expression…")
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.search_input, 1)
        self.only_this_taxon_checkbox = QCheckBox(self.tr("Only this taxon"), self._library_tab)
        if self._taxon_id is None:
            self.only_this_taxon_checkbox.setEnabled(False)
            self.only_this_taxon_checkbox.setChecked(False)
        else:
            self.only_this_taxon_checkbox.setChecked(True)
        self.only_this_taxon_checkbox.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self.only_this_taxon_checkbox)
        layout.addLayout(filter_row)

        self.results_list = QListWidget(self._library_tab)
        # Elide long rows instead of growing a horizontal scrollbar; matches
        # the row-eliding convention in ui/comparison_panel.py.
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.results_list, 1)

    def _on_filter_changed(self, *_args) -> None:
        self._selected_candidate = None
        self._populate_results_list()
        self._update_footer_state()

    def _refresh_candidates(self) -> None:
        if self._injected_candidates is not None:
            self._candidates = list(self._injected_candidates)
        else:
            self._candidates = MeasurementSetRepository.list_attachment_candidates(
                exclude_ids=self._exclude_ids
            )
        self._selected_candidate = None
        self._populate_results_list()
        self._update_footer_state()

    def _filtered_candidates(self) -> list[MeasurementSetCandidate]:
        return filter_library_candidates(
            self._candidates,
            taxon_id=self._taxon_id,
            only_this_taxon=self.only_this_taxon_checkbox.isChecked(),
            query=self.search_input.text(),
        )

    def _populate_results_list(self) -> None:
        self.results_list.clear()
        visible = self._filtered_candidates()
        for candidate in visible:
            self._add_candidate_item(candidate)
        new_pub_item = QListWidgetItem(self.tr("+ New publication…"))
        new_pub_item.setData(Qt.UserRole, _NEW_PUBLICATION_ROLE)
        new_pub_item.setForeground(self.palette().link())
        self.results_list.addItem(new_pub_item)

        if not visible:
            self.status_hint_label.setText(
                self.tr("No matching measurement sets in the library.")
                if self._candidates
                else self.tr("The reference library has no measurement sets yet.")
            )
        else:
            self.status_hint_label.setText("")
        self.preview_pane.clear()

    def _add_candidate_item(self, candidate: MeasurementSetCandidate) -> None:
        label = candidate.short_label or candidate.name_as_published or self.tr("Untitled")
        # short_label conventionally already ends with the year (see
        # database.reference_citation.build_short_label); only append it
        # when genuinely missing, to avoid "... 2018 (2018)".
        if candidate.year and str(candidate.year) not in label:
            label = f"{label} ({candidate.year})"
        detail = candidate.data_kind or ""
        if candidate.raw_text:
            detail = f"{detail} · {candidate.raw_text}" if detail else candidate.raw_text

        item = QListWidgetItem()
        item.setToolTip(label if not detail else f"{label}\n{detail}")
        item.setData(Qt.UserRole, candidate.measurement_set_id)
        item.setData(Qt.UserRole + 1, detail)
        self.results_list.addItem(item)
        row_widget = TwoLineRow(label, detail, self.results_list)
        item.setSizeHint(row_widget.sizeHint())
        self.results_list.setItemWidget(item, row_widget)

    def _on_selection_changed(self) -> None:
        items = self.results_list.selectedItems()
        if not items:
            self._selected_candidate = None
            self.preview_pane.clear()
            self._update_footer_state()
            return
        role = items[0].data(Qt.UserRole)
        if role == _NEW_PUBLICATION_ROLE:
            self._selected_candidate = None
            self._on_new_publication_clicked()
            return
        candidate = next(
            (c for c in self._candidates if c.measurement_set_id == role),
            None,
        )
        self._selected_candidate = candidate
        self._populate_preview(candidate)
        self._update_footer_state()

    def _populate_preview(self, candidate: MeasurementSetCandidate | None) -> None:
        if candidate is None:
            self.preview_pane.clear()
            return
        measurement_set: MeasurementSet | None = MeasurementSetRepository.get(
            candidate.measurement_set_id
        )
        title = candidate.short_label or candidate.name_as_published or self.tr("Untitled")
        meta = candidate.name_as_published or ""
        if candidate.locator_text:
            meta = f"{meta} · {candidate.locator_text}" if meta else candidate.locator_text
        rows: list[tuple[str, str, str, str]] = []
        if measurement_set is not None:
            for label, prefix in (
                (self.tr("Length"), "length"),
                (self.tr("Width"), "width"),
                (self.tr("Q"), "q"),
            ):
                vmin = getattr(measurement_set, f"{prefix}_min", None)
                vmax = getattr(measurement_set, f"{prefix}_max", None)
                vmean = getattr(measurement_set, f"{prefix}_mean", None)
                rows.append(
                    (
                        label,
                        self._format_stat(vmin),
                        self._format_stat(vmean),
                        self._format_stat(vmax),
                    )
                )
        note = candidate.raw_text or self.tr("No additional notes.")
        self.preview_pane.set_summary(title, meta, rows, note)

        if measurement_set is not None and measurement_set.raw_points_json:
            self.preview_pane.set_raw_spores(measurement_set.raw_points_json)
        else:
            # Range-kind measurement sets have no raw points to show.
            self.preview_pane.set_raw_spores(
                self.tr("This is a range summary; no raw spore points are stored.")
            )
        if measurement_set is not None:
            self.preview_pane.set_method(
                {
                    "mount": measurement_set.mount_medium or "",
                    "stain": measurement_set.stain or "",
                    "sample_type": measurement_set.preparation or "",
                    "objective": measurement_set.measurement_method or "",
                }
            )
            self.preview_pane.set_calibration(
                measurement_set.notes or self.tr("No calibration details recorded.")
            )
        self.preview_pane.set_provenance(
            self.tr("Publication: {work}").format(work=candidate.work_title or candidate.name_as_published or "—")
        )

    @staticmethod
    def _min_mean_max_from_points(points: list[dict]) -> dict:
        """Length/width/Q min-mean-max, for the My-observations preview.

        A lighter-weight sibling of ``MainWindow._reference_stats_from_points``
        (which also computes percentiles the Summary tab here does not use).
        """
        lengths = [p["length_um"] for p in points if p.get("length_um") is not None]
        widths = [p["width_um"] for p in points if p.get("width_um") is not None]
        if not lengths or not widths:
            return {}
        qs = [l / w for l, w in zip(lengths, widths) if w]
        stats: dict[str, float] = {}
        for prefix, values in (("length", lengths), ("width", widths), ("q", qs)):
            if not values:
                continue
            stats[f"{prefix}_min"] = min(values)
            stats[f"{prefix}_mean"] = sum(values) / len(values)
            stats[f"{prefix}_max"] = max(values)
        return stats

    @staticmethod
    def _format_stat(value) -> str:
        if value is None:
            return "—"
        try:
            return f"{float(value):.2f}"
        except Exception:
            return str(value)

    def _on_new_publication_clicked(self) -> None:
        try:
            from .reference_library_manager_dialog import ReferenceWorkEditor
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.tr("New publication"),
                self.tr("Reference library editor is unavailable: {error}").format(error=str(exc)),
            )
            self._populate_results_list()
            return
        editor = ReferenceWorkEditor(self, persist_on_accept=True)
        try:
            editor.exec()
        finally:
            editor.deleteLater()
        self._refresh_candidates()

    # ------------------------------------------------------------------
    # Community tab
    # ------------------------------------------------------------------

    def _build_community_tab(self) -> None:
        self._community_tab = QWidget(self)
        layout = QVBoxLayout(self._community_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._community_pane = CommunityResultsPane(
            self._community_tab,
            genus=self._genus,
            species=self._species,
            preview_pane=self.preview_pane,
            results=self._injected_community_results,
        )
        self._community_pane.selection_changed.connect(self._update_footer_state)
        layout.addWidget(self._community_pane, 1)

    # ------------------------------------------------------------------
    # My observations tab
    # ------------------------------------------------------------------

    def _build_my_observations_tab(self) -> None:
        self._my_observations_tab = QWidget(self)
        layout = QVBoxLayout(self._my_observations_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.my_observations_list = QListWidget(self._my_observations_tab)
        self.my_observations_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.my_observations_list.itemSelectionChanged.connect(
            self._on_my_observations_selection_changed
        )
        layout.addWidget(self.my_observations_list, 1)

        self.my_observations_status_label = QLabel("", self._my_observations_tab)
        self.my_observations_status_label.setStyleSheet("color: #7f8c8d;")
        self.my_observations_status_label.setWordWrap(True)
        layout.addWidget(self.my_observations_status_label)

    def _refresh_my_observations(self) -> None:
        if self._injected_my_observations is not None:
            self._my_observations = list(self._injected_my_observations)
        else:
            self._my_observations = default_my_observation_candidates(
                self._genus,
                self._species,
                exclude_observation_id=self._exclude_observation_id,
            )
        self._selected_observation = None
        self._populate_my_observations_list()
        self._update_footer_state()

    def _populate_my_observations_list(self) -> None:
        self.my_observations_list.clear()
        for candidate in self._my_observations:
            self._add_observation_item(candidate)
        self.my_observations_status_label.setText(
            "" if self._my_observations
            else self.tr("No previous observations of this taxon have spore measurements.")
        )
        if self.tabs.currentIndex() == self._my_observations_tab_index:
            self.preview_pane.clear()

    def _add_observation_item(self, candidate: PersonalObservationCandidate) -> None:
        label = (
            self.tr("My observation — {author}").format(author=candidate.author)
            if candidate.author
            else self.tr("My observation")
        )
        detail_parts = [candidate.date] if candidate.date else []
        detail_parts.append(self.tr("n = {count}").format(count=candidate.n))
        if candidate.location:
            detail_parts.append(candidate.location)
        detail = " · ".join(detail_parts)

        item = QListWidgetItem()
        item.setToolTip(label if not detail else f"{label}\n{detail}")
        item.setData(Qt.UserRole, candidate.observation_id)
        self.my_observations_list.addItem(item)
        row_widget = TwoLineRow(label, detail, self.my_observations_list)
        item.setSizeHint(row_widget.sizeHint())
        self.my_observations_list.setItemWidget(item, row_widget)

    def _on_my_observations_selection_changed(self) -> None:
        items = self.my_observations_list.selectedItems()
        if not items:
            self._selected_observation = None
            self.preview_pane.clear()
            self._update_footer_state()
            return
        observation_id = items[0].data(Qt.UserRole)
        candidate = next(
            (c for c in self._my_observations if c.observation_id == observation_id),
            None,
        )
        self._selected_observation = candidate
        self._populate_observation_preview(candidate)
        self._update_footer_state()

    def _populate_observation_preview(
        self, candidate: PersonalObservationCandidate | None
    ) -> None:
        if candidate is None:
            self.preview_pane.clear()
            return
        title = (
            self.tr("My observation — {author}").format(author=candidate.author)
            if candidate.author
            else self.tr("My observation")
        )
        meta_parts = [candidate.date] if candidate.date else []
        if candidate.location:
            meta_parts.append(candidate.location)
        meta = " · ".join(meta_parts)

        stats = self._min_mean_max_from_points(candidate.points)
        rows: list[tuple[str, str, str, str]] = []
        for label, prefix in (
            (self.tr("Length"), "length"),
            (self.tr("Width"), "width"),
            (self.tr("Q"), "q"),
        ):
            rows.append(
                (
                    label,
                    self._format_stat(stats.get(f"{prefix}_min")),
                    self._format_stat(stats.get(f"{prefix}_mean")),
                    self._format_stat(stats.get(f"{prefix}_max")),
                )
            )
        note = self.tr("n = {count} spore measurements").format(count=candidate.n)
        self.preview_pane.set_summary(title, meta, rows, note)

        self.preview_pane.set_raw_spores(
            json.dumps(candidate.points, indent=2, ensure_ascii=False, default=str)
        )
        self.preview_pane.set_method(
            {
                "mount": "",
                "stain": "",
                "sample_type": "",
                "objective": "",
            }
        )
        self.preview_pane.set_calibration(
            self.tr("Not applicable: this is a personal observation, not a normalized library entry.")
        )
        self.preview_pane.set_provenance(
            self.tr("Personal observation, {date}").format(date=candidate.date)
            if candidate.date
            else self.tr("Personal observation")
        )

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _update_footer_state(self) -> None:
        if self.tabs.currentIndex() == self._my_observations_tab_index:
            self.add_to_plot_btn.setEnabled(self._selected_observation is not None)
        elif self.tabs.currentIndex() == self._community_tab_index:
            self.add_to_plot_btn.setEnabled(self._community_pane.has_selection())
        else:
            self.add_to_plot_btn.setEnabled(self._selected_candidate is not None)

    def _on_add_to_plot_clicked(self) -> None:
        if self.tabs.currentIndex() == self._my_observations_tab_index:
            if self._attach_callback is None or self._selected_observation is None:
                return
            self._attach_callback(
                f"observation:{self._selected_observation.observation_id}", "compared"
            )
            self.accept()
            return
        if self.tabs.currentIndex() == self._community_tab_index:
            if self._cloud_attach_callback is None:
                return
            payload = self._community_pane.current_mode_payload()
            if not payload:
                return
            self._cloud_attach_callback(payload)
            self.accept()
            return
        if self._attach_callback is None or self._selected_candidate is None:
            return
        self._attach_callback(self._selected_candidate.measurement_set_id, "compared")
        self.accept()


__all__ = [
    "AddReferenceDialog",
    "filter_library_candidates",
    "PersonalObservationCandidate",
    "default_my_observation_candidates",
]
