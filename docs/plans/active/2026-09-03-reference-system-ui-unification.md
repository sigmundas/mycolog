# Reference-system UI unification (Sporely desktop)

Consolidate five parallel "add reference to the analysis plot" entry points into
**one comparison-centric panel** + **one tabbed picker dialog**. Match the two
approved mockups' structure/hierarchy (panel + picker), reusing existing widget
styles and the app's global tab style. Backend/model code stays; only UI entry
points are removed.

Status: Stages 1–4a complete — see **Landed stages** at the end of this doc.
Next up is stage 4b (Community tab). Executing stages in order; report after each.

## Subsystem map (verified 2026-09-03)

### Analysis-tab reference panel — `ui/main_window.py`
- `_build_reference_panel()` ~L9993 — builds the "Reference values" CollapsibleSection
  (`reference_section = CollapsibleSection(...)` L9357). Center of the feature.
- Plotted-dataset state (THE model):
  - `self.reference_series` (list[dict], init L7269) — the SET of datasets plotted + colors.
    Normalized entries; entries with `data["observation_reference_use_id"]` are the
    persisted library attachments.
  - `self.reference_values` (dict, init L7260) — legacy single active reference.
  - Row table: `self.ref_series_table` QTableWidget(0,5) L10124 — cols
    [Plot(checkbox) · color-chip("A") · Data set · Color · Library]; refreshed by
    `_refresh_reference_series_table()` L10766.
  - Ops: `_set_reference_series` L10936, add ~L10959, remove L10996,
    `_set_reference_series_enabled` L10720 (visibility toggle),
    `_set_reference_series_color` L10735 / `_open_reference_series_color_menu` L10609,
    `_reference_series_key` L10457.
  - Color palette: `reference_plot_palette()` L559 / `reference_plot_palette_groups()` L547 /
    `_blend_reference_palette_color()` L536. (Fixed ordered palette; obs = index 0 / blue.)
- Five entry points to remove/absorb (all in `_build_reference_panel`):
  1. Source dropdown: `self.ref_source_input` (editable QComboBox) L10035 +
     `_populate_reference_panel_sources()`; Plot: `self.ref_plot_btn` L10063 →
     `_on_reference_panel_plot_clicked`. → REPLACED by picker.
  2. Quick add: `self.ref_add_btn` "Quick add…" L10070 → `_on_reference_panel_add_clicked`;
     the "Add reference data" parse-string dialog is defined ~L5320-5365. → moves into
     picker "Enter manually" tab.
  3. Edit: `self.ref_edit_btn` L10079 → `_on_reference_panel_edit_clicked`. → dies (editing
     moves to per-row context menus).
  4. Community: `self.ref_cloud_btn` "Cloud..." L10039 → `_on_reference_panel_cloud_clicked`
     opens `CloudReferenceDialog`. → picker "Community" tab.
  5. Attach library: `self.ref_attach_library_btn` L10149 → `_on_attach_library_reference_clicked`
     opens `ReferenceLibraryAttachDialog`. → absorbed into picker "Library" tab (dialog dies).
- Manage library: `self.ref_manage_library_btn` L10157 → `_on_manage_reference_library_clicked`.
  → stays, becomes the small library icon-button next to "Add reference…".
- Taxon fields (panel copy): `ref_vernacular_input`/`ref_genus_input`/`ref_species_input`
  L10013-16. AI suggestions: `self.ref_ai_suggestions_combo` L10021 +
  `AISuggestionItemDelegate` + `_on_ref_ai_suggestion_activated` +
  `_refresh_reference_ai_suggestions()`. → taxon header chips (AI chips + "Edit taxon").
- Shape/MinMax: `self.ref_shape_selector` (SegmentedSelector) L10102 Ellipse/Square;
  `self.ref_show_minmax_checkbox` L10109. → move into Plot settings section
  (`plot_section = CollapsibleSection("Plot settings", ...)` L9356).
- Load/persist of series into per-obs settings blob: L22034-22078 (tab-switch/observation-open
  restore); `load_reference_values()` L23561.

### Community review pane — `ui/cloud_reference_dialog.py`
- `class CloudReferenceDialog(QDialog)` L129. Review pane is **inline** L263-322:
  `self.review_tabs = QTabWidget()` L263 with tabs Summary (L322), Raw spores (L295),
  Method (L314), Calibration (L318), Provenance (L322).
  - Summary tab: `summary_title_label`, `summary_meta_label`,
    `summary_table` QTableWidget(3,4) cols [Metric · Min · Median/Mean · Max] L277,
    `summary_note_label`.
  - Method tab: QFormLayout rows mount/stain/sample_type/contrast/objective/scale (`_method_labels`).
  - Raw spores / Calibration / Provenance: read-only QPlainTextEdit.
- Two footer buttons ("Import summary as reference" / "Use raw points for plot") → become a
  radio inside the Community tab ("Range summary" / "Raw points (n=X)").

### Shared tab style
- **No custom QTabWidget subclass.** Tabs are plain `QTabWidget` styled globally by QSS in
  `ui/styles.py:390-436` (`QTabWidget` / `QTabWidget::pane` / `QTabBar::tab` rules).
  → Picker source tabs AND the extracted preview sub-tabs must use plain `QTabWidget`.

### Other dialogs
- `ui/reference_library_manager_dialog.py` — Reference Library window (stays as curation
  back-office). Remove its "Attach to active observation" button + "Role: Compared" dropdown.
- `ui/reference_library_attach_dialog.py` — `ReferenceLibraryAttachDialog` (DIES; absorbed).
- Edit measurement set dialog — stays as-is (opened from library + per-row menu).
- `references/measurement_parser.py`, `references/reference_plotting.py` — backend, untouched.

### Persistence (open decision — RESOLVED: PERSISTED per-observation)
- `ObservationReferenceUseRepository` (imported `ui/main_window.py:165`) backs the
  `observation_reference_uses` table. Library attachments carry
  `data["observation_reference_use_id"]`, are synced (plan §12) and exposed via public
  observation API. Design explicitly separates "plotted temporarily" (session-only, no use_id)
  from "attached to observation" (persisted). Ref: plan doc L95-101, L204-210, L279-303, L482-604.
- Decision: KEEP existing persistence. Comparison row model gets `persisted` = bool(use_id);
  persisted rows show a small pin icon. Do NOT invent new persistence.

## reference_series entry schema (verified — `ui/main_window.py`)
Normalized entry = `{"key", "data": {...}, "label": str, "enabled": bool}`;
`_resolved_reference_series_entries()` adds `"color"`. Key methods:
- `_normalize_reference_series_entry` L10524; `_reference_series_key` L10457;
  `_format_reference_series_label` L10480 (single combined title line today).
- `data` keys: `source_kind` ∈ {`observation`,`points`,`reference`(default)} — the SOURCE-KIND
  discriminator; `observation_reference_use_id` (str; present ⇒ persisted Library attachment ⇒ pin);
  `genus`,`species`; range fields `length_min/length_max`, `core_min/core_max` (typical),
  `width_*`, `q_*`; `points` (list) + `points_label`/`source_label`/`source_type` for point sets;
  `source` (e.g. publication/mycena.no), `mount_medium`,`stain`; library rows also
  `short_label`,`name_as_published`,`locator_text`; `plot_color` (per-row override).
- Source-kind → badge: `observation`⇒"My obs"; `points`⇒"Community" if from cloud/mycena.no
  (source_type/source), else point set; `reference`+`observation_reference_use_id`⇒"Library";
  `reference` w/o use_id⇒"Manual". (Refine cloud vs manual by source string.)
- Range detail string: `_format_dimension_range(dim)` L5868 → `(min–)p05–p50–p95(–max)` per L/W/Q.
- Ops: visibility `_set_reference_series_enabled(key,bool)` L10720; color
  `_set_reference_series_color(key,color)` L10735 / `_open_reference_series_color_menu` L10609;
  remove `_remove_reference_series_key(key)` L10966; add `_add_reference_series_entry(data)` L10946.
- "This observation" row is NOT in reference_series — it's the active observation's own spores drawn
  as the blue histogram (`hist_color` #3498db light / #4a90d9 dark, L10557). Row 1 is synthetic;
  source n/date/spores from the active-observation measurements feeding that histogram
  (keyed by `self.active_observation_id`).

## Custom widgets to reuse
- `CollapsibleSection`, `SegmentedSelector`, `AISuggestionItemDelegate` (all `ui/main_window.py`).
- Plain `QTabWidget` + global QSS for all tabs.

## Renderer (Constraints TODO resolved)
`QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m tools.render_review_screenshots --scenario <id> <outdir>`
Existing `reference.*` scenarios incl. a dark one: `python -m tools.render_review_screenshots --list`.
Add scenarios for new widgets (comparison panel, picker) incl. long-content cases (8+ rows,
long publication title elision, æøå), light + dark.

## Stages (report after each; do not proceed past failing render/tests)
1. Extract community review pane → reusable `ReferencePreviewPane` widget (no visible change).
   Renderer check on community dialog.
2. Comparison list widget + row model backed by `reference_series`; add `persisted`/pin.
   Swap into panel ALONGSIDE old controls. Renderer check.
3. Add-reference picker dialog shell: 4 plain-QTabWidget tabs + shared ReferencePreviewPane;
   wire Library tab first. Title "Add reference — {taxon}". Renderer check.
4. Wire Community / My observations / Enter manually tabs (relocate existing flows). Renderer each.
   Split in execution: **4a** My observations + row-anatomy fix (`a36ec63`),
   **4a-fix** three live-app defects (`e8a67f1`), **4b** Community tab,
   **4c** Enter manually tab.
5. Verdict computation (pure, unit-tested) + badges + preview banner.
6. Remove dead entry points (Source dropdown, Plot, Edit, Attach library reference), taxon
   chips, color auto-assignment, polish. Renderer check on full Analysis tab.
7. Report persistence findings (above) + deferred items.

## Known issues (tracked, not yet fixed)
- Meta-line truncation: stage-1 screenshots of the extracted `ReferencePreviewPane`
  Summary tab show the meta label (source/date line) truncating without an ellipsis
  or tooltip on long content — pre-existing behavior carried over from
  `CloudReferenceDialog`, not introduced by the extraction. Needs a follow-up fix
  (elide + tooltip, matching the row-title elision pattern in
  `ui/comparison_panel.py::_ComparisonRowWidget.resizeEvent`) in a later stage;
  not in scope for stage 3.

## Stage 3 pre-check: rebuild feedback-loop / scroll-preservation audit
Verified 2026-09-04 against `ui/comparison_panel.py` before starting the picker
dialog:
- **Re-emit risk: none found.** `_ComparisonRowWidget.__init__` calls
  `self.checkbox.setChecked(row.visible)` (L139) *before*
  `self.checkbox.toggled.connect(...)` (L140), and `set_rows` (L253) always
  constructs a fresh `_ComparisonRowWidget` rather than mutating an existing one's
  checkbox — so there is no code path where a rebuild's own state restoration can
  emit `toggled`/`visibility_toggled`. Confirmed with a widget-level regression
  test (`tests/test_comparison_list_widget_rebuild.py::test_set_rows_does_not_reemit_visibility_toggled`).
- **Scroll position: preserved.** `set_rows` clears row widgets from
  `self._list_layout` but never replaces `self._container` or calls
  `self._scroll.setWidget(...)` again, so the `QScrollArea`'s vertical scrollbar
  value is untouched by a rebuild with equal-or-similar content height. Confirmed
  with `tests/test_comparison_list_widget_rebuild.py::test_set_rows_preserves_scroll_position`
  (9-row list, scroll to max, rebuild, assert value unchanged).
- **Focus/flicker: deferred.** `set_rows` deletes and recreates every row widget
  even when only one row's visibility changed, which will visibly flicker and drop
  focus/keyboard-navigation state on every toggle. Not fixed in this stage;
  candidate for a later polish pass (stage 6) that diffs rows instead of
  rebuilding wholesale.
No code changes were required in `ui/comparison_panel.py` itself; only the two
regression tests above were added to lock in the verified-safe behavior.

## Landed stages

Backfilled 2026-09-04 from the commits. Stage prompts live in
`~/Documents/Code/sporely/.sparring/prompts/`.

### Stage 1 — `272b20d` — extract `ReferencePreviewPane`
Pulled the tabbed Summary/Raw spores/Method/Calibration/Provenance review UI out
of `CloudReferenceDialog` into `ui/reference_preview_pane.py`.
`CloudReferenceDialog` forwards its old attribute names via properties, so
existing callers are unaffected and the change is invisible at runtime.
Verified: renderer scenarios `reference.community-preview(-dark)`.
Deferred: the Summary tab's meta-line truncates without ellipsis or tooltip —
pre-existing, carried over from the dialog (see Known issues).

### Stage 2 — `8290371` — `ComparisonListWidget`
Added `ui/comparison_panel.py` (`ComparisonRow` + `ComparisonListWidget`) as a
per-row presentation of the existing `reference_series` state, wired additively
below `ref_series_table`. Both lists refresh from the same
`_refresh_reference_series_table()` call site and route mutations through the
existing enable/colour ops, so no state was forked.
Verified: model-level tests for row creation/removal, visibility round-trip,
observation-row pinning; renderer scenarios `reference.comparison-list(-dark)`,
`-overflow`, `-longnames`.
Deferred: overflow menu edit/view/remove are stage-6 placeholders.

### Stage 3 part 0 — `bb65ed8` — rebuild-safety audit
Audited `set_rows` for the checkbox rebuild feedback loop and scroll
preservation before the picker work. Both properties already held
(`setChecked` before `connect`; the scroll area's content widget is reused, not
replaced), so no production change was needed.
Verified: `tests/test_comparison_list_widget_rebuild.py`.
Deferred: `set_rows` still recreates every row widget on any change — flicker
and focus loss are a stage-6 diffing pass.

### Stage 3 — `ab4bb38` — `AddReferenceDialog` shell + Library tab
Added the tabbed Library/Community/My observations/Enter manually picker. Only
Library wired: taxon + text filtering (AND semantics), preview pane populated
from the selected measurement set, "New publication…" reusing the existing
editor, and "Add to plot" routed through the existing
`_attach_normalized_reference_to_active_observation` so persistence and colour
assignment are not duplicated. Other three tabs show an honest placeholder. An
additive "Add reference…" button opens the picker; legacy entry points untouched.
Verified: `tests/test_add_reference_dialog.py`; renderer scenarios for populated,
empty-state, and stubbed tab.

### Stage 4a — `a36ec63` — row anatomy + My observations tab
Fixed the stage-3 row-anatomy gap (Library rows now render a second,
independently elided detail line). Wired the My observations tab over the same
query backing the legacy "My data &lt;date&gt;" entries, and hoisted
`ReferencePreviewPane` to dialog level so all tabs share one instance. A personal
observation has no measurement-set identity, so `MainWindow` dispatches on an
`observation:<id>` identifier prefix to the pre-existing legacy comparison-series
path instead of the normalized attach path.
Verified: `tests/test_add_reference_dialog.py`; renderer scenarios.
Deferred: Community → 4b, Enter manually → 4c.

### Stage 4a-fix — `e8a67f1` — three live-app defects
Three defects seen in a screenshot of the running app. (1)
`from_resolved_entry` now maps the legacy `source_kind == "observation"` string
to `SourceKind.MY_OBS`, leaving `SourceKind.OBSERVATION` reserved for the
current observation; this also removed the reserved-blue override that caused
the chip/plot colour mismatch. (2) Added
`ComparisonRow.for_current_observation` +
`MainWindow._current_observation_comparison_row` to synthesize pinned row 1 from
the active observation's own measurements, since
`_resolved_reference_series_entries` holds references only. (3) The
current-observation checkbox renders checked-and-disabled, as its scatter has no
independent toggle yet.
Verified: model tests + renderer scenarios updated to observation/library/my_obs;
all five manual tests confirmed passing by the user.

**Open defects carried into 4b** (from the 4a-fix review, 2026-09-04):
- `_current_observation_comparison_row`'s `n` counts a different population than
  the plot draws — it ignores the `gallery_filter_combo` category filter, omits
  the plot's `width > 0` check, and hand-rolls a category allow-list instead of
  reusing `normalize_measurement_category`. The category filter makes this
  user-reachable today.
- `test_chip_color_matches_plotted_color_after_a_reordering_sort` is
  tautological: it sorts a list of dataclasses and asserts their `color` fields
  are unchanged, which cannot fail. It gives no regression protection. Chip and
  plot colour cannot in fact diverge — both read `entry["color"]` from the same
  `_resolved_reference_series_entries` call — so the reserved-blue override was
  the whole cause, and the prompt's index-vs-sort-order hypothesis was a wrong
  diagnosis of a real symptom.
- `set_rows`' pin-first sort is now redundant with the caller's
  `rows.insert(0, current_row)`, since no reference row can carry
  `is_observation=True`. Two mechanisms for one job.
