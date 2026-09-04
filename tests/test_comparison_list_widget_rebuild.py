"""Widget-level tests for ComparisonListWidget.set_rows rebuild behavior.

Stage-2 sync path: checkbox toggle -> visibility_toggled -> (host) mutates
reference_series -> refresh -> set_rows rebuilds every row, including the
one just clicked. These tests pin down two properties that must hold across
that rebuild:

1. Programmatically restoring checkbox state during the rebuild (from the
   freshly-resolved ``ComparisonRow.visible``) must not re-emit
   ``visibility_toggled`` -- that would be a feedback loop.
2. Scroll position must survive a rebuild (e.g. a bare toggle on a
   many-row list should not silently jump the list back to the top).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.comparison_panel import ComparisonRow, ComparisonListWidget, SourceKind


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _row(key: str, visible: bool = True) -> ComparisonRow:
    return ComparisonRow(
        dataset_id=key,
        title=f"Row {key}",
        source_kind=SourceKind.LIBRARY,
        detail="n = 10",
        color="#e67e22",
        visible=visible,
        is_observation=False,
        verdict=None,
    )


def test_set_rows_does_not_reemit_visibility_toggled():
    _app()
    widget = ComparisonListWidget()
    rows = [_row(f"k{i}") for i in range(9)]
    widget.set_rows(rows)

    seen: list[tuple[object, bool]] = []
    widget.visibility_toggled.connect(lambda key, checked: seen.append((key, checked)))

    # Simulate the stage-2 sync path: the row model is rebuilt with the same
    # (or updated) visible flags after a toggle is handled by the host.
    rebuilt_rows = [_row(f"k{i}", visible=(i != 3)) for i in range(9)]
    widget.set_rows(rebuilt_rows)

    assert seen == [], (
        "set_rows must not re-emit visibility_toggled while restoring "
        f"checkbox state during rebuild; got {seen}"
    )


def test_set_rows_preserves_scroll_position():
    _app()
    widget = ComparisonListWidget()
    widget.resize(300, 80)  # force a small viewport so 9 rows overflow it
    rows = [_row(f"k{i}") for i in range(9)]
    widget.set_rows(rows)
    widget.show()

    scrollbar = widget._scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    scrolled_value = scrollbar.value()
    assert scrolled_value > 0, "fixture did not produce a scrollable list"

    widget.set_rows(rows)  # rebuild with identical content, as a toggle-refresh would do

    assert scrollbar.value() == scrolled_value
