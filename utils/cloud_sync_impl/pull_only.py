"""Strict read/write classification for Download from Cloud."""
from __future__ import annotations

from collections import Counter

from .errors import PullOnlyModeError

_PULL_ONLY_BLOCKED_CLIENT_METHODS = frozenset({
    '_patch', '_post', '_delete', '_storage_remove', 'push_observation', 'push_image_metadata',
    'push_measurement', 'upload_image_file', 'upload_original_image_file', 'set_image_storage_path',
    'set_image_desktop_id', 'set_desktop_id', 'set_observation_selected_taxon',
    'set_measurement_desktop_id', 'set_image_original_storage_path',
    'reserve_image_storage_path_for_promotion', 'release_image_storage_path_reservation',
    'soft_delete_image', 'delete_cloud_observation', 'delete_cloud_measurements_for_image',
    'push_calibration_reference_image', 'push_calibration_metadata', 'sync_reference_work',
    'sync_reference_taxon_treatment', 'sync_reference_measurement_set', 'sync_observation_reference_use',
    'submit_private_reference_for_curation', 'share_reference_contribution',
    'withdraw_reference_contribution', 'sync_reference_curated_fork',
})

_PULL_ONLY_ALLOWED_READ_METHODS = frozenset({
    'fetch_current_user_id', 'fetch_cloud_plan_profile', 'save_credentials', '_refresh_session_if_possible',
    'list_remote_observations', 'get_observation', 'list_remote_calibrations', 'find_remote_calibration',
    'list_reference_works', 'list_reference_taxon_treatments', 'list_reference_measurement_sets',
    'list_observation_reference_uses', 'search_public_curated_reference_sets',
    'get_public_curated_reference_set', 'search_public_reference_contributions',
    'get_public_reference_contribution', 'list_reference_curated_forks', 'pull_bulk_image_metadata',
    'pull_image_metadata', 'pull_measurements_for_images', 'pull_observation_identifications',
    'download_image_file', 'download_image_file_read_only', '_get', 'get_read_only', '_find_cloud_image',
    '_get_media_worker', '_build_original_storage_path', '_observation_images_support_ai_crop',
    '_observation_images_support_ai_crop_custom', '_observation_images_support_sample_source',
    '_observation_images_support_upload_metadata', '_using_default_r', 'list_image_changes_since',
    'list_measurement_changes_since',
})

_PULL_ONLY_ALLOWED_RPC_NAMES = frozenset({
    'search_community_spore_datasets', 'get_community_spore_dataset', 'community_spore_taxon_summary',
    'search_public_reference_values', 'get_public_observation', 'search_public_curated_reference_sets',
    'get_public_curated_reference_set', 'search_public_reference_contributions',
    'get_public_reference_contribution',
})


class PullOnlyCloudClient:
    is_pull_only = True

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped
        self.write_attempts: list[str] = []

    def _block(self, name: str, reason: str):
        def _blocked(*_args, **_kwargs):
            self.write_attempts.append(name)
            raise PullOnlyModeError(f"{reason} '{name}' is not allowed during Download from Cloud")
        return _blocked

    def _rpc(self, function_name: str, payload: dict | None = None):
        rpc_name = str(function_name or '').strip()
        if rpc_name not in _PULL_ONLY_ALLOWED_RPC_NAMES:
            attempt = f'_rpc:{rpc_name or "<missing>"}'
            self.write_attempts.append(attempt)
            raise PullOnlyModeError(f"Unrecognized or write-capable RPC '{rpc_name}' is not allowed during Download from Cloud")
        return self._wrapped._rpc(rpc_name, payload)

    def __getattr__(self, name: str):
        if name in _PULL_ONLY_BLOCKED_CLIENT_METHODS:
            return self._block(name, 'Cloud write')
        attr = getattr(self._wrapped, name)
        if not callable(attr):
            return attr
        if name in _PULL_ONLY_ALLOWED_READ_METHODS:
            return attr
        return self._block(name, 'Unrecognized client method')


def summarize_blocked_write_attempts(attempts) -> str:
    counts = Counter(str(name) for name in attempts if name)
    return ', '.join(f'{name} ×{count}' for name, count in counts.most_common()) if counts else ''
