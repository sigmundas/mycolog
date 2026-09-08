# Cloud-sync Pre-stage evidence — 2026-09-08

Status: **candidate evidence, not independently accepted**. This is an inventory annex to
[the canonical extraction plan](2026-08-23-cloud-sync-extraction.md), not another execution plan.
No extraction stage was started. All source locations describe the starting local worktree.

## Repository baseline

- Canonical root: `/Users/sigmundas/Documents/Code/sporely/sporely-py`.
- Branch `main`; HEAD `7acaad12824ec4d6bdd1848f3ef6603d063507a1`.
- HEAD subject: `docs: sharpen Parmasto comparison-foundation plan; declare it out of scope for reference-system UI`.
- `git status --porcelain=v1 --untracked-files=all` returned no entries before edits; no staged, unstaged, or untracked work was present. Ignored environments/caches were not inventoried.
- `utils/cloud_sync.py` has 26,187 lines. Its last change is `6db603c` (conflict-plan mosaic restoration).
- History anchor: `git log --follow` finds `de824a4` (2026-08-23, original plan path before the `5ad37dd` documentation reorganization); later plan edits are `f379171` and `e01f2a9`. Delta observations below compare `de824a4..HEAD`, not just calendar dates.
- Sources read first: current canonical handoff, child `AGENTS.md`, `.claude/rules/cloud-sync.md`, local `docs/supabase-sync-contract.md`, architecture map; technical overview for orientation. The current mosaic handoff records independent acceptance at `6db603c`; that is prior work, not acceptance of this Pre-stage.
- No GitHub, live cloud, real account, package installation, or cross-repository source audit was used. Equality of the two contract copies was not verified in this pass.

## Test baseline and exact reproduction

Use project `.venv` only. Every batch used `QT_QPA_PLATFORM=offscreen`; all completed with code 1 except the consumer batch (code 0).

| Batch | Result | Scope |
| --- | --- | --- |
| Focused safety + Stage 0 infrastructure | 169 passed, 1 failed in 5.06s | 9 files below |
| Broader legacy cloud + normalized-reference boundary | 1,732 passed, 3 failed, 6 skipped in 37.56s | 97 files below |
| Additional public consumer/UI/auth checks | 203 passed in 2.55s | 11 files below |
| Isolated failure reproduction + skipped gate | 3 failed, 6 skipped in 1.01s | three exact failing nodes + cross-repository gate |

These batches overlap; do not add their totals as unique coverage. This is not the entire repository suite, a live canary, or proof of cross-client behavior.

### Unresolved failures (all predate documentation edits)

1. `tests/test_cloud_media_pull_retry.py::test_cloud_media_materialization_state_detects_missing_and_ready_media` — `NameError: name 'suppress_reverse_identity' is not defined`, `utils/cloud_sync.py:26120`. `cloud_media_materialization_state_for_observation` reads this name in reverse-image matching without defining it; this is a production defect exposed by the fixture, not a proposed extraction regression. Portable-identity guard behavior needs a separately reviewed repair; do not delete the guard to green the test.
2. `tests/test_cloud_sync_progress_reset_and_prepare.py::test_reconcile_metadata_only_linked_images_skips_unchanged_siblings` — expected `{1825,1826}`, actual `{1826}` at test line 342. Stub `push_image_metadata` at line 307 accepts only three positional arguments. `_reconcile_metadata_only_linked_images` at line 20251 passes `remote_row=remote_row`; real `SporelyCloudClient.push_image_metadata` at line 16321 accepts it. Captured log reports the unexpected keyword and preparation fallback. Evidence points to stale test-double signature; no test was changed or quarantined.
3. `tests/test_legacy_reference_migration.py::test_migration_dry_run_makes_no_changes` — SQLite file bytes differ at offset 27 (`0x21` vs `0x25`), assertion at test line 416. Reproduces alone. The test establishes byte mutation, not which domain rows changed; root cause was not diagnosed in this inventory. Keep as an unresolved sibling baseline failure, not an approved waiver.

Six skips: `tests/test_stage6l_cross_repository_contract.py:52` defaults to unavailable historical paths `sporely-web-reference-stage6` and `sporely-landing-stage6j`. `SPORELY_STAGE6L_GATE` was not enabled. No sibling was searched or substituted. A future cross-repository gate must explicitly select canonical repositories and read their rules first.

The extraction gate remains **red**. Independent review must decide repair/explicit quarantine in a separate baseline work item before Stage 0 movement. Known red does not mean approved red; this pass neither fixes nor accepts these failures.

Local raw logs: `/tmp/sporely-prestage-focused.log`, `/tmp/sporely-prestage-broad.log`, `/tmp/sporely-prestage-consumers.log`, `/tmp/sporely-prestage-repro.log` (ephemeral; results and selections are preserved here).

### Commands / frozen selections

Focused:

```sh
QT_QPA_PLATFORM=offscreen ./.venv/bin/pytest -q FOCUSED_FILES
```

`FOCUSED_FILES` expands to:

```text
tests/test_cloud_download_only.py
tests/test_cloud_image_bytes_desired.py
tests/test_image_tombstones.py
tests/test_cloud_sync_fast_path.py
tests/test_cloud_sync_dirty_loop_steady_state.py
tests/test_child_change_probe.py
tests/test_cloud_sync_profile.py
tests/test_cloud_sync_progress_mapping.py
tests/test_cloud_sync_progress_reset_and_prepare.py
```

For each broader/consumer selection below, save that block as a UTF-8 file and run from the canonical repository:

```python
import os, subprocess
from pathlib import Path
files = Path("/tmp/selection.txt").read_text().splitlines()
raise SystemExit(subprocess.call(
    ["./.venv/bin/pytest", "-q", *files],
    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
))
```

Broader selection (frozen, sorted):

```text
tests/test_add_reference_dialog.py
tests/test_calibration_reference_recovery_ui.py
tests/test_child_change_probe.py
tests/test_cloud_account_lock.py
tests/test_cloud_ai_selection_sync.py
tests/test_cloud_anchor_promotion.py
tests/test_cloud_calibration_sync.py
tests/test_cloud_conflict_dialog.py
tests/test_cloud_conflict_plan_execution.py
tests/test_cloud_direct_r2_guard.py
tests/test_cloud_download_only.py
tests/test_cloud_image_bytes_desired.py
tests/test_cloud_image_calibration_linkage.py
tests/test_cloud_measurement_sync_v1.py
tests/test_cloud_media_audit.py
tests/test_cloud_media_policy.py
tests/test_cloud_media_pull_retry.py
tests/test_cloud_media_recovery.py
tests/test_cloud_metadata_sync.py
tests/test_cloud_original_sync_recovery.py
tests/test_cloud_original_sync_surface.py
tests/test_cloud_original_sync_upload.py
tests/test_cloud_reconciliation_report.py
tests/test_cloud_reference_taxon_lookup_integration.py
tests/test_cloud_spore_mosaic.py
tests/test_cloud_spore_mosaic_backfill.py
tests/test_cloud_spore_mosaic_build_result.py
tests/test_cloud_spore_mosaic_signature.py
tests/test_cloud_spore_mosaic_unchanged_sync.py
tests/test_cloud_storage_desired_initializer.py
tests/test_cloud_storage_intent_ledger.py
tests/test_cloud_sync_auth_refresh.py
tests/test_cloud_sync_change_notification.py
tests/test_cloud_sync_conflict_preflight.py
tests/test_cloud_sync_dialog_oauth.py
tests/test_cloud_sync_dirty_loop_steady_state.py
tests/test_cloud_sync_dirty_pending_images.py
tests/test_cloud_sync_exif_backfill.py
tests/test_cloud_sync_fast_path.py
tests/test_cloud_sync_image_captured_at.py
tests/test_cloud_sync_image_order.py
tests/test_cloud_sync_image_upload_policy.py
tests/test_cloud_sync_metadata_only.py
tests/test_cloud_sync_pending_image_repair.py
tests/test_cloud_sync_profile.py
tests/test_cloud_sync_progress_mapping.py
tests/test_cloud_sync_progress_reset_and_prepare.py
tests/test_cloud_sync_reset.py
tests/test_cloud_sync_sample_source.py
tests/test_cloud_taxonomy_identity_sync.py
tests/test_cloud_visibility_phase7.py
tests/test_curated_reference_forks.py
tests/test_curated_reference_sync.py
tests/test_image_push_identity.py
tests/test_image_tombstones.py
tests/test_legacy_reference_interactive_migration.py
tests/test_legacy_reference_migration.py
tests/test_main_window_reference_panel_taxon_lookup.py
tests/test_observation_push_identity.py
tests/test_observation_reference_use_pull.py
tests/test_observation_reference_use_sync.py
tests/test_observation_snapshot_persistence.py
tests/test_original_sync_policy.py
tests/test_portable_cloud_identity_guard.py
tests/test_preferences_cloud_sync_controls.py
tests/test_reference_add_dialog_focus.py
tests/test_reference_add_dialog_normalized.py
tests/test_reference_attach_persistence_e2e.py
tests/test_reference_cloud_adapter.py
tests/test_reference_cloud_sync_coordinator.py
tests/test_reference_entry_editor.py
tests/test_reference_library_attach_dialog_filter.py
tests/test_reference_library_bundle_roundtrip.py
tests/test_reference_library_delete_semantics.py
tests/test_reference_library_desktop_slice.py
tests/test_reference_library_manager_dialog.py
tests/test_reference_library_no_verification_no_visibility.py
tests/test_reference_library_preferences.py
tests/test_reference_library_pull_reconciliation.py
tests/test_reference_library_push_executor.py
tests/test_reference_library_repository.py
tests/test_reference_library_schema.py
tests/test_reference_library_snapshot.py
tests/test_reference_panel_coordinator_existing_set.py
tests/test_reference_panel_mainwindow_e2e.py
tests/test_reference_panel_taxon_drift_and_retry.py
tests/test_reference_quick_add_service.py
tests/test_reference_series_palette.py
tests/test_reference_snapshot_updates.py
tests/test_reference_successor_adoption.py
tests/test_reference_sync_mutation_ownership.py
tests/test_reference_sync_planner.py
tests/test_reference_sync_state.py
tests/test_reference_values_taxon_lookup_integration.py
tests/test_reference_work_editor_human_form.py
tests/test_spore_summary_sync.py
tests/test_stage6l_cross_repository_contract.py
```

Consumer selection (disjoint from broader selection):

```text
database/taxonomy/tests/test_stage_3b_3.py
tests/test_audit_cloud_media_health.py
tests/test_image_gallery_cloud_delete.py
tests/test_main_window_cloud_corner_auth.py
tests/test_main_window_cloud_sync_menu.py
tests/test_observation_details_cloud_layout.py
tests/test_observation_details_cloud_media.py
tests/test_observations_tab_cloud_sync.py
tests/test_sporely_cloud_auth.py
tests/test_sporely_cloud_oauth_session.py
tests/test_sync_observation_dirty_propagation.py
```

Isolated reproduction:

```sh
QT_QPA_PLATFORM=offscreen ./.venv/bin/pytest -q -rs \
  tests/test_cloud_media_pull_retry.py::test_cloud_media_materialization_state_detects_missing_and_ready_media \
  tests/test_cloud_sync_progress_reset_and_prepare.py::test_reconcile_metadata_only_linked_images_skips_unchanged_siblings \
  tests/test_legacy_reference_migration.py::test_migration_dry_run_makes_no_changes \
  tests/test_stage6l_cross_repository_contract.py
```

## Candidate movement boundary

Only the following manifest is proposed. All symbols remain available from the facade,
including private names used in-tree. No new runtime dependencies. `errors.py` depends
only on `json`; `summary.py` on `ContextVar`/`contextmanager`; `common.py` holds a five-line
pure conversion helper, not a new general
utility initiative. `profiling.py` imports `_safe_int` from `common.py`; `progress.py`
imports the clock and slow-step threshold from `profiling.py`. Preserve postponed
annotations. The facade imports/re-exports exact objects; owners never import the facade.

`common.py` is a narrow addition to the illustrative plan tree, needed because profiler
`summary_payload` calls `_safe_int` for result counters and leaving that dependency in
`cloud_sync.py` creates a reverse dependency. Move this helper mechanically, preserving
its exact exception handling and default; keep its facade export for all other callers.

The three ContextVars must each have one owner and one object. `sync_all` currently
sets/resets them directly (lines 6473–6477, 6903–6911), so aliases must share identity.
`CloudSyncProfiler.started_at` captures a callable in the dataclass field factory; preserve
that binding behavior. Ordinary re-exports do not redirect a moved function's globals.
Retarget only mocks for calls whose lookup owner actually moved; do not indiscriminately
retarget facade mocks used by still-unmoved orchestration.

Excluded: `PullOnlyCloudClient` and all three `_PULL_ONLY_*` registries (Stage 1), request/
response retry functions and timeouts (Stage 1), privacy/image-plan/WebP policy classifiers
and messages, conflict regexes and `summarize_sync_issues`, pull-only issue partitioning,
original upload/recovery result formatters, `_format_cloud_sync_observation_status`,
`summarize_sync_change_activity`, `_SYNC_SUMMARY_OBSERVATION_REFRESH_KEYS`, and
`sync_result_requires_observation_refresh`. The last two result classifiers embody UI/
entity policy and normalized-reference integration; keep them with orchestration.
Only the error classes move, not the auth, account-binding, byte, or identity policies
that raise/catch them. `format_sync_summary` is included as passive rendering of fixed
counters; do not include the adjacent activity classifier at line 4782.

## Stage 0 exact candidate manifest (unaccepted)

Source: local HEAD `7acaad12824ec4d6bdd1848f3ef6603d063507a1`. All locations below are in `utils/cloud_sync.py`; decorator lines are included when applicable. Dependencies list module-bound names, including standard-library imports, not builtins or local variables.

### errors.py

| Symbol | Lines | Module-bound dependencies |
| --- | --- | --- |
| `CloudSyncError` | 2075–2076 | — |
| `AccountMismatchError` | 2079–2080 | `CloudSyncError` |
| `CloudTemporarilyUnavailableError` | 2083–2084 | `CloudSyncError` |
| `CloudReauthRequiredError` | 2087–2095 | `CloudSyncError` |
| `PullOnlyModeError` | 2098–2106 | `CloudSyncError` |
| `PartialConflictPlanError` | 2287–2297 | `CloudSyncError` |
| `ObservationIdentityConflictError` | 2300–2310 | `CloudSyncError` |
| `ImageIdentityConflictError` | 2313–2317 | `CloudSyncError` |
| `CloudSessionAccountMismatchError` | 2320–2335 | `AccountMismatchError` |
| `CloudImageBytesNotDesiredError` | 5608–5614 | `CloudSyncError` |
| `ACCOUNT_MISMATCH_MESSAGE` | 2338–2342 | — |
| `_CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE` | 163–165 | — |
| `_SUPABASE_TRANSIENT_STATUS_CODES` | 148–148 | — |
| `_SUPABASE_TRANSIENT_ERROR_HINTS` | 149–162 | — |
| `_CLOUD_AUTH_ERROR_HINTS` | 2878–2894 | — |
| `_CLOUD_REAUTH_REQUIRED_HINTS` | 2901–2907 | — |
| `_collect_sync_error_details` | 2734–2829 | `json` |
| `format_cloud_sync_error_details` | 2832–2846 | `_collect_sync_error_details` |
| `is_cloud_auth_error` | 2910–2926 | `CloudReauthRequiredError`, `_CLOUD_AUTH_ERROR_HINTS`, `_collect_sync_error_details` |
| `is_cloud_reauth_required_error` | 2929–2958 | `CloudReauthRequiredError`, `_CLOUD_REAUTH_REQUIRED_HINTS`, `_collect_sync_error_details` |
| `is_cloud_temporary_unavailable_error` | 3023–3035 | `CloudTemporarilyUnavailableError`, `_CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE`, `_SUPABASE_TRANSIENT_ERROR_HINTS`, `_SUPABASE_TRANSIENT_STATUS_CODES`, `_collect_sync_error_details` |

### profiling.py

| Symbol | Lines | Module-bound dependencies |
| --- | --- | --- |
| `_CLOUD_DEBUG_TIMING` | 127–127 | `os` |
| `_cloud_timing_log` | 130–137 | `_CLOUD_DEBUG_TIMING`, `_cloud_sync_perf_counter` |
| `_CLOUD_SYNC_PROFILE_ENV` | 1700–1700 | — |
| `_CLOUD_SYNC_DEBUG_ENV` | 1701–1701 | — |
| `_CLOUD_SYNC_PROFILE_CONTEXT` | 1702–1705 | `ContextVar` |
| `_CLOUD_SYNC_SLOW_STEP_SECONDS` | 1713–1713 | — |
| `_cloud_sync_profile_enabled` | 1731–1732 | `_CLOUD_SYNC_PROFILE_ENV`, `os` |
| `_cloud_sync_debug_enabled` | 1735–1736 | `_CLOUD_SYNC_DEBUG_ENV`, `os` |
| `_cloud_sync_current_profiler` | 1739–1743 | `_CLOUD_SYNC_PROFILE_CONTEXT` |
| `_cloud_sync_profile_scope` | 1753–1762 | `_CLOUD_SYNC_PROFILE_CONTEXT`, `contextmanager` |
| `_cloud_sync_phase_scope` | 1777–1780 | `nullcontext` |
| `_cloud_sync_perf_counter` | 1783–1787 | `time` |
| `_cloud_sync_profile_print` | 1790–1797 | `json` |
| `CloudSyncProfiler` | 1800–2058 | `_cloud_sync_perf_counter`, `_cloud_sync_profile_print`, `_safe_int`, `contextmanager`, `dataclass`, `field`, `uuid` |

### progress.py

| Symbol | Lines | Module-bound dependencies |
| --- | --- | --- |
| `ProgressCallback` | 1697–1697 | `Callable` |
| `_CLOUD_SYNC_PROGRESS_TRACE_CONTEXT` | 1718–1721 | `ContextVar` |
| `_cloud_sync_progress_trace` | 1724–1728 | `_CLOUD_SYNC_PROGRESS_TRACE_CONTEXT` |
| `_progress_done` | 4466–4470 | — |
| `_progress_total` | 4473–4477 | — |
| `_trace_progress_gap` | 4480–4506 | `_CLOUD_SYNC_SLOW_STEP_SECONDS`, `_cloud_sync_perf_counter`, `_cloud_sync_progress_trace` |
| `_SYNC_PROGRESS_PHASES` | 4519–4530 | — |
| `_SYNC_PROGRESS_PHASE_RANGES` | 4531–4533 | `_SYNC_PROGRESS_PHASES` |
| `_SYNC_PROGRESS_TOTAL_UNITS` | 4534–4534 | — |
| `_sync_progress_percent` | 4537–4552 | `_SYNC_PROGRESS_PHASE_RANGES` |
| `_set_progress_phase` | 4555–4579 | `_SYNC_PROGRESS_PHASE_RANGES` |
| `_current_progress_phase` | 4582–4588 | `_SYNC_PROGRESS_PHASE_RANGES` |
| `_emit_progress` | 4591–4606 | `_SYNC_PROGRESS_TOTAL_UNITS`, `_current_progress_phase`, `_progress_done`, `_progress_total`, `_sync_progress_percent`, `_trace_progress_gap`, `ProgressCallback` |
| `_advance_progress` | 4609–4620 | `_progress_done`, `_progress_total` |
| `_extend_progress_total` | 4623–4634 | `_progress_done`, `_progress_total` |

### summary.py

| Symbol | Lines | Module-bound dependencies |
| --- | --- | --- |
| `_CLOUD_SYNC_SUMMARY_CONTEXT` | 1706–1709 | `ContextVar` |
| `_cloud_sync_current_summary` | 1746–1750 | `_CLOUD_SYNC_SUMMARY_CONTEXT` |
| `_cloud_sync_summary_scope` | 1765–1774 | `_CLOUD_SYNC_SUMMARY_CONTEXT`, `contextmanager` |
| `_SYNC_SUMMARY_KEYS` | 4637–4661 | — |
| `_new_sync_summary` | 4664–4665 | `_SYNC_SUMMARY_KEYS` |
| `_sync_summary_value` | 4668–4672 | — |
| `_increment_sync_summary` | 4675–4684 | `_sync_summary_value` |
| `format_sync_summary` | 4687–4779 | `_sync_summary_value` |

### common.py

| Symbol | Lines | Module-bound dependencies |
| --- | --- | --- |
| `_safe_int` | 8052–8056 | — |

## Import and monkeypatch inventory

### Scope and method

Method: AST walk of all tracked Python files at local HEAD `7acaad12824ec4d6bdd1848f3ef6603d063507a1`, including function-local imports and arbitrary aliases. Provider excluded. Each entry lists imported names, module attribute reads, literal reflective/patch targets with lines, and module/path strings. Static inventory cannot resolve arbitrary computed code.

### Production / tools / scripts

21 files (including source/path-only dependencies).

- `main.py` — import lines 90
  - imports: set_cloud_sync_source_app_version
- `one_time_exif_sync.py` — import lines 7
  - imports: SporelyCloudClient, _inject_obs_exif_into_field_image, _load_obs_exif_fallback
- `scripts/audit_cloud_media.py` — import lines 22
  - imports: CloudReauthRequiredError, SporelyCloudClient, get_app_settings
- `scripts/recover_cloud_media.py` — import lines 20
  - imports: SporelyCloudClient, get_app_settings
- `tools/audit_cloud_media_health.py` — import lines 29
  - imports: SporelyCloudClient, should_push_local_image_to_cloud
- `tools/cleanup_orphaned_r2_media.py` — import lines 22
  - imports: SUPABASE_KEY, SUPABASE_URL, SporelyCloudClient
- `tools/cloud_reconciliation_report.py` — import lines 1232
  - imports: SporelyCloudClient
  - module/path strings: L245: Local Stage-1 canonical byte-storage predicate. Mirrors ``utils.cloud_sync.cloud_image_bytes_desired`` semantics: anything not in the excluded set is desired. Reads only the raw setting the user alrea…
- `tools/migrate_images_to_r2.py` — import lines 18
  - imports: ImageIdentityConflictError, SporelyCloudClient, _normalize_cloud_media_key
- `tools/repair_supabase_storage_media.py` — import lines 48
  - imports: SUPABASE_KEY, SUPABASE_URL, SporelyCloudClient
- `ui/calibration_dialog.py` — import lines 40
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _calibration_recovery_cache_path, _calibration_recovery_cache_root, _calibration_reference_recovery_state, _normalize_calibration_uuid, download_calibration_reference_to_cache
- `ui/cloud_conflict_dialog.py` — import lines 36
  - imports: CloudSyncError, PartialConflictPlanError, SporelyCloudClient, SporelyReadOnlyCloudClient, _resolve_existing_local_image_asset_path, get_conflict_detail, resolve_conflict_keep_cloud, resolve_conflict_keep_local, resolve_conflict_merge, resolve_conflict_plan
- `ui/cloud_reference_dialog.py` — import lines 38
  - imports: CloudSyncError, SporelyCloudClient
- `ui/cloud_sync_dialog.py` — import lines 31, 65, 555
  - imports: ACCOUNT_MISMATCH_MESSAGE, AccountMismatchError, CloudReauthRequiredError, CloudSyncError, OAuthSporelyCloudClient, SporelyCloudClient, finalize_sync_candidates, format_original_upload_summary, is_cloud_auth_error, is_image_too_large_for_plan_error, partition_download_from_cloud_issues, sanitize_image_too_large_for_plan_error_message, summarize_blocked_write_attempts, summarize_image_too_large_for_plan_error, summarize_sync_issues, sync_all, unlink_local_observation_from_cloud
- `ui/image_import_dialog.py` — import lines 95, 457
  - imports: SporelyCloudClient, _cloud_identification_prediction_taxon
- `ui/main_window.py` — import lines 203, 360, 1988, 2237, 2265, 2471, 2741, 4069, 4147, 4419, 6335, 6542, 8476, 13466, 13507, 13552
  - imports: ACCOUNT_MISMATCH_MESSAGE, CLOUD_IMAGE_STORAGE_EXCLUDED_SETTING_PREFIX, OAuthSporelyCloudClient, SporelyCloudClient, clear_saved_cloud_password, ensure_database_linked_to_cloud_user, fetch_cloud_usage_summary, format_image_too_large_for_plan_reason, is_cloud_auth_error, is_cloud_reauth_required_error, mark_observation_dirty, privacy_slot_limit_user_message
  - module aliases: _cloud_sync_module, cloud_sync_module
  - module attributes: SporelyCloudClient, _initialize_cloud_image_storage_desired_state_for_observation, list_calibration_conflicts, repair_calibrations_local_wins, set_image_cloud_selected
- `ui/observations_tab.py` — import lines 174, 3871, 7829, 8175, 8227, 8554, 8595, 8650, 8988, 12095, 12608, 12648, 18463
  - imports: ACCOUNT_MISMATCH_MESSAGE, AccountMismatchError, CLOUD_IMAGE_STORAGE_EXCLUDED_SETTING_PREFIX, CLOUD_SYNC_SKIP_PREPARE_IMAGE_IDS_KEY, CloudSyncError, PENDING_REASON_ALREADY_SYNCED, PENDING_REASON_EXCLUDED, PENDING_REASON_PENDING_UPLOAD, SporelyCloudClient, _cloud_explicit_media_upload_selection, _cloud_identification_prediction_taxon, _cloud_publish_path_key, _cloud_sync_current_summary, _cloud_sync_debug_enabled, _explicit_image_restore_source, _format_cloud_sync_observation_status, _increment_sync_summary, _measurement_counts_for_observation_images, build_cloud_ai_state_from_observation_identifications, cloud_media_materialization_state_for_observation, cloud_observation_uses_privacy_slot, explain_pending_cloud_image_decision, fetch_cloud_usage_summary, finalize_sync_candidates, format_cloud_sync_error_details, format_original_upload_summary, format_sync_summary, is_cloud_auth_error, is_image_too_large_for_plan_error, materialize_cloud_media_for_observation, partition_download_from_cloud_issues, privacy_slot_limit_user_message, sanitize_image_too_large_for_plan_error_message, set_image_cloud_selected, should_pull_cloud_image_to_desktop, should_push_local_image_to_cloud, summarize_blocked_write_attempts, summarize_image_too_large_for_plan_error, summarize_sync_change_activity, summarize_sync_issues, sync_all, sync_result_requires_observation_refresh, unlink_local_observation_from_cloud
  - module aliases: _cloud_sync_module, cloud_sync_module
  - module attributes: _initialize_cloud_image_storage_desired_state_for_observation, set_image_cloud_selected
- `utils/cloud_media_audit.py` — import lines 23
  - imports: CloudReauthRequiredError, SporelyCloudClient, measurement_qualifies_for_public_spore_anchor
- `utils/cloud_media_recovery.py` — import lines 15
  - imports: _file_content_signature, _normalize_cloud_media_key, _sanitize_original_storage_filename, _store_cloud_image_file_signature
- `utils/cloud_spore_mosaic_backfill.py` — import lines 104, 132
  - imports: SporelyCloudClient, backfill_public_spore_mosaics
- `utils/reference_cloud_adapter.py` — import lines 8
  - imports: AccountMismatchError, CloudReauthRequiredError, CloudSyncError, CloudTemporarilyUnavailableError
- `utils/sporely_cloud_auth.py` — import lines 26
  - imports: SUPABASE_URL

### Tests

68 files (including source/path-only dependencies).

- `database/taxonomy/tests/test_stage_3b_3.py` — import lines 269
  - module aliases: cloud_sync
  - module attributes: _CONFLICT_COMPARE_FIELDS, _OBS_PUSH_COLS, _SNAPSHOT_OBS_FIELDS
- `tests/test_child_change_probe.py` — import lines 15
  - module aliases: cloud_sync
  - module attributes: ImageDB, PullOnlyCloudClient, SporelyCloudClient, _CHILD_CHANGE_CURSOR_VERSION, _CLOUD_CHILD_CHANGE_CURSOR_SETTING, _CLOUD_MEASUREMENT_RECONCILE_VERSION, _CLOUD_MEASUREMENT_RECONCILE_VERSION_SETTING, _apply_remote_images_to_local, _cloud_observation_snapshot_key, _load_child_change_cursor, _new_sync_summary, pull_all, sync_all
  - patch/reflective targets: _apply_remote_image_metadata_only_to_local (L1316), _backfill_missing_exif_on_cloud_images (L150), _detect_deleted_remote_observations (L159), _local_tombstoned_cloud_image_ids (L1315), _mark_cloud_observations_dirty_for_media_changes (L134), _mark_cloud_observations_dirty_for_pending_local_images (L135), _push_summary_for_current_observation (L157), _reconcile_missing_spore_measurements (L155), _reconcile_missing_spore_summaries (L156), _store_remote_snapshot (L158), ensure_database_linked_to_cloud_user (L1155), ensure_database_linked_to_cloud_user (L347), ensure_database_linked_to_cloud_user (L391), ensure_database_linked_to_cloud_user (L594), ensure_database_linked_to_cloud_user (L688), ensure_database_linked_to_cloud_user (L763), ensure_database_linked_to_cloud_user (L811), ensure_database_linked_to_cloud_user (L877), ensure_database_linked_to_cloud_user (L944), get_app_settings (L1025), get_app_settings (L1153), get_app_settings (L345), get_app_settings (L388), get_app_settings (L592), get_app_settings (L686), get_app_settings (L761), get_app_settings (L809), get_app_settings (L875), get_app_settings (L942), get_connection (L132), pull_all (L1169), pull_all (L356), pull_all (L400), pull_all (L603), pull_all (L697), pull_all (L772), pull_all (L820), pull_all (L886), pull_all (L953), pull_calibrations (L1157), pull_calibrations (L145), pull_calibrations (L349), pull_calibrations (L393), pull_calibrations (L596), pull_calibrations (L690), pull_calibrations (L765), pull_calibrations (L813), pull_calibrations (L879), pull_calibrations (L946), push_all (L1158), push_all (L350), push_all (L394), push_all (L597), push_all (L691), push_all (L766), push_all (L814), push_all (L880), push_all (L947), push_calibrations (L1156), push_calibrations (L140), push_calibrations (L348), push_calibrations (L392), push_calibrations (L595), push_calibrations (L689), push_calibrations (L764), push_calibrations (L812), push_calibrations (L878), push_calibrations (L945), update_app_settings (L1154), update_app_settings (L346), update_app_settings (L390), update_app_settings (L593), update_app_settings (L687), update_app_settings (L762), update_app_settings (L810), update_app_settings (L876), update_app_settings (L943)
- `tests/test_cloud_account_lock.py` — import lines 6
  - module aliases: cloud_sync
  - module attributes: ACCOUNT_MISMATCH_MESSAGE, AccountMismatchError, ensure_database_linked_to_cloud_user
  - patch/reflective targets: get_app_settings (L27), get_app_settings (L46), get_app_settings (L59), get_app_settings (L83), update_app_settings (L34), update_app_settings (L47), update_app_settings (L60), update_app_settings (L84)
- `tests/test_cloud_ai_selection_sync.py` — import lines 9
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _apply_remote_observation_fields, _create_local_from_remote, _merge_cloud_selected_ai_fields, _normalize_cloud_identification_service, _observation_push_payload, _remaining_local_changes_after_remote_merge, build_cloud_ai_state_from_observation_identifications
  - patch/reflective targets: _import_remote_measurements_for_observation (L235), _import_remote_measurements_for_observation (L81), get_connection (L28)
- `tests/test_cloud_anchor_promotion.py` — import lines 28
  - module aliases: cloud_sync
  - module attributes: CLOUD_SYNC_SKIP_PREPARE_IMAGE_IDS_KEY, CloudSyncError, ImageDB, PullOnlyCloudClient, PullOnlyModeError, SporelyCloudClient, _cloud_image_storage_excluded_ids_key, _cloud_image_storage_intent_ledger_key, _encode_postgrest_filter_value, _file_content_signature, _load_pending_image_promotion_key, _push_images_for_observation, _reconcile_metadata_only_linked_images, _store_cloud_image_file_signature, _store_pending_image_promotion_key, media_variant_key, normalize_media_key
  - patch/reflective targets: _ensure_metadata_anchors_for_public_spore_observation (L538), _local_image_source_bytes_unchanged (L579), _local_image_source_bytes_unchanged (L633), get_connection (L89), is_full_resolution_original_sync_enabled (L288)
- `tests/test_cloud_calibration_sync.py` — import lines 12
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, CloudflareR2Client, SporelyCloudClient, _CALIBRATION_REFERENCE_MAX_EDGE, _calibration_diff_fields, _calibration_payloads_match, _calibration_recovery_cache_path, _calibration_reference_recovery_state, _cloud_sync_summary_scope, _new_sync_summary, _select_representative_calibration_image_path, download_calibration_reference_to_cache, format_sync_summary, list_calibration_conflicts, pull_calibrations, push_calibrations, repair_calibrations_local_wins
  - patch/reflective targets: _cloud_sync_perf_counter (L600), app_data_dir (L63), get_connection (L57)
- `tests/test_cloud_conflict_dialog.py` — import lines 19
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, ImageDB, MeasurementDB, ObservationDB, SporelyReadOnlyCloudClient, _measurement_payloads_match, _measurement_push_diff_fields, _observation_field_values_match, build_conflict_plan_baseline, get_conflict_detail, resolve_conflict_keep_cloud, resolve_conflict_plan
  - patch/reflective targets: _apply_remote_images_to_local (L791), _apply_remote_observation_fields (L787), _apply_remote_observation_fields (L819), _format_recomputed_spore_statistics (L823), _import_remote_measurements_for_observation (L796), _load_cloud_observation_snapshot (L405), _load_cloud_observation_snapshot (L657), _load_local_measurement_lookup (L403), _load_local_measurement_lookup (L655), _pull_remote_images_for_sync (L785), _pull_remote_images_for_sync (L817), _pull_remote_images_for_sync (L866), _pull_remote_measurements_for_images (L404), _pull_remote_measurements_for_images (L656), _pull_remote_measurements_for_images (L792), _pull_remote_measurements_for_images (L818), _pull_remote_measurements_for_images (L839), _pull_remote_measurements_for_images (L867), _push_measurements_for_observation (L821), _record_remote_image_tombstones (L786), _refresh_local_cloud_media_signature (L798), _refresh_local_cloud_media_signature (L827), _stamp_observation_synced (L797), _stamp_observation_synced (L826), _store_remote_snapshot (L799), _store_remote_snapshot (L828)
- `tests/test_cloud_conflict_plan_execution.py` — import lines 27, 28
  - imports: CloudSyncError, SporelyReadOnlyCloudClient, build_conflict_plan_baseline, resolve_conflict_plan
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, CloudTemporarilyUnavailableError, ImageDB, MOSAIC_STATUS_GENERATED, MeasurementDB, ObservationDB, PartialConflictPlanError, SettingsDB, SporelyCloudClient, SporelyReadOnlyCloudClient, _EXPECTED_AFTER_MEASUREMENT_MATERIAL_FIELDS, _asymmetry_fingerprint_local_image, _asymmetry_fingerprint_local_measurement, _asymmetry_fingerprint_remote_measurement, _build_plan_from_automatic_decisions, _cloud_observation_snapshot, _filter_accepted_one_sided_images, _filter_accepted_one_sided_measurements, _intended_after_image_from_local, _load_cloud_observation_snapshot, _material_image_expected_state, _material_measurement_expected_state, _parse_cloud_observation_snapshot, _reconcile_accepted_asymmetry, _store_cloud_observation_snapshot, _store_remote_snapshot, finalize_sync_candidates, get_conflict_detail
  - patch/reflective targets: _apply_remote_images_to_local (L103), _apply_remote_images_to_local (L2539), _apply_remote_images_to_local (L2940), _apply_remote_observation_fields (L101), _apply_remote_observation_fields (L1502), _apply_remote_observation_fields (L2938), _format_recomputed_spore_statistics (L115), _format_recomputed_spore_statistics (L2948), _import_remote_measurements_for_observation (L107), _import_remote_measurements_for_observation (L2942), _load_cloud_observation_snapshot (L1380), _load_cloud_observation_snapshot (L2601), _load_cloud_observation_snapshot (L2936), _load_cloud_observation_snapshot (L609), _load_cloud_observation_snapshot (L629), _load_local_measurement_lookup (L2600), _load_local_measurement_lookup (L2934), _local_observation_id_by_cloud_id (L1985), _local_observation_id_by_cloud_id (L2019), _local_observation_id_by_cloud_id (L2065), _local_observation_id_by_cloud_id (L2956), _pull_remote_images_for_sync (L2930), _pull_remote_images_for_sync (L97), _pull_remote_measurements_for_images (L2587), _pull_remote_measurements_for_images (L2932), _pull_remote_measurements_for_images (L449), _pull_remote_measurements_for_images (L658), _pull_remote_measurements_for_images (L99), _push_images_for_observation (L112), _push_images_for_observation (L2210), _push_images_for_observation (L2946), _push_images_for_observation (L3234), _push_measurements_for_observation (L110), _push_measurements_for_observation (L1504), _push_measurements_for_observation (L1521), _push_measurements_for_observation (L1679), _push_measurements_for_observation (L2944), _push_measurements_for_observation (L459), _push_measurements_for_observation (L668), _push_spore_mosaic_for_observation (L412), _push_spore_mosaic_for_observation (L468), _push_spore_mosaic_for_observation (L86), _refresh_local_cloud_media_signature (L118), _refresh_local_cloud_media_signature (L2952), _stamp_observation_synced (L120), _stamp_observation_synced (L2950), _stamp_observation_synced (L416), _store_remote_snapshot (L127), _store_remote_snapshot (L1379), _store_remote_snapshot (L2954), _store_remote_snapshot (L414), _store_remote_snapshot (L608), _store_remote_snapshot (L628), _store_remote_snapshot (L688), get_conflict_detail (L2958)
  - module/path strings: L399: A reviewed local->cloud measurement upload runs the canonical mosaic helper before snapshot/signature/stamp finalization. The mosaic helper's own eligibility query only requires ``images.cloud_id``/me…; L698: Reproduces the independent-review gap: an automatic plan uploads one local-only measurement while a matched cloud-linked measurement differs from cloud and is left out of the plan's items entirely (a …
- `tests/test_cloud_direct_r2_guard.py` — import lines 6
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, CloudflareR2Client, IMAGE_TOO_LARGE_FOR_PLAN_MESSAGE, IMAGE_TOO_LARGE_FOR_PLAN_USER_MESSAGE, SporelyCloudClient, WEBP_REQUIRED_FOR_CLOUD_MEDIA_UPLOAD_MESSAGE, _format_size, features, format_image_too_large_for_plan_reason, infer_image_too_large_for_plan_reason
  - patch/reflective targets: _prepare_cloud_image_upload_file (L179), direct_r2_runtime_available (L263), media_worker_base_url (L186), media_worker_base_url (L264)
- `tests/test_cloud_download_only.py` — import lines 18
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, ImageDB, PullOnlyCloudClient, PullOnlyModeError, SporelyCloudClient, _PULL_ONLY_BLOCKED_CLIENT_METHODS, partition_download_from_cloud_issues, pull_all, summarize_blocked_write_attempts, sync_all
  - patch/reflective targets: _apply_remote_observation_fields (L400), _backfill_missing_exif_on_cloud_images (L753), _backfill_missing_exif_on_cloud_images (L860), _create_local_from_remote (L672), _detect_deleted_remote_observations (L401), _ensure_local_metadata_only_microscope_anchor (L719), _is_metadata_only_microscope_cloud_image (L716), _load_local_cloud_media_signature (L405), _local_cloud_media_signature (L406), _profile_generate_all_sizes (L459), _refresh_local_cloud_media_signature (L404), _store_local_media_signature_if_equivalent (L407), _store_remote_snapshot (L403), ensure_database_linked_to_cloud_user (L749), ensure_database_linked_to_cloud_user (L858), generate_all_sizes (L458), get_connection (L411), pull_calibrations (L751), pull_calibrations (L859), push_all (L866), push_calibrations (L865), update_app_settings (L402)
- `tests/test_cloud_image_bytes_desired.py` — import lines 29, 30
  - imports: CloudImageBytesNotDesiredError, CloudSyncError, cloud_image_bytes_desired
  - module aliases: cloud_sync
  - module attributes: PENDING_REASON_ALREADY_SYNCED, SporelyCloudClient, _associate_persisted_cloud_images, _cloud_image_storage_excluded_image_ids, _cloud_image_storage_initialized, _ensure_metadata_only_microscope_image_for_public_spores, _push_images_for_observation, explain_pending_cloud_image_decision, set_image_cloud_selected
  - patch/reflective targets: _prepare_cloud_image_upload_file (L1091), _prepare_cloud_image_upload_file (L406), _prepare_cloud_image_upload_file (L679), get_connection (L118), is_full_resolution_original_sync_enabled (L948), media_worker_base_url (L1092), media_worker_base_url (L407), media_worker_base_url (L680)
- `tests/test_cloud_image_calibration_linkage.py` — import lines 6
  - module aliases: cloud_sync
  - module attributes: CalibrationDB, ImageDB, MeasurementDB, ObservationDB, SporelyCloudClient, _import_remote_images, get_conflict_detail, pull_calibrations, tempfile
  - patch/reflective targets: _load_cloud_observation_snapshot (L339), _rename_to_detected_image_extension (L170), _store_cloud_image_file_signature (L171), generate_all_sizes (L169), get_connection (L89)
- `tests/test_cloud_measurement_sync_v1.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: CloudTemporarilyUnavailableError, ImageDB, ObservationDB, SporelyCloudClient, _clear_observation_dirty_if_no_real_changes, _cloud_observation_snapshot, _create_local_from_remote, _import_remote_measurements_for_observation, _measurement_payloads_match, _measurement_push_diff_fields, _push_measurements_for_observation
  - patch/reflective targets: _apply_remote_images_to_local (L268), _apply_remote_images_to_local (L439), _import_remote_images (L160), _load_cloud_observation_snapshot (L638), _load_cloud_observation_snapshot (L770), _load_local_cloud_media_signature (L676), _load_local_cloud_media_signature (L771), _local_cloud_media_signature (L677), _local_cloud_media_signature (L772), _refresh_local_cloud_media_signature (L161), _store_local_media_signature_if_equivalent (L678), _store_local_media_signature_if_equivalent (L773), get_connection (L106)
- `tests/test_cloud_media_audit.py` — import lines 11
  - module aliases: cloud_sync
  - module attributes: CloudReauthRequiredError, SporelyCloudClient, measurement_qualifies_for_public_spore_anchor
- `tests/test_cloud_media_pull_retry.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, CloudSyncProfiler, CloudflareR2Client, ImageDB, SporelyCloudClient, _cloud_sync_profile_scope, cloud_media_materialization_state_for_observation, materialize_cloud_media_for_observation, pull_all
  - patch/reflective targets: _apply_remote_observation_fields (L417), _apply_remote_observation_fields (L615), _apply_remote_observation_fields (L847), _backfill_missing_exif_on_cloud_images (L1004), _backfill_missing_exif_on_cloud_images (L416), _backfill_missing_exif_on_cloud_images (L614), _backfill_missing_exif_on_cloud_images (L846), _detect_deleted_remote_observations (L418), _detect_deleted_remote_observations (L616), _detect_deleted_remote_observations (L848), generate_all_sizes (L1003), generate_all_sizes (L1084), generate_all_sizes (L1190), generate_all_sizes (L1335), generate_all_sizes (L1445), generate_all_sizes (L419), generate_all_sizes (L617), generate_all_sizes (L849), get_connection (L1000), get_connection (L1086), get_connection (L1192), get_connection (L1337), get_connection (L1447), get_connection (L1537), get_connection (L1643), get_connection (L1662), get_connection (L421), get_connection (L619), get_connection (L851), update_app_settings (L1085), update_app_settings (L1191), update_app_settings (L1336), update_app_settings (L1446), update_app_settings (L420), update_app_settings (L618), update_app_settings (L850)
- `tests/test_cloud_metadata_sync.py` — import lines 9
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _CLOUD_SYNC_IN_BATCH_SIZE, _SNAPSHOT_MEAS_FIELDS, _cloud_observation_snapshot, _cloud_sync_summary_scope, _emit_progress, _new_sync_summary, pull_all, push_all, sync_all
  - patch/reflective targets: _backfill_missing_exif_on_cloud_images (L249), _backfill_missing_exif_on_cloud_images (L403), _backfill_missing_exif_on_cloud_images (L447), _backfill_missing_exif_on_cloud_images (L519), _backfill_missing_exif_on_cloud_images (L689), _backfill_missing_exif_on_cloud_images (L759), _create_local_from_remote (L456), _detect_deleted_remote_observations (L255), _detect_deleted_remote_observations (L405), _detect_deleted_remote_observations (L460), _detect_deleted_remote_observations (L521), _detect_deleted_remote_observations (L695), _detect_deleted_remote_observations (L767), _find_local_observation_for_remote_cached (L449), _load_cloud_observation_snapshot (L346), _load_cloud_observation_snapshot (L450), _load_cloud_observation_snapshot (L630), _load_cloud_observation_snapshot (L734), _load_cloud_observation_snapshot (L818), _load_linked_cloud_user_id (L247), _load_linked_cloud_user_id (L401), _load_linked_cloud_user_id (L517), _load_linked_cloud_user_id (L604), _load_local_cloud_media_signature (L253), _load_local_cloud_media_signature (L693), _load_local_cloud_media_signature (L763), _load_local_observation_lookup (L448), _local_cloud_media_signature (L254), _local_cloud_media_signature (L694), _local_cloud_media_signature (L764), _mark_cloud_observations_dirty_for_media_changes (L244), _mark_cloud_observations_dirty_for_media_changes (L383), _mark_cloud_observations_dirty_for_media_changes (L499), _mark_cloud_observations_dirty_for_media_changes (L601), _mark_cloud_observations_dirty_for_pending_local_images (L384), _mark_cloud_observations_dirty_for_pending_local_images (L500), _mark_cloud_observations_dirty_for_pending_local_images (L602), _pull_remote_measurements_for_images (L256), _pull_remote_measurements_for_images (L406), _pull_remote_measurements_for_images (L451), _pull_remote_measurements_for_images (L522), _pull_remote_measurements_for_images (L606), _pull_remote_measurements_for_images (L696), _pull_remote_measurements_for_images (L765), _push_summary_for_current_observation (L17), _reconcile_missing_spore_measurements (L19), _reconcile_missing_spore_summaries (L18), _refresh_local_cloud_media_signature (L251), _refresh_local_cloud_media_signature (L458), _refresh_local_cloud_media_signature (L691), _refresh_local_cloud_media_signature (L761), _save_linked_cloud_user_id (L248), _save_linked_cloud_user_id (L402), _save_linked_cloud_user_id (L518), _save_linked_cloud_user_id (L605), _store_local_media_signature_if_equivalent (L252), _store_local_media_signature_if_equivalent (L692), _store_local_media_signature_if_equivalent (L762), _store_remote_snapshot (L250), _store_remote_snapshot (L404), _store_remote_snapshot (L457), _store_remote_snapshot (L520), _store_remote_snapshot (L607), _store_remote_snapshot (L690), _store_remote_snapshot (L760), get_connection (L243), get_connection (L382), get_connection (L446), get_connection (L498), get_connection (L600), get_connection (L688), get_connection (L758), pull_calibrations (L246), pull_calibrations (L393), pull_calibrations (L509), push_calibrations (L245), push_calibrations (L385), push_calibrations (L501), push_calibrations (L603), update_app_settings (L257), update_app_settings (L407), update_app_settings (L459), update_app_settings (L523), update_app_settings (L697), update_app_settings (L766)
- `tests/test_cloud_original_sync_recovery.py` — import lines 8
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, SporelyCloudClient, recover_full_original_for_image
  - patch/reflective targets: app_data_dir (L55), get_connection (L49)
- `tests/test_cloud_original_sync_surface.py` — import lines 15
  - module aliases: cloud_sync
  - module attributes: format_original_recovery_summary, format_original_upload_summary
- `tests/test_cloud_original_sync_upload.py` — import lines 8
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, SporelyCloudClient, _IMG_PUSH_COLS, _image_calibration_uuid, _load_cloud_observation_snapshot, _normalize_image_captured_at_for_cloud, _push_images_for_observation, _store_remote_snapshot, normalize_media_key
  - patch/reflective targets: FULL_RESOLUTION_ORIGINAL_UPLOAD_MAX_BYTES (L460), get_connection (L45), is_full_resolution_original_sync_enabled (L246), is_full_resolution_original_sync_enabled (L275), is_full_resolution_original_sync_enabled (L302), is_full_resolution_original_sync_enabled (L358), is_full_resolution_original_sync_enabled (L395), is_full_resolution_original_sync_enabled (L420), is_full_resolution_original_sync_enabled (L458)
- `tests/test_cloud_spore_mosaic_backfill.py` — import lines 24
  - module aliases: cloud_sync
  - module attributes: MOSAIC_STATUS_FAIL_TILE_INSERT, MOSAIC_STATUS_FAIL_UPLOAD, MOSAIC_STATUS_GENERATED, MOSAIC_STATUS_SKIP_MISSING_SOURCE_IMAGES, MOSAIC_STATUS_SKIP_NO_ELIGIBLE_MEASUREMENTS, MOSAIC_STATUS_SKIP_NO_PUBLIC_SPORE_DATA, MOSAIC_STATUS_SKIP_NO_USABLE_SOURCES, _ensure_metadata_only_microscope_image_for_public_spores, _ensure_metadata_only_microscope_images_for_observation, _remote_image_row_matches_anchor_payload, backfill_public_spore_mosaics
  - patch/reflective targets: _cloud_explicit_media_upload_selection (L753), _ensure_metadata_only_microscope_image_for_public_spores (L984), _ensure_metadata_only_microscope_images_for_observation (L877), _ensure_metadata_only_microscope_images_for_observation (L901), _ensure_metadata_only_microscope_images_for_observation (L926), _ensure_metadata_only_microscope_images_for_observation (L942), _push_measurements_for_observation (L148), _push_measurements_for_observation (L456), _push_measurements_for_observation (L479), _push_measurements_for_observation (L501), _push_measurements_for_observation (L526), _push_measurements_for_observation (L882), _push_spore_mosaic_for_observation (L168), _push_spore_mosaic_for_observation (L196), _push_spore_mosaic_for_observation (L215), _push_spore_mosaic_for_observation (L241), _push_spore_mosaic_for_observation (L261), _push_spore_mosaic_for_observation (L290), _push_spore_mosaic_for_observation (L318), _push_spore_mosaic_for_observation (L332), _push_spore_mosaic_for_observation (L357), _push_spore_mosaic_for_observation (L381), _push_spore_mosaic_for_observation (L398), _push_spore_mosaic_for_observation (L415), _push_spore_mosaic_for_observation (L457), _push_spore_mosaic_for_observation (L480), _push_spore_mosaic_for_observation (L502), _push_spore_mosaic_for_observation (L527), _push_spore_mosaic_for_observation (L548), _push_spore_mosaic_for_observation (L567), _push_spore_mosaic_for_observation (L887), _push_spore_mosaic_for_observation (L906), _push_spore_mosaic_for_observation (L929), _push_spore_mosaic_for_observation (L948), diagnose_public_spore_mosaic_gates (L547), diagnose_public_spore_mosaic_gates (L562), get_connection (L143), is_cloud_auth_error (L382), is_cloud_auth_error (L403), is_cloud_auth_error (L532), is_cloud_auth_error (L927), is_cloud_temporary_unavailable_error (L383), is_cloud_temporary_unavailable_error (L404), is_cloud_temporary_unavailable_error (L533), is_cloud_temporary_unavailable_error (L928)
- `tests/test_cloud_spore_mosaic_build_result.py` — import lines 17
  - module aliases: cloud_sync
  - module attributes: MOSAIC_STATUS_SKIP_INVALID_GEOMETRY, MOSAIC_STATUS_SKIP_MISSING_CALIBRATION, MOSAIC_STATUS_SKIP_MISSING_SOURCE_IMAGES, MOSAIC_STATUS_SKIP_NO_USABLE_SOURCES, MOSAIC_STATUS_SKIP_RENDER_FAILURE, _classify_mosaic_build_skips
- `tests/test_cloud_spore_mosaic_signature.py` — import lines 24, 533
  - module aliases: cloud_sync, cs
  - module attributes: MOSAIC_STATUS_FAIL_TILE_INSERT, MOSAIC_STATUS_FAIL_UPLOAD, MOSAIC_STATUS_GENERATED, MOSAIC_STATUS_SKIP_UNCHANGED, _ensure_metadata_anchors_for_public_spore_observation, _load_local_mosaic_signature, _local_spore_mosaic_signature, _push_spore_mosaic_for_observation, _store_local_mosaic_signature, backfill_public_spore_mosaics
  - patch/reflective targets: _ensure_metadata_only_microscope_images_for_observation (L851), _ensure_metadata_only_microscope_images_for_observation (L860), _ensure_metadata_only_microscope_images_for_observation (L873), _ensure_metadata_only_microscope_images_for_observation (L891), _ensure_metadata_only_microscope_images_for_observation (L907), _ensure_metadata_only_microscope_images_for_observation (L926), _ensure_metadata_only_microscope_images_for_observation (L958), _push_measurements_for_observation (L957), _push_spore_mosaic_for_observation (L956), direct_r2_runtime_available (L472), direct_r2_runtime_available (L696), get_connection (L132), get_images_dir (L134), is_cloud_auth_error (L894), is_cloud_auth_error (L912), is_cloud_auth_error (L931), is_cloud_temporary_unavailable_error (L895), is_cloud_temporary_unavailable_error (L913), is_cloud_temporary_unavailable_error (L932)
- `tests/test_cloud_spore_mosaic_unchanged_sync.py` — import lines 25
  - module aliases: cloud_sync
  - module attributes: MOSAIC_STATUS_FAIL_TILE_INSERT, MOSAIC_STATUS_FAIL_UPLOAD, MOSAIC_STATUS_GENERATED, MOSAIC_STATUS_SKIP_UNCHANGED, _local_spore_mosaic_signature, _push_spore_mosaic_for_observation
  - patch/reflective targets: direct_r2_runtime_available (L119), get_connection (L117), get_images_dir (L118)
- `tests/test_cloud_storage_desired_initializer.py` — import lines 29
  - module aliases: cloud_sync
  - module attributes: _cloud_image_storage_excluded_image_ids, _cloud_image_storage_intent_initialized_ids, _initialize_cloud_image_storage_desired_state_for_observation, _set_cloud_image_storage_excluded_image_ids, cloud_image_bytes_desired
  - patch/reflective targets: get_connection (L75)
- `tests/test_cloud_storage_intent_ledger.py` — import lines 30
  - module aliases: cloud_sync
  - module attributes: _cloud_image_storage_excluded_ids_key, _cloud_image_storage_excluded_image_ids, _cloud_image_storage_intent_initialized_ids, _cloud_image_storage_intent_ledger_key, _cloud_metadata_only_image_ids, _cloud_metadata_only_image_ids_key, _ensure_cloud_image_storage_intent_initialized, _mark_cloud_observations_dirty_for_pending_local_images, _pending_cloud_pushable_image_ids, cloud_image_bytes_desired, cloud_image_storage_intent_initialized, requests, set_image_cloud_selected
  - patch/reflective targets: get_connection (L75)
- `tests/test_cloud_sync_auth_refresh.py` — import lines 10
  - module aliases: cloud_sync
  - module attributes: CloudReauthRequiredError, CloudSessionAccountMismatchError, CloudSyncError, CloudTemporarilyUnavailableError, OAuthSporelyCloudClient, SporelyCloudClient, _push_images_for_observation, _response_indicates_auth_error, _settings_session_is_compatible, is_cloud_auth_error, is_cloud_reauth_required_error, random, requests, time
  - patch/reflective targets: _push_pending_image_tombstones (L374), clear_saved_cloud_password (L1126), clear_saved_cloud_password (L1154), clear_saved_cloud_password (L1181), get_app_settings (L1004), get_app_settings (L1043), get_app_settings (L1071), get_app_settings (L1104), get_app_settings (L260), get_app_settings (L322), get_app_settings (L354), get_app_settings (L405), get_app_settings (L429), get_app_settings (L475), get_app_settings (L518), get_app_settings (L559), get_app_settings (L611), get_app_settings (L665), get_app_settings (L691), get_app_settings (L729), get_app_settings (L760), get_app_settings (L786), get_app_settings (L825), get_app_settings (L865), get_app_settings (L910), get_app_settings (L934), load_saved_cloud_password (L1021), load_saved_cloud_password (L1054), load_saved_cloud_password (L1077), load_saved_cloud_password (L323), load_saved_cloud_password (L355), load_saved_cloud_password (L671), load_saved_cloud_password (L692), load_saved_cloud_password (L735), update_app_settings (L1110), update_app_settings (L261), update_app_settings (L290), update_app_settings (L519), update_app_settings (L560), update_app_settings (L612), update_app_settings (L787), update_app_settings (L866)
- `tests/test_cloud_sync_change_notification.py` — import lines 13
  - module aliases: cloud_sync
  - module attributes: _CLOUD_SYNC_PROGRESS_TRACE_CONTEXT, _emit_progress, _new_sync_summary, summarize_sync_change_activity, sync_result_requires_observation_refresh
  - patch/reflective targets: _cloud_sync_perf_counter (L151), _cloud_sync_perf_counter (L168)
- `tests/test_cloud_sync_conflict_preflight.py` — import lines 37
  - module aliases: cloud_sync
  - module attributes: CONFLICT_REVIEW_PENDING_MARKER, _analyze_observation_push_conflicts, _cloud_observation_snapshot, _format_push_conflict_review_reasons, _local_cloud_media_signature, _set_observation_conflict_review_pending, push_all, resolve_conflict_keep_cloud, resolve_conflict_keep_local
  - patch/reflective targets: _apply_remote_images_to_local (L1071), _apply_remote_images_to_local (L1112), _apply_remote_observation_fields (L1118), _load_cloud_observation_snapshot (L1077), _load_cloud_observation_snapshot (L1209), _load_cloud_observation_snapshot (L452), _load_local_cloud_media_signature (L1210), _load_local_cloud_media_signature (L453), _local_tombstoned_cloud_image_ids (L439), _local_tombstoned_local_image_ids (L440), _mark_cloud_observations_dirty_for_media_changes (L435), _mark_cloud_observations_dirty_for_pending_local_images (L436), _pull_remote_images_for_sync (L1069), _pull_remote_images_for_sync (L1111), _push_images_for_observation (L1072), _push_images_for_observation (L477), _push_measurements_for_observation (L1073), _push_measurements_for_observation (L478), _push_pending_image_tombstones (L438), _push_spore_mosaic_for_observation (L1074), _push_spore_mosaic_for_observation (L479), _push_summary_for_current_observation (L432), _reconcile_missing_spore_measurements (L434), _reconcile_missing_spore_summaries (L433), _record_remote_image_tombstones (L1070), _record_remote_image_tombstones (L443), _refresh_local_cloud_media_signature (L1076), _refresh_local_cloud_media_signature (L1120), _refresh_local_cloud_media_signature (L1212), _refresh_local_cloud_media_signature (L455), _store_remote_snapshot (L1075), _store_remote_snapshot (L1119), _store_remote_snapshot (L1211), _store_remote_snapshot (L454), get_connection (L148), is_full_resolution_original_sync_enabled (L441), push_calibrations (L437), resolve_full_original_upload_source (L442)
- `tests/test_cloud_sync_dialog_oauth.py` — import lines 34
  - imports: CloudReauthRequiredError
- `tests/test_cloud_sync_dirty_loop_steady_state.py` — import lines 34, 35
  - imports: _OBS_PUSH_COLS, _load_local_cloud_media_signature, _local_cloud_media_signature, _local_media_signatures_match, _observation_push_payload, _refresh_local_cloud_media_signature, _remaining_local_changes_after_remote_merge
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _adopt_merge_filled_ai_fields_locally, _analyze_observation_field_changes, _local_cloud_media_signature, _merge_cloud_selected_ai_fields, _observation_field_values_match, push_all
  - patch/reflective targets: _mark_cloud_observations_dirty_for_media_changes (L311), _mark_cloud_observations_dirty_for_media_changes (L450), _mark_cloud_observations_dirty_for_media_changes (L607), _mark_cloud_observations_dirty_for_media_changes (L864), _mark_cloud_observations_dirty_for_pending_local_images (L316), _mark_cloud_observations_dirty_for_pending_local_images (L451), _mark_cloud_observations_dirty_for_pending_local_images (L608), _mark_cloud_observations_dirty_for_pending_local_images (L865), _push_summary_for_current_observation (L335), _push_summary_for_current_observation (L470), _push_summary_for_current_observation (L614), _push_summary_for_current_observation (L871), _reconcile_missing_spore_measurements (L326), _reconcile_missing_spore_measurements (L461), _reconcile_missing_spore_measurements (L612), _reconcile_missing_spore_measurements (L869), _reconcile_missing_spore_summaries (L329), _reconcile_missing_spore_summaries (L464), _reconcile_missing_spore_summaries (L613), _reconcile_missing_spore_summaries (L870), get_connection (L1095), get_connection (L1118), get_connection (L215), get_connection (L308), get_connection (L447), get_connection (L581), get_connection (L838), push_calibrations (L321), push_calibrations (L456), push_calibrations (L610), push_calibrations (L867)
- `tests/test_cloud_sync_dirty_pending_images.py` — import lines 8
  - module aliases: cloud_sync
  - module attributes: SettingsDB, _CLOUD_PENDING_IMAGE_REPAIR_AT_SETTING, _CLOUD_PENDING_IMAGE_REPAIR_VERSION, _CLOUD_PENDING_IMAGE_REPAIR_VERSION_SETTING, _cloud_pending_image_repair_scan_due, _mark_cloud_observations_dirty_for_pending_local_images, push_all
  - patch/reflective targets: _cloud_pending_image_repair_scan_due (L134), _cloud_pending_image_repair_scan_due (L218), _mark_cloud_observations_dirty_for_media_changes (L133), _mark_cloud_observations_dirty_for_media_changes (L217), _mark_cloud_observations_dirty_for_media_changes (L265), _mark_cloud_observations_dirty_for_pending_local_images (L139), _mark_cloud_observations_dirty_for_pending_local_images (L223), _mark_cloud_observations_dirty_for_pending_local_images (L266), get_connection (L131), get_connection (L215), get_connection (L263), get_connection (L59), push_calibrations (L144), push_calibrations (L228), push_calibrations (L271)
- `tests/test_cloud_sync_exif_backfill.py` — import lines 5
  - module aliases: cloud_sync
  - module attributes: ObservationDB, _backfill_missing_exif_on_cloud_images
  - patch/reflective targets: _inject_obs_exif_into_field_image (L118), _inject_obs_exif_into_field_image (L184), _inject_obs_exif_into_field_image (L68), get_connection (L111), get_connection (L166), get_connection (L37), get_connection (L56)
- `tests/test_cloud_sync_fast_path.py` — import lines 28, 827, 894
  - imports: _SNAPSHOT_OBS_FIELDS, _normalize_snapshot_value, _parse_sync_timestamp
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, _CHILD_CHANGE_CURSOR_VERSION, _CLOUD_CHILD_CHANGE_CURSOR_SETTING, _CLOUD_LAST_CHILD_SAFETY_PULL_AT_SETTING, _CLOUD_MEASUREMENT_RECONCILE_AT_SETTING, _CLOUD_MEASUREMENT_RECONCILE_VERSION, _CLOUD_MEASUREMENT_RECONCILE_VERSION_SETTING, _cloud_observation_snapshot_key, _new_sync_summary, _parse_sync_timestamp, _push_phase_requires_remote_observation_refresh, pull_all, push_all, sync_all
  - patch/reflective targets: _backfill_missing_exif_on_cloud_images (L176), _create_local_from_remote (L482), _detect_deleted_remote_observations (L193), _mark_cloud_observations_dirty_for_media_changes (L160), _mark_cloud_observations_dirty_for_pending_local_images (L161), _push_pending_image_tombstones (L236), _push_pending_image_tombstones (L258), _push_summary_for_current_observation (L187), _reconcile_missing_spore_measurements (L181), _reconcile_missing_spore_measurements (L210), _reconcile_missing_spore_measurements (L281), _reconcile_missing_spore_summaries (L184), _reconcile_missing_spore_summaries (L215), _reconcile_missing_spore_summaries (L286), _store_remote_snapshot (L192), ensure_database_linked_to_cloud_user (L382), ensure_database_linked_to_cloud_user (L605), get_app_settings (L378), get_app_settings (L595), get_connection (L158), pull_all (L394), pull_all (L638), pull_calibrations (L171), pull_calibrations (L395), pull_calibrations (L611), push_all (L388), push_all (L630), push_calibrations (L166), push_calibrations (L383), push_calibrations (L606), update_app_settings (L596)
- `tests/test_cloud_sync_image_captured_at.py` — import lines 8
  - module aliases: cloud_sync
  - module attributes: ImageDB, SporelyCloudClient, _IMG_PUSH_COLS, _OBSERVATION_IMAGE_SELECT_COLUMNS, _SNAPSHOT_IMG_FIELDS, _analyze_image_changes, _analyze_observation_push_conflicts, _apply_remote_image_metadata_only_to_local, _cloud_image_captured_at_to_local, _mark_cloud_observations_dirty_for_image_capture_time_changes, _normalize_image_captured_at_for_cloud, _reconcile_metadata_only_linked_images, _remote_image_payload
  - patch/reflective targets: _load_local_cloud_media_signature (L164), _local_cloud_image_media_signature (L169), _local_image_source_bytes_unchanged (L222), _stored_local_media_signature_image_stats (L221), _update_image_columns_without_touching_observation (L70), get_connection (L163), get_connection (L75), mark_observation_dirty (L178)
- `tests/test_cloud_sync_image_order.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: _normalize_cloud_pulled_image_order
  - patch/reflective targets: get_connection (L106)
- `tests/test_cloud_sync_image_upload_policy.py` — import lines 25, 26
  - imports: PENDING_REASON_ALREADY_SYNCED, PENDING_REASON_CACHE_ROW, PENDING_REASON_DUPLICATE, PENDING_REASON_EXCLUDED, PENDING_REASON_GENERATED, PENDING_REASON_MICROSCOPE_NO_MEASUREMENTS, PENDING_REASON_MISSING_FILE, PENDING_REASON_PENDING_UPLOAD, PENDING_REASON_WRONG_TYPE, explain_pending_cloud_image_decision
  - module aliases: cloud_sync
  - module attributes: _mark_cloud_observations_dirty_for_pending_local_images
  - patch/reflective targets: get_connection (L275), get_connection (L306), get_connection (L345), get_connection (L383), get_connection (L419), get_connection (L465), get_connection (L494)
- `tests/test_cloud_sync_metadata_only.py` — import lines 27
  - module aliases: cloud_sync
  - module attributes: _cloud_observation_snapshot, _file_content_signature, _local_cloud_image_media_signature, _local_cloud_media_signature, _local_media_signatures_match, _store_cloud_image_file_signature, _store_local_media_signature_if_equivalent, list_calibration_conflicts, pull_all, pull_calibrations, push_all, push_calibrations
  - patch/reflective targets: _backfill_missing_exif_on_cloud_images (L501), _detect_deleted_remote_observations (L505), _load_cloud_observation_snapshot (L502), _load_cloud_observation_snapshot (L594), _load_cloud_observation_snapshot (L674), _load_local_cloud_media_signature (L595), _load_local_cloud_media_signature (L675), _local_tombstoned_cloud_image_ids (L680), _local_tombstoned_local_image_ids (L681), _mark_cloud_observations_dirty_for_media_changes (L591), _mark_cloud_observations_dirty_for_media_changes (L671), _mark_cloud_observations_dirty_for_pending_local_images (L592), _mark_cloud_observations_dirty_for_pending_local_images (L672), _pull_remote_measurements_for_images (L504), _push_images_for_observation (L613), _push_measurements_for_observation (L614), _push_measurements_for_observation (L678), _push_pending_image_tombstones (L679), _refresh_local_cloud_media_signature (L597), _refresh_local_cloud_media_signature (L677), _store_local_cloud_media_signature (L344), _store_remote_snapshot (L503), _store_remote_snapshot (L596), _store_remote_snapshot (L676), _sync_existing_remote_image_to_local (L532), get_connection (L150), is_full_resolution_original_sync_enabled (L682), push_calibrations (L593), push_calibrations (L673), resolve_full_original_upload_source (L683), update_app_settings (L506)
- `tests/test_cloud_sync_pending_image_repair.py` — import lines 21
  - module aliases: cloud_sync
  - module attributes: CLOUD_SYNC_SKIP_PREPARE_IMAGE_IDS_KEY, ImageDB, SporelyCloudClient, _explicit_image_restore_source, _mark_cloud_observations_dirty_for_pending_local_images, _path_stat_signature, _push_images_for_observation, _store_local_cloud_media_signature, mark_observation_media_dirty, normalize_media_key, remember_explicit_image_restore_source
  - patch/reflective targets: _apply_image_sample_fields_to_push_payload (L212), _clear_explicit_image_restore_source (L218), _clear_local_cloud_media_signature (L245), _explicit_image_restore_source (L213), _file_content_signature (L279), _load_cloud_image_file_signature (L280), _store_cloud_image_file_signature (L281), get_connection (L65), is_full_resolution_original_sync_enabled (L278), is_full_resolution_original_sync_enabled (L472), is_full_resolution_original_sync_enabled (L516), is_full_resolution_original_sync_enabled (L697), is_full_resolution_original_sync_enabled (L755), is_full_resolution_original_sync_enabled (L780), mark_observation_dirty (L250)
- `tests/test_cloud_sync_profile.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: CloudSyncProfiler, SporelyCloudClient, _cloud_sync_profile_scope, _new_sync_summary, _profile_generate_all_sizes, _store_remote_snapshot, sync_all
  - patch/reflective targets: _store_cloud_observation_snapshot (L173), _store_cloud_observation_snapshot (L242), ensure_database_linked_to_cloud_user (L61), generate_all_sizes (L172), pull_all (L80), pull_calibrations (L92), push_all (L68), push_calibrations (L63)
- `tests/test_cloud_sync_progress_mapping.py` — import lines 19
  - module aliases: cloud_sync
  - module attributes: _SYNC_PROGRESS_PHASES, _advance_progress, _emit_progress, _set_progress_phase, _sync_progress_percent
  - module/path strings: L1: Progress bar semantics for the cloud sync worker. The UI shows a single progress bar backed by the ``(message, current, total)`` progress_cb events emitted by :mod:`utils.cloud_sync`. This test-file l…
- `tests/test_cloud_sync_progress_reset_and_prepare.py` — import lines 24
  - module aliases: cloud_sync
  - module attributes: _reconcile_metadata_only_linked_images, _refresh_local_cloud_media_signature
  - patch/reflective targets: get_connection (L112)
- `tests/test_cloud_sync_sample_source.py` — import lines 24, 25, 84, 486, 496
  - imports: _IMAGE_METADATA_ONLY_FIELDS, _IMG_PUSH_COLS, _SNAPSHOT_IMG_FIELDS, _analyze_image_changes, _apply_image_sample_fields_to_push_payload, _cloud_to_desktop_sample_source, _desktop_to_cloud_sample_source, _local_image_snapshot_payload, _remote_image_payload, _split_legacy_sample_type_into_source
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _local_cloud_media_signature
- `tests/test_cloud_taxonomy_identity_sync.py` — import lines 3
  - imports: SporelyCloudClient
- `tests/test_cloud_visibility_phase7.py` — import lines 9
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, IMAGE_TOO_LARGE_FOR_PLAN_MESSAGE, ImageDB, MeasurementDB, ObservationDB, SporelyCloudClient, _OBSERVATION_IDENTIFICATION_SELECT_COLUMNS, _OBSERVATION_IMAGE_SELECT_COLUMNS, _OBSERVATION_SELECT_COLUMNS, _SPORE_MEASUREMENT_SELECT_COLUMNS, _apply_remote_images_to_local, _apply_remote_observation_fields, _build_worker_storage_path, _cloud_image_captured_at_to_local, _cloud_metadata_only_image_ids, _cloud_observation_snapshot, _cloud_observation_snapshot_key, _cloud_sync_summary_scope, _cloud_visibility_to_sharing_scope, _create_local_from_remote, _ensure_local_metadata_only_microscope_anchor, _ensure_metadata_only_microscope_images_for_observation, _import_remote_images, _local_cloud_media_signature, _mark_cloud_observations_dirty_for_pending_local_images, _new_sync_summary, _normalize_sharing_scope, _observation_compare_payload, _observation_field_values_match, _observation_push_diff_fields, _push_images_for_observation, _push_measurements_for_observation, _push_pending_image_tombstones, _record_remote_image_tombstones, _sharing_scope_to_cloud_visibility, _summarize_image_changes, _sync_existing_remote_image_to_local, fetch_cloud_usage_summary, get_conflict_detail, is_privacy_slot_limit_error, mark_observation_dirty, normalize_media_key, privacy_slot_limit_user_message, pull_all, push_all, resolve_conflict_keep_local, summarize_sync_issues, tempfile
  - patch/reflective targets: _apply_remote_observation_fields (L4322), _apply_remote_observation_fields (L4635), _apply_remote_observation_fields (L4756), _backfill_missing_exif_on_cloud_images (L4090), _backfill_missing_exif_on_cloud_images (L4313), _backfill_missing_exif_on_cloud_images (L4626), _backfill_missing_exif_on_cloud_images (L4747), _clear_observation_dirty_if_no_real_changes (L4095), _detect_deleted_remote_observations (L4096), _detect_deleted_remote_observations (L4321), _detect_deleted_remote_observations (L4634), _detect_deleted_remote_observations (L4755), _ensure_metadata_anchors_for_public_spore_observation (L5769), _file_content_signature (L1470), _file_content_signature (L1597), _file_content_signature (L1693), _import_remote_images (L1870), _inject_obs_exif_into_field_image (L4186), _load_cloud_image_file_signature (L1471), _load_cloud_image_file_signature (L1598), _load_cloud_image_file_signature (L1694), _load_cloud_image_file_signature (L2238), _load_cloud_image_file_signature (L2328), _load_cloud_observation_snapshot (L3472), _load_cloud_observation_snapshot (L4314), _load_cloud_observation_snapshot (L446), _load_cloud_observation_snapshot (L4460), _load_cloud_observation_snapshot (L4501), _load_cloud_observation_snapshot (L4627), _load_cloud_observation_snapshot (L4748), _load_cloud_observation_snapshot (L692), _load_local_cloud_media_signature (L4315), _load_local_cloud_media_signature (L447), _load_local_cloud_media_signature (L4628), _load_local_cloud_media_signature (L4749), _load_local_cloud_media_signature (L693), _load_obs_exif_fallback (L4185), _local_cloud_media_signature (L4316), _local_cloud_media_signature (L4629), _local_cloud_media_signature (L4750), _local_tombstoned_cloud_image_ids (L4506), _mark_cloud_observations_dirty_for_media_changes (L2059), _mark_cloud_observations_dirty_for_media_changes (L2142), _mark_cloud_observations_dirty_for_media_changes (L2234), _mark_cloud_observations_dirty_for_media_changes (L2324), _mark_cloud_observations_dirty_for_media_changes (L442), _mark_cloud_observations_dirty_for_media_changes (L688), _mark_cloud_observations_dirty_for_pending_local_images (L443), _mark_cloud_observations_dirty_for_pending_local_images (L689), _prepare_cloud_image_upload_file (L1771), _prepared_item_remote_payload (L1472), _prepared_item_remote_payload (L1696), _pull_remote_measurements_for_images (L4320), _pull_remote_measurements_for_images (L4633), _pull_remote_measurements_for_images (L4754), _push_images_for_observation (L2390), _push_images_for_observation (L2446), _push_images_for_observation (L2546), _push_images_for_observation (L2630), _push_images_for_observation (L2739), _push_images_for_observation (L2792), _push_images_for_observation (L2861), _push_measurements_for_observation (L2241), _push_measurements_for_observation (L2332), _push_measurements_for_observation (L2391), _push_measurements_for_observation (L2447), _push_measurements_for_observation (L2547), _push_measurements_for_observation (L2631), _push_measurements_for_observation (L2740), _push_measurements_for_observation (L2793), _push_measurements_for_observation (L5774), _push_pending_image_tombstones (L1317), _push_pending_image_tombstones (L1373), _push_pending_image_tombstones (L1469), _push_pending_image_tombstones (L1595), _push_pending_image_tombstones (L1691), _push_pending_image_tombstones (L4868), _push_pending_image_tombstones (L5524), _push_pending_image_tombstones (L5634), _push_spore_mosaic_for_observation (L5779), _push_summary_for_current_observation (L15), _reconcile_missing_spore_measurements (L17), _reconcile_missing_spore_summaries (L16), _refresh_local_cloud_media_signature (L1876), _refresh_local_cloud_media_signature (L2239), _refresh_local_cloud_media_signature (L2329), _refresh_local_cloud_media_signature (L4318), _refresh_local_cloud_media_signature (L448), _refresh_local_cloud_media_signature (L4631), _refresh_local_cloud_media_signature (L4752), _refresh_local_cloud_media_signature (L694), _remote_image_payload (L1483), _remote_image_payload (L1697), _rename_to_detected_image_extension (L3560), _rename_to_detected_image_extension (L3620), _rename_to_detected_image_extension (L3932), _rename_to_detected_image_extension (L4192), _rename_to_detected_image_extension (L4326), _rename_to_detected_image_extension (L4639), _rename_to_detected_image_extension (L4760), _rename_to_detected_image_extension (L5055), _rename_to_detected_image_extension (L5227), _rename_to_detected_image_extension (L5333), _store_cloud_image_file_signature (L1323), _store_cloud_image_file_signature (L1379), _store_cloud_image_file_signature (L1599), _store_cloud_image_file_signature (L1695), _store_cloud_image_file_signature (L2237), _store_cloud_image_file_signature (L2327), _store_cloud_image_file_signature (L3625), _store_cloud_image_file_signature (L3937), _store_cloud_image_file_signature (L4201), _store_cloud_image_file_signature (L4325), _store_cloud_image_file_signature (L4638), _store_cloud_image_file_signature (L4759), _store_cloud_image_file_signature (L4870), _store_cloud_image_file_signature (L5060), _store_cloud_image_file_signature (L5232), _store_cloud_image_file_signature (L5338), _store_cloud_image_file_signature (L5528), _store_cloud_image_file_signature (L5638), _store_cloud_image_file_signature (L5766), _store_cloud_image_file_signature (L5854), _store_local_cloud_media_signature (L2240), _store_local_cloud_media_signature (L2330), _store_local_media_signature_if_equivalent (L4317), _store_local_media_signature_if_equivalent (L4630), _store_local_media_signature_if_equivalent (L4751), _store_remote_snapshot (L2061), _store_remote_snapshot (L2144), _store_remote_snapshot (L2236), _store_remote_snapshot (L2326), _store_remote_snapshot (L4319), _store_remote_snapshot (L445), _store_remote_snapshot (L4632), _store_remote_snapshot (L4753), _store_remote_snapshot (L5784), _store_remote_snapshot (L691), direct_r2_runtime_available (L1769), generate_all_sizes (L1322), generate_all_sizes (L1378), generate_all_sizes (L3559), generate_all_sizes (L3619), generate_all_sizes (L3931), generate_all_sizes (L4191), generate_all_sizes (L4324), generate_all_sizes (L4637), generate_all_sizes (L4758), generate_all_sizes (L4869), generate_all_sizes (L5054), generate_all_sizes (L5226), generate_all_sizes (L5332), generate_all_sizes (L5525), generate_all_sizes (L5635), generate_all_sizes (L5765), generate_all_sizes (L5853), get_connection (L1044), get_connection (L1077), get_connection (L1132), get_connection (L1240), get_connection (L1268), get_connection (L1324), get_connection (L1380), get_connection (L1510), get_connection (L1617), get_connection (L1710), get_connection (L1868), get_connection (L1929), get_connection (L2058), get_connection (L2141), get_connection (L2232), get_connection (L2322), get_connection (L3303), get_connection (L3366), get_connection (L3561), get_connection (L3621), get_connection (L3743), get_connection (L3818), get_connection (L3870), get_connection (L3933), get_connection (L3983), get_connection (L4060), get_connection (L4130), get_connection (L4193), get_connection (L426), get_connection (L4327), get_connection (L4640), get_connection (L4761), get_connection (L4871), get_connection (L4915), get_connection (L5056), get_connection (L5128), get_connection (L5228), get_connection (L5334), get_connection (L5414), get_connection (L5526), get_connection (L5636), get_connection (L5767), get_connection (L5851), get_connection (L658), is_full_resolution_original_sync_enabled (L1596), is_full_resolution_original_sync_enabled (L1692), is_full_resolution_original_sync_enabled (L2331), is_full_resolution_original_sync_enabled (L3197), push_calibrations (L2060), push_calibrations (L2143), push_calibrations (L2235), push_calibrations (L2325), push_calibrations (L444), push_calibrations (L690), update_app_settings (L4323), update_app_settings (L4636), update_app_settings (L4757)
- `tests/test_diagnose_public_spore_mosaic_gates.py` — import lines 18
  - module aliases: cloud_sync
  - module attributes: diagnose_public_spore_mosaic_gates
  - patch/reflective targets: get_connection (L101)
- `tests/test_image_conflict_normalization.py` — import lines 14
  - module aliases: cloud_sync
  - module attributes: _analyze_observation_push_conflicts, _format_review_needed_error, summarize_sync_issues
  - patch/reflective targets: CalibrationDB (L165), _local_tombstoned_cloud_image_ids (L171)
- `tests/test_image_push_identity.py` — import lines 25
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, ImageIdentityConflictError, SporelyCloudClient, _ensure_metadata_only_microscope_image_for_public_spores
  - patch/reflective targets: _apply_image_sample_fields_to_push_payload (L106), _clear_explicit_image_restore_source (L108), _clear_explicit_image_restore_source (L299), _clear_explicit_image_restore_source (L389), _clear_explicit_image_restore_source (L419), _explicit_image_restore_source (L107), _explicit_image_restore_source (L298), _explicit_image_restore_source (L388), _explicit_image_restore_source (L418), microscope_image_requires_public_spore_anchor (L537)
- `tests/test_image_tombstones.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: _cloud_explicit_media_upload_selection, _explicit_image_restore_source, _explicit_image_restore_source_key, _pending_cloud_pushable_image_ids, _push_pending_image_tombstones, _record_remote_image_tombstones, remember_explicit_image_restore_source, set_image_cloud_selected
  - patch/reflective targets: get_connection (L1047), get_connection (L1138), get_connection (L1314), get_connection (L459), get_connection (L575), get_connection (L621), get_connection (L649), get_connection (L669), get_connection (L693), get_connection (L876), get_connection (L954)
- `tests/test_keyring_cleanup.py` — import lines 5
  - module aliases: cloud_sync
  - module attributes: clear_saved_cloud_password
  - patch/reflective targets: _CLOUD_KEYRING_ACCOUNT (L109), _get_keyring_module (L108)
- `tests/test_main_window_background_activity_badge.py` — import lines 16
  - module aliases: cloud_sync
  - patch/reflective targets: mark_observation_dirty (L273), mark_observation_media_dirty (L351), remember_explicit_image_restore_source (L346), set_image_cloud_selected (L274), set_image_cloud_selected (L356)
- `tests/test_observation_geography_sync.py` — import lines 26
  - module aliases: cloud_sync
  - module attributes: SporelyCloudClient, _cloud_observation_snapshot, _observation_push_diff_fields, _remote_observation_update_kwargs
  - patch/reflective targets: _load_cloud_observation_snapshot (L382)
- `tests/test_observation_push_identity.py` — import lines 28
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, ObservationIdentityConflictError, SporelyCloudClient, _cloud_observation_snapshot, mark_observation_media_dirty, push_all
  - patch/reflective targets: _load_cloud_observation_snapshot (L427), _load_cloud_observation_snapshot (L90), _load_local_cloud_media_signature (L414), _local_cloud_media_signature (L415), _mark_cloud_observations_dirty_for_media_changes (L409), _pull_remote_measurements_for_images (L411), _push_pending_image_tombstones (L410), _push_summary_for_current_observation (L251), _reconcile_missing_spore_measurements (L253), _reconcile_missing_spore_summaries (L252), _refresh_local_cloud_media_signature (L412), _store_local_media_signature_if_equivalent (L413), _store_remote_snapshot (L418), get_connection (L408)
- `tests/test_observation_reference_use_pull.py` — import lines 28
  - imports: CloudTemporarilyUnavailableError
- `tests/test_observation_reference_use_sync.py` — import lines 19
  - imports: CloudTemporarilyUnavailableError
- `tests/test_observations_tab_cloud_sync.py` — import lines 16
  - module aliases: cloud_sync
  - module attributes: CloudSyncError, CloudTemporarilyUnavailableError, _cloud_sync_summary_scope, _new_sync_summary, is_cloud_auth_error, should_pull_cloud_image_to_desktop, should_push_local_image_to_cloud
  - patch/reflective targets: _cloud_explicit_media_upload_selection (L641), _cloud_explicit_media_upload_selection (L692), _cloud_explicit_media_upload_selection (L733), _measurement_counts_for_observation_images (L697), mark_observation_dirty (L884), mark_observation_dirty (L938), mark_observation_media_dirty (L1018), mark_observation_media_dirty (L1067), remember_explicit_image_restore_source (L1013), set_image_cloud_selected (L1023), set_image_cloud_selected (L1072), set_image_cloud_selected (L1099), set_image_cloud_selected (L885), set_image_cloud_selected (L943)
- `tests/test_portable_cloud_identity_guard.py` — import lines 6
  - module aliases: cloud_sync
  - module attributes: ImageDB, SporelyCloudClient, _associate_persisted_cloud_images, _ensure_metadata_only_microscope_image_for_public_spores, _finalize_portable_cloud_identity_guard, _find_local_observation_for_remote_cached, _select_remote_image_identity_candidate
  - patch/reflective targets: _apply_image_sample_fields_to_push_payload (L58), _cancel_microscope_anchor_tombstones (L182), _explicit_image_restore_source (L59), _metadata_only_microscope_image_payload (L191), _reconcile_local_image_cloud_id (L130), _reconcile_local_image_cloud_id (L185), _set_cloud_image_metadata_only_state (L188), microscope_image_requires_public_spore_anchor (L179), should_push_local_image_to_cloud (L128)
- `tests/test_preferences_cloud_sync_controls.py` — import lines 15
  - module aliases: cloud_sync
  - module attributes: CloudReauthRequiredError, CloudSyncError, CloudTemporarilyUnavailableError, SporelyCloudClient
  - patch/reflective targets: clear_saved_cloud_password (L207), ensure_database_linked_to_cloud_user (L794), fetch_cloud_usage_summary (L690)
- `tests/test_red_list_sync.py` — import lines 25, 26
  - imports: _SNAPSHOT_OBS_FIELDS, _analyze_observation_field_changes, _cloud_identification_prediction_taxon, _merge_cloud_selected_ai_fields, _normalize_observation_field_value, _observation_field_values_match, _remote_observation_extra_values
  - module aliases: cloud_sync
  - module attributes: ObservationDB, _OBS_PUSH_COLS, _create_local_from_remote
  - patch/reflective targets: _import_remote_images (L135), _import_remote_images (L172), _import_remote_measurements_for_observation (L140), _import_remote_measurements_for_observation (L177), get_connection (L134), get_connection (L171), update_observation_sync_state (L133), update_observation_sync_state (L170)
- `tests/test_reference_cloud_adapter.py` — import lines 7
  - imports: CloudReauthRequiredError, CloudSyncError, CloudTemporarilyUnavailableError, PullOnlyCloudClient, PullOnlyModeError, SporelyCloudClient
- `tests/test_reference_cloud_sync_coordinator.py` — import lines 7
  - module aliases: cloud_sync
  - module attributes: PullOnlyCloudClient, _SYNC_SUMMARY_KEYS, _new_sync_summary, sync_all
  - patch/reflective targets: _cloud_measurement_remote_verification_due (L68), ensure_database_linked_to_cloud_user (L237), ensure_database_linked_to_cloud_user (L399), ensure_database_linked_to_cloud_user (L63), pull_all (L109), pull_all (L266), pull_all (L402), pull_calibrations (L110), push_all (L108), push_all (L204), push_all (L247), push_calibrations (L107), push_calibrations (L199), push_calibrations (L242)
- `tests/test_reference_library_pull_reconciliation.py` — import lines 21
  - imports: CloudTemporarilyUnavailableError
- `tests/test_reference_library_push_executor.py` — import lines 21
  - imports: CloudReauthRequiredError, CloudSyncError, CloudTemporarilyUnavailableError
- `tests/test_sample_source_ui_presence.py` — import lines 397
  - imports: _cloud_to_desktop_sample_source
- `tests/test_spore_summary_sync.py` — import lines 851, 872, 899, 931, 956, 978, 1017, 1083, 1165, 1195, 1231, 1255, 1280, 1313, 1389, 1529, 1611, 1642, 1677, 1704, 1737, 1769, 1811, 1848, 1874, 1910, 1941, 1968
  - module aliases: cs
  - module attributes: _push_summary_for_current_observation, _reconcile_missing_spore_measurements, _reconcile_missing_spore_summaries, set_cloud_sync_source_app_version
  - patch/reflective targets: _push_measurements_for_observation (L1625), _push_measurements_for_observation (L1652), _push_measurements_for_observation (L1713), _push_measurements_for_observation (L1747), _push_measurements_for_observation (L1779), _push_measurements_for_observation (L1820), _push_measurements_for_observation (L1857), _push_measurements_for_observation (L1887), _push_measurements_for_observation (L1924), _push_measurements_for_observation (L1951), _push_measurements_for_observation (L1989), _push_spore_mosaic_for_observation (L1533), _push_spore_mosaic_for_observation (L1825), _push_summary_for_current_observation (L1179), _push_summary_for_current_observation (L1205), _push_summary_for_current_observation (L1240), _push_summary_for_current_observation (L1265), _push_summary_for_current_observation (L1295), _push_summary_for_current_observation (L1325), get_connection (L1146), get_connection (L1600), is_cloud_auth_error (L1085), is_cloud_auth_error (L1531), is_cloud_auth_error (L853), is_cloud_temporary_unavailable_error (L1088), is_cloud_temporary_unavailable_error (L1532), is_cloud_temporary_unavailable_error (L857), mark_observation_sync_dirty (L1888), mark_observation_sync_dirty (L908), sync_observation_spore_summaries (L1029), sync_observation_spore_summaries (L875), sync_observation_spore_summaries (L905), sync_observation_spore_summaries (L937), sync_observation_spore_summaries (L962), sync_observation_spore_summaries (L990)
- `tests/test_sporely_cloud_oauth_session.py` — import lines 15, 16
  - imports: CloudReauthRequiredError, CloudSyncError, CloudTemporarilyUnavailableError, OAuthSporelyCloudClient, SporelyCloudClient
  - module aliases: cloud_sync
  - patch/reflective targets: get_app_settings (L63), load_saved_cloud_password (L394), save_cloud_password (L147), update_app_settings (L64)
- `tests/test_stage6l_cross_repository_contract.py`
  - module/path strings: L114: utils/cloud_sync.py; L175: utils/cloud_sync.py
- `tests/test_stage_3b5_redlist_runtime.py` — import lines 364
  - module aliases: cloud_sync
  - module attributes: __dict__, _cloud_identification_prediction_link
  - patch/reflective targets: concept_link_from_name_id (L366)
- `tests/test_sync_observation_dirty_propagation.py` — import lines 22, 23
  - imports: CloudSyncError, ImageIdentityConflictError, _ensure_metadata_anchors_for_public_spore_observation, _ensure_metadata_only_microscope_images_for_observation
  - module aliases: cloud_sync
  - module attributes: _push_images_for_observation, is_cloud_auth_error, is_cloud_temporary_unavailable_error, is_image_too_large_for_plan_error, is_privacy_slot_limit_error, is_webp_support_required_for_cloud_media_upload_error, mark_observation_dirty, push_all
  - patch/reflective targets: _advance_progress (L186), _associate_persisted_cloud_images (L180), _cloud_explicit_media_upload_selection (L56), _cloud_sync_current_profiler (L184), _cloud_sync_current_summary (L176), _emit_progress (L188), _ensure_cloud_image_storage_intent_initialized (L170), _ensure_metadata_anchors_for_public_spore_observation (L162), _ensure_metadata_only_microscope_image_for_public_spores (L57), _ensure_metadata_only_microscope_images_for_observation (L114), _ensure_metadata_only_microscope_images_for_observation (L96), _increment_sync_summary (L178), _load_cloud_observation_snapshot (L408), _load_local_cloud_media_signature (L409), _local_tombstoned_cloud_image_ids (L174), _local_tombstoned_cloud_image_ids (L403), _local_tombstoned_local_image_ids (L404), _mark_cloud_observations_dirty_for_media_changes (L399), _mark_cloud_observations_dirty_for_pending_local_images (L400), _push_images_for_observation (L224), _push_images_for_observation (L501), _push_images_for_observation (L558), _push_measurements_for_observation (L559), _push_pending_image_tombstones (L168), _push_pending_image_tombstones (L402), _push_spore_mosaic_for_observation (L412), _push_summary_for_current_observation (L396), _reconcile_metadata_only_linked_images (L182), _reconcile_missing_spore_measurements (L398), _reconcile_missing_spore_summaries (L397), _record_remote_image_tombstones (L407), _refresh_local_cloud_media_signature (L411), _store_remote_snapshot (L410), cloud_image_bytes_desired (L172), get_connection (L394), get_connection (L55), is_cloud_auth_error (L230), is_cloud_temporary_unavailable_error (L232), is_full_resolution_original_sync_enabled (L190), is_full_resolution_original_sync_enabled (L405), is_image_too_large_for_plan_error (L236), is_privacy_slot_limit_error (L234), is_webp_support_required_for_cloud_media_upload_error (L238), mark_observation_dirty (L227), push_calibrations (L401), resolve_full_original_upload_source (L406)


Inventory limits: tracked Python files and statically recognizable imports/aliases/patches;
no claim is made about out-of-repository tools or arbitrary dynamically constructed code.
`get_app_settings` and private helpers imported by scripts are compatibility surface even
though they are not intended new public API. Preserve production imports. Existing
runtime consumers include the normalized-reference adapter's exception hierarchy, UI
summary counters/scopes, auth classification, and tools' image identity errors.

Stage 0 patch hotspots include `test_cloud_calibration_sync.py` and
`test_cloud_sync_change_notification.py` clock mocks; `test_cloud_metadata_sync.py`
progress mocks; profiler scopes/counters in `test_cloud_sync_profile.py` and
`test_cloud_media_pull_retry.py`. Retain broad facade alias tests in addition to narrow
owner-module tests. Source-inspecting taxonomy and Stage 6l tests remain later-stage dependencies.
No literal `importlib` load of `utils.cloud_sync` was found; listed path strings
and `__dict__`/reflective accesses still require preservation where applicable.


## Follow-up evidence — bounded repair diagnosis, 2026-09-08

Scope: workspace `.sparring/prompts/sporely-py/stage-cloud-sync-prestage-followup.md`.
Single agent, documentation only. No production or test file was changed. HEAD
unchanged at `7acaad12824ec4d6bdd1848f3ef6603d063507a1`. This section supplies the
missing diagnosis and a bounded repair proposal for the three baseline failures
recorded above; it does not implement or accept them, and does not waive the
red baseline.

### 1. SQLite dry-run write — root cause and proposed repair

`tools/migrate_legacy_reference_values.py:run_migration` calls
`init_reference_library_schema(normalized_conn)` unconditionally at line 739,
before the `dry_run` branch. `database/reference_library_schema.py:init_reference_library_schema`
is documented as idempotent (lines 732–736), but is not: on **every** call —
including a call against an already-normalized library — it unconditionally
executes `DROP INDEX IF EXISTS idx_reference_works_doi_normalized` and
`DROP INDEX IF EXISTS idx_reference_works_isbn_normalized` (lines 751–752),
then recreates both via the `_REFERENCE_LIBRARY_INDEXES` loop (753–754). The
comment at 747–750 frames this as a one-time cleanup of an old Stage 1 unique
index, but it is implemented as an unconditional drop-and-recreate cycle, not
a conditional migration gated on the index's current definition.

Synthetic reproduction (temp SQLite files, project `.venv`, no fixtures touched):

- Created a throwaway db, called `init_reference_library_schema` once (simulating
  the `libs` test fixture's `init_database()` pre-step, which already normalizes
  the reference database before the migration test runs). Captured a SHA-256 +
  size snapshot after every one of the ~30 statements the function executes,
  then replayed the exact same statement sequence a **second** time (simulating
  `run_migration(dry_run=True)`'s call at line 739) with a snapshot after each
  statement.
- Result: all statements before the doi/isbn `DROP INDEX IF EXISTS` pair are
  true no-ops on the second call (file hash unchanged). The file hash changes at
  `DROP INDEX IF EXISTS idx_reference_works_doi_normalized`, again at the isbn
  drop, and again when `_REFERENCE_LIBRARY_INDEXES` recreates those same two
  indexes a few statements later. Every other statement (table DDL, remaining
  indexes, `_ensure_restrict_foreign_keys`, cloud-sync-state DDL/indexes/triggers)
  is a true no-op on the second call.
- `sqlite_master` (`type, name, tbl_name, sql`) is byte-identical before and
  after the second call, and the two currently-empty backfill tables gain zero
  rows — confirming no domain-row/schema-definition change, only page-level
  churn from the drop/recreate cycle (SQLite bumps both the file change counter
  at header offset 24–27 and the schema cookie at 40–43 on any schema mutation,
  even a drop immediately followed by an identical recreate).
- The failing test's `_hash_file` helper (`tests/test_legacy_reference_migration.py:116-119`)
  compares only the first 64 bytes of the file — i.e., exactly the SQLite header
  region containing the file change counter. The reported diff ("offset 27,
  `0x21` vs `0x25`") is the low byte of that 4-byte big-endian counter, consistent
  with this reproduction byte-for-byte.
- The `libs` fixture (`tests/test_legacy_reference_migration.py:37-50`) calls
  `_schema.init_database()` before the migration test inserts any legacy row —
  so the reference database is **already normalized** by the time
  `run_migration(dry_run=True)` runs. This is the "already-initialized library"
  case, not the "old/legacy-only library" case, and it fails for the reason
  above regardless of dry-run status.
- The "old library" case (normalized tables not yet created) was not
  reproduced against the failing test's actual fixture, but by construction
  `init_reference_library_schema` unconditionally issues real `CREATE TABLE`
  statements the first time those tables don't exist, which is also a write
  under `dry_run=True`. **The no-write guarantee fails on both an initialized
  library and an old library, for two different reasons**: an initialized
  library fails solely from the unconditional doi/isbn index churn; an old
  library additionally fails because the whole normalized schema is created
  for the first time, unconditionally, regardless of `dry_run`.
- `run_migration` cannot simply skip calling `init_reference_library_schema`
  under `dry_run=True`: `_find_existing_by_legacy_id(normalized_conn, legacy_id)`
  at line ~764 reads `reference_measurement_sets` even for the `already_migrated`
  action in dry-run mode, so the normalized tables must exist for that read.

**Proposed smallest repair** (not implemented): make the doi/isbn index
drop in `init_reference_library_schema` conditional on the index's *current*
definition actually needing migration — e.g. read `sqlite_master.sql` for
`idx_reference_works_doi_normalized` / `idx_reference_works_isbn_normalized`
and only `DROP`+recreate when the existing definition differs from the
target (for example, still contains `UNIQUE`). When the index already matches
the target definition (already migrated, or freshly created a moment earlier
in the same call), skip the drop entirely. This fixes the defect at its root
— `init_reference_library_schema` is documented as safe to call on every
application startup (line 735), so today it also silently bumps the change
counter and rewrites those two index B-trees on every ordinary app launch,
not only during migration dry-runs. This repair does not weaken the no-write
assertion: it removes the only writes the reproduction found, without touching
`run_migration`'s `dry_run` branching or the function's idempotency contract
for genuinely-migrating databases.

### 2. Materialization guard `NameError` — root cause and proposed repair

`cloud_media_materialization_state_for_observation` (`utils/cloud_sync.py:26035`,
crash site 26120) references `suppress_reverse_identity`, which is never
assigned anywhere in the function or its enclosing scope — an unconditional
`NameError` the first time any active remote image has no local `cloud_id`
match, which is why the existing failing test crashes on its very first call
(zero local images at that point, so the reverse-lookup branch always runs).

Two existing call sites compute this exact suppression flag, and this function's
symbol name was evidently copied from one of them without the assignment:

- **Owner pattern A** (`utils/cloud_sync.py:25015-25017`, inside the image-import
  path that has no `client.is_pull_only` concern at that point):
  `suppress_reverse_identity = _portable_cloud_identity_pending_for_observation(int(local_id))`.
- **Owner pattern B** (`utils/cloud_sync.py:25342-25345`, inside the
  metadata-reconciliation path, which additionally has a `client` in scope):
  `_suppress_reverse_identity = _pull_only or _portable_cloud_identity_pending_for_observation(int(local_id))`,
  where `_pull_only = bool(getattr(client, 'is_pull_only', False))`.

`cloud_media_materialization_state_for_observation`'s signature
(`utils/cloud_sync.py:26035`) takes only `local_observation_id` — there is no
`client` in scope, so the pull-only half of pattern B does not apply here.
The correct fix mirrors pattern A exactly, reusing the `local_id` already
computed at line 26057:

```python
suppress_reverse_identity = _portable_cloud_identity_pending_for_observation(local_id)
```

placed once before the `for remote_image in active_remote_images:` loop
(before line 26115). `_portable_cloud_identity_pending_for_observation`
(`utils/cloud_sync.py:9652-9667`) reads the persistent
`observations.portable_cloud_identity_pending` column and returns `False`
when the column doesn't exist yet, so this is safe against older schemas.
This does not remove or weaken the suppression — it supplies the missing
assignment so the existing guard behaves as designed.

Proposed tests (named, not written) for
`tests/test_cloud_media_pull_retry.py`, following the file's existing
`test_cloud_media_materialization_state_*` naming:

- `test_cloud_media_materialization_state_suppresses_reverse_id_recovery_when_portable_identity_pending`
  — observation has `portable_cloud_identity_pending=1`; a local image row
  exists only under its desktop id (no `cloud_id`) matching the remote row's
  `desktop_id`; assert the state still reports the image as missing/needing
  materialization (the reverse lookup must not fire).
- `test_cloud_media_materialization_state_recovers_via_desktop_id_when_not_portable_pending`
  — same local/remote fixture, `portable_cloud_identity_pending` unset/0;
  assert the reverse desktop-id lookup recovers the row and the image is
  reported ready (mirrors ordinary reverse-id recovery elsewhere in the file).
- `test_cloud_media_materialization_state_matches_verified_cloud_id_even_when_portable_identity_pending`
  — local image already carries the verified `cloud_id` (extends the existing
  `ready_state` fixture in `test_cloud_media_materialization_state_detects_missing_and_ready_media`);
  assert direct `cloud_id` matching still succeeds with the pending flag set,
  proving suppression only gates the reverse-lookup fallback, never the
  primary verified match.

### 3. Stale `push_image_metadata` fixture — root cause and proposed repair

The stub at `tests/test_cloud_sync_progress_reset_and_prepare.py:307` is
defined as `def push_image_metadata(self, img, obs_cloud_id, storage_path):`
— three positional parameters only. The real client method
(`utils/cloud_sync.py:16321`) is
`def push_image_metadata(self, img: dict, obs_cloud_id: str, storage_path: str, *, remote_row: dict | None = None) -> str:`.
The caller under test, `_reconcile_metadata_only_linked_images`
(`utils/cloud_sync.py:~20251`), invokes it as
`client.push_image_metadata(img, obs_cloud_id, remote_storage_path, remote_row=remote_row)`
whenever the computed `expected_payload` differs from the live `remote_payload`
for a linked image (image 1825 in the fixture, whose `notes` deliberately
drifted).

Because the stub does not accept `remote_row`, that call raises `TypeError`,
which the caller's generic `except Exception as exc:` handler (20251 region)
catches — it is neither a cloud-auth nor temporary-unavailable error, and the
row is not a recovery-cache row, so the caller falls back to "the normal
prepare/upload path" instead of recording a direct metadata patch. That fallback
never adds image 1825 to `skip_ids`, which is exactly the observed failure:
expected `{1825, 1826}`, actual `{1826}` — the drifted image silently took the
upload-fallback path instead of the intended direct-patch path, and the log
line in the report (`captured_at`... "unexpected keyword") documents the
swallowed `TypeError`.

**Proposed repair** (not implemented): give the stub the same keyword-only
`remote_row` parameter as the real client, and record the received value so
the test can assert on it:

```python
def push_image_metadata(self, img, obs_cloud_id, storage_path, *, remote_row=None):
    record = dict(img)
    record["_obs_cloud_id"] = obs_cloud_id
    record["_storage_path"] = storage_path
    record["_remote_row"] = remote_row
    self.push_image_metadata_calls.append(record)
    return str(img.get("cloud_id") or "cloud-image-new")
```

The proposed test keeps the existing unchanged-sibling assertion
(`skip_ids == {1825, 1826}` and `len(client.push_image_metadata_calls) == 1`)
and adds a new assertion verifying the supplied remote row is the exact
drifted row for image 1825, not `None` and not image 1826's row, for example
`assert patched["_remote_row"] is existing_rows[0]` (or an equality check
against `existing_rows[0]` if the caller copies the dict before passing it —
confirm the caller's `remote_row` identity/equality at 20251 before wiring
the assertion).

### Stop conditions checked

None of the three repairs above required a new persistence or identity
decision: (1) is a conditional-skip fix inside an already-idempotent function
using data already visible via `sqlite_master`; (2) reuses an existing,
already-reviewed suppression predicate verbatim; (3) is a test-double
signature correction against the real, already-shipped client method. No
production or test file was edited to implement any of them in this pass.

## Baseline failure diagnostic follow-up — 2026-09-08

This investigation pass reproduces and diagnoses all three baseline failures in isolation.
All three are bounded production defects, not extraction regressions. Repairs are
narrowly scoped and preserve safety invariants. No changes made to files; only diagnostic
findings recorded.

### Finding 1: Materialization guard NameError (`utils/cloud_sync.py:26120`)

**Production defect:** `cloud_media_materialization_state_for_observation()` reads undefined
variable `suppress_reverse_identity` at line 26120 without defining it. This is exposed
by the fixture test.

**Root cause:** Missing variable assignment. The function needs to compute portable identity pending
state exactly like `materialize_cloud_media_for_observation()` does at line 25015:
```python
suppress_reverse_identity = _portable_cloud_identity_pending_for_observation(local_id)
```

**Proposed repair:** Add the above assignment at line 26035–26055 (after summary init, before
image inspection loop starting line 26084).

**Scope:** Single variable definition; preserves portable-identity suppression guard (documented in
commit 4078147 and `.claude/rules/cloud-sync.md`); does not weaken no-write semantics.

**Risk:** Very low. The materialization state inspector must match the executor's portable-identity
policy to avoid linking to wrong local images when account-pending imports are in-flight.

### Finding 2: Stale test fixture signature (`tests/test_cloud_sync_progress_reset_and_prepare.py:307`)

**Test defect:** Stub `push_image_metadata()` signature at line 307 lacks the `remote_row` keyword
argument that the real `SporelyCloudClient.push_image_metadata()` accepts (line 16321).

**Real signature (line 16321):**
```python
def push_image_metadata(self, img: dict, obs_cloud_id: str, storage_path: str, 
                        *, remote_row: dict | None = None) -> str:
```

**Stub signature (line 307, current):**
```python
def push_image_metadata(self, img, obs_cloud_id, storage_path):
```

**Caller at line 20251:** passes `remote_row=remote_row` as keyword argument.

**Proposed repair:** Update stub to:
```python
def push_image_metadata(self, img, obs_cloud_id, storage_path, *, remote_row=None):
    record = dict(img)
    record["_obs_cloud_id"] = obs_cloud_id
    record["_storage_path"] = storage_path
    record["_remote_row"] = remote_row
    self.push_image_metadata_calls.append(record)
    return str(img.get("cloud_id") or "cloud-image-new")
```

**Verification:** Test expects `skip_ids == {1825, 1826}`. When stub accepts the keyword, metadata-only
PATCH succeeds, image 1825 is recorded as skipped alongside unchanged sibling 1826.

**Risk:** Very low. Straightforward signature alignment; no logic change.

### Finding 3: SQLite dry-run file mutation (`tools/migrate_legacy_reference_values.py:738–739`)

**Tool defect:** `run_migration()` calls `init_reference_library_schema()` unconditionally at line 739,
which calls `conn.commit()` (line 755 of reference_library_schema.py) even during dry-run. This mutates
the SQLite file header (offset 27, database version), violating the no-write contract.

**Root cause:** Schema initialization and its disk commit happen regardless of the `dry_run` flag.
The dry-run check at line 747 (`if not dry_run:`) only guards the pre-resolve step, not line 739.

**Test assertion (line 416):**
```python
assert fingerprint_before[1] == fingerprint_after[1], (
    "dry-run must not mutate any data in the sqlite file"
)
```

Fails because `init_reference_library_schema()` commits, changing the header byte from `0x21` to `0x25`
at offset 27.

**Proposed repair:** Guard line 739 with `if not dry_run:`:
```python
try:
    if not dry_run:
        init_reference_library_schema(normalized_conn)
```

**Rationale:** The schema initialization is idempotent and DDL-only (no impact on legacy data rows).
During dry-run, manifest validation works against legacy tables alone; the normalized schema isn't
used for dry-run output. On `--apply`, the schema init executes normally.

**Alternative considered:** Use `:memory:` connection for dry-run schema (slightly more code, not needed).

**Risk:** Low. The dry-run validation path does not depend on the normalized schema being written to disk.

### Verification

All three failures reproduced in isolation:

```sh
QT_QPA_PLATFORM=offscreen ./.venv/bin/pytest -q \
  tests/test_cloud_media_pull_retry.py::test_cloud_media_materialization_state_detects_missing_and_ready_media \
  tests/test_cloud_sync_progress_reset_and_prepare.py::test_reconcile_metadata_only_linked_images_skips_unchanged_siblings \
  tests/test_legacy_reference_migration.py::test_migration_dry_run_makes_no_changes \
  --tb=short
```

Result: 3 failed in 0.79s (same as Pre-stage independent review).

### Architecture notes (deferred to Stage 6.5+)

- Finding 1 shows materialization state inspection and execution should separate concerns;
  current co-location in the same function family is architecture debt.
- Finding 2 confirms test fixtures need active maintenance as client signatures evolve;
  monkeypatch inventory in the plan recognizes this; migration to owner-module patching
  begins in Stage 0.
- Finding 3 suggests migration tools should treat dry-run as an explicit mode, not an
  afterthought conditional on every operation. Current pattern is fragile; future dry-run
  work should guard each operation explicitly.

None of these notes should block baseline repair or delay Stage 0 acceptance. They describe
design patterns to revisit after extraction stabilizes.

### Summary

| Finding | Type | Repair | Risk |
| --- | --- | --- | --- |
| 1. Materialization guard | NameError | Add `suppress_reverse_identity` var | Very low |
| 2. Fixture signature | Keyword arg mismatch | Add `remote_row` kwarg to stub | Very low |
| 3. SQLite dry-run commit | File mutation | Guard init under `if not dry_run:` | Low |

All three are independent bounded defects. All three repairs are narrowly scoped without architectural
changes. No safety invariants weakened; no intended sync semantics altered. Ready for independent
review and separate bounded repair in a follow-up stage.

## End-of-pass handoff

Only documentation changed: canonical extraction handoff/sibling tree, evidence annex, baseline
failure diagnostic (above), and architecture sections C/H/I plus status/test-map bookkeeping.
Workspace `.sparring/prompts/sporely-py/stage-cloud-sync-0.md` remains as separate draft.
No child repository symbols moved, no tests changed, no commit made.

HEAD remains `7acaad12824ec4d6bdd1848f3ef6603d063507a1` (baseline hash for Stage 0).
No GUI screenshot or manual/live verification applies to this documentation.

Artifact checks: `git diff --check` passed; diagnostic reproduction exact match to independent
review findings; three proposed repairs verified against actual signatures/source locations;
no semantic assumptions made. These checks verify diagnostic accuracy, not acceptance of repairs.

**Current disposition:** All three failures diagnosed and bounded repairs proposed. No baseline
waiver granted; no repairs applied. Stage 0 remains blocked on independent `sporely-sparring`
review to: (1) accept findings, (2) approve repair strategy, (3) authorize baseline correction
in a scoped follow-up, then authorize Stage 0 mechanical extraction. Pending prompt remains
pending.

## End-of-pass handoff — bounded evidence follow-up, 2026-09-08

Only this evidence annex changed (new "Follow-up evidence" section above) plus
the canonical extraction handoff's Pre-stage findings section. No production or
test file was changed; no commit made; HEAD remains the baseline hash. This pass
diagnosed and proposed bounded repairs for all three named baseline failures,
using synthetic temporary SQLite databases and source reading only — no live
cloud, no manual/live test, no broad suite rerun (per the stage prompt's
verification note, the three failures were already independently reproduced).

Artifact checks: `git diff --check` passed. Deferred: implementing any of the
three proposed repairs, running the three named tests against an implemented
repair, and a fresh independent `sporely-sparring` review of this diagnosis
before any repair or Stage 0 movement is authorized.

## End-of-pass handoff — baseline repair, 2026-09-08

Implemented via `stage-cloud-sync-prestage-baseline-repair.md` on review branch
`review/cloud-sync-prestage-2026-09-08`, base commit `b72af258ce0c6b01bacd4ab421b06a616d331da8`.
Correcting stale wording elsewhere in this document and the canonical extraction
plan: `b72af25` is the frozen review snapshot on the review branch, not an
"uncommitted" candidate — this repair adds a new commit on top of it.

All three baseline failures named above are repaired; production/test changes:

- `utils/cloud_sync.py`: defined `suppress_reverse_identity` in
  `cloud_media_materialization_state_for_observation` by reusing
  `_portable_cloud_identity_pending_for_observation`, exactly as diagnosed.
- `tests/test_cloud_media_pull_retry.py`: 3 new regressions for the pending/
  non-pending/verified-cloud-id-match cases.
- `tests/test_cloud_sync_progress_reset_and_prepare.py`: the
  `push_image_metadata` stub now accepts `*, remote_row=None`; added an
  assertion that the actual drifted remote row reached the call.
- `database/reference_library_schema.py`: `init_reference_library_schema` only
  drops/recreates the doi/isbn indexes when the stored index definition
  actually differs from the target, making an already-normalized library's
  initialization byte-identical on repeat calls.
- `tools/migrate_legacy_reference_values.py`: `run_migration` now runs its
  `dry_run=True` simulation against a `tempfile.TemporaryDirectory` copy of
  `database_path`, never opening the real file for writing — this is the
  additional mechanism the independent web sparring reviewer required beyond
  the index-idempotency fix, since a genuinely legacy-only database still
  needs normalized tables to exist somewhere for the simulation's read
  queries. `--apply` (`dry_run=False`) is unchanged.
- `tests/test_legacy_reference_migration.py`: added
  `test_migration_dry_run_on_legacy_only_database_makes_no_changes` exercising
  a `reference_values`-only database (Case B); the existing already-normalized
  test (Case A) continues to pass unmodified.

Test results (`QT_QPA_PLATFORM=offscreen ./.venv/bin/pytest`, project `.venv`):

- Three formerly-failing nodes, individually: 3 passed (was 3 failed); the 6
  Stage 6l cross-repository checks in the same invocation remain skipped
  (sibling worktrees unavailable) — not counted as passes.
- Focused baseline (9 files): 170 passed (was 169 passed / 1 failed).
- Broader selection (97 files): 1739 passed, 6 skipped (was 1,732 passed / 3
  failed / 6 skipped) — the +7 is the 3 previously-failing nodes plus the 4
  new regression tests.
- Additional-consumer selection (11 files): 203 passed, unchanged.
- `git diff --check` clean; `py_compile` clean on every touched production
  file.
- Direct SQLite demonstrations: already-normalized init is byte-identical on
  a repeat call (Case A); the new legacy-only regression test demonstrates
  zero byte change and zero normalized tables left behind after a
  `dry_run=True` migration against a `reference_values`-only database
  (Case B).

Out of scope, not touched: the early `synced` stamp/re-dirty behavior, the
summary retry `mark_observation_sync_dirty` signature mismatch, Stage 0
extraction, typed issue/outcome architecture, push/pull orchestration,
reference-cloud sibling architecture, anchor adoption/reservation risk, the
broader no-op-write audit, and the Stage 6l cross-repository gate. These
remain deferred exactly as recorded above.

**Current disposition:** all three baseline failures are repaired and green in
this candidate commit on the review branch. This pass does **not** self-declare
the Pre-stage independently accepted — that decision belongs to a fresh
independent `sporely-sparring` review of the pushed candidate. Stage 0 remains
blocked until that review explicitly accepts this repair.

## End-of-pass handoff — WAL-safe dry-run follow-up, 2026-09-08

Implemented via `stage-cloud-sync-prestage-baseline-repair-wal-followup.md` on
review branch `review/cloud-sync-prestage-2026-09-08`, base commit
`0e9482647c395ee69a6ed581f93d5098062881b0` (which sits on top of the immutable
baseline-repair candidate `ca16130fa54bfc6597a6215b8b6b87979a80e845`, itself
unmodified by this pass).

The independent web reviewer reviewed `b72af25..ca16130` and provisionally
accepted repairs 2 and 3 above (materialization `suppress_reverse_identity`,
the stale `push_image_metadata` fixture) and the conditional DOI/ISBN index
migration described under repair 1. Those are not redesigned here. One
blocker remained: the dry-run scratch copy at
`tools/migrate_legacy_reference_values.py:run_migration` used
`shutil.copy2(database_path, scratch_path)`, a raw filesystem copy of only
the main `.db` file. `database/schema.py::get_reference_connection` runs the
reference database in `PRAGMA journal_mode = WAL`, so a committed
transaction can exist only in the `reference_values.db-wal` sidecar until a
checkpoint occurs; a raw copy of the main file alone can miss such committed
state, without requiring the caller to close Sporely or checkpoint first.
Rejected as insufficient evidence of committed source state under WAL.

Repair: added `_snapshot_reference_database_for_dry_run` in
`tools/migrate_legacy_reference_values.py`, following the existing WAL-safe
precedent `utils/archive/full_backup.py::_snapshot_database` — open the
source read-only via a `mode=ro` URI connection and use
`sqlite3.Connection.backup` so committed WAL pages are included in the
scratch snapshot, then normalize the scratch copy's journal mode back to
`DELETE` (a WAL-mode source can otherwise propagate that setting to the
throwaway copy). `run_migration`'s `dry_run=True` branch now calls this
helper instead of `shutil.copy2`; `--apply` behavior is unchanged. The
now-unused `shutil` import was removed from the migration tool.

Added `test_migration_dry_run_sees_committed_row_still_resident_in_wal` to
`tests/test_legacy_reference_migration.py`: a writer connection commits a
legacy row under `PRAGMA journal_mode=WAL` / `PRAGMA wal_autocheckpoint=0`
and stays open (asserting the `-wal` sidecar is non-empty, so the row is
verified resident only there, not checkpointed into the main file), then
`run_migration(..., dry_run=True)` is asserted to report the row as a
simulated create while the real database's byte fingerprint is unchanged.
Verified this regression actually protects the contract: temporarily
reverting the helper call to `shutil.copy2` makes the test fail
(`report.created` empty, the row reported `"not found in reference_values"`);
restoring the WAL-safe snapshot makes it pass again.

Test results (`QT_QPA_PLATFORM=offscreen ./.venv/bin/pytest`, project
`.venv`):

- New WAL regression, standalone: 1 passed.
- Full `tests/test_legacy_reference_migration.py`: 24 passed — preserves the
  three formerly-red baseline nodes' repairs, the initialized-database and
  legacy-only dry-run no-write regressions, and normal `--apply` coverage.
- Focused baseline (9 files, frozen list): 170 passed, unchanged from the
  `ca16130` repair.
- Broader selection (97 files, frozen list): 1,740 passed, 6 skipped — one
  more pass than `ca16130`'s 1,739, from the new WAL regression; the six
  Stage 6l cross-repository skips remain unavailable evidence, not counted
  as passes.
- Additional-consumer selection (11 files, frozen list): 203 passed,
  unchanged.
- `git diff --check` clean; `py_compile` clean on
  `tools/migrate_legacy_reference_values.py` and
  `tests/test_legacy_reference_migration.py`.

Out of scope, not touched: Stage 0 extraction, early synced-stamp/re-dirty
behavior, the summary retry signature mismatch, observation/image identity
architecture beyond the already-landed `NameError` fix, reference-cloud
sibling architecture, anchor risks, general SQLite backup/refactoring, the
full-backup implementation itself, unrelated workflow documentation, and the
broader no-op-write audit. These remain deferred exactly as recorded above.

**Current disposition:** no baseline failure remains outstanding from this
follow-up's scope; the dry-run scratch-copy mechanism is now WAL-safe. This
pass does **not** self-declare the Pre-stage independently accepted — that
decision belongs to a fresh independent `sporely-sparring` review of the
complete repair (`ca16130` plus this follow-up commit) on the review branch.
Stage 0 remains blocked until that review explicitly accepts it.
