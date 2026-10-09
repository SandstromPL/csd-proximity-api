"""HTTP API: GET /search/?lat=<f>&long=<f>&cat=<str>&rad=<f>&link=<bool>

link=true  -> rank by road distance over the roads in assets/link.txt
link=false -> every neighbouring pair of grid points is connected
The same fields are also accepted in a POST body (form, multipart or JSON).

Standard library only (no `cgi`, which Python 3.13+ removed), so it runs on any Python 3.8+.
Run:  python3 server.py [--host 0.0.0.0] [--port 8000]
"""

import argparse
import json
import math
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import Grid, search_bfs, search_bruteforce

GRID = Grid()
GRID.full_grid()  # build both graphs at startup
METHODS = {"bfs": search_bfs, "brute": search_bruteforce}
TRUE, FALSE = {"true", "1", "yes", "t", "y"}, {"false", "0", "no", "f", "n"}
MAX_BODY = 1024 * 1024
USAGE = "use /search/?lat=&long=&cat=&rad=&link=true|false"


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def parse_bool(value):
    v = _text(value).strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise ValueError(f"link must be true or false, got {_text(value)!r}")


def parse_multipart(content_type, body):
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    return {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) or b""
            for part in msg.iter_parts()}


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
        if urlparse(self.path).path.rstrip("/") != "/search":
            return self._send(404, {"error": USAGE})
        try:
            lat, lon = float(_text(params["lat"])), float(_text(params["long"]))
            cat, rad = _text(params["cat"]).strip().lower(), float(_text(params["rad"]))
            link = parse_bool(params.get("link", "true"))
            if not (math.isfinite(lat) and math.isfinite(lon)):
                raise ValueError("lat/long must be finite numbers")
            method = METHODS[_text(params.get("method", "bfs"))]
            t0 = time.perf_counter()
            res = method(GRID.graph(link), lat, lon, cat, rad,
                         tie=_text(params.get("tie", "id")),
                         radius_mode=_text(params.get("radius_mode", "endpoint")))
            ms = (time.perf_counter() - t0) * 1000
        except KeyError as e:
            return self._send(400, {"error": f"missing or invalid parameter {e}; {USAGE}"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        self._send(200, {
            "ids": [i for i, _ in res],
            "results": [{"id": i, "grid_distance": d} for i, d in res],
            "count": len(res),
            "link": link,
            "time_ms": round(ms, 3),
        })

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        self._handle({k: v[0] for k, v in q.items()})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "request body too large"})
        body = self.rfile.read(n)
        params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        ctype = self.headers.get("Content-Type", "")
        try:
            if ctype.startswith("multipart/form-data"):
                params.update(parse_multipart(ctype, body))
            elif ctype.startswith("application/x-www-form-urlencoded"):
                params.update({k: v[0] for k, v in parse_qs(_text(body)).items()})
            elif body.strip():
                data = json.loads(body)
                # JSON booleans arrive as True/False; parse_bool expects text.
                params.update({k: (str(v).lower() if isinstance(v, bool) else v) for k, v in data.items()})
        except (ValueError, AttributeError) as e:
            return self._send(400, {"error": f"could not parse request body: {e}"})
        self._handle(params)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"Serving on http://{a.host}:{a.port}/search/")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
