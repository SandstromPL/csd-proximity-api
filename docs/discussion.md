# Discussion Notes: Grid-Based Nearest-Location API Assignment

> Purpose: Preserve the discussion so far about how to reason through the assignment, its concepts, possible algorithm choices, ambiguities, and suggested reading resources.
>
> Important: This document records the assignment details and analysis discussed so far. The intended traversal model must be verified; the road-network wording is ambiguous because no road/link data is supplied.

---

## 1. Assignment objective and requirements

The assignment asks for an API that recommends the 10 closest locations from a supplied dataset.

The specification says:

- The dataset contains location IDs, latitude, longitude, and category.
- Locations lie on a 1 × 1 grid.
- Some direct links/roads between locations may be missing, as in a real-world road network.
- The API accepts current latitude, current longitude, category, search, and radius.
- The route must be `IP/search/`; the fields must be `lat`, `long`, `cat`, and `rad`.
- The API returns 10 recommended location IDs.
- Returned locations must match the requested category and satisfy the search radius.
- Radius means circular distance from the query coordinates, while “closest” means actual traversal distance on the grid.
- No road/link/network information is provided.
- The specification mentions approximately 1,000,000 locations in the dataset description, while the evaluation section says the implementation should handle 10,000 locations.
- There are 10 hidden queries. Each has a precomputed set of 10 true nearest locations. All students are tested against the same hidden queries.
- Every query has at least 10 valid locations.
- Each correct match earns 1 point, for up to 100 matches across 10 queries. API-result marks are points divided by 10, up to 10; report marks are 10.

The central distinction is:

1. **Radius condition:** circular/geometric distance.
2. **Ranking condition:** grid/traversal distance.

These must not be silently treated as the same metric.

## 2. Start with the problem, not the technology

Do not begin by choosing FastAPI, a database, Redis, a KD-tree, or another tool.

First translate the requirements into a precise mathematical/computational problem.

Input:

- Query point `q = (lat, long)`
- Requested category `C`
- Radius `R`
- Dataset points `p1, p2, ..., pn`, each with ID, coordinates, and category

A candidate `p` is valid when:

- `category(p) == C`, and
- its circular/geometric distance from `q` is at most `R`.

Among valid candidates, return the 10 with the smallest traversal/grid distance from `q`.

This decomposes into three subproblems:

1. **Spatial/category filtering:** determine which locations are eligible.
2. **Distance computation:** calculate the required traversal distance for each eligible location, according to the correct graph/grid model.
3. **Top-K retrieval:** return the 10 smallest-distance candidates.

Thinking in these separate stages makes it easier to reason about correctness and optimization.

## 3. What “1 × 1 grid” might mean

The phrase “locations lie on a 1 × 1 grid” can describe coordinates over a unit square, but it does not by itself define how movement is allowed.

The supplied CSV was inspected during the discussion. The reported observations were:

- 10,000 rows
- 100 unique latitude values
- 100 unique longitude values
- coordinates spanning 0 to 1
- apparently a 100 × 100 regular grid
- 8 categories, each appearing 1,250 times
- example coordinate values begin at 0 and increase by roughly 0.010101 intervals

These observations suggest a regular grid, but they do not establish the evaluator's exact intended traversal rules.

### Convert coordinates to grid indices

Instead of repeatedly working with floating-point coordinates, a regular grid can be represented by integer indices:

- geographic coordinate → `(row, column)`
- example: `(0.0, 0.0)` → `(0, 0)`
- example: `(0.0, 0.010101...)` → `(0, 1)`
- example: `(0.010101..., 0.0)` → `(1, 0)`

A discrete grid representation can make neighbor lookup and grid operations easier.

Be careful with floating-point arithmetic. Expressions such as `0.3 / 0.1` are not guaranteed to behave exactly like integer arithmetic. Prefer mapping known coordinate values to indices or using a robust coordinate-to-index mapping rather than blindly dividing and truncating.

## 4. Distance models: the main ambiguity

### 4.1 Euclidean/circular distance

For coordinates `(x1, y1)` and `(x2, y2)`, the planar Euclidean distance is:

\[
d_E = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}
\]

This is the natural distance for testing whether a point lies inside a circular radius, assuming the assignment's coordinate units and planar interpretation.

The radius condition is:

\[
d_E(q,p) \le R
\]

Do not automatically use this distance to rank the final results, because the assignment explicitly distinguishes circular radius from traversal distance.

### 4.2 Manhattan distance

If movement is allowed in four directions—up, down, left, and right—and every step costs one unit, the distance on an unobstructed grid is Manhattan (L1) distance:

\[
d_M = |x_2-x_1| + |y_2-y_1|
\]

For grid indices:

\[
d_M = |r_2-r_1| + |c_2-c_1|
\]

Example: from grid coordinate `(10,20)` to `(13,25)`, a path takes 3 vertical steps and 5 horizontal steps, for a total of 8.

Manhattan distance is a plausible interpretation of “grid traversal distance” only if the movement model is an unobstructed four-directional grid with equal step costs. It should not be assumed if obstacles, missing links, diagonal movement, or other rules change connectivity.

### 4.3 Graph/network distance

Coordinates describe where points are; graph edges describe which movements are possible.

For example, two points can be geographically close but require a long detour if a connecting edge is missing. If there is no path, their network distance may be infinite or undefined.

A graph model has:

- vertices/nodes: locations or grid cells
- edges: allowed direct movements
- edge weights: travel costs or distances, if specified

The assignment says roads/links may be missing but provides no road/link/network data. This is a major ambiguity.

Consider two networks with identical coordinates:

- World 1: `A — B — C`
- World 2: `A    B — C`

The shortest traversal distance from A to C differs, despite identical coordinates. Therefore, an arbitrary real-world road network cannot be reconstructed from coordinates alone.

Possible interpretations to investigate:

**Interpretation A — unobstructed Manhattan grid:** every adjacent grid cell is connected and movement is four-directional.

**Interpretation B — graph of existing cells:** cells/locations that are absent act like obstacles; only permitted neighboring cells are connected.

**Interpretation C — arbitrary missing road edges:** the intended graph contains missing connections that cannot be inferred from the supplied data. If this is what the specification means, the problem is under-specified without further information.

Do not claim that actual roads have been reconstructed if no network data exists. Do not invent arbitrary road connections. Document the assumption selected and, if possible, ask the assignment organizer what “missing links/roads” means.

## 5. Two distance rules in one query

The assignment's wording means that the filtering metric and ranking metric can differ:

- **Eligibility:** circular/geometric distance must be within radius.
- **Ranking:** traversal/grid distance determines which valid points are closest.

Example with query `Q = (0,0)` and candidates:

- A = `(3,4)`
- B = `(5,0)`
- C = `(2,2)`

Euclidean distances:

- A = 5
- B = 5
- C ≈ 2.828

Manhattan distances:

- A = 7
- B = 5
- C = 4

With radius 5, all three pass the circular-radius condition, but ranking by Manhattan distance gives:

1. C — 4
2. B — 5
3. A — 7

The example illustrates why Euclidean distance must not automatically be used for ranking and Manhattan distance must not automatically be used for the circular-radius test.

Mathematically, the requested result is:

\[
\operatorname{Top10}
\{p : \operatorname{category}(p)=C,\ d_{\text{circle}}(q,p)\le R\}
\]

ordered by the intended traversal metric `d_grid(q,p)`.

## 6. Graph algorithms: when each is appropriate

### BFS (Breadth-First Search)

Use BFS when every edge has equal cost, such as moving from one grid cell to a permitted neighboring cell with cost 1.

BFS explores vertices level by level. In an unweighted graph, each BFS level corresponds to a shortest-path distance from the start node.

For a nearest-10 problem, a possible strategy is:

1. Start from the query's grid node.
2. Explore neighboring nodes in BFS order.
3. Check each reached location's category and circular-radius eligibility.
4. Record valid candidates.
5. Once 10 candidates are found, do not stop until the relevant BFS distance layer has been fully processed if all candidates tied at that distance must be considered.
6. Stop when the next layer cannot produce a better traversal distance.

This can avoid calculating a distance separately for every point, if the intended graph really is an unweighted grid/network and the search respects the radius constraint.

Important caveat: the query coordinates may not themselves correspond to a dataset node. The implementation must define how to connect or locate the query point in the grid.

### Dijkstra's algorithm

Use Dijkstra when edges have different non-negative costs. For example, different roads might have different travel distances or travel times.

Dijkstra repeatedly processes the node with the smallest currently known distance. If the assignment does not provide edge weights, Dijkstra may be unnecessary or impossible to apply meaningfully.

### A* search

A* combines path costs with a heuristic to guide search toward a known destination. Manhattan distance is a common heuristic for four-directional grids.

However, this assignment asks for the 10 nearest eligible locations, rather than the shortest path to one known destination. A* is therefore not automatically the best choice.

## 7. Search outward versus checking every candidate

A brute-force approach thinks:

```text
For every location:
    filter by category
    filter by radius
    compute ranking distance
sort candidates
return the first 10
```

A graph-search approach can instead think:

```text
Start at the query
Expand outward in increasing traversal distance
Check locations as they are reached
Stop once the nearest 10 are established
```

The second approach can be more efficient when the graph model is correct and nearby qualifying locations are found early. It is not automatically superior in every dataset or interpretation; it depends on how the graph is defined, how the query point maps to it, and how the radius condition is enforced.

## 8. Spatial filtering and radius-based pruning

A radius test can be made more efficient by first considering the square bounding box around the query:

- latitude in `[lat - R, lat + R]`
- longitude in `[long - R, long + R]`

Then apply the exact circular-distance check to the remaining points.

This bounding-box step is only a coarse filter; points in the corners of the square can be outside the circle and must be rejected by the exact radius test.

This assumes the coordinates use compatible planar units and that `R` is expressed in those units. If coordinates are real geographic latitude/longitude in degrees and radius is a physical distance, the distance calculation must account for geographic units and curvature. The supplied example dataset appears to use a unit-square coordinate system, but the API contract should make the units explicit.

The radius is a constraint, not necessarily the metric used to rank results.

## 9. Spatial indexing concepts

A spatial index helps reduce the number of points examined for spatial queries. The right choice depends on the data geometry, distance metric, and query workload.

### KD-tree

Useful for nearest-neighbor and radius queries over points in k-dimensional space. SciPy's `cKDTree` provides nearest-neighbor and radius-query functionality.

However, a KD-tree's ordinary nearest-neighbor behavior is based on the selected geometric metric. It does not automatically solve graph shortest-path distance. A KD-tree can help with geometric candidate filtering, but it must not be mistaken for a solution to an arbitrary network-distance ranking problem.

### R-tree / spatial database index

R-trees and related spatial indexes are useful for searching geometric objects and bounding boxes. PostGIS commonly uses GiST-based spatial indexes to accelerate spatial predicates.

Again, a spatial index can speed up geometric filtering but does not magically provide traversal distances over an unspecified graph.

### Uniform grid / grid hash

Because this dataset appears to be a regular grid, a grid representation may be simpler than a general-purpose spatial index. Integer row/column indices allow direct lookup of a cell and its neighbors.

### How to choose

Ask:

- What is the geometry?
- What is the ranking distance metric?
- Which query types are required?
- Is the dataset static or frequently updated?
- Is the space regular?
- Must results be exact?
- Is the expensive part spatial filtering, graph traversal, or sorting?

Do not select a KD-tree simply because the phrase “nearest points” appears in the assignment.

## 10. Category filtering

The category is another eligibility condition. One option is to precompute an index:

```text
category -> locations in that category
```

For example:

```text
bank       -> [...]
store      -> [...]
hospital   -> [...]
school     -> [...]
```

Then category-specific queries can avoid considering locations of other categories.

Alternatively, BFS can check the category when visiting each cell. With a small grid and only a few categories, this may already be adequate.

Which option is better depends on the actual query workload and algorithm. Do not optimize before measuring.

The inspected CSV was reported to have eight categories, each occurring 1,250 times. That is a dataset observation, not a guarantee about any larger evaluation dataset.

## 11. Top-K selection

If many candidates pass the filters, the implementation only needs the 10 best, not a fully sorted list.

### Full sorting

If there are `m` eligible candidates, sorting them all costs approximately:

\[
O(m\log m)
\]

Then take the first 10.

### Size-10 max-heap

Maintain a max-heap of the best 10 candidates found so far:

1. Insert until the heap has 10 items.
2. The heap root is the worst (largest-distance) item among the current best 10.
3. If a new candidate is better, remove the root and insert the new candidate.
4. At the end, sort the retained 10 items into the required output order.

This costs approximately:

\[
O(m\log 10)
\]

which is effectively linear in `m` when `K = 10` is fixed.

Tie handling matters: if equal distances are possible, use a deterministic secondary rule (such as location ID) unless the evaluator specifies another rule. A tie-break rule can affect exact-match scoring, so it should match the evaluator if known.

If BFS is used and its distance layers are correct, it may be possible to avoid a heap entirely, but the implementation must handle ties and finish the necessary layer before stopping.

## 12. Data scale and efficiency

The assignment text mentions approximately 1,000,000 locations in one place and 10,000 in the evaluation requirements. The supplied CSV was reported to contain 10,000 rows.

For 10,000 locations, scanning every row for each query is usually a reasonable baseline. For 1,000,000, indexing and pruning become more important, although a carefully implemented exact scan can still be feasible in some workloads.

The hidden evaluation has only 10 queries, and every query is guaranteed to have at least 10 valid locations. The scoring emphasizes correct returned IDs, not just speed.

Therefore, prioritize:

1. Correct interpretation of the distance model.
2. Correct category and radius filtering.
3. Correct top-10 ranking and tie behavior.
4. Performance.
5. API polish and deployment details.

Approximate nearest-neighbor methods are risky because hidden-query scoring rewards exact ID matches. Prefer an exact method unless the scale or latency requirements justify approximation and the scoring permits it.

## 13. Dataset inspection questions

Before finalizing the algorithm, inspect the supplied CSV and answer:

1. Is the grid complete?
2. Are there exactly 100 unique latitude and 100 unique longitude values?
3. Are any grid cells missing?
4. How are IDs mapped to coordinates?
5. Are IDs assigned row-major or in some other order?
6. What is the grid spacing?
7. Are coordinates duplicated?
8. Are categories randomly distributed or patterned?
9. What does each category's spatial distribution look like?
10. How many candidates fall inside several sample radii?
11. How often do Euclidean and Manhattan rankings disagree?
12. Can example queries be constructed where the top 10 differs under competing distance interpretations?
13. Does the dataset contain enough information to define graph edges?
14. Does the API query point always lie on the grid, or can it lie between grid cells?

The previously reported CSV observations were: 10,000 rows; 100 unique values for each coordinate axis; coordinates from 0 to 1; eight categories with 1,250 records each; and an apparently complete 100 × 100 grid. These observations should be revalidated against the actual file before being relied on in implementation or reporting.

## 14. Recommended implementation progression

Build progressively so that every optimization can be checked against a simple baseline.

### Version 1 — brute-force baseline

For each location:

1. Check category.
2. Check circular radius.
3. Compute traversal distance under the selected model.
4. Collect valid candidates.
5. Sort by traversal distance and any required tie-breaker.
6. Return the first 10.

This is a reference implementation under the chosen model. It is not automatically the ground truth if the model itself is wrong.

### Version 2 — grid representation

Map latitude/longitude values to integer `(row, column)` indices. Use the grid structure for direct lookup and neighbor access.

### Version 3 — exploit graph structure

If the intended model is an unweighted grid graph, implement BFS from the query's grid location and investigate safe early stopping after finding 10 eligible locations.

### Version 4 — spatial pruning

Use the radius's bounding box to avoid examining points that cannot qualify, followed by the exact circular-distance check.

### Version 5 — category indexing

Precompute category-to-location or category-to-cell indexes if profiling shows a benefit.

### Version 6 — benchmark and verify

Benchmark the brute-force baseline and optimized methods on 10k, 100k, and (if available) 1M rows. Verify that optimized methods return the same result as the baseline under the same precisely defined distance model. Performance testing cannot establish that the chosen model matches the evaluator, so resolve or document that ambiguity separately.

## 15. Suggested architecture

```text
                  CSV
                   |
                   v
          +-------------------+
          | Preprocessing     |
          |                   |
          | coordinate -> grid|
          | category index    |
          +---------+---------+
                    |
                    v
                API request
             lat,long,cat,rad
                    |
                    v
          +-------------------+
          | Eligibility filter|
          |                   |
          | category match    |
          | circular radius   |
          +---------+---------+
                    |
                    v
            Valid candidates
                    |
                    v
          +-------------------+
          | Traversal distance|
          |                   |
          | Manhattan / BFS / |
          | Dijkstra, as       |
          | justified by model|
          +---------+---------+
                    |
                    v
                 Top 10
                    |
                    v
               JSON response
```

This is a conceptual architecture; the order of filtering and traversal may change in an optimized implementation.

## 16. Common mistakes to avoid

- Do not rank by straight-line distance when the specification calls for traversal distance.
- Do not use Manhattan distance for the radius condition if the specification says circular distance.
- Do not invent road connections or claim to reconstruct actual roads from coordinates alone.
- Do not automatically add OpenStreetMap data; external roads may not match the evaluator's intended grid/network.
- Do not choose A* merely because it sounds faster. It is designed around a destination and heuristic, while this is a nearest-10 problem.
- Do not build a complex database stack for a 10k-row dataset before a simple baseline exists.
- Do not use approximate nearest-neighbor methods without considering the exact-match scoring.
- Do not assume that a KD-tree solves graph shortest paths.
- Do not ignore ties or query points that fall between grid nodes.
- Do not optimize before checking correctness and measuring performance.
- Do not silently resolve the “missing roads but no network data” ambiguity. Investigate it and state the assumption.

## 17. Thought process to practice on similar problems

Ask these questions in order:

1. **What exactly is being optimized?** Here, the 10 smallest traversal distances.
2. **What makes a candidate valid?** Matching category and being inside circular radius.
3. **What distance metric is used for each purpose?** Circular distance for eligibility; traversal distance for ranking.
4. **What structure does the input have?** Apparently a regular 2D grid.
5. **Is the space a graph?** Potentially: cells/locations are vertices and allowed movements are edges.
6. **Are edge weights equal?** If yes, BFS may apply; if non-negative and variable, Dijkstra may apply.
7. **Is this one destination or many?** It is a nearest-10/multi-target problem, so A* is not an automatic choice.
8. **Can irrelevant points be excluded?** Use category filtering and radius-based spatial filtering.
9. **Can the search stop early?** Possibly with BFS, after enough valid locations and all relevant distance ties are handled.
10. **What does the evaluator reward?** Correct location IDs, so exactness comes first.

The central conceptual combination is:

**Spatial filtering + graph shortest-path reasoning + Top-K retrieval.**

## 18. Reading roadmap and resources

Read in this order rather than trying to learn every topic simultaneously.

### Phase 1 — Grid distance and pathfinding intuition

**Red Blob Games — Introduction to A\***  
https://www.redblobgames.com/pathfinding/a-star/introduction.html

Focus on grid representations, pathfinding intuition, distance metrics, and how the movement model affects the result.

### Phase 2 — Graphs, BFS, and shortest paths

**Cornell CS — Shortest Paths lecture**  
https://www.cs.cornell.edu/courses/cs2110/2026sp/lectures/lec23/

Focus on BFS, why levels represent shortest-path distances in unweighted graphs, and the ideas behind Dijkstra.

**Red Blob Games — A\* implementation**  
https://www.redblobgames.com/pathfinding/a-star/implementation.html

Focus on grid implementations of BFS, Dijkstra, and A*, and how their roles differ.

### Phase 3 — Spatial indexing

**SciPy — `cKDTree` documentation**  
https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html

Focus on nearest-neighbor queries and radius queries. Remember that ordinary KD-tree nearest-neighbor results are geometric, not automatically network shortest-path results.

### Phase 4 — Spatial databases

**PostGIS — Spatial indexes FAQ**  
https://postgis.net/documentation/faq/spatial-indexes/

Learn how spatial indexes accelerate geometric predicates.

**PostGIS — `ST_DWithin`**  
https://postgis.net/docs/ST_DWithin.html

Relate the function to testing whether geometries are within a specified distance.

**PostGIS — KNN distance operator**  
https://www.postgis.net/docs/manual-dev/en/geometry_distance_knn.html

Understand index-assisted nearest-neighbor search and its distinction from graph traversal distance.

### Phase 5 — Real road networks

**OSMnx — Getting started**  
https://osmnx.readthedocs.io/en/stable/getting-started.html

Learn how real street networks are represented as graphs, why topology and geometric proximity differ, and how edge data matters for shortest paths.

### Phase 6 — Top-K selection

Study the max-heap approach to finding the smallest `K` values without sorting every candidate. Understand the complexity difference between full sorting, approximately `O(m log m)`, and maintaining a fixed-size heap, approximately `O(m log K)`.

## 19. The key diagram

```text
                Query Q
          lat, long, cat, radius
                    |
           +--------+--------+
           |                 |
           v                 v
    GEOMETRIC SPACE     GRID / NETWORK
           |                 |
     "inside radius?"  "how close by
           |            traversal?"
      Euclidean            BFS /
       distance          Dijkstra /
           |             justified
           |              distance
           +--------+--------+
                    |
                    v
             Valid candidates
                    |
                    v
                  Top 10
                    |
                    v
              Location IDs
```

## 20. Recommended next step

Before coding the final solution, investigate the actual CSV and the ambiguous road statement.

Specifically:

1. Revalidate the grid structure and category distribution.
2. Draw the grid conceptually and map IDs to cells.
3. Construct sample queries.
4. Calculate answers under each plausible distance interpretation.
5. Find cases where the top 10 differs between interpretations.
6. Determine whether the assignment organizer or evaluation material clarifies the intended graph.
7. Only then select the final algorithm and API implementation.

The critical unresolved issue remains: **if “missing roads” means arbitrary missing edges, coordinates and categories alone cannot reveal the true traversal distance.** If it means a particular grid-neighbor rule, that rule needs to be established and documented.

---

## Source references

The following links were recommended during the discussion for further study:

- Red Blob Games, Introduction to A*: https://www.redblobgames.com/pathfinding/a-star/introduction.html
- Cornell CS, Shortest Paths lecture: https://www.cs.cornell.edu/courses/cs2110/2026sp/lectures/lec23/
- Red Blob Games, A* implementation: https://www.redblobgames.com/pathfinding/a-star/implementation.html
- SciPy, `cKDTree`: https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html
- PostGIS, Spatial indexes FAQ: https://postgis.net/documentation/faq/spatial-indexes/
- PostGIS, `ST_DWithin`: https://postgis.net/docs/ST_DWithin.html
- PostGIS, KNN distance operator: https://www.postgis.net/docs/manual-dev/en/geometry_distance_knn.html
- OSMnx, Getting started: https://osmnx.readthedocs.io/en/stable/getting-started.html

These are reading recommendations, not proof that any one algorithm is the evaluator's intended solution.
