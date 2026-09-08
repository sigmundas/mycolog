"""Stage 0 ownership verification: confirm mechanical extraction placement is correct."""
from __future__ import annotations

import utils.cloud_sync as cs_facade
import utils.cloud_sync_impl.errors as cs_errors
import utils.cloud_sync_impl.profiling as cs_profiling
import utils.cloud_sync_impl.progress as cs_progress
import utils.cloud_sync_impl.summary as cs_summary


def test_cloud_image_bytes_not_desired_error_identity():
    """CloudImageBytesNotDesiredError is defined once in errors.py and re-exported from facade."""
    assert cs_facade.CloudImageBytesNotDesiredError is cs_errors.CloudImageBytesNotDesiredError
    # Verify it's in the errors module
    assert hasattr(cs_errors, 'CloudImageBytesNotDesiredError')
    assert callable(cs_errors.CloudImageBytesNotDesiredError)


def test_transient_status_codes_identity():
    """_SUPABASE_TRANSIENT_STATUS_CODES is imported from errors, not re-defined in facade."""
    assert cs_facade._SUPABASE_TRANSIENT_STATUS_CODES is cs_errors._SUPABASE_TRANSIENT_STATUS_CODES
    assert cs_facade._SUPABASE_TRANSIENT_STATUS_CODES == {429, 500, 502, 503, 504}


def test_transient_error_hints_identity():
    """_SUPABASE_TRANSIENT_ERROR_HINTS is imported from errors, not re-defined in facade."""
    assert cs_facade._SUPABASE_TRANSIENT_ERROR_HINTS is cs_errors._SUPABASE_TRANSIENT_ERROR_HINTS
    assert 'bad gateway' in cs_facade._SUPABASE_TRANSIENT_ERROR_HINTS
    assert 'timeout' in cs_facade._SUPABASE_TRANSIENT_ERROR_HINTS


def test_temporarily_unavailable_message_identity():
    """_CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE is imported from errors, not re-defined."""
    assert cs_facade._CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE is cs_errors._CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE
    assert 'temporarily unavailable' in cs_facade._CLOUD_TEMPORARILY_UNAVAILABLE_MESSAGE.lower()


def test_cloud_sync_phase_scope_identity():
    """_cloud_sync_phase_scope is defined in profiling.py and re-exported from facade."""
    assert cs_facade._cloud_sync_phase_scope is cs_profiling._cloud_sync_phase_scope
    assert hasattr(cs_profiling, '_cloud_sync_phase_scope')
    assert callable(cs_profiling._cloud_sync_phase_scope)


def test_cloud_sync_phase_scope_not_in_progress():
    """_cloud_sync_phase_scope is not defined in progress.py."""
    assert not hasattr(cs_progress, '_cloud_sync_phase_scope')


def test_summary_no_progress_import():
    """summary.py does not import from progress.py."""
    # Check that summary module source code does not have progress import
    import inspect
    summary_source = inspect.getsource(cs_summary)
    assert 'from .progress import' not in summary_source
    assert 'from progress import' not in summary_source
    # But summary should still be functional
    assert hasattr(cs_summary, '_cloud_sync_summary_scope')
    assert hasattr(cs_summary, '_cloud_sync_current_summary')
