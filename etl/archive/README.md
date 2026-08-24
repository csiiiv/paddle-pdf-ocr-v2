# Retired ETL implementations

This directory preserves the superseded model-layout pipeline for historical
review and source comparison. None of these files are registered in
`etl/run_etl.py`, exposed by the active artifact store, or exercised by the
active test suite.

Archived stages:

- `002.00-layout.py` — model regions and zones;
- `003.00-table-cells.py` — model-derived table cells;
- `004.00-extract.py` — page extract with fallback zones;
- `005.00-schema.py` — zone-based schema inference.

Their former tests are under `tests/`, and the retired region/zone helper is
under `_shared/`. Treat these as implementation history, not executable ETL
entry points. The active deterministic sequence is documented in
`docs/ETL_DAG.md`.
