"""Compatibility exports for older imports.

The backend implementation lives in services.api.palmeiras_api. Keep this file
thin so compatibility imports cannot drift from the shared service package.
"""

from services.api.palmeiras_api.adapters import write_response
from services.api.palmeiras_api.shared import *


def json_response(handler, status, data, *, cache_control="public, max-age=300"):
    write_response(handler, (status, data, "application/json; charset=utf-8", cache_control))


def text_response(
    handler,
    status,
    text,
    *,
    content_type="text/plain; charset=utf-8",
    cache_control="public, max-age=300",
):
    write_response(handler, (status, text, content_type, cache_control))
