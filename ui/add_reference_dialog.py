"""Tabbed "Add reference" picker dialog (Stage 3 shell).

Consolidates the reference-add entry points into one dialog: source tabs
(Library / Community / My observations / Enter manually) sharing a filter
row, a results list, and a single :class:`ReferencePreviewPane` (reused
from Stage 1 — never rebuilt here). Only the Library tab is wired this
stage; the other three show an honest, visibly-stubbed placeholder.

The Library tab does not fork any add/attach logic: selecting a result and
clicking "Add to plot" calls the ``attach_callback`` supplied by the host
(MainWindow), which is expected to be
``MainWindow._attach_normalized_reference_to_active_observation`` — the
exact path the (soon to be retired) ``ReferenceLibraryAttachDialog`` uses.
Color assignment is not touched here: it happens automatically, keyed by
list position, inside ``MainWindow._resolved_reference_series_entries``.
"""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
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

from database.reference_library import (
    MeasurementSet,
    MeasurementSetCandidate,
    MeasurementSetRepository,
)

from .reference_preview_pane import ReferencePreviewPane

_NEW_PUBLICATION_ROLE = "new_publication"


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

    Only the "Library" tab is functional this stage; "Community",
    "My observations", and "Enter manually" show stub panes (wired in a
    later stage per the plan).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        taxon_label: str = "",
        taxon_id: int | str | None = None,
        exclude_measurement_set_ids: Iterable[str] | None = None,
        attach_callback: Callable[[str, str], None] | None = None,
        candidates: list[MeasurementSetCandidate] | None = None,
    ) -> None:
        super().__init__(parent)
        self._taxon_id: str | None = str(taxon_id).strip() or None if taxon_id is not None else None
        self._exclude_ids = {str(x) for x in (exclude_measurement_set_ids or [])}
        self._attach_callback = attach_callback
        # Optional injected candidate list, mirroring
        # ReferenceLibraryAttachDialog's testability convention: when
        # provided, skips the repository query so tests/scenarios can run
        # against deterministic fixtures without a real reference DB.
        self._injected_candidates = (
            [c for c in candidates if str(c.measurement_set_id) not in self._exclude_ids]
            if candidates is not None
            else None
        )
        self._candidates: list[MeasurementSetCandidate] = []
        self._selected_candidate: MeasurementSetCandidate | None = None

        title = self.tr("Add reference")
        if taxon_label:
            title = self.tr("Add reference — {taxon}").format(taxon=taxon_label)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(820, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self._build_library_tab()
        self.tabs.addTab(self._library_tab, self.tr("Library"))
        self.tabs.addTab(
            _StubTabPane(self.tr("Coming in a later stage")),
            self.tr("Community"),
        )
        self.tabs.addTab(
            _StubTabPane(self.tr("Coming in a later stage")),
            self.tr("My observations"),
        )
        self.tabs.addTab(
            _StubTabPane(self.tr("Coming in a later stage")),
            self.tr("Enter manually"),
        )

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

        self._refresh_candidates()

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

        splitter = QSplitter(Qt.Horizontal, self._library_tab)
        self.results_list = QListWidget(splitter)
        # Elide long rows instead of growing a horizontal scrollbar; matches
        # the row-eliding convention in ui/comparison_panel.py.
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.results_list)

        self.preview_pane = ReferencePreviewPane(splitter)
        splitter.addWidget(self.preview_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.preview_pane.clear()

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
        metrics = QFontMetrics(self.results_list.font())
        available_width = max(self.results_list.viewport().width() - 12, 120)
        elided_label = metrics.elidedText(label, Qt.ElideRight, available_width)
        item = QListWidgetItem(elided_label)
        item.setToolTip(label)
        item.setData(Qt.UserRole, candidate.measurement_set_id)
        item.setData(Qt.UserRole + 1, detail)
        self.results_list.addItem(item)

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

    def _update_footer_state(self) -> None:
        self.add_to_plot_btn.setEnabled(self._selected_candidate is not None)

    def _on_add_to_plot_clicked(self) -> None:
        if self._selected_candidate is None or self._attach_callback is None:
            return
        self._attach_callback(self._selected_candidate.measurement_set_id, "compared")
        self.accept()


__all__ = ["AddReferenceDialog", "filter_library_candidates"]
