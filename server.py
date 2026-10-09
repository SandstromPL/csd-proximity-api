"""HTTP API: GET /search/?lat=<f>&long=<f>&cat=<str>&rad=<f>

Standard library only, so it deploys anywhere with Python 3.
Run:  python3 server.py [--host 0.0.0.0] [--port 8000]
"""

import argparse
import json
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import Grid, search_bfs, search_bruteforce

GRID = Grid()
METHODS = {"bfs": search_bfs, "brute": search_bruteforce}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, params):
        path = urlparse(self.path).path
        if path.rstrip("/") != "/search":
            return self._send(404, {"error": "use /search/?lat=&long=&cat=&rad="})
        try:
            lat, lon = float(params["lat"]), float(params["long"])
            cat, rad = str(params["cat"]).strip().lower(), float(params["rad"])
            if not (math.isfinite(lat) and math.isfinite(lon)):
                raise ValueError("lat/long must be finite numbers")
            method = METHODS[params.get("method", "bfs")]
            t0 = time.perf_counter()
            res = method(GRID, lat, lon, cat, rad,
                         tie=params.get("tie", "id"),
                         radius_mode=params.get("radius_mode", "endpoint"))
            ms = (time.perf_counter() - t0) * 1000
        except KeyError as e:
            return self._send(400, {"error": f"missing or invalid parameter {e}"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        self._send(200, {
            "ids": [i for i, _ in res],
            "results": [{"id": i, "grid_distance": d} for i, d in res],
            "count": len(res),
            "time_ms": round(ms, 3),
        })

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        self._handle({k: v[0] for k, v in q.items()})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "body must be JSON"})
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        self._handle({**q, **body})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"Serving on http://{a.host}:{a.port}/search/")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
