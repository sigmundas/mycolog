"""Cloud sync summary and result bookkeeping."""
from __future__ import annotations

from contextvars import ContextVar

from .progress import _CLOUD_SYNC_SLOW_STEP_SECONDS, _cloud_sync_perf_counter, _progress_done, _progress_total


_CLOUD_SYNC_SUMMARY_CONTEXT: ContextVar[dict[str, int] | None] = ContextVar(
    'cloud_sync_summary',
    default=None,
)


def _cloud_sync_current_summary() -> dict[str, int] | None:
    try:
        return _CLOUD_SYNC_SUMMARY_CONTEXT.get()
    except Exception:
        return None


from contextlib import contextmanager

@contextmanager
def _cloud_sync_summary_scope(sync_summary: dict[str, int]):
    token = _CLOUD_SYNC_SUMMARY_CONTEXT.set(sync_summary)
    try:
        yield sync_summary
    finally:
        try:
            _CLOUD_SYNC_SUMMARY_CONTEXT.reset(token)
        except Exception:
            pass


_SYNC_SUMMARY_KEYS = (
    'observations_checked',
    'observations_redirtied_pending_local_images',
    'observations_patched',
    'observations_skipped_noop',
    'observations_deleted_remote',
    'images_checked',
    'images_prepared_local',
    'images_uploaded',
    'images_skipped_already_synced',
    'images_cloud_id_repaired',
    'images_deleted_remote',
    'measurements_checked',
    'measurements_patched',
    'measurements_skipped_noop',
    'calibrations_pushed',
    'calibrations_pulled',
    'calibrations_skipped_noop',
    'calibrations_conflicts',
    'calibration_reference_images_uploaded',
    'calibration_remote_lookups',
    'storage_quota_delta_rpc_calls',
    'remote_media_downloads',
    'remote_media_materializations',
)


def _new_sync_summary() -> dict[str, int]:
    return {key: 0 for key in _SYNC_SUMMARY_KEYS}


def _sync_summary_value(sync_summary: dict | None, key: str) -> int:
    try:
        return max(0, int((sync_summary or {}).get(key, 0) or 0))
    except Exception:
        return 0


def _increment_sync_summary(sync_summary: dict | None, key: str, amount: int = 1) -> None:
    if not isinstance(sync_summary, dict):
        return
    try:
        increment = max(0, int(amount))
    except Exception:
        increment = 0
    if increment <= 0:
        return
    sync_summary[key] = _sync_summary_value(sync_summary, key) + increment


def format_sync_summary(sync_summary: dict | None) -> str | None:
    summary = dict(sync_summary or {})
    if not summary:
        return None

    lines: list[str] = []

    observation_bits = []
    observations_checked = _sync_summary_value(summary, 'observations_checked')
    if observations_checked:
        observation_bits.append(f'{observations_checked} checked')
    observations_redirtied = _sync_summary_value(summary, 'observations_redirtied_pending_local_images')
    if observations_redirtied:
        observation_bits.append(f'{observations_redirtied} re-dirtied due to pending local images')
    observations_patched = _sync_summary_value(summary, 'observations_patched')
    if observations_patched:
        observation_bits.append(f'{observations_patched} patched')
    observations_noop = _sync_summary_value(summary, 'observations_skipped_noop')
    if observations_noop:
        observation_bits.append(f'{observations_noop} skipped as no-op')
    observations_deleted = _sync_summary_value(summary, 'observations_deleted_remote')
    if observations_deleted:
        observation_bits.append(f'{observations_deleted} deleted remotely')
    if observation_bits:
        lines.append(f"Observations: {'; '.join(observation_bits)}.")

    image_bits = []
    images_checked = _sync_summary_value(summary, 'images_checked')
    if images_checked:
        image_bits.append(f'{images_checked} checked')
    images_prepared = _sync_summary_value(summary, 'images_prepared_local')
    if images_prepared:
        image_bits.append(f'{images_prepared} prepared for upload')
    images_uploaded = _sync_summary_value(summary, 'images_uploaded')
    if images_uploaded:
        image_bits.append(f'{images_uploaded} uploaded')
    images_skipped = _sync_summary_value(summary, 'images_skipped_already_synced')
    if images_skipped:
        image_bits.append(f'{images_skipped} skipped as already synced')
    images_repaired = _sync_summary_value(summary, 'images_cloud_id_repaired')
    if images_repaired:
        image_bits.append(f'{images_repaired} cloud_id associations repaired')
    images_deleted = _sync_summary_value(summary, 'images_deleted_remote')
    if images_deleted:
        image_bits.append(f'{images_deleted} deleted remotely')
    if image_bits:
        lines.append(f"Images: {'; '.join(image_bits)}.")

    measurement_bits = []
    measurements_checked = _sync_summary_value(summary, 'measurements_checked')
    if measurements_checked:
        measurement_bits.append(f'{measurements_checked} checked')
    measurements_patched = _sync_summary_value(summary, 'measurements_patched')
    if measurements_patched:
        measurement_bits.append(f'{measurements_patched} patched')
    measurements_noop = _sync_summary_value(summary, 'measurements_skipped_noop')
    if measurements_noop:
        measurement_bits.append(f'{measurements_noop} skipped as no-op')
    if measurement_bits:
        lines.append(f"Measurements: {'; '.join(measurement_bits)}.")

    calibration_bits = []
    calibrations_pushed = _sync_summary_value(summary, 'calibrations_pushed')
    if calibrations_pushed:
        calibration_bits.append(f'{calibrations_pushed} pushed')
    calibrations_pulled = _sync_summary_value(summary, 'calibrations_pulled')
    if calibrations_pulled:
        calibration_bits.append(f'{calibrations_pulled} pulled')
    calibrations_noop = _sync_summary_value(summary, 'calibrations_skipped_noop')
    if calibrations_noop:
        calibration_bits.append(f'{calibrations_noop} skipped as no-op')
    calibrations_conflicts = _sync_summary_value(summary, 'calibrations_conflicts')
    if calibrations_conflicts:
        calibration_bits.append(f'{calibrations_conflicts} conflicts')
    calibration_reference_uploads = _sync_summary_value(summary, 'calibration_reference_images_uploaded')
    if calibration_reference_uploads:
        calibration_bits.append(f'{calibration_reference_uploads} reference image(s) uploaded')
    if calibration_bits:
        lines.append(f"Calibrations: {'; '.join(calibration_bits)}.")

    storage_quota_delta_calls = _sync_summary_value(summary, 'storage_quota_delta_rpc_calls')
    if storage_quota_delta_calls:
        lines.append(f'Storage quota delta RPC calls: {storage_quota_delta_calls}.')

    remote_downloads = _sync_summary_value(summary, 'remote_media_downloads')
    remote_materializations = _sync_summary_value(summary, 'remote_media_materializations')
    if remote_downloads or remote_materializations:
        lines.append(
            'Remote media downloads/materializations: '
            f'{remote_downloads} downloads; {remote_materializations} materializations.'
        )

    return '\n'.join(lines) if lines else None
