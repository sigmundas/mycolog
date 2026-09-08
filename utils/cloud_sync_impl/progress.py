"""Cloud sync progress tracking infrastructure."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Callable

from .profiling import _cloud_sync_perf_counter, _CLOUD_SYNC_SLOW_STEP_SECONDS


ProgressCallback = Callable[[str, int, int], None]

# Per-sync progress trace. When set, every progress message emission records its
# monotonic timestamp so a gap between two UI updates (i.e. a backend step that
# produced no progress text) can be logged and traced to whatever was running.
_CLOUD_SYNC_PROGRESS_TRACE_CONTEXT: ContextVar[dict | None] = ContextVar(
    'cloud_sync_progress_trace',
    default=None,
)


def _cloud_sync_progress_trace() -> dict | None:
    try:
        return _CLOUD_SYNC_PROGRESS_TRACE_CONTEXT.get()
    except Exception:
        return None


def _progress_done(progress_state: dict | None) -> int:
    try:
        return max(0, int((progress_state or {}).get('done', 0) or 0))
    except Exception:
        return 0


def _progress_total(progress_state: dict | None) -> int:
    try:
        return max(0, int((progress_state or {}).get('total', 0) or 0))
    except Exception:
        return 0


def _trace_progress_gap(message: str) -> None:
    """Log when a long backend step elapsed between two UI progress updates.

    The UI only shows the *last* emitted message. If a slow step runs while that
    message stays on screen (e.g. the bar appears frozen on "Checking
    calibration 4/8"), the gap is logged here naming both messages so the pause
    can be traced to the actual backend work, even when that work emits no
    progress text of its own.
    """
    trace = _cloud_sync_progress_trace()
    if not isinstance(trace, dict):
        return
    now = _cloud_sync_perf_counter()
    last_t = trace.get('last_t')
    last_msg = trace.get('last_msg')
    start = trace.get('start', now)
    if last_t is not None:
        gap = now - last_t
        if gap >= _CLOUD_SYNC_SLOW_STEP_SECONDS:
            print(
                f"[cloud_sync] progress gap: {gap * 1000:.0f}ms with no UI update "
                f"(stuck showing \"{last_msg}\") before \"{message}\" "
                f"at +{(now - start):.1f}s into sync",
                flush=True,
            )
    trace['last_t'] = now
    trace['last_msg'] = message


# Weighted global progress model for cloud sync.
#
# The UI shows a single progress bar; each sync phase maps onto a fixed
# percentage range. Per-phase (done, total) counters are turned into a global
# 0–100 value by _sync_progress_percent so the bar advances monotonically at
# roughly the pace of real work — never jumping to 99% while phases like
# "Loading cloud measurements" or "Checking cloud observation N/M" are still
# running.
#
# Ordered by execution — the tuple is (name, start_percent, end_percent).
_SYNC_PROGRESS_PHASES: tuple[tuple[str, int, int], ...] = (
    ('auth', 0, 5),
    ('calibration_push', 5, 12),
    ('observation_preflight', 12, 18),
    ('push_observations', 18, 45),
    ('refresh_remote', 45, 50),
    ('pull_preflight', 50, 65),
    ('pull_measurements', 65, 75),
    ('pull_observations', 75, 92),
    ('calibration_pull', 92, 97),
    ('finalize', 97, 100),
)
_SYNC_PROGRESS_PHASE_RANGES: dict[str, tuple[int, int]] = {
    name: (start, end) for name, start, end in _SYNC_PROGRESS_PHASES
}
_SYNC_PROGRESS_TOTAL_UNITS = 100


def _sync_progress_percent(phase: str | None, done: int, total: int) -> int:
    """Map per-phase (done, total) onto the global 0–100 progress scale.

    Unknown or missing phases resolve to 0 so a bug in phase wiring can never
    silently pin the bar to 99%.
    """
    start, end = _SYNC_PROGRESS_PHASE_RANGES.get(str(phase or ''), (0, 0))
    try:
        done_int = max(0, int(done))
        total_int = max(0, int(total))
    except Exception:
        done_int, total_int = 0, 0
    if total_int <= 0:
        return int(start)
    frac = min(1.0, done_int / total_int)
    return int(round(start + frac * (end - start)))


def _set_progress_phase(
    progress_state: dict | None,
    phase_name: str,
    phase_total: int = 0,
) -> None:
    """Enter a named sync phase and reset the per-phase (done, total) counter.

    Progress is tracked *per phase*, not globally: each phase gets a fresh
    ``done``/``total`` pair which the ``_emit_progress`` mapper then squeezes
    into that phase's slice of the global 0–100 range. The finalize phase is
    the only one allowed to reach 100%; other phases cap at their configured
    end percentage even if more work than expected turns out to be needed.
    """
    if not isinstance(progress_state, dict):
        return
    if phase_name not in _SYNC_PROGRESS_PHASE_RANGES:
        # Silently ignore unknown phases so tests that seed a raw
        # {done, total} dict without wiring phases keep working.
        return
    progress_state['phase'] = phase_name
    progress_state['done'] = 0
    try:
        progress_state['total'] = max(0, int(phase_total or 0))
    except Exception:
        progress_state['total'] = 0


def _current_progress_phase(progress_state: dict | None) -> str | None:
    if not isinstance(progress_state, dict):
        return None
    phase = progress_state.get('phase')
    if isinstance(phase, str) and phase in _SYNC_PROGRESS_PHASE_RANGES:
        return phase
    return None


def _emit_progress(
    progress_cb: ProgressCallback | None,
    message: str,
    progress_state: dict | None,
) -> None:
    _trace_progress_gap(message)
    if not callable(progress_cb):
        return
    phase = _current_progress_phase(progress_state)
    if phase is not None:
        phase_done = _progress_done(progress_state)
        phase_total = _progress_total(progress_state)
        percent = _sync_progress_percent(phase, phase_done, phase_total)
        progress_cb(message, percent, _SYNC_PROGRESS_TOTAL_UNITS)
    else:
        progress_cb(message, _progress_done(progress_state), max(1, _progress_total(progress_state)))


def _advance_progress(
    progress_state: dict | None,
    amount: int = 1,
) -> tuple[int, int]:
    state = progress_state or {}
    try:
        increment = max(0, int(amount))
    except Exception:
        increment = 0
    state['done'] = _progress_done(state) + increment
    state['total'] = _progress_total(state)
    return _progress_done(state), _progress_total(state)


def _extend_progress_total(
    progress_state: dict | None,
    amount: int,
) -> tuple[int, int]:
    state = progress_state or {}
    try:
        increment = max(0, int(amount))
    except Exception:
        increment = 0
    state['done'] = _progress_done(state)
    state['total'] = _progress_total(state) + increment
    return _progress_done(state), _progress_total(state)
