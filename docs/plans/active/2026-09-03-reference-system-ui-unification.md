# Reference-system UI unification (Sporely desktop)

Consolidate five parallel "add reference to the analysis plot" entry points into
**one comparison-centric panel** + **one tabbed picker dialog**. Match the two
approved mockups' structure/hierarchy (panel + picker), reusing existing widget
styles and the app's global tab style. Backend/model code stays; only UI entry
points are removed.

Status: Stages 4b (`c345ac8`) and 4b-fix (`14525ff`) are already committed.
Fresh top-level acceptance review on 2026-09-05: **4b-fix2 confirmed** within
its approved corrective scope. User confirmed all seven manual checks passed.

## Current stage / handoff — 2026-09-05

### 4b-fix2 correction — independently reviewed and manually accepted

Selected prompt (archive after verified commit):
`/Users/sigmundas/Documents/Code/sporely/.sparring/prompts/sporely-py/stage-4b-fix2.md`.
Implementation reviewed against base `14525ff91f6b7ada1f899c03852f54eb065b1fe1`.
All seven manual checks passed per the user in this acceptance session.
The user authorized committing this verified correction and archiving its prompt.
No 4c implementation was performed.

This pass began with partial corrective code/tests, renderer plumbing, and
TS/QM edits already in the working tree, in addition to AGENTS.md and the
review/handoff edits. Those edits were preserved and the correction completed
in place. The older claim that the working tree contains only a handoff edit
is historical, not the present state.

Corrected scope and reuse:
- `ui/cloud_reference_dialog.py`, `CommunityResultsPane` (~1202–1570): request
  generations in `refresh` and `_on_result_selection_changed` guard search and
  detail success/error callbacks. Superseded requests remain in `_worker_refs`
  until the existing `_release_worker` path releases them. `closeEvent`
  invalidates callbacks and waits for all tracked requests, including superseded
  ones. Target changes themselves do not wait. Existing `_CloudSearchWorker`,
  `_CloudDetailWorker`, preview helpers and `current_mode_payload` are reused;
  adapters, network contracts and persistence are unchanged.
- `ui/add_reference_dialog.py`, `__init__` (~358–360) and
  `_on_taxon_target_text_entered` (~488–517): dialog `finished` closes the
  Community pane; unchanged selected labels reuse structured item data through
  `_apply_taxon_target`. Deliberately edited text retains the existing parser.
- `ui/main_window.py`, `_on_add_reference_clicked` (~11539–11559) and
  `_active_sporely_taxon_id` (~13101–13129): one captured observation snapshot
  supplies name and ID. The existing ID helper accepts an optional snapshot;
  existing callers still fetch the active observation. Reused
  `ObservationDB.get_observation`, `_clean_ref_genus_text`,
  `_clean_ref_species_text`; existing drift guards and attach closures remain.
- Both picker/pane modules use explicit `QCoreApplication.translate` contexts
  for their own strings: lupdate had extracted these into the empty context,
  where Qt could not find them at runtime. The Norwegian popup screenshot
  exposed this despite successful QM compilation.
- `tests/test_add_reference_dialog.py`: isolated settings and preview stubs,
  actual Qt keyboard selection/Return, structured own-target/free-text tests,
  synthetic host observations and a write-rejecting persistence stub. Removed
  the incoming host tests' real SQLite-row setup. Existing filter/attach tests
  are retained. `tests/test_community_results_pane_requests.py`: manually driven
  fake workers, A→B→C ordering, late success/error, selection/clear invalidation,
  worker release, post-close callbacks and rejecting the owning picker.
- `tools/review_ui/registry.py` (`ReviewScenario`) and `runner.py` (`_capture`):
  bounded generic options preserve builder sizing and capture a post-show
  surface such as the real combo popup. `tests/test_render_review_screenshots.py`
  adds two focused tests for those facilities.
- `tools/review_ui/scenarios/references.py`: `_fixture` isolates geometry and
  splitter QSettings per builder; existing suppressed/colour/default/selector
  builders are reused, with both-theme and Norwegian cases. Default sizing
  skips viewport resize/adjustSize. Popup evidence captures the actual separate
  popup surface, not a closed combo or a composite desktop screenshot.
- `tools/update_translations.sh` includes comparison_panel, cloud_reference_dialog
  and reference_preview_pane. Paired `i18n/Sporely_{nb_NO,sv_SE,de_DE}.{ts,qm}`
  refreshed, preserving incoming translations and correcting context placement.
  Final extraction: 2318 finished translations per language, zero unfinished;
  no unrelated unfinished entries remain to list. No backlog sweep was performed.
- This canonical plan updated; pre-existing `AGENTS.md` edit left untouched.
  No changes to comparison_panel production logic in this correction.

Verification:
- Pre-fix reproduction loaded exactly the three UI modules from `14525ff` into
  an isolated Python process, then ran the corrected no-database test fixtures.
  **11 failed, 33 passed**: AI Return, own Return, all three mismatched-host
  cases, skipped B/C searches, stale search/detail success/error, clear-target
  detail, and outstanding-worker cleanup. Source tree was never reverted.
  Log: `/private/tmp/sporely-fix2-baseline.log`; harness:
  `/private/tmp/sporely-fix2-baseline.py`. Two further close regressions were
  added after this baseline run. Earlier incoming-fixture runs hit unintended
  database access; these are not counted as behavioral reproduction evidence.
- Required focused command (dialog, Community requests, comparison model,
  comparison rebuild, palette): **62 passed in 9.39s**. Log:
  `/private/tmp/sporely-fix2-tests.log`.
- New renderer tests only: **2 passed, 10 deselected in 0.83s** via
  `pytest tests/test_render_review_screenshots.py -q -k
  'test_capture_natural_size or test_capture_open_popup'`.
- Required `py_compile` for five named modules, plus touched renderer/test
  Python files: passed. `git diff --check`: passed.
- `./tools/update_translations.sh`: passed; TS/QM context fix checked through
  actual Norwegian renderer output. No production dependencies or heavy builds.
- `python -m tools.render_review_screenshots --list`: passed. Required
  reference-library group: **40 screenshots**, manifest:
  `/private/tmp/sporely-stage-4b-fix2-review/manifest.json`.

Inspected manifest-listed evidence (12 scoped images; remaining group images
were generated but are not claimed as individually reviewed):
- `reference.fix2-suppressed-{light,dark}.png`: observation n=6 cystidia,
  dim unchecked reference rows, bottom spore-only hint visible.
- `reference.fix2-colors-{light,dark}.png`: blue/orange/yellow chips are distinct.
- `reference.fix2-natural-{light,dark}.png`: actual initial **1209×438** capture,
  all four source and five preview tabs visible without arrow scrollers, with
  empty isolated geometry and splitter settings.
- `reference.fix2-popup-{light,dark}.png`: actual open popup (800×45), own entry,
  82%/41% candidates, long vernacular name and æøå visible without clipping.
- `reference.add-dialog-library{,-dark}.png`: unchecked taxon filter, each
  literature row identifies its taxon; long range text elides after the taxon.
- `reference.fix2-selector-nb-no.png` and `reference.fix2-hint-nb-no.png`:
  “Denne observasjonen” and “Referansedata gjelder sporemålinger.” load and fit.
  Fixture names/badges intentionally remain fixture text. Popup capture is of
  the popup alone; the natural-dialog captures establish the surrounding layout.
All paths above are relative to the manifest directory. Static evidence does
not establish interaction, hardware behavior, or persistence across restart.

Scope adjustments with reasons: the incoming partial host tests were replaced
because the prompt forbids database rows; explicit translation contexts were
necessary because translated selector evidence initially remained English;
shared renderer changes were limited to the sizing/popup facilities permitted
by the prompt. No persistence/adapter/callback abstraction or UI redesign.

Verification tier: **human-gated, now accepted**. Manual acceptance checklist —
all seven **PASS**, explicitly confirmed by the user on 2026-09-05:
1. With spore and cystidium measurements and an attached reference, switch
   Spores → cystidia → Spores. Count must follow population; references dim and
   uncheck outside Spores; original enabled states restore without flicker/loops.
2. Compare observation/reference chips to plotted Spores series. Colours must
   agree and be visibly distinct.
3. Inspect a Library row in the comparison list. Its second line must show the
   measurement range, not repeat the publication title.
4. Open Add reference: four source and five preview tabs must fit without
   arrows. Resize/move splitter, close/reopen, restart app/reopen. Geometry and
   splitter must persist and tabs must still fit.
5. Select AI targets by mouse and keyboard, press Return; type a non-AI taxon
   and Return. Switch targets rapidly during Community loading and inspect
   Library/Community/My observations. Title/filters must follow target; no
   percentage/vernacular leaks, unintended add, or obsolete results/details.
   Change the old panel target and reopen: own entry still identifies the
   observation consistently.
6. Uncheck Library's Only this taxon: every row must identify its taxon.
   Recheck: filtering must return to the selected target.
7. Reopen Edit Observation: identification unchanged — PASS.

Independent acceptance review verified the targeted production diff, baseline
harness/log (11 expected pre-fix failures), tests and renderer changes. The
required 62 corrective tests passed again; the combined run including the full
renderer module returned **71 passed, 3 failed in 36.26s**. All three failures
are stale scenario-inventory expectations in
`tests/test_render_review_screenshots.py` (lines 76, 85, 153), not capture
failures: they omit existing reference scenarios and the portable-import group.
The first two failures were reproduced with the reference registry loaded from
`14525ff` (30 reference scenarios versus 10 expected); the third asserts the
same outdated inventory after a successful default capture. The ten new scoped
scenarios increase that inventory but do not cause the underlying mismatch.
This is tracked test-maintenance debt, not a claim that the full suite is green.
The two new capture tests pass. No production correction was required by review.

Reviewer inspected all 12 scoped manifest images: natural-size tab bars fit in
both themes, popup contents/percentages/æøå are visible, suppressed rows and
colour distinctions are present, unfiltered rows identify taxa, and Norwegian
selector/hint translations load. Compiled catalogues for nb_NO/sv_SE/de_DE
resolve selector, Community status and comparison hint strings; all have zero
unfinished TS entries. Syntax checks for all touched Python files and
`git diff --check` passed. Pre-existing AGENTS.md edits are excluded from the
stage commit. No authoritative security boundary changed; security escalation
is not warranted.

Deferred unchanged: 4c/manual entry, verdict computation, old-control removal,
palette stability and callback unification. No fresh top-level final review
was substituted by a subagent.

### Incoming corrective handoff (preserved)

Next authorized implementation: **4b-fix2**, a bounded correction within the
approved 4b intent. Pending prompt:
`.sparring/prompts/sporely-py/stage-4b-fix2.md` (relative to the workspace parent).
It covers the three reviewed taxon-target blockers, failing-then-passing
regression tests, scoped translations, and missing meaningful static evidence.
The implementer updates this plan and stops after agent-verifiable checks,
leaving corrective work uncommitted and the seven manual checks pending for
the user. No 4c work is authorized. This review pass wrote only the corrective
prompt and this handoff; it did not implement the corrections.

### Prior handoff evidence

At review, HEAD is `14525ff91f6b7ada1f899c03852f54eb065b1fe1`. The prompt is
now `.sparring/prompts/sporely-py/completed/stage-4b-fix.md`; there were no
top-level pending prompts before 4b-fix2 was authored. The earlier selector
claim is stale.
This pass changes only this handoff; no production implementation was duplicated.
The pre-existing working-tree edit to `AGENTS.md` was preserved.

Verification rerun:
- Required comparison-model/dialog/widget tests: **46 passed in 3.26s**.
- `tests/test_reference_series_palette.py`: **2 passed in 0.60s**.
- Required `py_compile` of the four UI modules: passed.
- Repository reference-library renderer: 30 screenshots generated; manifest at
  `/private/tmp/sporely-stage-4b-fix-20260905/manifest.json`.
- Inspected suppressed list (n=6 cystidia, dim unchecked references and hint),
  color list (blue/orange/yellow), default-size dialog (four source and five
  preview tabs visible), selected AI target (82%), and dark Library with taxon
  filter unchecked (taxa visible). These are static evidence only.

Evidence limitations: the existing AI scenario captures a selected candidate,
not the open popup requested by the prompt; suppressed/color/default/AI scenarios
have no dedicated dark counterparts. The default-size scenario supplies a
1400x760 viewport, so the screenshot alone does not prove natural default sizing.
These gaps remain for the fresh review; do not represent this as full acceptance.

Existing paths confirmed: `MainWindow._reference_overlays_allowed_for_category`
is shared by plot and comparison list; `update_gallery` refreshes the list after
the plot (no new signal connection). `_collect_reference_ai_suggestions` reads
stored Artsorakel/iNaturalist predictions; `_on_ref_ai_suggestion_activated` is
the old panel fill path. `comparison_panel._format_detail` now uses library
kind/raw text like `AddReferenceDialog._add_candidate_item`; previously it fell
through to source text, duplicating the title's publication.

Manual status: all seven 4b-fix manual items are **not run in this pass**:
1. Switch Spores to cystidia and back; verify count and reference dimming restore.
2. Verify distinct observation/reference colors in chips and plot.
3. Verify library row detail is the measurement range.
4. Verify all tabs fit and dialog size persists after resize/close/reopen.
5. Select an AI target, then enter an arbitrary taxon; verify filter and title.
6. Uncheck Only this taxon; verify each row identifies its taxon.
7. Reopen Edit Observation; verify identification was unchanged.

Commit status: existing implementation remains at `14525ff`; this handoff is
uncommitted pending review of the outstanding evidence/manual gates. No push.
Deferred: stage 4c manual entry, stage 5 verdicts, stage 6 control removal and
palette stability. Suggested future callback unification: one typed request
dataclass with a source-kind discriminator and explicit local-set, observation,
cloud, or manual payload, handled by one dispatcher. Cost: adapt existing caller
closures and dialog submission paths, plus per-variant validation/tests; no
persistence change is inherently required. Not implemented in this stage.

## Independent review — 2026-09-05

Verdict: **partly confirmed**. No stage 4c prompt issued; no implementation edits.
`.sparring/latest.md` (Captured 2026-09-05 00:01 CEST) describes an unrelated
AGENTS.md scout, not the implementation. Review therefore used the committed
diff, completed prompt, and current handoff. The earlier backfill already
records stages 1–4a-fix; do not duplicate it based on the skill's stale note.

Confirmed: the category suppression predicate is shared by plot and list;
`update_gallery` refreshes the comparison rows; library details use kind/raw
text; automatic reference colours start at index 1. Focused verification:
`./.venv/bin/pytest tests/test_comparison_panel_model.py tests/test_add_reference_dialog.py tests/test_comparison_list_widget_rebuild.py tests/test_reference_series_palette.py -q`
→ **48 passed in 6.66s**. `py_compile` of add_reference_dialog,
cloud_reference_dialog, comparison_panel and main_window passed. These results
do not settle the live acceptance checks.

Blocking findings for a bounded corrective stage before 4c:
1. `ui/cloud_reference_dialog.py:1288–1359`: `set_taxon` changes the target,
   but `refresh` returns while an old search worker exists. Its completion
   accepts the old results unconditionally, without launching the new target's
   search. Reproduced offline with a real pane, a sentinel in-flight worker,
   and synthetic completion: current target `Amanita fulva`, accepted result
   `Cortinarius limonius`. Guard stale search/error and detail callbacks by
   request identity and ensure the latest requested target is actually loaded;
   `_on_detail_finished` at 1437 also accepts old detail unconditionally.
2. `ui/add_reference_dialog.py:425–428,488–498`: Return on the editable combo
   always parses display text, including an unchanged AI label. Calling the
   connected handlers with an 82% candidate reproducibly changes species from
   `rubellus` to `rubellus  82%`. Preserve structured selected-item data when
   text is unchanged; parse only deliberately edited free text. Tests currently
   call selection and typing handlers separately and miss this sequence.
3. `ui/main_window.py:11540–11545`: initial genus/species come from editable
   old reference-panel fields, while taxon ID comes from the active observation
   (`_active_sporely_taxon_id`, 13093). The old AI handler at 12948 changes those
   fields. After selecting another old-panel target, the dialog's “This
   observation” entry can name that target while Library filters by the actual
   observation ID. Initialize own-target identity consistently from the active
   observation; keep comparison target distinct. Add a mismatched-panel fixture.

Evidence/maintenance still owed: the manifest has 30 screens but the default
scenario forces 1400x760, the AI scenario is selected rather than open, and
suppressed/colours/default/AI lack dark counterparts. Preserve the earlier
static inspection report as a claim; this review did not re-inspect PNGs.
Required translation refresh was not committed: new selector/hint source
strings are absent from the Norwegian catalogue, and comparison_panel.py is
absent from tools/update_translations.sh's source list. Correct extraction
coverage and refresh the paired TS/QM files under the localization rules.

All seven manual checks above remain unconfirmed; “not run in this pass” is
not proof of an earlier pass. Extend acceptance to keyboard selection/Return,
rapid target changes with Community loading, and reopening after changing the
old panel target. Test geometry AND splitter persistence across app restart.
The completed prompt's split self-verifiable/post-commit gate conflicts with
AGENTS.md's human-gated interaction rule; the existing commit is not acceptance
and should not be rewritten. A corrective implementation must remain
uncommitted until its human gate passes. A focused stage-boundary correctness
review is warranted after correction; no authoritative security boundary change
was found that warrants a security-reviewer escalation.

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
