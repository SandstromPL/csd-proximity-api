"""Cross-check the two search methods and measure how much the open choices matter.

  python3 crosscheck.py [N]
"""

import random
import sys
import time

from engine import Grid, search_bfs, search_bruteforce, search_manhattan

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
g = Grid()
rng = random.Random(42)


def query():
    # Mix of on-grid and off-grid points, a range of radii.
    if rng.random() < 0.5:
        v = rng.randrange(len(g.adj))
        lat, lon = g.lat[v], g.lon[v]
    else:
        lat, lon = rng.random(), rng.random()
    return lat, lon, rng.choice(g.categories), rng.choice([0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 1.5])


def ids(r):
    return [i for i, _ in r]


qs = [query() for _ in range(N)]

# Boundary-heavy cases: on-grid centres with radii that land exactly on grid points.
step = g.lon_vals[1] - g.lon_vals[0]
edge_qs = []
for _ in range(N):
    v = rng.randrange(len(g.adj))
    a, b = rng.randint(0, 6), rng.randint(0, 6)
    edge_qs.append((g.lat[v], g.lon[v], rng.choice(g.categories), step * (a * a + b * b) ** 0.5))

bad = 0
for q in qs + edge_qs:
    lat, lon, cat, rad = q
    if g.count_in_circle(*q) != sum(g.eligible(v, lat, lon, cat, rad) for v in range(len(g.adj))):
        bad += 1
        print("COUNT MISMATCH", q)
print(f"[0] count_in_circle vs full scan over {2 * N} queries: {bad} mismatches\n")
qs += edge_qs
mismatch = {"endpoint": 0, "path": 0}
for mode in mismatch:
    for tie in ("id", "euclid"):
        for q in qs:
            a, b = search_bfs(g, *q, tie=tie, radius_mode=mode), search_bruteforce(g, *q, tie=tie, radius_mode=mode)
            if a != b:
                mismatch[mode] += 1
                print("MISMATCH", mode, tie, q, a, b)
print(f"\n[1] BFS-early-stop vs brute force over {len(qs)} queries x 2 tie rules:", mismatch)


def overlap(f1, f2):
    """Average IDs that differ (out of 10) among queries with >= 10 results under both."""
    diff = cnt = whole = 0
    for q in qs:
        a, b = ids(f1(q)), ids(f2(q))
        if len(a) < 10 or len(b) < 10:
            continue
        cnt += 1
        d = len(set(a) - set(b))
        diff += d
        whole += d > 0
    return f"{diff / cnt:.2f} IDs/query differ, {100 * whole / cnt:.1f}% of queries affected (n={cnt})"


print("\n[2] Sensitivity to modelling choices (all on the same queries):")
print("  tie id vs tie euclid      :", overlap(lambda q: search_bfs(g, *q), lambda q: search_bfs(g, *q, tie="euclid")))
print("  radius endpoint vs path   :", overlap(lambda q: search_bfs(g, *q), lambda q: search_bfs(g, *q, radius_mode="path")))
print("  graph BFS vs Manhattan    :", overlap(lambda q: search_bfs(g, *q), lambda q: search_manhattan(g, *q)))

print("\n[3] Timing (mean per query):")
for name, f in (("bfs early-stop", search_bfs), ("brute force", search_bruteforce)):
    t0 = time.perf_counter()
    for q in qs:
        f(g, *q)
    print(f"  {name:15s} {(time.perf_counter() - t0) / N * 1000:.3f} ms")
