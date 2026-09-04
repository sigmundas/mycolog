"""Model-level tests for ui.comparison_panel.ComparisonRow.

No Qt event loop needed: these exercise the pure translation from
main_window's resolved reference_series entries into ComparisonRow objects,
independent of any widget.
"""
from __future__ import annotations

from ui.comparison_panel import ComparisonRow, ComparisonListWidget, SourceKind, RESERVED_OBSERVATION_COLOR


def _observation_entry(key="obs-key"):
    return {
        "key": key,
        "label": "This observation",
        "enabled": True,
        "color": "#111111",  # ignored for observation rows; reserved color wins
        "preferred_color": None,
        "data": {"source_kind": "observation", "points": [(1, 2)] * 20},
    }


def _library_entry(key="lib-key", enabled=True):
    return {
        "key": key,
        "label": "Funga Nordica",
        "enabled": enabled,
        "color": "#e67e22",
        "preferred_color": "#e67e22",
        "data": {
            "source_kind": "reference",
            "length_min": 8.5,
            "length_max": 10.8,
        },
    }


def _community_points_entry(key="com-key"):
    return {
        "key": key,
        "label": "sporely_community_user_42",
        "enabled": True,
        "color": "#8e44ad",
        "preferred_color": None,
        "data": {"source_kind": "points", "points": list(range(48))},
    }


def test_adding_dataset_produces_a_row():
    rows = ComparisonListWidget.rows_from_resolved_entries([_library_entry()])
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_id == "lib-key"
    assert row.title == "Funga Nordica"
    assert row.source_kind == SourceKind.LIBRARY
    assert row.verdict is None


def test_removing_dataset_removes_the_row():
    entries = [_observation_entry(), _library_entry()]
    rows = ComparisonListWidget.rows_from_resolved_entries(entries)
    assert len(rows) == 2

    entries_after_removal = [_observation_entry()]
    rows_after = ComparisonListWidget.rows_from_resolved_entries(entries_after_removal)
    assert len(rows_after) == 1
    assert rows_after[0].dataset_id == "obs-key"


def test_visibility_round_trips_between_row_and_dataset_state():
    enabled_entry = _library_entry(enabled=True)
    disabled_entry = _library_entry(enabled=False)

    enabled_row = ComparisonRow.from_resolved_entry(enabled_entry)
    disabled_row = ComparisonRow.from_resolved_entry(disabled_entry)

    assert enabled_row.visible is True
    assert disabled_row.visible is False


def test_observation_row_stays_first_regardless_of_insertion_order():
    entries = [_community_points_entry(), _library_entry(), _observation_entry()]
    rows = ComparisonListWidget.rows_from_resolved_entries(entries)
    assert rows[0].is_observation is False  # not yet ordered; ordering happens in set_rows

    ordered = sorted(rows, key=lambda r: 0 if r.is_observation else 1)
    assert ordered[0].is_observation is True
    assert ordered[0].dataset_id == "obs-key"


def test_observation_row_keeps_reserved_color():
    row = ComparisonRow.from_resolved_entry(_observation_entry())
    assert row.color == RESERVED_OBSERVATION_COLOR
