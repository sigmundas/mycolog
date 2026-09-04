"""Reference Library scenarios and isolated SQLite fixture construction."""
from __future__ import annotations

import json
from unittest.mock import patch

from PySide6.QtWidgets import QTableWidgetItem

from database import schema as db_schema

from ..context import ReviewContext
from ..registry import ReviewScenario, ScenarioRegistry


def _fixture(context: ReviewContext):
    cached = context.state.get("reference.fixture")
    if cached is not None:
        return cached
    assert context.temporary_root is not None
    fixture_dir = context.temporary_root / "reference-library"
    fixture_dir.mkdir()
    main_db = fixture_dir / "mushrooms.db"
    reference_db = fixture_dir / "reference_values.db"
    context.enter_fixture(patch.object(db_schema, "get_database_path", lambda: main_db))
    context.enter_fixture(
        patch.object(db_schema, "get_reference_database_path", lambda: reference_db)
    )
    context.enter_fixture(
        patch.object(
            db_schema,
            "get_bundled_reference_database_path",
            lambda: fixture_dir / "no-bundled-reference.db",
        )
    )
    db_schema.init_database()
    work, sets = _seed_library()
    cached = {"work": work, "sets": sets, "fixture_dir": fixture_dir}
    context.state["reference.fixture"] = cached
    return cached


def _select_work(dialog, work_id: str) -> None:
    for row in range(dialog.publication_combo.count()):
        if str(dialog.publication_combo.itemData(row) or "") == work_id:
            dialog.publication_combo.setCurrentIndex(row)
            return
    raise RuntimeError(f"publication {work_id} is missing from the picker")


def _populate_range(dialog) -> None:
    expression = "(8.1–)8.5–10.8(–11.4) × (4.2–)4.5–5.8(–6.1) µm, Q = 1.7–2.1, Qm = 1.89, n = 36"
    dialog.measurement_paste_input.setText(expression)
    dialog._parse_measurement_btn.click()


def _populate_raw_points(dialog) -> None:
    dialog.tabs.setCurrentIndex(1)
    points = (
        (8.4, 4.6),
        (8.8, 4.7),
        (9.1, 4.9),
        (9.4, 5.0),
        (9.7, 5.1),
        (10.0, 5.3),
        (10.4, 5.5),
        (10.8, 5.7),
    )
    dialog.spore_table._ensure_rows(len(points))
    for row, (length, width) in enumerate(points):
        dialog.spore_table.setItem(row, 0, QTableWidgetItem(f"{length:.1f}"))
        dialog.spore_table.setItem(row, 1, QTableWidgetItem(f"{width:.1f}"))


def _make_add_dialog(context: ReviewContext, *, taxon_id: int | None = 7):
    from ui.main_window import ReferenceAddDialog

    fixture = _fixture(context)
    dialog = ReferenceAddDialog(
        context.host,
        "Cortinarius",
        "limonius",
        "Gulbelteslørsopp",
        observation_id=42,
        sporely_taxon_id=taxon_id,
    )
    _select_work(dialog, fixture["work"].id)
    return dialog


def _seed_library():
    from database.reference_library import (
        MeasurementSet,
        MeasurementSetRepository,
        ReferenceWork,
        ReferenceWorkRepository,
        TaxonTreatment,
        TaxonTreatmentRepository,
    )

    work = ReferenceWorkRepository.create(
        ReferenceWork(
            id="",
            type="article",
            title="A comprehensive revision of northern European Cortinarius species",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            authors_json=json.dumps(
                [
                    {"family": "Niskanen", "given": "Tuula"},
                    {"family": "Liimatainen", "given": "Kare"},
                    {"family": "Kytövuori", "given": "Ilkka"},
                ]
            ),
            container_title="Fungal Diversity and Systematics of Northern Europe",
            year=2018,
            volume="42",
            pages="115–198",
            doi="10.1000/cortinarius.2018.42",
        )
    )
    treatment = TaxonTreatmentRepository.create(
        TaxonTreatment(
            id="",
            reference_work_id=work.id,
            taxon_id="7",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="pp. 146–148, fig. 32",
        )
    )
    sets = [
        MeasurementSetRepository.create(
            MeasurementSet(
                id="",
                taxon_treatment_id=treatment.id,
                character="spore_size",
                data_kind="range",
                raw_text="(8.1–)8.5–10.8(–11.4) × (4.2–)4.5–5.8(–6.1) µm",
                length_min=8.1,
                length_core_min=8.5,
                length_core_max=10.8,
                length_max=11.4,
                width_min=4.2,
                width_core_min=4.5,
                width_core_max=5.8,
                width_max=6.1,
                q_min=1.7,
                q_max=2.1,
                q_mean=1.89,
                sample_size=36,
            )
        ),
        MeasurementSetRepository.create(
            MeasurementSet(
                id="",
                taxon_treatment_id=treatment.id,
                character="spore_size",
                data_kind="raw_points",
                raw_text="8 paired measurements from the holotype collection",
                raw_points_json=json.dumps(
                    [
                        {"length": 8.4, "width": 4.6},
                        {"length": 9.1, "width": 4.9},
                        {"length": 10.0, "width": 5.3},
                        {"length": 10.8, "width": 5.7},
                    ]
                ),
                sample_size=4,
            )
        ),
        MeasurementSetRepository.create(
            MeasurementSet(
                id="",
                taxon_treatment_id=treatment.id,
                character="spore_size",
                data_kind="summary",
                raw_text="L = 9.6 ± 0.7 µm; W = 5.1 ± 0.4 µm; n = 36",
                length_mean=9.6,
                width_mean=5.1,
                sample_size=36,
            )
        ),
    ]

    other_work = ReferenceWorkRepository.create(
        ReferenceWork(
            id="",
            type="book",
            title="The genus Cortinarius in temperate and boreal forests",
            short_label="Brandrud et al. 2020",
            authors_json=json.dumps([{"family": "Brandrud", "given": "T. E."}]),
            year=2020,
            publisher="Nordic Mycological Press",
            place="Oslo",
        )
    )
    other_treatment = TaxonTreatmentRepository.create(
        TaxonTreatment(
            id="",
            reference_work_id=other_work.id,
            taxon_id="99",
            name_as_published="Cortinarius rubellus Cooke",
            locator_text="Vol. 2, p. 311",
        )
    )
    MeasurementSetRepository.create(
        MeasurementSet(
            id="",
            taxon_treatment_id=other_treatment.id,
            character="spore_size",
            data_kind="range",
            raw_text="8.0–9.5 × 5.5–6.5 µm",
            length_core_min=8.0,
            length_core_max=9.5,
            width_core_min=5.5,
            width_core_max=6.5,
        )
    )
    return work, sets


def _attach_candidates():
    from database.reference_library import MeasurementSetCandidate

    return [
        MeasurementSetCandidate(
            measurement_set_id="candidate-range",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="pp. 146–148, fig. 32",
            data_kind="range",
            raw_text="(8.1–)8.5–10.8(–11.4) × (4.2–)4.5–5.8(–6.1) µm",
            revision=1,
            reference_work_id="work-main",
            reference_treatment_id="treatment-main",
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="candidate-points",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="supplementary dataset S4",
            data_kind="raw_points",
            raw_text="8 paired holotype measurements",
            revision=1,
            reference_work_id="work-main",
            reference_treatment_id="treatment-main",
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="candidate-other",
            short_label="Brandrud et al. 2020",
            name_as_published="Cortinarius rubellus Cooke",
            locator_text="Vol. 2, p. 311",
            data_kind="range",
            raw_text="8.0–9.5 × 5.5–6.5 µm",
            revision=1,
            reference_work_id="work-other",
            reference_treatment_id="treatment-other",
            taxon_id="99",
        ),
    ]


def _make_attach_dialog(context: ReviewContext):
    from ui.reference_library_attach_dialog import ReferenceLibraryAttachDialog

    _fixture(context)
    dialog = ReferenceLibraryAttachDialog(
        context.host,
        candidates=_attach_candidates(),
        taxon_id=7,
    )
    dialog.table.selectRow(0)
    return dialog


def _range(context: ReviewContext):
    dialog = _make_add_dialog(context)
    _populate_range(dialog)
    return dialog


def _raw_points(context: ReviewContext):
    dialog = _make_add_dialog(context)
    _populate_raw_points(dialog)
    return dialog


def _existing_set(context: ReviewContext):
    dialog = _make_add_dialog(context)
    dialog.use_existing_radio.setChecked(True)
    dialog._existing_sets_table.selectRow(0)
    return dialog


def _new_publication(context: ReviewContext):
    from ui.reference_library_manager_dialog import ReferenceWorkEditor

    _fixture(context)
    dialog = ReferenceWorkEditor(context.host)
    article_index = dialog.type_combo.findData("article")
    dialog.type_combo.setCurrentIndex(article_index)
    dialog.title_input.setText(
        "Morphological variation and species limits in northern European Cortinarius"
    )
    dialog.authors_editor.add_row(family="Niskanen", given="Tuula")
    dialog.authors_editor.add_row(family="Liimatainen", given="Kare")
    dialog.year_input.setText("2024")
    dialog.container_input.setText("Studies in Mycology and Boreal Fungal Diversity")
    dialog.volume_input.setText("108")
    dialog.issue_input.setText("2")
    dialog.pages_input.setText("145–189")
    dialog.doi_input.setText("10.1000/sim.2024.108.2")
    return dialog


def _library_manager(context: ReviewContext):
    from ui.reference_library_manager_dialog import ReferenceLibraryManagerDialog

    fixture = _fixture(context)
    dialog = ReferenceLibraryManagerDialog(
        context.host,
        active_observation_id=42,
        cloud_client=object(),
        sporely_taxon_id=7,
    )
    dialog.refresh_works(select_id=fixture["work"].id)
    dialog._refresh_hierarchy_for_current_work(
        select_set_id=fixture["sets"][0].id
    )
    return dialog


def _no_taxon(context: ReviewContext):
    dialog = _make_add_dialog(context, taxon_id=None)
    _populate_range(dialog)
    return dialog


def _parmasto(context: ReviewContext):
    dialog = _make_add_dialog(context)
    dialog.tabs.setCurrentIndex(2)
    values = {
        "parmasto_length_mean": "9.62",
        "parmasto_width_mean": "5.08",
        "parmasto_q_mean": "1.89",
        "parmasto_v_sp_length": "7.4",
        "parmasto_v_sp_width": "8.1",
        "parmasto_v_sp_q": "6.3",
        "parmasto_v_ind_length": "5.8",
        "parmasto_v_ind_width": "6.6",
        "parmasto_v_ind_q": "4.9",
    }
    for key, value in values.items():
        dialog.parmasto_inputs[key].setText(value)
    return dialog


def _community_preview(context: ReviewContext):
    from ui.reference_preview_pane import ReferencePreviewPane

    pane = ReferencePreviewPane(context.host)
    pane.set_summary(
        title="Cantharellus cibarius Fr. (Observation dataset) — Niskanen, Liimatainen & Kytövuori 2018, a comprehensive revision of northern European Cantharellus species with extensive morphological notes",
        meta="Contributor: sporely_community_user_42  •  Date: 2024-07-15  •  n=48",
        rows=[
            ("Length", "7.50", "9.20", "11.40"),
            ("Width", "4.10", "5.30", "6.60"),
            ("Q", "1.65", "1.73", "1.95"),
        ],
        note="QC signals: Mount recorded, Stain recorded, Scale recorded, Measurement points recorded",
    )
    pane.set_raw_spores(
        "L=7.50  W=4.10  Q=1.83\n"
        "L=8.40  W=4.60  Q=1.83\n"
        "L=9.10  W=4.90  Q=1.86\n"
        "L=9.40  W=5.00  Q=1.88\n"
        "L=9.70  W=5.10  Q=1.90\n"
        "L=10.00  W=5.30  Q=1.89\n"
        "L=10.40  W=5.50  Q=1.89\n"
        "L=11.40  W=6.60  Q=1.73"
    )
    pane.set_method(
        {
            "mount": "Melzer's reagent",
            "stain": "Congo red",
            "sample_type": "Fresh fruitbody",
            "contrast": "Phase contrast",
            "objective": "100× oil immersion",
            "scale": "0.08 µm/px",
        }
    )
    pane.set_calibration("Scale: 0.08 µm/px\nCalibration details come from image/objective metadata in the synced observation dataset.")
    pane.set_provenance(
        "Kind: observation\n"
        "Contributor: sporely_community_user_42\n"
        "Date: 2024-07-15\n"
        "Observation id: obs-00042\n"
        "Location and private observation content are intentionally excluded from this review flow."
    )
    return pane


def _comparison_row(
    dataset_id,
    title,
    source_kind,
    detail,
    color,
    *,
    visible=True,
    is_observation=False,
):
    from ui.comparison_panel import ComparisonRow, SourceKind

    return ComparisonRow(
        dataset_id=dataset_id,
        title=title,
        source_kind=SourceKind(source_kind) if isinstance(source_kind, str) else source_kind,
        detail=detail,
        color=color,
        visible=visible,
        is_observation=is_observation,
    )


def _comparison_list_basic(context: ReviewContext):
    from ui.comparison_panel import RESERVED_OBSERVATION_COLOR, ComparisonListWidget

    widget = ComparisonListWidget(context.host)
    widget.set_rows(
        [
            _comparison_row(
                "obs-1", "This observation", "observation", "n = 20",
                RESERVED_OBSERVATION_COLOR, is_observation=True,
            ),
            _comparison_row(
                "lib-1", "Funga Nordica", "library", "8.5–10.8 × 4.5–5.8 µm", "#e67e22",
            ),
            _comparison_row(
                "myobs-1", "Sigmund Ås 2026-08-02", "my_obs", "n = 17", "#2ecc71",
            ),
        ]
    )
    return widget


def _comparison_list_overflow(context: ReviewContext):
    from ui.comparison_panel import RESERVED_OBSERVATION_COLOR, ComparisonListWidget

    widget = ComparisonListWidget(context.host)
    rows = [
        _comparison_row(
            "obs-1", "This observation", "observation", "n = 20",
            RESERVED_OBSERVATION_COLOR, is_observation=True,
        )
    ]
    palette = ["#e67e22", "#8e44ad", "#2ecc71", "#e74c3c", "#1abc9c", "#f1c40f", "#34495e", "#c0392b"]
    kinds = ["library", "community", "my_obs"]
    for index in range(8):
        rows.append(
            _comparison_row(
                f"row-{index}",
                f"Reference set {index + 1}",
                kinds[index % len(kinds)],
                f"n = {10 + index}",
                palette[index % len(palette)],
            )
        )
    widget.set_rows(rows)
    return widget


def _comparison_list_longnames(context: ReviewContext):
    from ui.comparison_panel import RESERVED_OBSERVATION_COLOR, ComparisonListWidget

    widget = ComparisonListWidget(context.host)
    widget.set_rows(
        [
            _comparison_row(
                "obs-1", "This observation", "observation", "n = 20",
                RESERVED_OBSERVATION_COLOR, is_observation=True,
            ),
            _comparison_row(
                "lib-long",
                "A comprehensive revision of northern European Cortinarius species with extensive morphological and molecular notes",
                "library",
                "8.5–10.8 × 4.5–5.8 µm",
                "#e67e22",
            ),
            _comparison_row(
                "com-nordic",
                "Kantarell og trakttrompetsopp fra Ørsta og Ålesund — Blåbærgrøtsopp",
                "community",
                "n = 12",
                "#8e44ad",
            ),
        ]
    )
    return widget


def _add_dialog_candidates():
    from database.reference_library import MeasurementSetCandidate

    # Reuses the long-names data (60+ char title, æøå) already exercised by
    # reference.comparison-list-longnames rather than inventing a new fixture.
    return [
        MeasurementSetCandidate(
            measurement_set_id="add-dialog-1",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="pp. 146–148, fig. 32",
            data_kind="range",
            raw_text="(8.1–)8.5–10.8(–11.4) × (4.2–)4.5–5.8(–6.1) µm, Q = 1.7–2.1, n = 36",
            revision=1,
            reference_work_id="work-main",
            reference_treatment_id="treatment-main",
            work_title=(
                "A comprehensive revision of northern European Cortinarius "
                "species with extensive morphological and molecular notes"
            ),
            year=2018,
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="add-dialog-2",
            short_label="Niskanen, Liimatainen & Kytövuori 2018",
            name_as_published="Cortinarius limonius (Fr.) Fr.",
            locator_text="supplementary dataset S4",
            data_kind="raw_points",
            raw_text="8 paired holotype measurements",
            revision=1,
            reference_work_id="work-main",
            reference_treatment_id="treatment-main",
            year=2018,
            taxon_id="7",
        ),
        MeasurementSetCandidate(
            measurement_set_id="add-dialog-3",
            short_label="Kantarell og trakttrompetsopp fra Ørsta og Ålesund",
            name_as_published="Cortinarius rubellus Cooke — Blåbærgrøtsopp",
            locator_text="Vol. 2, p. 311",
            data_kind="range",
            raw_text="8.0–9.5 × 5.5–6.5 µm",
            revision=1,
            reference_work_id="work-other",
            reference_treatment_id="treatment-other",
            year=2020,
            taxon_id="99",
        ),
    ]


def _add_dialog_library(context: ReviewContext):
    from ui.add_reference_dialog import AddReferenceDialog

    _fixture(context)
    dialog = AddReferenceDialog(
        context.host,
        taxon_label="Cortinarius limonius",
        taxon_id="7",
        candidates=_add_dialog_candidates(),
        attach_callback=lambda *_args: None,
    )
    dialog.only_this_taxon_checkbox.setChecked(False)
    dialog.results_list.setCurrentRow(0)
    return dialog


def _add_dialog_library_empty(context: ReviewContext):
    from ui.add_reference_dialog import AddReferenceDialog

    _fixture(context)
    dialog = AddReferenceDialog(
        context.host,
        taxon_label="Cortinarius limonius",
        taxon_id="not-present-in-any-candidate",
        candidates=_add_dialog_candidates(),
        attach_callback=lambda *_args: None,
    )
    # "Only this taxon" defaults to checked; no candidate matches this
    # taxon id, so the results pane must show the honest empty state.
    return dialog


def _add_dialog_my_observations_candidates():
    from ui.add_reference_dialog import PersonalObservationCandidate

    # Reuses the long-locality/æøå convention from _add_dialog_candidates
    # rather than inventing a new fixture.
    return [
        PersonalObservationCandidate(
            observation_id=501,
            date="2024-06-12",
            author="Åse Øyen",
            location="Ørsta og Ålesund, ved gammel bjørkeskog med et forbausende langt stedsnavn",
            points=[
                {"length_um": 8.4, "width_um": 5.1},
                {"length_um": 8.9, "width_um": 5.4},
                {"length_um": 9.2, "width_um": 5.6},
            ],
        ),
        PersonalObservationCandidate(
            observation_id=502,
            date="2023-09-03",
            author="",
            location="",
            points=[{"length_um": 8.0, "width_um": 5.0}],
        ),
        PersonalObservationCandidate(
            observation_id=503,
            date="2022-10-21",
            author="Kari Nordmann",
            location="Trøndelag",
            points=[
                {"length_um": 7.8, "width_um": 4.9},
                {"length_um": 8.3, "width_um": 5.2},
            ],
        ),
    ]


def _add_dialog_my_observations(context: ReviewContext):
    from ui.add_reference_dialog import AddReferenceDialog

    _fixture(context)
    dialog = AddReferenceDialog(
        context.host,
        taxon_label="Cortinarius limonius",
        taxon_id="7",
        candidates=_add_dialog_candidates(),
        my_observations=_add_dialog_my_observations_candidates(),
        attach_callback=lambda *_args: None,
    )
    dialog.tabs.setCurrentIndex(dialog._my_observations_tab_index)
    dialog.my_observations_list.setCurrentRow(0)
    return dialog


def _add_dialog_stub_tab(context: ReviewContext):
    from ui.add_reference_dialog import AddReferenceDialog

    _fixture(context)
    dialog = AddReferenceDialog(
        context.host,
        taxon_label="Cortinarius limonius",
        taxon_id="7",
        candidates=_add_dialog_candidates(),
        attach_callback=lambda *_args: None,
    )
    dialog.tabs.setCurrentIndex(1)  # Community stub
    return dialog


def register_reference_scenarios(registry: ScenarioRegistry) -> None:
    scenarios = (
        ReviewScenario(
            id="reference.add-range",
            group="reference-library",
            title="Add reference — normalized range data",
            description="An existing publication and realistic parsed literature range exercise the normalized table.",
            viewport=(900, 720),
            build=_range,
        ),
        ReviewScenario(
            id="reference.raw-points",
            group="reference-library",
            title="Add reference — raw measurement points",
            description="Multiple paired length and width observations exercise the editable raw-data branch.",
            viewport=(900, 720),
            build=_raw_points,
        ),
        ReviewScenario(
            id="reference.existing-measurement-set",
            group="reference-library",
            title="Attach an existing measurement set while adding a reference",
            description="An existing publication set is selected while new-data tabs remain disabled.",
            viewport=(900, 720),
            build=_existing_set,
        ),
        ReviewScenario(
            id="reference.new-publication",
            group="reference-library",
            title="Create a new publication",
            description="A populated bibliography editor exercises field grouping, citation preview, and scrolling.",
            viewport=(720, 640),
            build=_new_publication,
        ),
        ReviewScenario(
            id="reference.library-manager",
            group="reference-library",
            title="Reference Library hierarchy",
            description="A selected publication, taxon treatment, and measurement set exercise the three-pane CRUD manager.",
            viewport=(1100, 700),
            build=_library_manager,
        ),
        ReviewScenario(
            id="reference.no-taxon",
            group="reference-library",
            title="No-taxon legacy fallback",
            description="The fallback notice explains that range data will be saved only to the legacy list.",
            viewport=(900, 720),
            build=_no_taxon,
        ),
        ReviewScenario(
            id="reference.parmasto",
            group="reference-library",
            title="Parmasto biometrics legacy path",
            description="Realistic Parmasto values exercise the retained legacy-only biometric branch.",
            viewport=(900, 720),
            build=_parmasto,
        ),
        ReviewScenario(
            id="reference.attach-taxon-filter",
            group="reference-library",
            title="Attach library reference with taxon filter",
            description="The attachment chooser is scoped to the active taxon with a candidate selected.",
            viewport=(980, 520),
            build=_make_attach_dialog,
        ),
        ReviewScenario(
            id="reference.nb-no",
            group="reference-library",
            title="Reference range workflow in Norwegian Bokmål",
            description="The real Norwegian translator exercises labels, tabs, headers, and button placement.",
            viewport=(900, 720),
            build=_range,
            locale="nb_NO",
        ),
        ReviewScenario(
            id="reference.dark",
            group="reference-library",
            title="Reference attachment chooser in application dark mode",
            description="The real dark palette and stylesheet exercise inputs, selection, disabled states, and buttons.",
            viewport=(980, 520),
            build=_make_attach_dialog,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.community-preview",
            group="reference-library",
            title="Community review pane — ReferencePreviewPane standalone (light)",
            description="Exercises ReferencePreviewPane with a full summary table, long title, method fields, raw spores, and provenance in light theme.",
            viewport=(600, 500),
            build=_community_preview,
        ),
        ReviewScenario(
            id="reference.community-preview-dark",
            group="reference-library",
            title="Community review pane — ReferencePreviewPane standalone (dark)",
            description="Same ReferencePreviewPane state in dark theme to verify palette correctness.",
            viewport=(600, 500),
            build=_community_preview,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.comparison-list",
            group="reference-library",
            title="Comparison list — observation, library, and my_obs rows",
            description="Three plotted datasets exercise checkbox, color chip, badge, and detail line rendering.",
            viewport=(420, 260),
            build=_comparison_list_basic,
        ),
        ReviewScenario(
            id="reference.comparison-list-dark",
            group="reference-library",
            title="Comparison list — dark theme",
            description="Same three-row state in dark theme to verify contrast.",
            viewport=(420, 260),
            build=_comparison_list_basic,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.comparison-list-overflow",
            group="reference-library",
            title="Comparison list — nine rows, scrolling",
            description="Nine rows must scroll within a fixed-height panel while staying usable.",
            viewport=(420, 320),
            build=_comparison_list_overflow,
        ),
        ReviewScenario(
            id="reference.comparison-list-longnames",
            group="reference-library",
            title="Comparison list — long titles and æøå",
            description="A publication title over 60 characters must elide; Norwegian names with æ, ø, å must render correctly.",
            viewport=(420, 260),
            build=_comparison_list_longnames,
        ),
        ReviewScenario(
            id="reference.add-dialog-library",
            group="reference-library",
            title="Add-reference picker — Library tab, result selected",
            description="Library tab with three results (incl. a 60+ char title and æøå names); one selected populates the preview pane.",
            viewport=(900, 560),
            build=_add_dialog_library,
        ),
        ReviewScenario(
            id="reference.add-dialog-library-dark",
            group="reference-library",
            title="Add-reference picker — Library tab (dark)",
            description="Same Library-tab state in dark theme to verify contrast.",
            viewport=(900, 560),
            build=_add_dialog_library,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.add-dialog-library-empty",
            group="reference-library",
            title="Add-reference picker — Library tab, no matches",
            description="\"Only this taxon\" checked with zero matches: honest empty state, Add to plot stays disabled.",
            viewport=(900, 560),
            build=_add_dialog_library_empty,
        ),
        ReviewScenario(
            id="reference.add-dialog-library-empty-dark",
            group="reference-library",
            title="Add-reference picker — Library tab, no matches (dark)",
            description="Same empty-state case in dark theme.",
            viewport=(900, 560),
            build=_add_dialog_library_empty,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.add-dialog-myobs",
            group="reference-library",
            title="Add-reference picker — My observations tab, result selected",
            description="Three personal observations of the working taxon (incl. æøå names and a long locality); one selected populates the shared preview pane with raw spores.",
            viewport=(900, 560),
            build=_add_dialog_my_observations,
        ),
        ReviewScenario(
            id="reference.add-dialog-myobs-dark",
            group="reference-library",
            title="Add-reference picker — My observations tab (dark)",
            description="Same My-observations-tab state in dark theme to verify contrast.",
            viewport=(900, 560),
            build=_add_dialog_my_observations,
            theme="dark",
        ),
        ReviewScenario(
            id="reference.add-dialog-stub-tab",
            group="reference-library",
            title="Add-reference picker — stubbed Community tab",
            description="Community tab shows an honest \"coming in a later stage\" placeholder rather than a broken UI.",
            viewport=(900, 560),
            build=_add_dialog_stub_tab,
        ),
        ReviewScenario(
            id="reference.add-dialog-stub-tab-dark",
            group="reference-library",
            title="Add-reference picker — stubbed Community tab (dark)",
            description="Same stub-tab state in dark theme.",
            viewport=(900, 560),
            build=_add_dialog_stub_tab,
            theme="dark",
        ),
    )
    for scenario in scenarios:
        registry.register(scenario)
