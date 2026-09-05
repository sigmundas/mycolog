"""Model-level test for MainWindow._resolved_reference_series_entries's
automatic colour assignment (stage-4b-fix Part 2.3).

Binds the real method to a minimal stub rather than constructing a full
MainWindow, following the established convention in
tests/test_reference_library_desktop_slice.py.
"""
from __future__ import annotations

import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.comparison_panel import RESERVED_OBSERVATION_COLOR
from ui.main_window import MainWindow, reference_plot_palette


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _stub_with_references(entries: list[dict]) -> SimpleNamespace:
    stub = SimpleNamespace()
    stub.reference_series = entries
    stub.reference_values = {}
    stub._normalize_reference_series_entry = MethodType(
        MainWindow._normalize_reference_series_entry, stub
    )
    stub._reference_series_key = MethodType(MainWindow._reference_series_key, stub)
    stub._format_reference_series_label = MethodType(
        MainWindow._format_reference_series_label, stub
    )
    return stub


def test_manual_entry_label_prefers_name_as_published_over_genus_species():
    """Stage 5 Part 2: a manual-tab entry's ``name_as_published`` (already
    captured by ``ReferenceEntryEditor``) must win over the genus/species
    reconstruction for every source kind, not only Library-attached rows.
    """
    _app()
    stub = _stub_with_references([])
    label = stub._format_reference_series_label(
        {
            "genus": "Cortinarius",
            "species": "limonius",
            "name_as_published": "Cortinarius limonius (Fr.) Fr., sensu auct.",
            "source_kind": "reference",
        }
    )
    assert label == "Cortinarius limonius (Fr.) Fr., sensu auct."


def test_first_automatic_reference_color_is_not_the_observation_color():
    """Index 0 of the palette is reserved for the current-observation row
    (comparison_panel.RESERVED_OBSERVATION_COLOR); the first reference must
    start at index 1 so it is not the same (or a visually indistinguishable
    near-identical) blue.
    """
    _app()
    stub = _stub_with_references(
        [{"genus": "Cortinarius", "species": "limonius", "source": "Funga Nordica"}]
    )
    resolved = MainWindow._resolved_reference_series_entries(stub, dark=False)

    assert len(resolved) == 1
    palette = reference_plot_palette(False)
    assert resolved[0]["color"] == palette[1]
    assert resolved[0]["color"] != RESERVED_OBSERVATION_COLOR
    assert resolved[0]["color"] != palette[0]


def test_second_automatic_reference_color_differs_from_the_first():
    _app()
    stub = _stub_with_references(
        [
            {"genus": "Cortinarius", "species": "limonius", "source": "Funga Nordica"},
            {"genus": "Cortinarius", "species": "rubellus", "source": "Brandrud et al."},
        ]
    )
    resolved = MainWindow._resolved_reference_series_entries(stub, dark=False)

    assert len(resolved) == 2
    assert resolved[0]["color"] != resolved[1]["color"]
    palette = reference_plot_palette(False)
    assert resolved[0]["color"] == palette[1]
    assert resolved[1]["color"] == palette[2]
