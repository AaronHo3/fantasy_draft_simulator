# Benchmarks

Measured 2026-10-10T01:46:47+00:00 on macOS-26.6.2-arm64-arm-64bit / arm (Python 3.12.13), 600 synthetic players, 12 managers. Produced by `make bench`; numbers below are from the last run, not targets.

## Layer A engine (fast ranking over all available players)

| picks made | p50 ms | p95 ms |
|---|---|---|
| 0 | 5.3 | 5.7 |
| 30 | 7.7 | 9.1 |
| 78 | 9.8 | 10.7 |
| 130 | 11.6 | 12.4 |

## End-to-end service calls (engine + explanations + roster views, no HTTP)

- Fast recommendation (limit 25, 8 delta tables): p50 8.9 ms, p95 10.3 ms over 10 calls.
- Pick commit through the SQLite event store (validate + replay + persist): p50 0.11 ms, p95 0.17 ms.

## Refinement (Layers B/C) at the user's mid-draft pick, shortlist of 8

| budget ms | mean computed ms | max computed ms | mean weekly scenarios | tier |
|---|---|---|---|---|
| 1000 | 890.0 | 898.0 | 1500 | C |
| 1500 | 1294.0 | 1295.0 | 2200 | C |
| 3000 | 2592.0 | 2600.0 | 4400 | C |

Targets from the brief: committed pick visible in ~100 ms (client-side optimistic), cached fast rankings < 250 ms p95, refined shortlist in ~1–2 s p95 under the default budget. See PROGRESS.md for the pass/fail reading.
