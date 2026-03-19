"""
Palmeiras Web - Local Development Server (port 5001)

Serves static files and proxies /api/* to Vercel production.
For full local dev with Python functions, use: vercel dev

Usage:
    python server.py
    open http://localhost:5001
"""
import os
import sys
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.error

PORT = 5001
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PROXY_TARGET = 'https://palmeiras-web.vercel.app'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._proxy()
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def _proxy(self):
        """Proxy /api/* to Vercel production."""
        url = f'{PROXY_TARGET}{self.path}'
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e), 'url': url}).encode())

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


if __name__ == '__main__':
    os.chdir(DIRECTORY)
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Palmeiras Web running at http://localhost:{PORT}')
    print(f'  API proxied to {PROXY_TARGET}')
    print(f'  Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
