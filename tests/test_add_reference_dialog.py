"""Model-level tests for ui.add_reference_dialog.AddReferenceDialog (Library tab).

Exercises the taxon filter, the search filter's AND-combination with it, and
the Add-to-plot enable/disable state -- without touching persistence or the
plotting path (``attach_callback`` is a stub). Uses the ``candidates=``
constructor override (mirroring ReferenceLibraryAttachDialog's testability
convention) so no real reference database is needed.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from database.reference_library import MeasurementSetCandidate
from ui.add_reference_dialog import AddReferenceDialog, filter_library_candidates


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
    return AddReferenceDialog(
        None,
        taxon_label="Cortinarius limonius",
        taxon_id=7,
        candidates=_candidates(),
        **kwargs,
    )


def _result_row_for(dialog: AddReferenceDialog, measurement_set_id: str) -> int:
    from PySide6.QtCore import Qt

    for row in range(dialog.results_list.count()):
        item = dialog.results_list.item(row)
        if item.data(Qt.UserRole) == measurement_set_id:
            return row
    raise AssertionError(f"no results-list row for {measurement_set_id!r}")


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
