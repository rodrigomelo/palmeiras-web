"""Compatibility wrapper for the collector service.

The real collector implementation lives in services.collector.palmeiras_collector.
"""

from services.collector import palmeiras_collector as _impl
from services.collector.palmeiras_collector import *

_deterministic_external_id = _impl._deterministic_external_id
_match_to_record = _impl._match_to_record
_sanitize_match_record = _impl._sanitize_match_record
