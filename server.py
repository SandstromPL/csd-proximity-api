"""HTTP API: /search/ with fields lat, long, cat, rad, link

`link` is the road-linkage .txt file. It may be sent as
  - a file upload            curl -F lat=0.5 -F long=0.5 -F cat=bank -F rad=0.1 -F link=@link.txt URL
  - the file text in a form field, JSON string, or raw text/plain POST body
  - an http(s) URL to the file, or the name of a file in assets/
and defaults to assets/link.txt when omitted.

Standard library only (no `cgi`, which Python 3.13+ removed), so it runs on any Python 3.8+.
Run:  python3 server.py [--host 0.0.0.0] [--port 8000]
"""

import argparse
import json
import math
import os
import threading
import time
import urllib.request
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import DATA_DIR, Grid, search_bfs, search_bruteforce

GRID = Grid()
GRID_LOCK = threading.Lock()
METHODS = {"bfs": search_bfs, "brute": search_bruteforce}
MAX_BODY = 50 * 1024 * 1024
USAGE = "use /search/ with lat, long, cat, rad and optional link (road-link .txt file)"


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def resolve_grid(link):
    """Return (grid, source) for the request's link field."""
    if link is None or not _text(link).strip():
        return GRID, "default:assets/link.txt"
    text = _text(link).strip()
    if text.startswith(("http://", "https://")) and "\n" not in text:
        with urllib.request.urlopen(text, timeout=10) as r:
            text, source = _text(r.read(MAX_BODY)), "url"
    elif "\n" not in text and os.path.basename(text) == text and os.path.isfile(os.path.join(DATA_DIR, text)):
        with open(os.path.join(DATA_DIR, text)) as f:
            text, source = f.read(), f"file:assets/{text}"
    else:
        source = "uploaded"
    with GRID_LOCK:
        return GRID.with_links(text), source


def parse_multipart(content_type, body):
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    fields = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            fields[name] = part.get_payload(decode=True) or b""
    return fields


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
            if not (math.isfinite(lat) and math.isfinite(lon)):
                raise ValueError("lat/long must be finite numbers")
            method = METHODS[_text(params.get("method", "bfs"))]
            t0 = time.perf_counter()
            grid, source = resolve_grid(params.get("link"))
            res = method(grid, lat, lon, cat, rad,
                         tie=_text(params.get("tie", "id")),
                         radius_mode=_text(params.get("radius_mode", "endpoint")))
            ms = (time.perf_counter() - t0) * 1000
        except KeyError as e:
            return self._send(400, {"error": f"missing or invalid parameter {e}; {USAGE}"})
        except (ValueError, OSError) as e:
            return self._send(400, {"error": str(e)})
        self._send(200, {
            "ids": [i for i, _ in res],
            "results": [{"id": i, "grid_distance": d} for i, d in res],
            "count": len(res),
            "link": {"source": source, **grid.link_stats},
            "time_ms": round(ms, 3),
        })

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        self._handle({k: v[0] for k, v in q.items()})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "request body too large"})
        body = self.rfile.read(n)
        params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
        ctype = self.headers.get("Content-Type", "")
        try:
            if ctype.startswith("multipart/form-data"):
                params.update(parse_multipart(ctype, body))
            elif ctype.startswith("application/x-www-form-urlencoded"):
                params.update({k: v[0] for k, v in parse_qs(_text(body), keep_blank_values=True).items()})
            elif body.lstrip().startswith(b"{"):
                params.update(json.loads(body))
            elif body.strip():
                params["link"] = body  # raw link file as the body, fields in the query string
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": f"could not parse request body: {e}"})
        self._handle(params)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"Serving on http://{a.host}:{a.port}/search/")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
