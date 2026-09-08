"""Cloud sync profiling and timing infrastructure."""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .common import _safe_int


_CLOUD_DEBUG_TIMING = str(os.environ.get('SPORELY_DEBUG_RAW_TIMING') or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _cloud_timing_log(stage: str, start: float | None, *, detail: str = '') -> None:
    if not _CLOUD_DEBUG_TIMING or start is None:
        return
    elapsed_ms = max(0.0, (_cloud_sync_perf_counter() - start) * 1000.0)
    if detail:
        print(f"[raw-timing] cloud delete {stage}: {elapsed_ms:.1f} ms | {detail}")
    else:
        print(f"[raw-timing] cloud delete {stage}: {elapsed_ms:.1f} ms")


_CLOUD_SYNC_PROFILE_ENV = 'SPORELY_CLOUD_SYNC_PROFILE'
_CLOUD_SYNC_DEBUG_ENV = 'SPORELY_DEBUG_CLOUD_SYNC'
_CLOUD_SYNC_PROFILE_CONTEXT: ContextVar['CloudSyncProfiler | None'] = ContextVar(
    'cloud_sync_profiler',
    default=None,
)

# A single sync sub-step taking longer than this is logged so a silent UI pause
# can be traced to the exact calibration / step responsible.
_CLOUD_SYNC_SLOW_STEP_SECONDS = 1.0


def _cloud_sync_profile_enabled() -> bool:
    return str(os.getenv(_CLOUD_SYNC_PROFILE_ENV) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _cloud_sync_debug_enabled() -> bool:
    return str(os.getenv(_CLOUD_SYNC_DEBUG_ENV) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _cloud_sync_current_profiler() -> 'CloudSyncProfiler | None':
    try:
        return _CLOUD_SYNC_PROFILE_CONTEXT.get()
    except Exception:
        return None


@contextmanager
def _cloud_sync_profile_scope(profiler: 'CloudSyncProfiler'):
    token = _CLOUD_SYNC_PROFILE_CONTEXT.set(profiler)
    try:
        yield profiler
    finally:
        try:
            _CLOUD_SYNC_PROFILE_CONTEXT.reset(token)
        except Exception:
            pass


def _cloud_sync_perf_counter() -> float:
    try:
        return time.perf_counter()
    except Exception:
        return 0.0


def _cloud_sync_profile_print(payload: dict) -> None:
    try:
        print(
            f"[cloud_sync_profile] {json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}",
            flush=True,
        )
    except Exception:
        pass


@dataclass
class CloudSyncProfiler:
    sync_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: float = field(default_factory=_cloud_sync_perf_counter)
    phase_durations_ms: dict[str, float] = field(default_factory=dict)
    download_image_file_calls: int = 0
    download_image_file_duration_ms: float = 0.0
    download_image_file_bytes: int = 0
    generate_all_sizes_calls: int = 0
    generate_all_sizes_duration_ms: float = 0.0
    pull_bulk_image_metadata_calls: int = 0
    pull_bulk_image_metadata_rows: int = 0
    pull_measurements_for_images_calls: int = 0
    pull_measurements_for_images_rows: int = 0
    store_remote_snapshot_fetch_images_count: int = 0
    store_remote_snapshot_fetch_measurements_count: int = 0
    retry_missing_cloud_media_branch_runs: int = 0
    original_upload_calls: int = 0
    original_upload_bytes: int = 0
    original_upload_skipped_disabled: int = 0
    original_upload_skipped_ineligible: int = 0
    original_upload_skipped_too_large: int = 0
    original_upload_failed_uploads: int = 0
    original_download_calls: int = 0
    original_download_bytes: int = 0
    original_download_skipped_disabled: int = 0
    original_download_skipped_missing_key: int = 0
    original_download_skipped_existing_local_original: int = 0
    original_download_skipped_existing_cache: int = 0
    original_download_failed_downloads: int = 0

    def _emit(self, payload: dict) -> None:
        payload = dict(payload or {})
        payload.setdefault('sync_id', self.sync_id)
        _cloud_sync_profile_print(payload)

    def phase(self, phase_name: str):
        @contextmanager
        def _phase_scope():
            start = _cloud_sync_perf_counter()
            try:
                yield
            finally:
                try:
                    elapsed_ms = max(0.0, (_cloud_sync_perf_counter() - start) * 1000.0)
                    key = str(phase_name or '').strip() or 'unknown'
                    self.phase_durations_ms[key] = self.phase_durations_ms.get(key, 0.0) + elapsed_ms
                    self._emit({
                        'event': 'phase',
                        'phase': key,
                        'duration_ms': round(elapsed_ms, 3),
                    })
                except Exception:
                    pass

        return _phase_scope()

    def record_download_image_file(self, duration_ms: float, bytes_downloaded: int = 0) -> None:
        try:
            self.download_image_file_calls += 1
            self.download_image_file_duration_ms += max(0.0, float(duration_ms))
            self.download_image_file_bytes += max(0, int(bytes_downloaded))
        except Exception:
            pass

    def record_generate_all_sizes(self, duration_ms: float) -> None:
        try:
            self.generate_all_sizes_calls += 1
            self.generate_all_sizes_duration_ms += max(0.0, float(duration_ms))
        except Exception:
            pass

    def record_pull_bulk_image_metadata(self, row_count: int) -> None:
        try:
            self.pull_bulk_image_metadata_calls += 1
            self.pull_bulk_image_metadata_rows += max(0, int(row_count))
        except Exception:
            pass

    def record_pull_measurements_for_images(self, row_count: int) -> None:
        try:
            self.pull_measurements_for_images_calls += 1
            self.pull_measurements_for_images_rows += max(0, int(row_count))
        except Exception:
            pass

    def record_store_remote_snapshot_fetch(self, *, images: bool = False, measurements: bool = False) -> None:
        try:
            if images:
                self.store_remote_snapshot_fetch_images_count += 1
            if measurements:
                self.store_remote_snapshot_fetch_measurements_count += 1
        except Exception:
            pass

    def record_retry_missing_cloud_media_branch(self) -> None:
        try:
            self.retry_missing_cloud_media_branch_runs += 1
        except Exception:
            pass

    def record_original_upload_success(self, bytes_uploaded: int = 0) -> None:
        try:
            self.original_upload_calls += 1
            self.original_upload_bytes += max(0, int(bytes_uploaded))
        except Exception:
            pass

    def record_original_upload_skipped_disabled(self) -> None:
        try:
            self.original_upload_skipped_disabled += 1
        except Exception:
            pass

    def record_original_upload_skipped_ineligible(self) -> None:
        try:
            self.original_upload_skipped_ineligible += 1
        except Exception:
            pass

    def record_original_upload_skipped_too_large(self) -> None:
        try:
            self.original_upload_skipped_too_large += 1
        except Exception:
            pass

    def record_original_upload_failed(self) -> None:
        try:
            self.original_upload_failed_uploads += 1
        except Exception:
            pass

    def record_original_download_success(self, bytes_downloaded: int = 0) -> None:
        try:
            self.original_download_calls += 1
            self.original_download_bytes += max(0, int(bytes_downloaded))
        except Exception:
            pass

    def record_original_download_skipped_disabled(self) -> None:
        try:
            self.original_download_skipped_disabled += 1
        except Exception:
            pass

    def record_original_download_skipped_missing_key(self) -> None:
        try:
            self.original_download_skipped_missing_key += 1
        except Exception:
            pass

    def record_original_download_skipped_existing_local_original(self) -> None:
        try:
            self.original_download_skipped_existing_local_original += 1
        except Exception:
            pass

    def record_original_download_skipped_existing_cache(self) -> None:
        try:
            self.original_download_skipped_existing_cache += 1
        except Exception:
            pass

    def record_original_download_failed(self) -> None:
        try:
            self.original_download_failed_downloads += 1
        except Exception:
            pass

    def summary_payload(self, result: dict | None = None, error: Exception | None = None) -> dict:
        try:
            now = _cloud_sync_perf_counter()
            payload = {
                'event': 'summary',
                'status': 'error' if error else 'ok',
                'duration_ms': round(max(0.0, (now - self.started_at) * 1000.0), 3),
                'phases_ms': {
                    key: round(value, 3)
                    for key, value in sorted(self.phase_durations_ms.items(), key=lambda item: item[0])
                },
                'metrics': {
                    'download_image_file': {
                        'calls': self.download_image_file_calls,
                        'duration_ms': round(self.download_image_file_duration_ms, 3),
                        'bytes': self.download_image_file_bytes,
                    },
                    'generate_all_sizes': {
                        'calls': self.generate_all_sizes_calls,
                        'duration_ms': round(self.generate_all_sizes_duration_ms, 3),
                    },
                    'pull_bulk_image_metadata': {
                        'calls': self.pull_bulk_image_metadata_calls,
                        'rows': self.pull_bulk_image_metadata_rows,
                    },
                    'pull_measurements_for_images': {
                        'calls': self.pull_measurements_for_images_calls,
                        'rows': self.pull_measurements_for_images_rows,
                    },
                    'store_remote_snapshot': {
                        'fetched_images': self.store_remote_snapshot_fetch_images_count,
                        'fetched_measurements': self.store_remote_snapshot_fetch_measurements_count,
                    },
                    'retry_missing_cloud_media': {
                        'branch_runs': self.retry_missing_cloud_media_branch_runs,
                    },
                    'original_upload': {
                        'calls': self.original_upload_calls,
                        'bytes': self.original_upload_bytes,
                        'skipped_disabled': self.original_upload_skipped_disabled,
                        'skipped_ineligible': self.original_upload_skipped_ineligible,
                        'skipped_too_large': self.original_upload_skipped_too_large,
                        'failed_uploads': self.original_upload_failed_uploads,
                    },
                    'original_download': {
                        'calls': self.original_download_calls,
                        'bytes': self.original_download_bytes,
                        'skipped_disabled': self.original_download_skipped_disabled,
                        'skipped_missing_key': self.original_download_skipped_missing_key,
                        'skipped_existing_local_original': self.original_download_skipped_existing_local_original,
                        'skipped_existing_cache': self.original_download_skipped_existing_cache,
                        'failed_downloads': self.original_download_failed_downloads,
                    },
                },
            }
            if result is not None:
                payload['result'] = {
                    'pushed': int(result.get('pushed', 0) or 0),
                    'pulled': int(result.get('pulled', 0) or 0),
                    'calibrations_pushed': int(result.get('calibrations_pushed', 0) or 0),
                    'calibrations_pulled': int(result.get('calibrations_pulled', 0) or 0),
                    'deleted_remote': len(result.get('deleted_remote') or []),
                    'error_count': len(result.get('errors') or []),
                }
                sync_summary = result.get('sync_summary')
                if isinstance(sync_summary, dict):
                    payload['result']['sync_summary'] = {
                        str(key): _safe_int(value)
                        for key, value in sync_summary.items()
                    }
            if error is not None:
                error_text = str(error or '').strip()
                if error_text:
                    payload['error'] = error_text[:300]
                payload['error_type'] = error.__class__.__name__
            return payload
        except Exception:
            return {
                'event': 'summary',
                'status': 'error' if error else 'ok',
                'duration_ms': 0.0,
                'phases_ms': {},
                'metrics': {},
            }

    def finish(self, result: dict | None = None, error: Exception | None = None) -> None:
        try:
            self._emit(self.summary_payload(result=result, error=error))
        except Exception:
            pass
