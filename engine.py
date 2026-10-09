"""Nearest-location search on a 100x100 grid road network.

Data:
  locations.csv : ID,Latitude,Longitude,Category          (loaded once)
  link file     : one road per line, "a b" with a, b grid points. Supplied per
                  request; assets/link.txt is the default. Accepted line forms:
                    Lon_A Lat_A Lon_B Lat_B     (sample format: longitude first!)
                    Lon_A,Lat_A Lon_B,Lat_B
                    ID_A ID_B

Model:
  - Eligibility: category matches AND Euclidean distance from the raw query
    point to the location is <= rad.
  - Ranking: shortest-path hop count on the link graph (unweighted -> BFS),
    starting from the grid node nearest to the query point.
  - Ties: broken by a configurable key (default: location ID ascending).

Two methods are provided and must agree:
  search_bfs        - BFS that stops once the top 10 is settled (fast path).
  search_bruteforce - full BFS over the whole graph, filter, then sort (reference).
"""

import bisect
import copy
import csv
import hashlib
import math
import os
import re
from collections import OrderedDict, deque

K = 10
EPS = 1e-9
SNAP_TOL = 1e-3  # a link endpoint must be this close to a grid value (spacing ~0.0101)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_SEPARATORS = re.compile(r"[,;()\[\]]")


class Grid:
    def __init__(self, loc_path=None, link_path=None):
        loc_path = loc_path or os.path.join(DATA_DIR, "locations.csv")
        link_path = link_path or os.path.join(DATA_DIR, "link.txt")

        rows = list(csv.DictReader(open(loc_path, newline="")))
        # Map the exact coordinate strings to indices; never divide floats.
        self.lat_vals = sorted({float(r["Latitude"]) for r in rows})
        self.lon_vals = sorted({float(r["Longitude"]) for r in rows})
        lat_idx = {v: i for i, v in enumerate(self.lat_vals)}
        lon_idx = {v: i for i, v in enumerate(self.lon_vals)}
        self.nrows, self.ncols = len(self.lat_vals), len(self.lon_vals)

        n = self.nrows * self.ncols
        self.id = [0] * n          # node -> location ID
        self.lat = [0.0] * n
        self.lon = [0.0] * n
        self.cat = [""] * n
        for r in rows:
            la, lo = float(r["Latitude"]), float(r["Longitude"])
            v = lat_idx[la] * self.ncols + lon_idx[lo]
            self.id[v], self.lat[v], self.lon[v], self.cat[v] = int(r["ID"]), la, lo, r["Category"]
        self.categories = sorted(set(self.cat))

        # row_prefix[cat][r][c] = number of `cat` locations in row r, columns [0, c).
        self.row_prefix = {}
        for c_name in self.categories:
            table = []
            for r in range(self.nrows):
                acc = [0]
                for c in range(self.ncols):
                    acc.append(acc[-1] + (self.cat[r * self.ncols + c] == c_name))
                table.append(acc)
            self.row_prefix[c_name] = table

        self.node_of_id = {self.id[v]: v for v in range(n)}

        self._cache = OrderedDict()  # sha1(link text) -> Grid view
        with open(link_path) as f:
            self.adj, self.link_stats = self.parse_links(f.read())

    def parse_links(self, text):
        """Build an adjacency list from link-file text. Returns (adj, stats)."""
        n = self.nrows * self.ncols
        adj = [set() for _ in range(n)]
        stats = {"lines": 0, "edges": 0, "skipped": 0, "off_grid": 0, "non_adjacent": 0}
        for line in text.splitlines():
            parts = _SEPARATORS.sub(" ", line).split()
            if not parts:
                continue
            stats["lines"] += 1
            try:
                if len(parts) == 4:
                    lon_a, lat_a, lon_b, lat_b = map(float, parts)
                    a, b = self._node_on_grid(lat_a, lon_a), self._node_on_grid(lat_b, lon_b)
                elif len(parts) == 2:
                    a, b = self.node_of_id.get(int(parts[0])), self.node_of_id.get(int(parts[1]))
                else:
                    raise ValueError
            except ValueError:  # header, comment or malformed line
                stats["skipped"] += 1
                continue
            if a is None or b is None:
                stats["off_grid"] += 1
                continue
            if a == b:
                stats["skipped"] += 1
                continue
            ra, ca = divmod(a, self.ncols)
            rb, cb = divmod(b, self.ncols)
            if abs(ra - rb) + abs(ca - cb) != 1:
                # Spec says links only join neighbours; keep it as one hop anyway.
                stats["non_adjacent"] += 1
            if b not in adj[a]:
                adj[a].add(b)
                adj[b].add(a)
                stats["edges"] += 1
        # Sorted lists: deterministic neighbour order and fast iteration.
        return [sorted(s) for s in adj], stats

    def with_links(self, text):
        """A view of this grid that uses the given link text (cached by content)."""
        key = hashlib.sha1(text.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        adj, stats = self.parse_links(text)
        if stats["edges"] == 0:
            raise ValueError(f"link file contains no usable links: {stats}")
        view = copy.copy(self)  # shares the location arrays; only adj differs
        view.adj, view.link_stats = adj, stats
        self._cache[key] = view
        if len(self._cache) > 8:
            self._cache.popitem(last=False)
        return view

    def _node_on_grid(self, lat, lon):
        r = self._nearest(self.lat_vals, lat)
        c = self._nearest(self.lon_vals, lon)
        if abs(self.lat_vals[r] - lat) > SNAP_TOL or abs(self.lon_vals[c] - lon) > SNAP_TOL:
            return None
        return r * self.ncols + c

    @staticmethod
    def _nearest(vals, x):
        i = bisect.bisect_left(vals, x)
        if i == 0:
            return 0
        if i == len(vals):
            return len(vals) - 1
        return i if vals[i] - x < x - vals[i - 1] else i - 1

    def _node_exact(self, lat, lon):
        return self._nearest(self.lat_vals, lat) * self.ncols + self._nearest(self.lon_vals, lon)

    def snap(self, lat, lon):
        """Grid node nearest (Euclidean) to an arbitrary query point."""
        return self._node_exact(lat, lon)

    def euclid2(self, v, lat, lon):
        return (self.lat[v] - lat) ** 2 + (self.lon[v] - lon) ** 2

    def in_circle(self, v, lat, lon, rad):
        return self.euclid2(v, lat, lon) <= rad * rad + EPS

    def eligible(self, v, lat, lon, cat, rad):
        return self.cat[v] == cat and self.in_circle(v, lat, lon, rad)

    def count_in_circle(self, lat, lon, cat, rad):
        """Exact number of eligible locations, in O(rows spanned * log cols).

        Per row the circle covers one contiguous column run; bisect a slightly
        widened run, then trim both ends with the same in_circle() test that
        eligible() uses, so the count can never be lower than the true one.
        """
        slack = 1e-6
        r_lo = bisect.bisect_left(self.lat_vals, lat - rad - slack)
        r_hi = bisect.bisect_right(self.lat_vals, lat + rad + slack)
        prefix = self.row_prefix[cat]
        total = 0
        for r in range(r_lo, r_hi):
            half = math.sqrt(max(0.0, rad * rad + EPS - (self.lat_vals[r] - lat) ** 2))
            c_lo = bisect.bisect_left(self.lon_vals, lon - half - slack)
            c_hi = bisect.bisect_right(self.lon_vals, lon + half + slack) - 1
            base = r * self.ncols
            while c_lo <= c_hi and not self.in_circle(base + c_lo, lat, lon, rad):
                c_lo += 1
            while c_hi >= c_lo and not self.in_circle(base + c_hi, lat, lon, rad):
                c_hi -= 1
            if c_lo <= c_hi:
                total += prefix[r][c_hi + 1] - prefix[r][c_lo]
        return total

    def tie_key(self, tie, v, d, lat, lon):
        if tie == "euclid":
            return (d, round(self.euclid2(v, lat, lon), 12), self.id[v])
        return (d, self.id[v])


def _check(grid, cat, rad):
    if cat not in grid.categories:
        raise ValueError(f"unknown category {cat!r}; expected one of {grid.categories}")
    if not (rad >= 0 and math.isfinite(rad)):
        raise ValueError("rad must be a non-negative number")


def _passable(grid, v, lat, lon, rad, radius_mode):
    # 'endpoint': roads outside the circle may be used; only the result must be inside.
    # 'path'    : the whole route must stay inside the circle.
    return radius_mode == "endpoint" or grid.in_circle(v, lat, lon, rad)


def search_bfs(grid, lat, lon, cat, rad, k=K, tie="id", radius_mode="endpoint"):
    """Layered BFS from the snapped node; stops after the layer that completes the top k.

    If fewer than k locations are eligible at all, it stops as soon as every one
    of them has been reached instead of exhausting the graph.
    """
    _check(grid, cat, rad)
    # In 'path' mode some of these may be unreachable; the BFS then simply
    # runs out of frontier, so an over-estimate here is always safe.
    target = min(k, grid.count_in_circle(lat, lon, cat, rad))
    if target == 0:
        return []
    src = grid.snap(lat, lon)
    seen = {src}
    layer, d = [src], 0
    found = []  # (key, node)
    while layer:
        for v in layer:
            if grid.eligible(v, lat, lon, cat, rad):
                found.append((grid.tie_key(tie, v, d, lat, lon), v))
        # Everything in later layers has distance > d, so once we hold k
        # results after finishing layer d, the top k cannot change. With fewer
        # than k eligible in total, holding all of them is also final.
        if len(found) >= target:
            break
        nxt = []
        for v in layer:
            for w in grid.adj[v]:
                if w not in seen and _passable(grid, w, lat, lon, rad, radius_mode):
                    seen.add(w)
                    nxt.append(w)
        layer, d = nxt, d + 1
    found.sort()
    return [(grid.id[v], key[0]) for key, v in found[:k]]


def bfs_all(grid, src, lat=None, lon=None, rad=None, radius_mode="endpoint"):
    dist = [-1] * len(grid.adj)
    dist[src] = 0
    q = deque([src])
    while q:
        v = q.popleft()
        for w in grid.adj[v]:
            if dist[w] < 0 and (rad is None or _passable(grid, w, lat, lon, rad, radius_mode)):
                dist[w] = dist[v] + 1
                q.append(w)
    return dist


def search_bruteforce(grid, lat, lon, cat, rad, k=K, tie="id", radius_mode="endpoint"):
    """Reference: distances to every node, filter every node, full sort."""
    _check(grid, cat, rad)
    dist = bfs_all(grid, grid.snap(lat, lon), lat, lon, rad, radius_mode)
    cands = [
        (grid.tie_key(tie, v, dist[v], lat, lon), v)
        for v in range(len(dist))
        if dist[v] >= 0 and grid.eligible(v, lat, lon, cat, rad)
    ]
    cands.sort()
    return [(grid.id[v], key[0]) for key, v in cands[:k]]


def search_manhattan(grid, lat, lon, cat, rad, k=K):
    """Ignores the link graph (assumes every road exists). For comparison only."""
    _check(grid, cat, rad)
    src = grid.snap(lat, lon)
    r0, c0 = divmod(src, grid.ncols)
    cands = []
    for v in range(len(grid.adj)):
        if grid.eligible(v, lat, lon, cat, rad):
            r, c = divmod(v, grid.ncols)
            cands.append(((abs(r - r0) + abs(c - c0), grid.id[v]), v))
    cands.sort()
    return [(grid.id[v], key[0]) for key, v in cands[:k]]
