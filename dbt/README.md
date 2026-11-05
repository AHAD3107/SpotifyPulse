# dbt Core Dimensional Transformation Project

This directory contains the dbt Core project for SpotifyPulse, managing SQL data transformations inside PostgreSQL 17 to build the Gold dimensional warehouse (Kimball Star Schema).

## Directory Structure (To be implemented in Phase 5)

* `dbt_project.yml`: dbt project configuration.
* `packages.yml`: Dependencies (e.g., `dbt-labs/dbt_utils`).
* `models/`:
  * `staging/`: Clean views over PostgreSQL `staging` schema.
  * `intermediate/`: Deduplication, M:N bridge unnesting, surrogate keys.
  * `marts/core/`: Conformed dimensions (`dim_date`, `dim_time`, `dim_user`, `dim_track`, `dim_album`, `dim_artist`, `dim_playlist`) and bridges (`bridge_track_artist`, `bridge_album_artist`).
  * `marts/analytics/`: Incremental fact tables (`fact_listening_event`, `fact_top_track_snapshot`, `fact_top_artist_snapshot`, `fact_playlist_item_snapshot`).
* `tests/`: Custom SQL data quality tests and schema assertions.

