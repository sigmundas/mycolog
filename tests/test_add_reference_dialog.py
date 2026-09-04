"""Model-level tests for ui.add_reference_dialog.AddReferenceDialog.

Exercises the Library tab's taxon filter and search-filter AND-combination,
the My-observations tab's candidate loading and row rendering, and the
Add-to-plot enable/disable state and callback dispatch for both tabs --
without touching persistence or the plotting path (``attach_callback`` is a
stub). Uses the ``candidates=``/``my_observations=`` constructor overrides
(mirroring ReferenceLibraryAttachDialog's testability convention) so no real
database is needed.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from database.reference_library import MeasurementSetCandidate
from ui.add_reference_dialog import (
    AddReferenceDialog,
    PersonalObservationCandidate,
    default_my_observation_candidates,
    filter_library_candidates,
    format_ai_candidate_display,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _candidates() -> list[MeasurementSetCandidate]:
    return [
        MeasurementSetCandidate(
            measurement_set_id="ms-1",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="pp. 146–148",
            data_kind="range",
            raw_text="(8.1–)8.5–10.8(–11.4) µm",
            revision=1,
            reference_work_id="w-1",
            reference_treatment_id="t-1",
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="ms-2",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="supplementary dataset S4",
            data_kind="raw_points",
            raw_text="8 paired holotype measurements",
            revision=1,
            reference_work_id="w-1",
            reference_treatment_id="t-1",
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="ms-3",
            short_label="Brandrud et al. 2020",
            name_as_published="Cortinarius rubellus Cooke",
            locator_text="Vol. 2, p. 311",
            data_kind="range",
            raw_text="8.0–9.5 µm",
            revision=1,
            reference_work_id="w-2",
            reference_treatment_id="t-2",
            taxon_id="99",
        ),
    ]


def _make_dialog(**kwargs) -> AddReferenceDialog:
    _app()
    defaults = {
        "taxon_label": "Cortinarius limonius",
        "taxon_id": 7,
        "candidates": _candidates(),
        # Injected (even empty) so the Community tab never spawns a real
        # network search thread just from constructing the dialog.
        "community_results": [],
    }
    defaults.update(kwargs)
    return AddReferenceDialog(None, **defaults)


def _result_row_for(dialog: AddReferenceDialog, measurement_set_id: str) -> int:
    from PySide6.QtCore import Qt

    for row in range(dialog.results_list.count()):
        item = dialog.results_list.item(row)
        if item.data(Qt.UserRole) == measurement_set_id:
            return row
    raise AssertionError(f"no results-list row for {measurement_set_id!r}")


def _ai_candidates() -> list[dict]:
    return [
        {
            "source": "arts",
            "scientific_name": "Cortinarius rubellus",
            "vernacular": "Bittersnerlerørsopp",
            "genus": "Cortinarius",
            "species": "rubellus",
            "score": 0.82,
        },
    ]


def test_format_ai_candidate_display():
    text = format_ai_candidate_display(_ai_candidates()[0])
    assert text == "Cortinarius rubellus (Bittersnerlerørsopp)  82%"


def test_taxon_target_combo_defaults_to_own_taxon():
    dialog = _make_dialog(genus="Cortinarius", species="limonius")
    assert dialog.taxon_target_combo.currentIndex() == 0
    assert "Cortinarius limonius" in dialog.taxon_target_combo.currentText()


def test_selecting_ai_candidate_refilters_library_and_updates_title():
    dialog = _make_dialog(
        genus="Cortinarius", species="limonius", ai_candidates=_ai_candidates()
    )
    assert dialog.taxon_target_combo.count() == 2
    # A real click both moves currentIndex and emits activated(); the two
    # are driven separately here to exercise the same path.
    dialog.taxon_target_combo.setCurrentIndex(1)
    dialog._on_taxon_target_activated(1)

    assert dialog._genus == "Cortinarius"
    assert dialog._species == "rubellus"
    assert dialog._taxon_id is None
    assert "Cortinarius rubellus" in dialog.windowTitle()
    assert "82%" in dialog.taxon_target_combo.currentText()
    # ms-3 is published as "Cortinarius rubellus Cooke" with no taxon_id
    # match against the picker's target -- the text fallback must still
    # narrow to it.
    assert {c.measurement_set_id for c in dialog._filtered_candidates()} == {"ms-3"}


def test_typing_arbitrary_taxon_filters_library_via_text_match():
    dialog = _make_dialog(genus="Cortinarius", species="limonius")
    dialog.taxon_target_combo.setCurrentText("Cortinarius rubellus")
    dialog._on_taxon_target_text_entered()

    assert dialog._genus == "Cortinarius"
    assert dialog._species == "rubellus"
    assert {c.measurement_set_id for c in dialog._filtered_candidates()} == {"ms-3"}


def test_typed_text_with_only_one_word_is_ignored():
    dialog = _make_dialog(genus="Cortinarius", species="limonius")
    dialog.taxon_target_combo.setCurrentText("Cortinarius")
    dialog._on_taxon_target_text_entered()
    # Unchanged: still the taxon the dialog opened on.
    assert dialog._genus == "Cortinarius"
    assert dialog._species == "limonius"


def test_only_this_taxon_defaults_checked_even_without_taxon_id():
    dialog = _make_dialog(taxon_id=None, genus="", species="")
    assert dialog.only_this_taxon_checkbox.isChecked() is True


def test_unchecking_only_this_taxon_shows_taxon_in_row_detail():
    dialog = _make_dialog()
    dialog.only_this_taxon_checkbox.setChecked(False)
    row = _result_row_for(dialog, "ms-3")
    widget = dialog.results_list.itemWidget(dialog.results_list.item(row))
    assert "Cortinarius rubellus" in widget._full_detail


def test_changing_taxon_target_never_touches_exclude_observation_id():
    dialog = _make_dialog(
        genus="Cortinarius", species="limonius", ai_candidates=_ai_candidates()
    )
    before = dialog._exclude_observation_id
    dialog._on_taxon_target_activated(1)
    assert dialog._exclude_observation_id == before


def test_derived_minimum_size_fits_both_tab_bars():
    """The dialog's minimum width must be at least the source tab bar's own
    size hint plus the preview pane's sub-tab bar's own size hint -- the
    exact condition that avoids the QTabWidget scroll-arrow fallback (see
    stage-4b-fix Part 2.2). No hardcoded pixel width is asserted here; the
    check is relative to the widgets' own hints.
    """
    dialog = _make_dialog()
    min_size = dialog.minimumSize()
    source_tabbar_w = dialog.tabs.tabBar().sizeHint().width()
    preview_tabbar_w = dialog.preview_pane.review_tabs.tabBar().sizeHint().width()
    assert min_size.width() >= source_tabbar_w + preview_tabbar_w


def test_only_this_taxon_checked_shows_only_working_taxon_sets():
    dialog = _make_dialog()
    assert dialog.only_this_taxon_checkbox.isChecked() is True
    filtered = dialog._filtered_candidates()
    assert {c.measurement_set_id for c in filtered} == {"ms-1", "ms-2"}


def test_only_this_taxon_unchecked_shows_all_sets():
    dialog = _make_dialog()
    dialog.only_this_taxon_checkbox.setChecked(False)
    filtered = dialog._filtered_candidates()
    assert {c.measurement_set_id for c in filtered} == {"ms-1", "ms-2", "ms-3"}


def test_search_filter_combines_with_taxon_filter():
    dialog = _make_dialog()
    # "Brandrud" only matches ms-3, which is a different taxon -- AND
    # semantics mean it must be excluded while "Only this taxon" is checked.
    dialog.search_input.setText("Brandrud")
    assert dialog._filtered_candidates() == []

    dialog.only_this_taxon_checkbox.setChecked(False)
    filtered = dialog._filtered_candidates()
    assert {c.measurement_set_id for c in filtered} == {"ms-3"}


def test_search_filter_narrows_within_working_taxon():
    dialog = _make_dialog()
    # "holotype" appears only in ms-2's raw expression -- confirms the
    # search matches raw expression text, not just publication/taxon.
    dialog.search_input.setText("holotype")
    filtered = dialog._filtered_candidates()
    assert {c.measurement_set_id for c in filtered} == {"ms-2"}


def test_filter_library_candidates_pure_function_matches_dialog_behavior():
    candidates = _candidates()
    only_taxon = filter_library_candidates(
        candidates, taxon_id="7", only_this_taxon=True
    )
    assert {c.measurement_set_id for c in only_taxon} == {"ms-1", "ms-2"}
    all_candidates = filter_library_candidates(
        candidates, taxon_id="7", only_this_taxon=False
    )
    assert {c.measurement_set_id for c in all_candidates} == {"ms-1", "ms-2", "ms-3"}


def test_add_to_plot_disabled_with_no_selection():
    dialog = _make_dialog()
    assert dialog.add_to_plot_btn.isEnabled() is False


def test_add_to_plot_enabled_once_a_result_is_selected():
    dialog = _make_dialog()
    dialog.results_list.setCurrentRow(_result_row_for(dialog, "ms-1"))
    assert dialog._selected_candidate is not None
    assert dialog._selected_candidate.measurement_set_id == "ms-1"
    assert dialog.add_to_plot_btn.isEnabled() is True


def test_add_to_plot_invokes_callback_and_accepts():
    received = []
    dialog = _make_dialog(attach_callback=lambda ms_id, role: received.append((ms_id, role)))
    dialog.results_list.setCurrentRow(_result_row_for(dialog, "ms-1"))
    dialog._on_add_to_plot_clicked()
    assert received == [("ms-1", "compared")]


def test_library_row_renders_two_lines_title_and_detail():
    dialog = _make_dialog()
    row = _result_row_for(dialog, "ms-2")
    widget = dialog.results_list.itemWidget(dialog.results_list.item(row))
    assert "Niskanen" in widget.title_label.text()
    # data_kind + raw_text, per the row-anatomy spec (kind + raw expression).
    assert "raw_points" in widget.detail_label.text()
    assert "8 paired holotype measurements" in widget.detail_label.text()


# ---------------------------------------------------------------------
# My observations tab
# ---------------------------------------------------------------------


def _my_observations() -> list[PersonalObservationCandidate]:
    return [
        PersonalObservationCandidate(
            observation_id=101,
            date="2024-05-01",
            author="Åse Øyen",
            location="Trøndelag, æøå-lokalitet med et forbausende langt navn på over seksti tegn",
            points=[{"length_um": 8.0, "width_um": 5.0}, {"length_um": 9.0, "width_um": 5.5}],
        ),
        PersonalObservationCandidate(
            observation_id=102,
            date="2023-11-20",
            author="",
            location="",
            points=[{"length_um": 7.5, "width_um": 4.5}],
        ),
    ]


def _my_obs_row_for(dialog: AddReferenceDialog, observation_id: int) -> int:
    for row in range(dialog.my_observations_list.count()):
        item = dialog.my_observations_list.item(row)
        if item.data(Qt.UserRole) == observation_id:
            return row
    raise AssertionError(f"no my-observations row for {observation_id!r}")


def _make_my_obs_dialog(**kwargs) -> AddReferenceDialog:
    _app()
    return AddReferenceDialog(
        None,
        taxon_label="Cortinarius limonius",
        candidates=[],
        my_observations=_my_observations(),
        **kwargs,
    )


def test_my_observations_tab_lists_injected_candidates():
    dialog = _make_my_obs_dialog()
    assert dialog.my_observations_list.count() == 2


def test_my_observations_detail_line_shows_date_n_and_locality():
    dialog = _make_my_obs_dialog()
    row = _my_obs_row_for(dialog, 101)
    widget = dialog.my_observations_list.itemWidget(dialog.my_observations_list.item(row))
    detail = widget._full_detail
    assert "2024-05-01" in detail
    assert "n = 2" in detail
    assert "Trøndelag" in detail


def test_my_observations_detail_line_omits_locality_when_unavailable():
    dialog = _make_my_obs_dialog()
    row = _my_obs_row_for(dialog, 102)
    widget = dialog.my_observations_list.itemWidget(dialog.my_observations_list.item(row))
    detail = widget._full_detail
    assert "2023-11-20" in detail
    assert "n = 1" in detail


def test_my_observations_selection_populates_shared_preview_pane():
    dialog = _make_my_obs_dialog()
    dialog.tabs.setCurrentIndex(dialog._my_observations_tab_index)
    dialog.my_observations_list.setCurrentRow(_my_obs_row_for(dialog, 101))
    assert "n = 2" in dialog.preview_pane.summary_note_label.text()
    assert "8.0" in dialog.preview_pane.raw_spores_text.toPlainText()


def test_my_observations_add_to_plot_uses_observation_prefixed_identifier():
    received = []
    dialog = _make_my_obs_dialog(
        attach_callback=lambda identifier, role: received.append((identifier, role))
    )
    dialog.tabs.setCurrentIndex(dialog._my_observations_tab_index)
    dialog.my_observations_list.setCurrentRow(_my_obs_row_for(dialog, 101))
    dialog._on_add_to_plot_clicked()
    assert received == [("observation:101", "compared")]


def test_my_observations_add_to_plot_disabled_with_no_selection():
    dialog = _make_my_obs_dialog()
    dialog.tabs.setCurrentIndex(dialog._my_observations_tab_index)
    assert dialog.add_to_plot_btn.isEnabled() is False


# ---------------------------------------------------------------------
# Community tab
# ---------------------------------------------------------------------


def _community_results() -> list[dict]:
    return [
        {
            "_kind": "observation",
            "genus": "Cortinarius",
            "species": "limonius",
            "contributor_label": "sporely_community_user_7",
            "observed_on": "2025-05-01",
            "measurement_count": 3,
            "q_min": 1.1,
            "q_p50": 1.3,
            "q_max": 1.5,
            "measurements_json": [
                {"length_um": 8.0, "width_um": 5.0},
                {"length_um": 9.0, "width_um": 6.0},
                {"length_um": 10.0, "width_um": 7.0},
            ],
            "length_min": 8.0,
            "length_p50": 9.0,
            "length_max": 10.0,
            "width_min": 5.0,
            "width_p50": 6.0,
            "width_max": 7.0,
        },
        {
            "_kind": "reference",
            "genus": "Cortinarius",
            "species": "limonius",
            "source": "mycena.no",
            "contributor_label": "mycena.no",
            "measurement_count": 0,
            "length_min": 8.0,
            "length_max": 10.5,
        },
    ]


def _make_community_dialog(**kwargs) -> AddReferenceDialog:
    _app()
    kwargs.setdefault("community_results", _community_results())
    return AddReferenceDialog(
        None,
        taxon_label="Cortinarius limonius",
        genus="Cortinarius",
        species="limonius",
        candidates=[],
        **kwargs,
    )


def test_community_tab_lists_injected_results():
    dialog = _make_community_dialog()
    assert dialog._community_pane.results_list.count() == 2


def test_community_selection_populates_shared_preview_pane():
    dialog = _make_community_dialog()
    dialog.tabs.setCurrentIndex(dialog._community_tab_index)
    dialog._community_pane.results_list.setCurrentRow(0)
    assert "Cortinarius limonius" in dialog.preview_pane.summary_title_label.text()
    assert "8.0" in dialog.preview_pane.raw_spores_text.toPlainText()


def test_community_add_to_plot_range_summary_uses_reference_source_kind():
    received = []
    dialog = _make_community_dialog(cloud_attach_callback=lambda data: received.append(data))
    dialog.tabs.setCurrentIndex(dialog._community_tab_index)
    dialog._community_pane.results_list.setCurrentRow(0)
    assert dialog._community_pane.range_summary_radio.isChecked() is True
    dialog._on_add_to_plot_clicked()
    assert len(received) == 1
    assert received[0]["source_kind"] == "reference"


def test_community_add_to_plot_raw_points_uses_points_source_kind_and_real_n():
    received = []
    dialog = _make_community_dialog(cloud_attach_callback=lambda data: received.append(data))
    dialog.tabs.setCurrentIndex(dialog._community_tab_index)
    dialog._community_pane.results_list.setCurrentRow(0)
    assert "n=3" in dialog._community_pane.raw_points_radio.text()
    dialog._community_pane.raw_points_radio.setChecked(True)
    dialog._on_add_to_plot_clicked()
    assert len(received) == 1
    assert received[0]["source_kind"] == "points"
    assert len(received[0]["points"]) == 3


def test_community_raw_points_radio_disabled_without_measurements():
    dialog = _make_community_dialog()
    dialog.tabs.setCurrentIndex(dialog._community_tab_index)
    dialog._community_pane.results_list.setCurrentRow(1)
    assert dialog._community_pane.raw_points_radio.isEnabled() is False
    assert dialog._community_pane.range_summary_radio.isChecked() is True


def test_community_add_to_plot_disabled_with_no_selection():
    dialog = _make_community_dialog()
    dialog.tabs.setCurrentIndex(dialog._community_tab_index)
    assert dialog.add_to_plot_btn.isEnabled() is False


def test_community_tab_shows_empty_state_with_no_results():
    dialog = _make_community_dialog(community_results=[])
    assert dialog._community_pane.results_list.count() == 0
    assert dialog._community_pane.status_label.text() != ""


def test_default_my_observation_candidates_filters_by_taxon_and_requires_points(monkeypatch):
    from ui import add_reference_dialog as mod

    def fake_get_personal_observations_for_species(genus, species, exclude_observation_id=None):
        assert (genus, species) == ("Cortinarius", "limonius")
        assert exclude_observation_id == 42
        return [
            {"id": 201, "date": "2024-01-01", "author": "A"},
            {"id": 202, "date": "2024-02-02", "author": "B"},
        ]

    def fake_get_measurements_for_observation(observation_id):
        # Observation 202 has no usable measurements and must be excluded.
        if observation_id == 201:
            return [{"length_um": 8.0, "width_um": 5.0, "measurement_type": "spore"}]
        return []

    def fake_get_observation(observation_id):
        return {"location": "Oppland"} if observation_id == 201 else {}

    monkeypatch.setattr(
        mod.ObservationDB,
        "get_personal_observations_for_species",
        staticmethod(fake_get_personal_observations_for_species),
    )
    monkeypatch.setattr(
        mod.MeasurementDB,
        "get_measurements_for_observation",
        staticmethod(fake_get_measurements_for_observation),
    )
    monkeypatch.setattr(
        mod.ObservationDB, "get_observation", staticmethod(fake_get_observation)
    )

    result = default_my_observation_candidates(
        "Cortinarius", "limonius", exclude_observation_id=42
    )
    assert [c.observation_id for c in result] == [201]
    assert result[0].location == "Oppland"
    assert result[0].n == 1
