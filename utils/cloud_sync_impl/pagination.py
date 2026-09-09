"""Complete deterministic PostgREST pagination for cloud-sync readers."""
from __future__ import annotations

import json


_CLOUD_SYNC_MAX_ROWS_PER_PAGE = 1000


def _facade():
    from utils import cloud_sync
    return cloud_sync


class CloudPaginationMixin:
    def _get_paginated(self, path: str, *, page_size: int = _CLOUD_SYNC_MAX_ROWS_PER_PAGE, max_rows: int | None = None, max_response_bytes: int | None = None) -> list:
        cs = _facade()
        if page_size <= 0 or (max_rows is not None and max_rows <= 0) or (max_response_bytes is not None and max_response_bytes <= 0):
            raise cs.CloudSyncError(f'GET {path}: invalid page_size {page_size}')
        all_rows: list = []
        response_bytes = 0
        offset = 0
        sep = '&' if '?' in path else '?'
        while True:
            rows = self._get(f'{path}{sep}limit={page_size}&offset={offset}')
            if not isinstance(rows, list):
                raise cs.CloudSyncError(f'GET {path}: expected list response for paginated fetch, got {type(rows).__name__}')
            response_bytes += len(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            if max_response_bytes is not None and response_bytes > max_response_bytes:
                raise cs.CloudSyncError(f'GET {path}: response exceeds {max_response_bytes} bytes')
            all_rows.extend(rows)
            if max_rows is not None and len(all_rows) > max_rows:
                raise cs.CloudSyncError(f'GET {path}: response exceeds {max_rows} rows')
            if len(rows) < page_size:
                return all_rows
            offset += len(rows)
