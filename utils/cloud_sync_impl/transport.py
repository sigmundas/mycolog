"""HTTP/session primitives for the cloud-sync client boundary."""
from __future__ import annotations

import requests

from utils.r2_storage import CloudflareMediaWorkerClient, CloudflareR2Client


def _facade():
    # This module is intentionally importable before the compatibility facade.
    # The facade owns the still-unmoved auth helpers and configuration slots.
    from utils import cloud_sync
    return cloud_sync


class CloudTransportMixin:
    """Mechanically extracted request, refresh, and REST write primitives."""

    def __init__(self, access_token: str, user_id: str, refresh_token: str | None = None):
        cs = _facade()
        self.access_token = access_token
        self.user_id = user_id
        self.refresh_token = str(refresh_token or '').strip() or None
        self._s = requests.Session()
        self._r2: CloudflareR2Client | None = None
        self._media_worker: CloudflareMediaWorkerClient | None = None
        self._column_support_cache: dict[tuple[str, str], bool] = {}
        self._cloud_image_storage_key_cache: dict[str, str] = {}
        self._s.headers.update({
            'apikey': cs.SUPABASE_KEY,
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        })

    def _get_r2(self) -> CloudflareR2Client:
        if self._r2 is None:
            self._r2 = CloudflareR2Client.from_env()
        return self._r2

    def _get_media_worker(self) -> CloudflareMediaWorkerClient:
        if self._media_worker is None:
            self._media_worker = CloudflareMediaWorkerClient.from_access_token(self.access_token)
        return self._media_worker

    def _using_default_r2_loader(self) -> bool:
        if "_get_r2" in self.__dict__:
            return False
        return type(self)._get_r2 is CloudTransportMixin._get_r2

    def _response_indicates_auth_error(self, response: requests.Response) -> bool:
        return _facade()._response_indicates_auth_error(response)

    def _adopt_session_from_values(self, access_token: str, user_id: str | None, refresh_token: str | None) -> None:
        cs = _facade()
        self.access_token = access_token
        self.user_id = cs._decode_jwt_subject(access_token) or cs._normalize_cloud_user_id(user_id) or self.user_id
        if refresh_token:
            self.refresh_token = refresh_token
        self._s.headers.update({'Authorization': f'Bearer {self.access_token}'})
        self._media_worker = None

    def _refresh_session_if_possible(self) -> bool:
        cs = _facade()
        with cs._CLOUD_REFRESH_LOCK:
            settings_access, settings_user_id, settings_refresh = cs._read_current_cloud_session_settings()
            self_access = str(self.access_token or '').strip() or None
            if not cs._settings_session_is_compatible(self.user_id, settings_user_id, settings_access):
                raise cs.CloudSessionAccountMismatchError(
                    "Stored cloud session belongs to a different account than this client instance; refusing to adopt or refresh."
                )
            if settings_access and settings_access != self_access and not cs._jwt_expires_soon(settings_access):
                self._adopt_session_from_values(settings_access, settings_user_id, settings_refresh)
                return True
            candidate_refresh = settings_refresh or (str(self.refresh_token or '').strip() or None)
            if not candidate_refresh:
                return False
            try:
                refreshed = type(self).refresh_login(candidate_refresh)
            except cs.CloudTemporarilyUnavailableError:
                raise
            except cs.CloudReauthRequiredError:
                after_access, after_user_id, after_refresh = cs._read_current_cloud_session_settings()
                if not cs._settings_session_is_compatible(self.user_id, after_user_id, after_access):
                    raise
                if after_access and after_access != settings_access and not cs._jwt_expires_soon(after_access):
                    self._adopt_session_from_values(after_access, after_user_id, after_refresh)
                    return True
                if after_refresh and after_refresh != candidate_refresh:
                    try:
                        refreshed = type(self).refresh_login(after_refresh)
                    except cs.CloudTemporarilyUnavailableError:
                        raise
                    except cs.CloudReauthRequiredError:
                        raise
                    except cs.CloudSyncError:
                        return False
                else:
                    raise
            except cs.CloudSyncError:
                return False
            self._adopt_session_from_values(refreshed.access_token, refreshed.user_id, refreshed.refresh_token)
            try:
                self.save_credentials()
            except Exception:
                pass
            return True

    def _request_with_refresh(self, method: str, url: str, *, refresh_on_auth_error: bool = True, **kwargs):
        return _facade()._request_with_transient_retry(
            self._s.request, method, url, refresh_on_auth_error=refresh_on_auth_error,
            refresh_callback=self._refresh_session_if_possible if refresh_on_auth_error else None, **kwargs,
        )

    def _get(self, path: str) -> list:
        cs = _facade()
        resp = self._request_with_refresh('GET', f'{cs.SUPABASE_URL}/rest/v1/{path}', timeout=cs._SUPABASE_REST_TIMEOUT)
        if not resp.ok:
            raise cs.CloudSyncError(f'GET {path}: {resp.text}')
        return resp.json()

    def get_read_only(self, path: str) -> list:
        cs = _facade()
        resp = self._request_with_refresh('GET', f'{cs.SUPABASE_URL}/rest/v1/{path}', timeout=cs._SUPABASE_REST_TIMEOUT, refresh_on_auth_error=False)
        if not resp.ok:
            status = int(getattr(resp, 'status_code', 0) or 0)
            if status in {401, 403} or self._response_indicates_auth_error(resp):
                raise cs.CloudReauthRequiredError('Read-only cloud audit authentication expired; sign in again before retrying.')
            raise cs.CloudSyncError(f'GET {path}: {resp.text}')
        return resp.json()

    def _post(self, path: str, payload: dict) -> list:
        cs = _facade()
        resp = self._request_with_refresh('POST', f'{cs.SUPABASE_URL}/rest/v1/{path}', json=payload, headers={'Prefer': 'return=representation'}, timeout=cs._SUPABASE_REST_TIMEOUT)
        if not resp.ok:
            raise cs.CloudSyncError(f'POST {path}: {resp.text}')
        return resp.json()

    def _rpc(self, function_name: str, payload: dict | None = None):
        cs = _facade()
        rpc_name = str(function_name or '').strip()
        if not rpc_name:
            raise cs.CloudSyncError('Missing RPC function name')
        resp = self._request_with_refresh('POST', f'{cs.SUPABASE_URL}/rest/v1/rpc/{rpc_name}', json=dict(payload or {}), timeout=cs._SUPABASE_REST_TIMEOUT)
        if not resp.ok:
            raise cs.CloudSyncError(f'RPC {rpc_name}: {resp.text}')
        if not resp.content:
            return None
        return resp.json()

    def _patch(self, path: str, payload: dict) -> None:
        cs = _facade()
        resp = self._request_with_refresh('PATCH', f'{cs.SUPABASE_URL}/rest/v1/{path}', json=payload, headers={'Prefer': 'return=minimal'}, timeout=cs._SUPABASE_REST_TIMEOUT)
        if not resp.ok:
            raise cs.CloudSyncError(f'PATCH {path}: {resp.text}')

    def _delete(self, path: str) -> None:
        cs = _facade()
        resp = self._request_with_refresh('DELETE', f'{cs.SUPABASE_URL}/rest/v1/{path}', headers={'Prefer': 'return=minimal'}, timeout=cs._SUPABASE_REST_TIMEOUT)
        if not resp.ok:
            raise cs.CloudSyncError(f'DELETE {path}: {resp.text}')

    def _storage_remove(self, storage_paths: list[str]) -> None:
        cs = _facade()
        cleaned = [key for path in (storage_paths or []) if (key := cs._normalize_cloud_media_key(path))]
        if not cleaned:
            return
        try:
            self._get_media_worker().delete_objects(cleaned)
            cs._increment_sync_summary(cs._cloud_sync_current_summary(), 'storage_quota_delta_rpc_calls')
        except Exception as exc:
            raise cs.CloudSyncError(f'Media delete failed: {exc}') from exc
