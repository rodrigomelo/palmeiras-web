"""Compatibility adapter for GET /api/news and /api/v1/news."""

from http.server import BaseHTTPRequestHandler

from services.api.palmeiras_api.adapters import (
    cors_options_response,
    write_current_route,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        cors_options_response(self)

    def do_GET(self):
        write_current_route(self)

    def do_HEAD(self):
        write_current_route(self, include_body=False)
