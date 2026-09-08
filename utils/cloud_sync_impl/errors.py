"""Cloud sync error types and classification helpers."""
from __future__ import annotations

import json


_SUPABASE_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_SUPABASE_TRANSIENT_ERROR_HINTS = (
    'bad gateway',
    'connection aborted',
    'connection refused',
    'connection reset',
    'could not connect to server',
    'gateway timeout',
    'postgrest unavailable',
    'schema cache',
    'service unavailable',
    'temporarily unavailable',
    'timed out',
    'timeout',
)
_CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE = (
    'Supabase/cloud sync is temporarily unavailable; local data was not overwritten.'
)


class CloudSyncError(Exception):
    pass


class AccountMismatchError(CloudSyncError):
    pass


class CloudTemporarilyUnavailableError(CloudSyncError):
    pass


class CloudReauthRequiredError(CloudSyncError):
    """Raised when the refresh endpoint proves the refresh token is dead.

    Distinct from CloudTemporarilyUnavailableError (Supabase glitch, retry
    likely fine) and from generic CloudSyncError (transport-level noise).
    Reaching this state means the current session cannot be resumed and the
    user must sign in again — but callers still must not wipe stored tokens
    unless the user explicitly signs out.
    """


class PullOnlyModeError(CloudSyncError):
    """Raised when a cloud-write is attempted during a Download-from-Cloud run.

    Download from Cloud is strictly cloud → desktop. Any code path that
    reaches an upload, PATCH/POST/DELETE, storage removal, or write-back
    identity call while the pull-only client is active raises this error.
    The wrapper counts every attempt on ``write_attempts`` so tests can
    prove zero cloud writes reached the network.
    """


class PartialConflictPlanError(CloudSyncError):
    """Raised when a conflict plan fails mid-execution.

    Carries the partial operation log so the caller (typically the in-dialog
    apply worker) can present per-item statuses, keep the conflict visible,
    and offer a safe retry using ``prior_result`` on the next call.
    """

    def __init__(self, message: str, *, partial_result: dict):
        super().__init__(message)
        self.partial_result = dict(partial_result or {})


class ObservationIdentityConflictError(CloudSyncError):
    """Raised when observation push identity cannot be resolved safely.

    Two links tie a local observation to a cloud row: the direct link
    (local ``observations.cloud_id``) and the reverse link (remote
    ``observations.desktop_id``). This error is raised when they resolve to
    different cloud rows, or when the reverse-link recovery lookup matches
    more than one cloud row. PATCHing either candidate could overwrite the
    wrong row and POSTing would create a duplicate, so the push must fail
    and leave the observation dirty/retryable for review.
    """


class ImageIdentityConflictError(CloudSyncError):
    """Raised when image push identity is ambiguous or contradictory.

    The caller must not PATCH or POST. Leave the image dirty/retryable.
    """


class CloudSessionAccountMismatchError(AccountMismatchError):
    """Raised when a stale SporelyCloudClient sees on-disk session tokens
    that belong to a different Sporely Cloud user than the one this
    client is bound to.

    Usually happens when the user signed out and signed back in as a
    different account while an old worker/thread was still alive: the
    worker's in-memory ``user_id`` still points at the previous
    account, but the on-disk tokens now belong to the new one.  We
    refuse to adopt the new account's tokens or call the refresh
    endpoint with them — the worker should surface this and stop.
    Inherits from :class:`AccountMismatchError` so existing handlers
    that only catch that base class keep working; catch this subclass
    to distinguish "stale worker" from "database linked to a different
    account".
    """


ACCOUNT_MISMATCH_MESSAGE = (
    "This local database is permanently linked to another Sporely Cloud account. "
    "Please switch to the correct OS user profile, or use the 'Reset Cloud Sync' "
    "tool in Settings to migrate your data to a new account."
)

_CLOUD_AUTH_ERROR_HINTS = (
    'jwt expired',
    'invalid jwt',
    'expired access token',
    'access token expired',
    'token expired',
    'session expired',
    'authentication failed',
    'invalid_grant',
    'not logged in',
    'unauthorized',
    'pgrst301',
    'pgrst303',
    # Supabase returns this when password login is attempted without a captcha
    # token — the user must sign in interactively (e.g. via browser).
    'captcha_failed',
)

# Hints that identify a *terminal* refresh-token invalidation coming from
# Supabase's refresh endpoint.  Anything matching this list means the
# session cannot be resumed and the user must sign in again.  A plain
# 401 or an expired-JWT hint is NOT enough — those are recoverable by
# refreshing.
_CLOUD_REAUTH_REQUIRED_HINTS = (
    'invalid_grant',
    'invalid refresh token',
    'refresh token not found',
    'refresh_token_not_found',
    'refresh_token_already_used',
)


def _collect_sync_error_details(value, seen: set[int] | None = None) -> tuple[str, list[str]]:
    if seen is None:
        seen = set()
    try:
        marker = id(value)
    except Exception:
        marker = None
    if marker is not None and marker in seen:
        return '', []
    if marker is not None:
        seen.add(marker)

    code = ''
    texts: list[str] = []
    if value is None:
        return code, texts

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return code, texts
        texts.append(text)
        if text[:1] in {'{', '['}:
            try:
                parsed = json.loads(text)
            except Exception:
                return code, texts
            parsed_code, parsed_texts = _collect_sync_error_details(parsed, seen)
            if parsed_code and not code:
                code = parsed_code
            texts.extend(parsed_texts)
        if not code:
            lowered = text.lower()
            if '23514' in text:
                code = '23514'
            elif 'check_violation' in lowered:
                code = 'check_violation'
        return code, texts

    if isinstance(value, dict):
        for key in ('code', 'sqlstate', 'status_code', 'statusCode', 'status'):
            raw_code = value.get(key)
            if raw_code not in (None, ''):
                candidate = str(raw_code).strip()
                if candidate and not code:
                    code = candidate
        for key in ('message', 'details', 'hint', 'error', 'body', 'text', 'reason', 'response'):
            if key not in value:
                continue
            sub_code, sub_texts = _collect_sync_error_details(value.get(key), seen)
            if sub_code and not code:
                code = sub_code
            texts.extend(sub_texts)
        return code, texts

    for attr in ('code', 'sqlstate', 'status_code', 'statusCode', 'status'):
        try:
            raw_code = getattr(value, attr)
        except Exception:
            raw_code = None
        if raw_code not in (None, ''):
            candidate = str(raw_code).strip()
            if candidate and not code:
                code = candidate
    for attr in ('message', 'details', 'hint', 'error', 'body', 'text', 'reason', 'response', 'payload', 'response_payload'):
        try:
            raw_value = getattr(value, attr)
        except Exception:
            raw_value = None
        if raw_value is None:
            continue
        sub_code, sub_texts = _collect_sync_error_details(raw_value, seen)
        if sub_code and not code:
            code = sub_code
        texts.extend(sub_texts)
    for attr in ('__cause__', '__context__'):
        try:
            chained_value = getattr(value, attr)
        except Exception:
            chained_value = None
        if chained_value is None:
            continue
        sub_code, sub_texts = _collect_sync_error_details(chained_value, seen)
        if sub_code and not code:
            code = sub_code
        texts.extend(sub_texts)
    text = str(value).strip()
    if text:
        texts.append(text)
        if not code:
            lowered = text.lower()
            if '23514' in text:
                code = '23514'
            elif 'check_violation' in lowered:
                code = 'check_violation'
    return code, texts


def format_cloud_sync_error_details(error) -> str:
    code, texts = _collect_sync_error_details(error)
    parts: list[str] = []
    code_text = str(code or '').strip()
    if code_text:
        parts.append(f"code={code_text}")
    for text in dict.fromkeys(texts):
        cleaned = str(text or '').strip()
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    if not parts:
        fallback = str(error or '').strip()
        if fallback:
            parts.append(fallback)
    return " | ".join(parts)


def is_cloud_auth_error(error) -> bool:
    """Broad classification: does *error* smell like an auth/token issue?

    Used by the request layer to decide whether to try a refresh and by
    the sync loops to decide whether to abort early.  Deliberately does
    not match a raw ``403`` — PostgREST returns 403 for RLS denials,
    which are authorization (not authentication) failures and must not
    be conflated with an expired session.
    """
    if isinstance(error, CloudReauthRequiredError):
        return True
    code, texts = _collect_sync_error_details(error)
    haystack = ' '.join(dict.fromkeys(texts)).lower()
    code_text = str(code or '').strip().lower()
    if code_text == '401':
        return True
    return any(hint in haystack for hint in _CLOUD_AUTH_ERROR_HINTS)


def is_cloud_reauth_required_error(error) -> bool:
    """Strict classification: is this error terminal for the current session?

    Returns True only when we can prove the stored refresh token itself
    is dead — e.g. the refresh endpoint returned ``invalid_grant`` — so
    the UI can prompt the user to sign in again.  A wrapper such as
    ``CloudTemporarilyUnavailableError`` chained from a generic ``"auth
    refresh failed"`` string is NOT sufficient: that shape can result
    from a rotation race or a transient Supabase blip, and treating it
    as terminal would wipe a still-valid refresh token on next restart.
    """
    if isinstance(error, CloudReauthRequiredError):
        return True
    seen: set[int] = set()
    value = error
    while value is not None:
        if isinstance(value, CloudReauthRequiredError):
            return True
        try:
            marker = id(value)
        except Exception:
            marker = None
        if marker is not None:
            if marker in seen:
                break
            seen.add(marker)
        value = getattr(value, '__cause__', None) or getattr(value, '__context__', None)
    code, texts = _collect_sync_error_details(error)
    haystack = ' '.join(dict.fromkeys(texts)).lower()
    return any(hint in haystack for hint in _CLOUD_REAUTH_REQUIRED_HINTS)


def is_cloud_temporary_unavailable_error(error) -> bool:
    if isinstance(error, CloudTemporarilyUnavailableError):
        return True
    code, texts = _collect_sync_error_details(error)
    haystack = ' '.join(dict.fromkeys(texts)).lower()
    code_text = str(code or '').strip().lower()
    if code_text in {'pgrst000', 'pgrst001', 'pgrst002', 'pgrst003'}:
        return True
    if code_text in {str(status) for status in _SUPABASE_TRANSIENT_STATUS_CODES}:
        return True
    if _CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE.lower() in haystack:
        return True
    return any(hint in haystack for hint in _SUPABASE_TRANSIENT_ERROR_HINTS)
