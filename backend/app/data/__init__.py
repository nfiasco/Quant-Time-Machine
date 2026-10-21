"""Point-in-time data layer: every record carries when it became public, and every read
is "as of" a knowledge time, so nothing can see the future (doc/time-model.md).

- `timeutil`: the market clock and the knowledge-time (`as_of`) parser
- `calendar`: the NYSE trading calendar
- `store` and `tables`: the append-only Parquet store, and the tables in it
- `view`: `PointInTimeView`, the only way to read the store
- `errors`: errors that reads raise and the API answers
- `raw_cache`, `http`, and `ingest`: downloading sources into the store
"""
