# Proximity Search API

CSL559 (Computer System Design), Lab 7.

Returns the 10 closest locations of a given category within a radius. "Closest" is measured by traversal distance on a 100×100 grid road network, not straight-line distance.

## Run

Needs Python 3.8+ only, no packages to install.

```bash
python3 server.py --host 0.0.0.0 --port 8000
```

## Use

```
GET /search/?lat=0.5&long=0.5&cat=bank&rad=0.1&link=true
```

| Field | Meaning |
|---|---|
| `lat`, `long` | Query point, in [0, 1] |
| `cat` | `bank`, `cafe`, `hospital`, `park`, `pharmacy`, `restaurant`, `school`, `store` |
| `rad` | Search radius (straight-line), same units as the coordinates |
| `link` | `true`: use only the roads in `assets/link.txt`; `false`: every neighbouring pair of points is connected |

Response (`ids` = 10 location IDs, nearest first):

```json
{"ids": [4850, 4948, 4648, 4753, 4947, 5349, 4451, 5348, 4351, 4654], "results": [...], "count": 10, "link": true, "time_ms": 0.1}
```

## How it works

A breadth-first search from the query's nearest grid point, one distance level at a time. It stops once the top 10 are settled. Ties are broken by the smaller ID. See [`report/report.pdf`](report/report.pdf) for details.

## Files

| Path | Contents |
|---|---|
| `engine.py` | Data loading and search algorithms |
| `server.py` | HTTP API (standard library) |
| `crosscheck.py` | Verifies the fast search against a brute-force reference: `python3 crosscheck.py` |
| `assets/` | `locations.csv`, `link.txt` |
| `report/` | Report (LaTeX source and PDF) |
