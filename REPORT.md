# Lab 07 — Nearest-Location Recommendation API

**Course:** Computer System Design  **Author:** Paritosh L.
**Code:** `engine.py` (algorithms), `server.py` (HTTP API), `crosscheck.py` (validation)
**Data:** `docs/locations.csv`, `docs/link.txt`  **Assignment material:** `assets/`

---

## 1. Problem statement

Build an API at `IP/search/` with fields `lat, long, cat, rad`. It returns the IDs of the **10 closest locations** that:

1. have category `cat`, and
2. lie within **circular (Euclidean) distance** `rad` of the query point.

"Closest" means **traversal distance on the grid road network**, not straight-line distance. Some roads between neighbouring locations are missing.

Formally, for query `q = (lat, long)`:

```
Result = Top-10 by d_road(q, p)  over  { p : category(p) = cat  and  d_euclid(q, p) <= rad }
```

The two distances serve different purposes:

| Purpose | Metric |
|---|---|
| Eligibility (inside radius?) | Euclidean distance from the query point |
| Ranking (which is closest?) | Shortest-path hop count on the road graph |

---

## 2. Input data and analysis

### 2.1 `locations.csv`

| Property | Observation |
|---|---|
| Rows | 10,000 (the "≈1,000,000" in the spec is treated as a typo; see §7) |
| Columns | `ID, Latitude, Longitude, Category` |
| Distinct latitudes / longitudes | 100 / 100, spacing 1/99 ≈ 0.010101, range [0, 1] |
| Grid completeness | Full 100 × 100 grid, no duplicates, no gaps |
| ID layout | Row-major: `ID = row·100 + col + 1` (row = latitude index) |
| Categories | 8 (`bank, cafe, hospital, park, pharmacy, restaurant, school, store`), 1,250 each |

### 2.2 `link.txt` (road network, supplied later)

The format is `Longitude_A Latitude_A Longitude_B Latitude_B`. **Longitude comes first, the opposite of the CSV.** The supplied note says that all points are on the grid, that there are no diagonal links, and that links exist only between neighbours.

| Property | Observation |
|---|---|
| Links | 14,800 undirected (full 4-neighbour grid would have 19,800 → **5,000 roads missing, ~25 %**) |
| Validity | All endpoints are grid points; all links join 4-neighbours; no duplicates |
| Connectivity | **1 connected component**: every location is reachable from every other |
| Degree distribution | deg 1: 111 (dead ends), deg 2: 2,601, deg 3: 4,865, deg 4: 2,423 |
| Detour vs. Manhattan | Mean road/Manhattan ratio ≈ 1.06, worst case 9× |

### 2.3 Consequences of the analysis

- The road graph is **fully specified**, so traversal distance is computable exactly. No guessing or reconstruction is needed.
- All edges are **unweighted** (one grid step each), so shortest path = **BFS hop count**. Dijkstra or A* would add nothing.
- Manhattan distance is **not** a valid substitute because of the missing roads. It changes the top-10 in 86 % of queries (§6).
- Geometric indexes such as KD-trees, R-trees and PostGIS can only help with the radius filter. They cannot rank by road distance. With a regular grid, direct index arithmetic is simpler and faster.

---

## 3. Assumptions

Each assumption is listed with its justification and, where measured, its impact (§6).

| # | Assumption | Justification | Measured impact if wrong |
|---|---|---|---|
| A1 | Road distance = number of edges on the shortest path in `link.txt` (each edge cost 1) | Grid is uniform; note says links only between neighbours; no weights provided | — (core model) |
| A2 | Radius is checked as Euclidean distance from the **raw query point** to the **location**, in the same unit-square units as the coordinates | Spec: "Radius is the circular distance from the current latitude and longitude" | — |
| A3 | **Endpoint-only radius**: routes may pass through nodes outside the circle; only the returned location must be inside | Spec constrains *which locations* are valid, not the route | Path-restricted variant differs in only **0.1 %** of queries |
| A4 | **Off-grid query points are snapped** to the nearest grid node (nearest latitude value × nearest longitude value = Euclidean nearest node) to start the traversal | Traversal must start from a graph node; nearest node is the natural choice | Not measurable without hidden queries; zero effect when queries are on-grid |
| A5 | **Ties** in road distance are broken by **smaller location ID** | Deterministic, simple, likely in a reference implementation | Alternative (closer Euclidean first) differs in **43 %** of queries (~0.5 IDs each). **Largest open risk** |
| A6 | Boundary inclusion: `d_euclid ≤ rad` with ε = 1e-9 tolerance | Avoids floating-point exclusion of points exactly on the circle | Only affects boundary-exact cases |
| A7 | Category match is case-insensitive (`Bank` = `bank`), whitespace-trimmed | Robustness; CSV categories are all lower-case | None on valid input |
| A8 | Dataset size is 10,000 (not 1,000,000) | The supplied file has 10,000 rows; evaluation section says 10,000 | Algorithm still scales; see §7 |
| A9 | If fewer than 10 locations qualify, return all that do (sorted) | Spec guarantees ≥ 10 for the hidden queries; graceful otherwise | None for evaluation |
| A10 | Coordinates are mapped to indices by **lookup of the 100 known values**, never by dividing floats | Avoids `x / 0.010101` rounding errors | — |

---

## 4. Design: the two methods

Both methods use the same data structures and the same model (A1–A10). They differ only in how much of the graph they explore.

### 4.1 Preprocessing (once, at startup)

1. Read the CSV. Map each distinct latitude and longitude to an index (0–99), and store each location at node `v = row·100 + col`. Arrays hold `id[v]`, `lat[v]`, `lon[v]` and `cat[v]`.
2. Read `link.txt`. **Swap the order to (lat, lon)**, map both endpoints to nodes, and build an adjacency list. Neighbours are sorted for determinism.
3. Cost: O(V + E) time and memory, with V = 10,000 and E = 14,800. It takes about 0.1 s.

### 4.2 Method 1: Layered BFS with early stopping (`search_bfs`, served by the API)

```
src  = snap(lat, long)                       # A4
layer = [src], d = 0, found = []
while layer not empty:
    for v in layer:
        if cat[v] == cat and euclid(v, q) <= rad:  found.add((d, id[v]))
    if |found| >= 10: break                  # top-10 is now final
    layer = unvisited neighbours of layer;  d += 1
return the 10 smallest (d, id) in found
```

**Why the early stop is correct.**
- BFS visits nodes in non-decreasing road distance, and every node in layer `d` has distance exactly `d`.
- Stopping happens only *after a full layer* has been processed. So when there are ≥ 10 candidates, every unseen node has distance > `d`.
- Any unseen node therefore ranks strictly behind all current candidates, so it cannot enter the top 10.
- Ties *within* the last layer are all collected before the sort, so the tie-break (A5) is applied over the complete tied set.
- The search is not pruned at the radius boundary, because under A3 a shortest route may leave the circle and come back.

**Complexity.** The worst case is O(V + E) per query. In practice it touches only the nodes within the 10th-result distance: on average **~117 of 10,000 nodes**, about **0.21 ms** per query.

### 4.3 Method 2: Brute-force reference (`search_bruteforce`)

1. Run a full BFS from `src` to get the road distance to **every** node.
2. Keep every node with a matching category, inside the radius, and reachable.
3. Sort all of them by `(distance, id)` and take the first 10.

It has no early stopping and no cleverness, so it is easy to verify by inspection. It costs O(V + E + m log m) per query, about **2.26 ms**.

Its purpose is to serve as the **ground truth for validating Method 1**. Any difference between the two would expose a bug in the early-stopping logic.

### 4.4 Supporting variants (for analysis only)

- `tie="euclid"`: break ties by Euclidean distance, then ID (tests A5).
- `radius_mode="path"`: the BFS may only traverse nodes inside the circle (tests A3). This is implemented in both methods.
- `search_manhattan`: ignores `link.txt` and assumes every road exists. It shows why the road graph matters.

### 4.5 Approaches considered and rejected

| Approach | Reason rejected |
|---|---|
| Rank by Euclidean distance | Spec explicitly says ranking is by traversal distance |
| Rank by Manhattan distance | Ignores the 5,000 missing roads; wrong in 86 % of queries |
| Dijkstra / A* | Edges unweighted → BFS is optimal; A* targets a single known destination, not "nearest 10" |
| KD-tree / R-tree / PostGIS | Only geometric; cannot produce road distance; overkill for a regular grid |
| All-pairs precomputation (10⁴ × 10⁴) | 100 M distances (~200 MB+), unnecessary when a query takes 0.2 ms |
| Approximate NN | Scoring rewards exact ID matches |

---

## 5. API

The API uses only the Python 3 standard library (`http.server`), so there are no dependencies to install.

```
python3 server.py --host 0.0.0.0 --port 8000
GET  http://<IP>:8000/search/?lat=0.5&long=0.5&cat=bank&rad=0.1
POST http://<IP>:8000/search/      body: {"lat":0.5,"long":0.5,"cat":"bank","rad":0.1}
```

Example response:

```json
{"ids": [4850, 4948, 4648, 4753, 4947, 5349, 4451, 5348, 4351, 4654],
 "results": [{"id": 4850, "grid_distance": 1}, {"id": 4948, "grid_distance": 4}, ...],
 "count": 10, "time_ms": 0.1}
```

- `ids` is the required output: 10 location IDs, nearest first.
- Bad input returns HTTP 400 with a message. This covers an unknown category, a missing or non-numeric field, and a negative radius.
- `/search` without a trailing slash is also accepted.
- Optional parameters `method=brute`, `tie=euclid` and `radius_mode=path` expose the variants. The defaults are what the evaluator hits.

---

## 6. Validation and sensitivity analysis

`python3 crosscheck.py 2000` runs 2,000 random queries (seed 42):
- half are on grid points and half are arbitrary off-grid points;
- the category is random;
- `rad` is drawn from {0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 1.5}.

### 6.1 Method 1 vs. Method 2 (correctness)

| Configuration | Mismatches |
|---|---|
| endpoint radius, tie by ID | 0 / 2000 |
| endpoint radius, tie by Euclid | 0 / 2000 |
| path radius, tie by ID | 0 / 2000 |
| path radius, tie by Euclid | 0 / 2000 |

The early-stopping BFS returns **exactly** the same IDs, in the same order, as the brute-force reference in all 8,000 comparisons.

### 6.2 Sensitivity to modelling choices

These compare the default configuration against one changed choice. They are computed over queries with ≥ 10 results under both configurations.

| Changed choice | Queries whose top-10 changes | Avg. IDs changed (of 10) | Interpretation |
|---|---|---|---|
| Tie: ID → Euclidean | 43.4 % | 0.49 | Ties at the 10th position are common; the rule matters |
| Radius: endpoint → path-restricted | 0.1 % | 0.00 | Practically irrelevant on this data |
| Road BFS → Manhattan (no missing roads) | 86.2 % | 1.60 | The road network is essential |

### 6.3 Performance

| Method | Mean time per query | Nodes touched (avg) |
|---|---|---|
| BFS early-stop (served) | 0.21 ms | ~117 |
| Brute force (reference) | 2.26 ms | 10,000 |

---

## 7. Scalability

- Preprocessing is linear. Memory is O(V + E), which is a few MB at 10⁴ nodes and a few hundred MB in pure Python at 10⁶.
- Early-stop BFS cost depends on the **local density** of the requested category, not on the total dataset size. With 8 balanced categories it explores roughly 10 × 8 × (detour factor) nodes, whether the grid is 10⁴ or 10⁶.
- For a larger grid the same code works unchanged. Moving the arrays to NumPy would reduce memory.

---

## 8. Limitations and open risks

1. **Tie-breaking (A5)** is the main risk. The evaluator's rule is unknown, and it changes results in ~43 % of random queries. The scoring impact is bounded because typically only one ID differs.
2. **Off-grid snapping (A4)**: if the evaluator starts from a different node, for example the nearest *eligible* node, results may differ for off-grid queries.
3. The radius is planar Euclidean in unit-square units. It is not a geodesic or kilometre distance, because the coordinates are in [0, 1].
4. The server is a single-process standard-library HTTP server. That is adequate for evaluation; a production deployment would use a WSGI/ASGI server behind a reverse proxy.

---

## 9. Summary

- The dataset is a complete 100 × 100 grid. The supplied links form a connected, unweighted road graph with 25 % of roads missing.
- The correct ranking metric is therefore BFS hop count. Eligibility is a Euclidean radius check from the query point.
- The served method is a layered BFS with a provably safe early stop. It was cross-checked against an exhaustive reference with **0 mismatches in 8,000 comparisons**.
- It is about **10× faster** (0.2 ms per query).
- The only material uncertainty is the evaluator's tie-break rule, which is documented above.
