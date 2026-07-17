"""
Palmeiras Agenda local development server.

This server is an adapter only: static web files come from apps/web and API
requests are dispatched to services/api/palmeiras_api, the same backend package
used by production.
"""

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from services.api.palmeiras_api import dispatch_request

DIRECTORY = Path(__file__).parent
WEB_ROOT = DIRECTORY / "apps" / "web"
if not WEB_ROOT.exists():
    WEB_ROOT = DIRECTORY

ENV_PATH = DIRECTORY / ".env"
if ENV_PATH.exists():
    with ENV_PATH.open() as env_file:
        for line in env_file:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5001"))
DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:5001",
    "http://localhost:3000",
    "https://palmeiras.rodrigolanna.com.br",
}
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
} or DEFAULT_ALLOWED_ORIGINS


class Handler(SimpleHTTPRequestHandler):
    """Static web + shared API request handler for local development."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' https: data:; "
            "connect-src 'self' https://*.supabase.co https://palmeiras.rodrigolanna.com.br; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")

    def end_headers(self):
        self._send_security_headers()
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if any(part.startswith(".") for part in Path(path).parts):
            self.send_error(404)
            return

        response = dispatch_request(path, parsed.query)
        if response is not None:
            self._send_api_response(response)
            return

        if path == "/":
            self.path = "/index.html"

        if path == "/sw.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write((WEB_ROOT / "sw.js").read_bytes())
            return

        return super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if any(part.startswith(".") for part in Path(path).parts):
            self.send_error(404)
            return

        response = dispatch_request(path, parsed.query)
        if response is not None:
            self._send_api_response(response, include_body=False)
            return

        if path == "/":
            self.path = "/index.html"

        if path == "/sw.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return

        return super().do_HEAD()

    def _send_api_response(self, response, include_body=True):
        status, data, content_type, cache_control = response
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        if not include_body:
            return
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode("utf-8")
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


class PalmeirasHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_URL") or not (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLIC_KEY")
        or os.environ.get("SUPABASE_KEY")
    ):
        print("WARNING: Supabase env vars are not configured; API routes will return 503.", file=sys.stderr)

    print(f"Palmeiras Agenda running at http://{HOST}:{PORT}")
    print(f"Serving web app from {WEB_ROOT}")
    server = PalmeirasHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
