"""Regressions for ``community_detail_preview_fields`` method-recorded logic
(stage-5-fix Part 0/1).

Reproduces the reviewed defect at ui/cloud_reference_dialog.py:426: the
provenance summary's "method recorded" flag was ``bool(qc_lines)``, which
counted ``has_point_geometry`` (measurement points) as a recorded method and
ignored the actual displayed method fields (mount medium, stain, sample
type, contrast, objective). A geometry-only detail therefore showed "method
recorded: yes", and a detail with an actual method (e.g. mount medium) but
no QC flags set showed "not reported".
"""
from __future__ import annotations

from ui.cloud_reference_dialog import community_detail_preview_fields


def _tr(text: str) -> str:
    return text


def test_geometry_only_qc_is_not_a_recorded_method():
    detail = {
        "_kind": "observation",
        "genus": "Amanita",
        "species": "muscaria",
        "contributor_label": "Someone",
        "measurement_count": 10,
        "qc_flags": {"has_point_geometry": True},
    }
    fields = community_detail_preview_fields(detail, _tr)
    assert "method recorded: not reported" in fields["provenance_summary"]


def test_reported_mount_medium_without_qc_flags_is_a_recorded_method():
    detail = {
        "_kind": "observation",
        "genus": "Amanita",
        "species": "muscaria",
        "contributor_label": "Someone",
        "measurement_count": 10,
        "mount_medium": "KOH",
        "qc_flags": {},
    }
    fields = community_detail_preview_fields(detail, _tr)
    assert "method recorded: yes" in fields["provenance_summary"]


def test_no_method_and_no_qc_flags_is_not_recorded():
    detail = {
        "_kind": "observation",
        "genus": "Amanita",
        "species": "muscaria",
        "contributor_label": "Someone",
        "measurement_count": 10,
        "qc_flags": {},
    }
    fields = community_detail_preview_fields(detail, _tr)
    assert "method recorded: not reported" in fields["provenance_summary"]


def test_populated_method_metadata_with_qc_flags_is_recorded():
    detail = {
        "_kind": "observation",
        "genus": "Amanita",
        "species": "muscaria",
        "contributor_label": "Someone",
        "measurement_count": 10,
        "stain": "Melzer's",
        "qc_flags": {"has_stain": True, "has_point_geometry": True},
    }
    fields = community_detail_preview_fields(detail, _tr)
    assert "method recorded: yes" in fields["provenance_summary"]
