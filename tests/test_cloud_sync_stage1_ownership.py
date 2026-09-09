"""Stage 1 ownership and import-compatibility checks."""
from __future__ import annotations

import inspect
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


def test_every_relevant_public_client_method_is_explicitly_read_or_write_classified():
    """A new sync-facing client callable must join a canonical pull-only registry."""
    non_sync_public_methods = {
        # Authentication/session construction and credential cleanup.
        'login', 'refresh_login', 'from_stored_credentials', 'clear_session', 'clear_credentials',
        # Profile/account settings and their cloud-side mutations.
        'fetch_current_user_info', 'fetch_profile', 'update_profile', 'upload_profile_avatar',
        'count_remote_privacy_slots',
        # Interactive public/community browsing, outside desktop sync orchestration.
        'pull_web_observations', 'search_community_spore_datasets',
        'get_community_spore_dataset', 'community_spore_taxon_summary',
        'search_public_reference_values',
    }
    public_client_methods = {
        name
        for name, method in inspect.getmembers(cloud_sync.SporelyCloudClient, callable)
        if not name.startswith('_')
    }
    classified = (
        cloud_sync._PULL_ONLY_ALLOWED_READ_METHODS
        | cloud_sync._PULL_ONLY_BLOCKED_CLIENT_METHODS
    )
    assert public_client_methods - non_sync_public_methods <= classified


def test_pull_only_classifies_private_low_level_transport_contract_methods():
    """Private transport primitives remain explicit despite public-surface discovery."""
    assert {'_get', '_refresh_session_if_possible'} <= cloud_sync._PULL_ONLY_ALLOWED_READ_METHODS
    assert {'_post', '_patch', '_delete', '_storage_remove'} <= cloud_sync._PULL_ONLY_BLOCKED_CLIENT_METHODS
