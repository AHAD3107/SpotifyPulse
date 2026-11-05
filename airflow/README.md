# Apache Airflow Orchestration

This directory houses DAG definitions, custom hooks, and operators for orchestrating SpotifyPulse data pipelines.

## Orchestration Plan (To be implemented in Phase 6)

* `dags/`:
  * `spotify_pulse_hourly_scrobble_dag.py`: Hourly cursor-based extraction of `/v1/me/player/recently-played`, raw Bronze landing, and staging normalization.
  * `spotify_pulse_daily_snapshot_dag.py`: Daily snapshots of top tracks, top artists, and playlist items.
  * `spotify_pulse_dbt_transform_dag.py`: Triggered upon staging completion to execute `dbt run` and `dbt test`.
* `plugins/`: Custom operators and sensors.

