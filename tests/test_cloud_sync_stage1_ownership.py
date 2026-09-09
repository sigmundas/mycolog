"""Stage 1 ownership and import-compatibility checks."""
from __future__ import annotations

import subprocess
import sys

from utils import cloud_sync
from utils.cloud_sync_impl import pagination, pull_only, transport


def test_facade_reexports_stage1_remote_boundary_owners():
    assert cloud_sync.PullOnlyCloudClient is pull_only.PullOnlyCloudClient
    assert cloud_sync._PULL_ONLY_BLOCKED_CLIENT_METHODS is pull_only._PULL_ONLY_BLOCKED_CLIENT_METHODS
    assert cloud_sync._PULL_ONLY_ALLOWED_READ_METHODS is pull_only._PULL_ONLY_ALLOWED_READ_METHODS
    assert cloud_sync._PULL_ONLY_ALLOWED_RPC_NAMES is pull_only._PULL_ONLY_ALLOWED_RPC_NAMES
    assert cloud_sync.SporelyCloudClient._get is transport.CloudTransportMixin._get
    assert cloud_sync.SporelyCloudClient._get_paginated is pagination.CloudPaginationMixin._get_paginated


def test_stage1_leaf_and_facade_imports_work_in_fresh_processes():
    for statement in (
        'import utils.cloud_sync',
        'import utils.cloud_sync_impl.transport; import utils.cloud_sync_impl.pagination; import utils.cloud_sync_impl.pull_only',
    ):
        result = subprocess.run([sys.executable, '-c', statement], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_every_sync_client_method_is_explicitly_read_or_write_classified():
    """New sync-facing client operations must declare their pull-only safety."""
    sync_surface = {
        'fetch_current_user_id', 'fetch_cloud_plan_profile', 'list_remote_observations',
        'list_remote_calibrations', 'pull_bulk_image_metadata', 'pull_image_metadata',
        'pull_measurements_for_images', 'pull_observation_identifications', 'download_image_file',
        'list_image_changes_since', 'list_measurement_changes_since', '_get', 'get_read_only',
        '_patch', '_post', '_delete', '_storage_remove', 'push_observation',
        'push_image_metadata', 'push_measurement', 'upload_image_file',
        'upload_original_image_file', 'set_image_storage_path', 'set_image_desktop_id',
        'set_desktop_id', 'set_measurement_desktop_id', 'set_image_original_storage_path',
        'reserve_image_storage_path_for_promotion', 'release_image_storage_path_reservation',
        'soft_delete_image', 'delete_cloud_observation', 'delete_cloud_measurements_for_image',
        'push_calibration_reference_image', 'push_calibration_metadata',
    }
    classified = (
        cloud_sync._PULL_ONLY_ALLOWED_READ_METHODS
        | cloud_sync._PULL_ONLY_BLOCKED_CLIENT_METHODS
    )
    assert sync_surface <= classified
