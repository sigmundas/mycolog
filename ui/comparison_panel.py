"""Comparison list widget for plotted reference/observation datasets.

Wraps the existing ``reference_series`` state (see ``main_window.py``) in a
richer per-row presentation than the legacy ``ref_series_table``. This stage
does NOT fork state: rows are built from the same resolved entries
(``_resolved_reference_series_entries``) and mutations are routed back
through the existing ops (``_set_reference_series_enabled``,
``_set_reference_series_color``, ``_remove_reference_series_key``). The
legacy QTableWidget list and this widget are kept in sync by both being
refreshed from the same call site.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

RESERVED_OBSERVATION_COLOR = "#3498db"


class SourceKind(Enum):
    OBSERVATION = "observation"
    LIBRARY = "library"
    COMMUNITY = "community"
    MY_OBS = "my_obs"
    MANUAL = "manual"

    @classmethod
    def from_raw(cls, raw: str | None) -> "SourceKind":
        if not raw:
            return cls.MANUAL
        raw = str(raw).strip().lower()
        for member in cls:
            if member.value == raw:
                return member
        # Legacy data uses "reference"/"points" for library/manual entries.
        if raw == "reference":
            return cls.LIBRARY
        if raw == "points":
            return cls.MANUAL
        return cls.MANUAL


@dataclass
class ComparisonRow:
    """One row in the comparison list.

    ``verdict`` is always ``None`` in this stage; verdict computation lands
    in stage 5. Badges render nothing when it is ``None``.
    """

    dataset_id: object  # matches _reference_series_key(...) return value
    title: str
    source_kind: SourceKind
    detail: str
    color: str
    visible: bool
    is_observation: bool
    verdict: object | None = None

    @classmethod
    def from_resolved_entry(cls, entry: dict) -> "ComparisonRow | None":
        """Build a row from one item of ``_resolved_reference_series_entries()``."""
        if not isinstance(entry, dict):
            return None
        key = entry.get("key")
        if key is None:
            return None
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        raw_kind = data.get("source_kind")
        is_observation = raw_kind == "observation"
        kind = SourceKind.OBSERVATION if is_observation else SourceKind.from_raw(raw_kind)
        detail = _format_detail(data)
        color = RESERVED_OBSERVATION_COLOR if is_observation else str(entry.get("color") or "#adb5bd")
        return cls(
            dataset_id=key,
            title=str(entry.get("label") or ""),
            source_kind=kind,
            detail=detail,
            color=color,
            visible=bool(entry.get("enabled", True)),
            is_observation=is_observation,
            verdict=None,
        )


def _format_detail(data: dict) -> str:
    points = data.get("points")
    if isinstance(points, (list, tuple)) and points:
        return f"n = {len(points)}"
    n_value = data.get("n") or data.get("sample_size")
    if n_value:
        return f"n = {n_value}"
    length_min = data.get("length_min")
    length_max = data.get("length_max")
    if length_min is not None and length_max is not None:
        return f"{length_min}–{length_max} µm"
    return str(data.get("source") or data.get("summary") or "")


_SOURCE_KIND_LABELS = {
    SourceKind.OBSERVATION: "Observation",
    SourceKind.LIBRARY: "Library",
    SourceKind.COMMUNITY: "Community",
    SourceKind.MY_OBS: "My observations",
    SourceKind.MANUAL: "Manual",
}


class _ComparisonRowWidget(QFrame):
    toggled = Signal(object, bool)
    color_requested = Signal(object, QWidget)
    remove_requested = Signal(object)

    def __init__(self, row: ComparisonRow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row
        self.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(row.visible)
        self.checkbox.toggled.connect(lambda checked: self.toggled.emit(row.dataset_id, checked))
        layout.addWidget(self.checkbox)

        self.color_chip = QLabel(self)
        self.color_chip.setFixedSize(14, 14)
        self.color_chip.setStyleSheet(
            f"background-color: {row.color}; border-radius: 3px; border: 1px solid #666;"
        )
        layout.addWidget(self.color_chip)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        self.title_label = QLabel(self)
        self.title_label.setTextInteractionFlags(Qt.NoTextInteraction)
        # Ignored so the label's full-text size hint never forces the row (and
        # therefore the scroll area) wider than the viewport; elision in
        # resizeEvent then shrinks the displayed text to fit instead.
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setMinimumWidth(0)
        title_font_metrics = QFontMetrics(self.title_label.font())
        self._title_metrics = title_font_metrics
        self._full_title = row.title
        self.title_label.setText(row.title)
        self.title_label.setToolTip(row.title)
        title_row.addWidget(self.title_label, 1)

        self.badge_label = QLabel(_SOURCE_KIND_LABELS.get(row.source_kind, ""), self)
        self.badge_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        title_row.addWidget(self.badge_label, 0)

        # Verdict badge slot: empty while verdict is None (stage 5 fills it in).
        self.verdict_label = QLabel("", self)
        title_row.addWidget(self.verdict_label, 0)

        text_col.addLayout(title_row)

        self.detail_label = QLabel(row.detail, self)
        self.detail_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        text_col.addWidget(self.detail_label)

        layout.addLayout(text_col, 1)

        self.overflow_btn = QToolButton(self)
        self.overflow_btn.setText("⋯")
        self.overflow_btn.setAutoRaise(True)
        self.overflow_btn.clicked.connect(self._open_overflow_menu)
        layout.addWidget(self.overflow_btn)

        if row.is_observation:
            self.overflow_btn.setEnabled(False)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        elided = self._title_metrics.elidedText(
            self._full_title, Qt.ElideRight, max(self.title_label.width(), 20)
        )
        self.title_label.setText(elided)

    def _open_overflow_menu(self) -> None:
        menu = QMenu(self)
        change_color = menu.addAction(self.tr("Change color…"))
        change_color.setEnabled(not self._row.is_observation)
        edit_action = menu.addAction(self.tr("Edit measurement set…"))
        edit_action.setEnabled(False)  # TODO(stage-6): implement measurement-set editing
        view_action = menu.addAction(self.tr("View details…"))
        view_action.setEnabled(False)  # TODO(stage-6): implement details view
        remove_action = menu.addAction(self.tr("Remove"))
        remove_action.setEnabled(False)  # TODO(stage-6): wire remove from overflow menu
        chosen = menu.exec(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomLeft()))
        if chosen is change_color:
            self.color_requested.emit(self._row.dataset_id, self.overflow_btn)


class ComparisonListWidget(QWidget):
    """Scrollable list of :class:`ComparisonRow` entries.

    Backed by the caller's resolved ``reference_series`` entries; this widget
    does not own or duplicate that state. Call :meth:`set_rows` whenever the
    underlying data changes, and connect :attr:`visibility_toggled` /
    :attr:`color_change_requested` to the existing ops
    (``_set_reference_series_enabled`` / ``_open_reference_series_color_menu``).
    """

    visibility_toggled = Signal(object, bool)
    color_change_requested = Signal(object, QWidget)
    remove_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        # Rows elide their title instead of growing the row width, so the
        # list only ever needs to scroll vertically.
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll, 1)

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._container)

        self._rows: list[ComparisonRow] = []

    def set_rows(self, rows: list[ComparisonRow]) -> None:
        """Replace all rows. Observation row (if present) is pinned first."""
        ordered = sorted(rows, key=lambda r: 0 if r.is_observation else 1)
        self._rows = ordered

        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for row in ordered:
            row_widget = _ComparisonRowWidget(row, self._container)
            row_widget.toggled.connect(self.visibility_toggled.emit)
            row_widget.color_requested.connect(self.color_change_requested.emit)
            row_widget.remove_requested.connect(self.remove_requested.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row_widget)

    def rows(self) -> list[ComparisonRow]:
        return list(self._rows)

    @staticmethod
    def rows_from_resolved_entries(entries: list[dict]) -> list[ComparisonRow]:
        rows = []
        for entry in entries or []:
            row = ComparisonRow.from_resolved_entry(entry)
            if row is not None:
                rows.append(row)
        return rows
