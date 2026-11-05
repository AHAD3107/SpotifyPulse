# SpotifyPulse ETL Pipeline Specification (Final Architecture Audit)

## 1. Pipeline Overview & Processing Lifecycle

The SpotifyPulse ETL pipeline processes music events, affinity snapshots, and playlist data through a robust, idempotent three-stage architecture:

```
┌─────────────────┐      HTTPX Async      ┌─────────────────────────────┐
│   Spotify API   │ ────────────────────► │  Bronze Transient Landing   │
│  / Demo Engine  │  (JSON Snapshots)     │  (Configurable TTL: 14 Days)│
└─────────────────┘                       └──────────────┬──────────────┘
                                                         │
                                                         ▼ Pandas / Pydantic V2
                                                  ┌─────────────────────────────┐
                                                  │  Staging Relational Layer   │
                                                  │  - Event Fingerprinting     │
                                                  │  - Episode Filter (Option A)│
                                                  │  (Rolling TTL: 30 Days)     │
                                                  └──────────────┬──────────────┘
                                                         │
                                                         ▼ dbt Core
                                                  ┌─────────────────────────────┐
                                                  │  Gold Dimensional Warehouse │
                                                  │  (Star Schema analytics)    │
                                                  │  (Facts TTL: 730 Days)      │
                                                  └─────────────────────────────┘
```

The pipeline supports dual-mode execution:
1. **Live Production Mode**: Connects to the Spotify Web API via OAuth 2.0 with rate-limited, cursor-managed asynchronous requests.
2. **Demo Mode**: Leverages an offline deterministic mock data generator yielding identical JSON schemas, enabling local development and portfolio evaluation without Spotify developer credentials.

---

## 2. Bronze Layer: Ingestion & Transient Landing

### 2.1 Extraction Strategy by Entity (Verified 2026 Endpoints)

| Entity | Endpoint | Strategy | Cadence | Query Parameters / Pagination |
| :--- | :--- | :--- | :--- | :--- |
| **Recently Played** | `GET /v1/me/player/recently-played` | Incremental (Cursor) | Hourly | `limit=50`, `after={last_played_at_epoch_ms}` |
| **Top Tracks** | `GET /v1/me/top/tracks` | Full Snapshot | Daily | `time_range={short_term, medium_term, long_term}`, `limit=50` |
| **Top Artists** | `GET /v1/me/top/artists` | Full Snapshot | Daily | `time_range={short_term, medium_term, long_term}`, `limit=50` |
| **User Playlists** | `GET /v1/me/playlists` | Full Snapshot | Daily | `limit=50`, `offset={n}` (owned & collaborative only) |
| **Playlist Items** | `GET /v1/playlists/{id}/items` | Full Snapshot | Daily | `limit=50`, `offset={n}` |
| **User Profile** | `GET /v1/me` | Snapshot | Daily | None |

> [!IMPORTANT] Endpoint Migration
> The legacy `GET /v1/playlists/{id}/tracks` endpoint is deprecated. The extraction pipeline strictly invokes `GET /v1/playlists/{id}/items`.

### 2.2 Ingestion File Format & Audit Envelope
Raw JSON payloads are stored in `data/bronze/{entity}/{year}/{month}/{day}/{run_id}.json` wrapped with an audit envelope:
```json
{
  "_metadata": {
    "run_id": "c98f8287-6e42-4911-9a99-cf8021c33c39",
    "endpoint": "/v1/me/player/recently-played",
    "ingestion_timestamp_utc": "2026-11-05T08:00:15.123456Z",
    "user_id": "spotify_user_xyz",
    "is_demo_mode": false,
    "http_status": 200,
    "record_count": 50,
    "episodes_excluded_count": 0,
    "cursor_before": null,
    "cursor_after": 1793874015000
  },
  "payload": { ... }
}
```

### 2.3 Error Handling: Rate Limits vs `QUOTA_EXCEEDED` vs `invalid_grant`
1. **Burst Rate Limiting (`HTTP 429` with `Retry-After`)**:
   * Reads `Retry-After` header.
   * Sleeps for `Retry-After + jitter` (0.5s–2.0s).
   * Retries up to `rate_limit_max_retries` (default 5).
2. **Account Quota Exhaustion (`429 QUOTA_EXCEEDED`)**:
   * Occurs when the developer account's shared quota pool (across up to 25 Client IDs) is exhausted.
   * **Never retry in a loop**. Immediately halts pipeline execution and logs a high-severity alert.
3. **Six-Month Refresh Token Expiration (`400 invalid_grant`)**:
   * Occurs when the 6-month refresh token lifetime has elapsed without interactive re-authorization.
   * **Never retry**. Delete invalid credentials, flag user status as `REAUTHORIZATION_REQUIRED`, and pause scheduled jobs until reauthorization.

---

## 3. Staging Layer: Transformation, Validation & Deduplication

### 3.1 Event Fingerprinting Algorithm (`source_event_fingerprint`)
To prevent collisions when multiple local tracks or unresolvable items have surrogate `track_key = -1`, the staging pipeline generates a deterministic SHA-256 fingerprint from the original source payload:

```python
import hashlib

def compute_source_event_fingerprint(
    user_id: str,
    played_at_utc: str,
    spotify_track_id: str | None,
    track_name: str | None,
    artist_name: str | None,
    album_name: str | None,
    duration_ms: int | None,
) -> str:
    """Generate deterministic SHA-256 fingerprint for a listening event."""
    if spotify_track_id and spotify_track_id.strip():
        identity = f"spotify:{spotify_track_id.strip()}"
    else:
        norm_title = (track_name or "").strip().lower()
        norm_artist = (artist_name or "").strip().lower()
        norm_album = (album_name or "").strip().lower()
        dur = duration_ms if duration_ms is not None else 0
        identity = f"local:{norm_title}|{norm_artist}|{norm_album}|{dur}"

    canonical = f"{user_id.strip()}|{played_at_utc.strip()}|{identity}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

* **Guarantees**:
  * Two different local tracks at the same timestamp produce distinct fingerprints.
  * Re-ingesting the identical event produces the identical fingerprint, allowing safe `ON CONFLICT (source_event_fingerprint) DO NOTHING`.
  * Preserves events with missing Spotify IDs without colliding on `track_key = -1`.
* **Edge Case Limitation**: If two completely identical local tracks (same title, artist, album, duration) ended at the exact same millisecond, they produce identical fingerprints. This is an unavoidable data limitation when Spotify provides zero distinct metadata.

### 3.2 Playlist Item Processing & Episode Exclusion (Option A)
* When unnesting `GET /v1/playlists/{id}/items`:
  * If `item.type == 'episode'` (podcast episode): The record is **excluded** from the music staging table and incremented in `bronze.ingestion_runs.episodes_excluded_count`.
  * If `item.type == 'track'`: The record is cleaned and inserted into `staging.stg_playlist_items`.
* Uniqueness is enforced via `(spotify_playlist_id, snapshot_id, position_in_playlist)` to preserve duplicate tracks at distinct positions.

---

## 4. Gold Layer: dbt Core Dimensional Modeling

The Gold layer uses **dbt Core** to execute modular, tested transformations building the Kimball Star Schema.

### 4.1 Incremental Listening Event Model
```sql
{{ config(
    materialized='incremental',
    unique_key='source_event_fingerprint',
    on_schema_change='sync_all_columns'
) }}

WITH source_events AS (
    SELECT * FROM {{ ref('stg_spotify__recently_played') }}
    {% if is_incremental() %}
        -- Only process events newer than the current maximum in the fact table
        WHERE played_at_utc > (SELECT MAX(played_at_utc) FROM {{ this }})
    {% endif %}
),
transformed AS (
    SELECT
        {{ dbt_utils.generate_surrogate_key(['se.source_event_fingerprint']) }} AS listening_event_key,
        se.source_event_fingerprint,
        u.user_key,
        COALESCE(t.track_key, -1) AS track_key,
        COALESCE(a.album_key, -1) AS album_key,
        d.date_key,
        tm.time_key,
        se.played_at_utc,
        se.context_type,
        se.context_uri,
        se.track_duration_ms,  -- Catalog metadata only; NOT actual listening duration
        1 AS observed_event_count, -- Fixed observed event occurrence
        se.ingestion_run_id
    FROM source_events se
    JOIN {{ ref('dim_user') }} u ON se.spotify_user_id = u.spotify_user_id
    LEFT JOIN {{ ref('dim_track') }} t ON se.spotify_track_id = t.spotify_track_id
    LEFT JOIN {{ ref('dim_album') }} a ON se.album_id = a.spotify_album_id
    JOIN {{ ref('dim_date') }} d ON CAST(TO_CHAR(se.played_at_utc, 'YYYYMMDD') AS INT) = d.date_key
    JOIN {{ ref('dim_time') }} tm ON CAST(TO_CHAR(se.played_at_utc, 'HH24MISS') AS INT) = tm.time_key
)
SELECT * FROM transformed;
```

---

## 5. Multi-Tier Data Retention & Disconnect Purge

### 5.1 Multi-Tier Retention Schedule
* **Bronze Raw Payloads**: Purged after `DATA_BRONZE_RETENTION_DAYS` (default 14 days).
* **Staging Tables**: Rolling window of `DATA_STAGING_RETENTION_DAYS` (default 30 days).
* **Gold Fact Events**: Retained for `DATA_FACTS_RETENTION_DAYS` (default 730 days / 2 years).
* **Snapshots**: Top charts retained for 365 days; playlist snapshots retained for 90 days.

### 5.2 Account Disconnect & Cascading Data Deletion (`POST /auth/disconnect`)
When a user disconnects their account:
1. Invalidate active user session and abort outbound HTTP requests.
2. Delete access and refresh tokens from encrypted storage.
3. Remove scheduled ingestion DAGs for the user.
4. Execute cascading deletions across all storage layers:
   * **Bronze**: Delete matching JSON files from `data/bronze/*/*/*/{user_id}_*.json`.
   * **Staging**:
     ```sql
     DELETE FROM staging.stg_recently_played WHERE spotify_user_id = :uid;
     DELETE FROM staging.stg_top_tracks WHERE spotify_user_id = :uid;
     DELETE FROM staging.stg_top_artists WHERE spotify_user_id = :uid;
     DELETE FROM staging.stg_playlists WHERE owner_id = :uid;
     ```
   * **Gold**:
     ```sql
     DELETE FROM analytics.fact_listening_event WHERE user_key = :ukey;
     DELETE FROM analytics.fact_top_track_snapshot WHERE user_key = :ukey;
     DELETE FROM analytics.fact_top_artist_snapshot WHERE user_key = :ukey;
     DELETE FROM analytics.dim_user WHERE user_key = :ukey;
     ```
5. Return user guidance and link to [Spotify Account Apps Portal](https://www.spotify.com/account/apps/) to revoke authorization on Spotify's servers.
