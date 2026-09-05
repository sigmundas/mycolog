"""Model-level tests for ui.comparison_panel.ComparisonRow.

No Qt event loop needed: these exercise the pure translation from
main_window's resolved reference_series entries into ComparisonRow objects,
independent of any widget.
"""
from __future__ import annotations

from ui.comparison_panel import ComparisonRow, ComparisonListWidget, SourceKind, RESERVED_OBSERVATION_COLOR


def _my_obs_entry(key="myobs-key", color="#2ecc71"):
    """A previously-recorded personal observation attached as a reference.

    Legacy state marks this ``source_kind: "observation"`` (see
    ``_attach_personal_observation_reference_to_active_observation`` in
    ``main_window.py``), which collides with the string used for
    ``SourceKind.OBSERVATION``. It must map to ``SourceKind.MY_OBS`` and must
    never be pinned or reserved-blue — only the current-observation row
    (built via ``ComparisonRow.for_current_observation``) gets that.
    """
    return {
        "key": key,
        "label": "Sigmund Ås 2026-08-02",
        "enabled": True,
        "color": color,
        "preferred_color": None,
        "data": {"source_kind": "observation", "points": [(1, 2)] * 17},
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


def _sorted_for_display(rows: list[ComparisonRow]) -> list[ComparisonRow]:
    """Mirror ``ComparisonListWidget.set_rows``'s pin-first ordering."""
    return sorted(rows, key=lambda r: 0 if r.is_observation else 1)


def _normalized_library_entry(key="use-1"):
    """A library-attached row (has ``observation_reference_use_id``), the
    shape ``translate_observation_reference_use`` produces. ``source`` is
    the publication short_label, same as the title -- the detail line must
    not repeat it (see stage-4b-fix Part 2.1).
    """
    return {
        "key": key,
        "label": "A. fulva — Danmarks basidiesvampe",
        "enabled": True,
        "color": "#0072bd",
        "preferred_color": None,
        "data": {
            "source_kind": "reference",
            "observation_reference_use_id": key,
            "source": "Danmarks basidiesvampe",
            "reference_data_kind": "range",
            "raw_text": "7-9.5 × 5.5-7.5",
            "length_p05": 7.0,
            "length_p95": 9.5,
        },
    }


def test_library_row_detail_is_the_measurement_range_not_the_publication_name():
    row = ComparisonRow.from_resolved_entry(_normalized_library_entry())
    assert row.detail == "range · 7-9.5 × 5.5-7.5"


def test_provenance_surfaces_reported_fields_and_not_reported_for_the_rest():
    """Stage 5 Part 5: whichever of method/mount/stain/sample size/specimen
    count are present must surface in the row's provenance tooltip text,
    with "not reported" for the rest -- never a judgment about the value.
    """
    entry = _library_entry()
    entry["data"]["mount_medium"] = "KOH"
    entry["data"]["stain"] = "Congo red"
    row = ComparisonRow.from_resolved_entry(entry)
    assert "Mount medium: KOH" in row.provenance
    assert "Stain: Congo red" in row.provenance
    assert "Method: not reported" in row.provenance
    assert "Sample size: not reported" in row.provenance
    assert "Specimen count: not reported" in row.provenance


def test_rows_from_resolved_entries_marks_dimmed_when_suppressed():
    rows = ComparisonListWidget.rows_from_resolved_entries([_library_entry()], dimmed=True)
    assert rows[0].dimmed is True


def test_rows_from_resolved_entries_not_dimmed_by_default():
    rows = ComparisonListWidget.rows_from_resolved_entries([_library_entry()])
    assert rows[0].dimmed is False


def test_adding_dataset_produces_a_row():
    rows = ComparisonListWidget.rows_from_resolved_entries([_library_entry()])
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_id == "lib-key"
    assert row.title == "Funga Nordica"
    assert row.source_kind == SourceKind.LIBRARY


def test_removing_dataset_removes_the_row():
    entries = [_my_obs_entry(), _library_entry()]
    rows = ComparisonListWidget.rows_from_resolved_entries(entries)
    assert len(rows) == 2

    entries_after_removal = [_my_obs_entry()]
    rows_after = ComparisonListWidget.rows_from_resolved_entries(entries_after_removal)
    assert len(rows_after) == 1
    assert rows_after[0].dataset_id == "myobs-key"


def test_visibility_round_trips_between_row_and_dataset_state():
    enabled_entry = _library_entry(enabled=True)
    disabled_entry = _library_entry(enabled=False)

    enabled_row = ComparisonRow.from_resolved_entry(enabled_entry)
    disabled_row = ComparisonRow.from_resolved_entry(disabled_entry)

    assert enabled_row.visible is True
    assert disabled_row.visible is False


def test_previous_personal_observation_maps_to_my_obs_not_observation():
    row = ComparisonRow.from_resolved_entry(_my_obs_entry())
    assert row.source_kind == SourceKind.MY_OBS
    assert row.is_observation is False


def test_my_obs_row_is_not_pinned_and_does_not_take_reserved_blue():
    entries = [_community_points_entry(), _library_entry(), _my_obs_entry()]
    rows = ComparisonListWidget.rows_from_resolved_entries(entries)
    my_obs_row = next(r for r in rows if r.dataset_id == "myobs-key")

    assert my_obs_row.color == "#2ecc71"  # its own resolved plot color, not reserved blue
    assert my_obs_row.color != RESERVED_OBSERVATION_COLOR

    ordered = _sorted_for_display(rows)
    # No row is pinned: order is unchanged, so my_obs stays in insertion position.
    assert [r.dataset_id for r in ordered] == ["com-key", "lib-key", "myobs-key"]


def test_current_observation_row_is_present_first_and_reserved_blue():
    reference_rows = ComparisonListWidget.rows_from_resolved_entries(
        [_community_points_entry(), _library_entry(), _my_obs_entry()]
    )
    current_row = ComparisonRow.for_current_observation(
        dataset_id="observation:99",
        title="This observation",
        date="2026-08-24",
        n=20,
    )
    ordered = _sorted_for_display([current_row, *reference_rows])

    assert ordered[0] is current_row
    assert ordered[0].source_kind == SourceKind.OBSERVATION
    assert ordered[0].color == RESERVED_OBSERVATION_COLOR
    assert ordered[0].is_observation is True
    assert ordered[0].detail == "2026-08-24 · n = 20"


def test_raw_observation_entry_maps_to_my_obs_and_never_reserved_blue():
    """Pin the actual regression risk, not an inability to fail.

    A raw ``source_kind == "observation"`` entry (legacy naming collision
    with ``SourceKind.OBSERVATION``) must resolve to ``SourceKind.MY_OBS``
    and must never come back colored ``RESERVED_OBSERVATION_COLOR`` -- that
    color is reserved exclusively for the pinned current-observation row
    built by ``for_current_observation``.
    """
    row = ComparisonRow.from_resolved_entry(_my_obs_entry())
    assert row.source_kind == SourceKind.MY_OBS
    assert row.color != RESERVED_OBSERVATION_COLOR
