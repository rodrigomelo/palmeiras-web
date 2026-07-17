"""HTTP adapters for the shared Palmeiras API routes."""

import json
from urllib.parse import urlparse

from .routes import dispatch_request


def cors_options_response(handler):
    """Respond to a CORS preflight OPTIONS request."""
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def write_response(handler, response, include_body=True):
    """Write a route response tuple to a BaseHTTPRequestHandler instance."""
    status, data, content_type, cache_control = response
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    if not include_body:
        return

    if isinstance(data, (dict, list)):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    elif isinstance(data, bytes):
        body = data
    else:
        body = str(data).encode("utf-8")
    handler.wfile.write(body)


def write_current_route(handler, include_body=True):
    """Dispatch the current handler path and write its response."""
    parsed = urlparse(handler.path)
    response = dispatch_request(parsed.path, parsed.query)
    if response is None:
        handler.send_error(404)
        return
    write_response(handler, response, include_body=include_body)
