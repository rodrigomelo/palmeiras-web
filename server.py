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

# API configuration is read during module import, so local environment values
# must be loaded first. Production systemd variables are already present.
from services.api.palmeiras_api import dispatch_request  # noqa: E402

HOST = os.environ.get("HOST", "127.0.0.1")
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
            "script-src 'self' https://cdn.jsdelivr.net; "
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
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length") from None
        if length < 2 or length > 64 * 1024:
            raise ValueError("invalid request size")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("application/json required")
        try:
            return json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("invalid JSON") from None

    def _handle_api_mutation(self, method):
        parsed = urlparse(self.path)
        origin = self.headers.get("Origin", "")
        if origin and origin not in ALLOWED_ORIGINS:
            self._send_api_response((403, {"error": "origin_not_allowed"}, "application/json; charset=utf-8", "no-store"))
            return
        try:
            body = self._read_json_body()
        except ValueError as error:
            self._send_api_response((400, {"error": str(error)}, "application/json; charset=utf-8", "no-store"))
            return
        response = dispatch_request(
            parsed.path,
            parsed.query,
            method=method,
            body=body,
            context={"user_agent": self.headers.get("User-Agent", "")},
        )
        if response is None:
            self._send_api_response((404, {"error": "not_found"}, "application/json; charset=utf-8", "no-store"))
            return
        self._send_api_response(response)

    def do_POST(self):
        self._handle_api_mutation("POST")

    def do_DELETE(self):
        self._handle_api_mutation("DELETE")

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
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if not include_body:
            return
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


class PalmeirasHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_URL") or not (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLIC_KEY")
        or (
            os.environ.get("ALLOW_SERVICE_ROLE_PUBLIC_API") == "1"
            and os.environ.get("SUPABASE_KEY")
        )
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
