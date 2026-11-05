# SpotifyPulse Technical Decisions & Architecture Decision Records (ADRs)

## Overview

This document records the architectural and technology decisions made for the **SpotifyPulse** platform, detailing the context, options considered, decisions made, and consequences, including the **June 2026 Refresh Token Expiration** and **July 2026 Web API Quota Updates**.

---

## ADR 001: Python 3.12 & uv as Package / Environment Manager

### Context
Data engineering projects often suffer from slow dependency resolution, bloated virtual environments, and inconsistent build environments across local machines and CI/CD pipelines.

### Decision
Use **Python 3.12** managed via **`uv`** (Astral's ultra-fast Rust-based Python package and environment manager).

### Rationale
* **Performance**: `uv` resolves and installs dependencies 10-100x faster than traditional `pip` and `poetry`.
* **Standardization**: Native support for standard `pyproject.toml` (PEP 517/518/621/735).
* **Deterministic Builds**: Unified `uv.lock` lockfile guarantees zero drift between developer workstations, CI tests, and container images.

---

## ADR 002: Kimball Star Schema with Layered Data Architecture (Retiring Lakehouse Terminology)

### Context
Raw API data from Spotify is deeply nested, JSON-formatted, and subject to transient availability. Downstream analytical queries require fast slicing across time, artists, albums, and tracks. Earlier design drafts referred to the architecture as a "Data Lakehouse".

### Decision
Adopt an accurate description: **Layered Data Engineering Architecture** using a Medallion-style staging flow:
* **Bronze**: Transient raw landing buffer for immutable JSON snapshots with automated retention pruning.
* **Staging**: Cleaned, normalized, deduplicated relational tables in PostgreSQL 17.
* **Gold**: Kimball Star Schema data warehouse consisting of conformed dimensions (`dim_*`), fact tables (`fact_*`), and bridge tables (`bridge_*`).

### Rationale
* **Architectural Precision**: SpotifyPulse utilizes PostgreSQL 17, local partitioned file storage, dbt Core, and Python. It does not employ distributed big data lakehouse engines (e.g. Apache Spark, Delta Lake, Apache Iceberg, or Trino). Retiring "lakehouse" terminology ensures accurate communication.

---

## ADR 003: OAuth Architecture: Authorization Code Flow for Confidential Server-Side Backend

### Context
Evaluating whether to implement the standard Authorization Code Flow or Authorization Code Flow with PKCE for user authentication.

### Decision
Implement the standard **OAuth 2.0 Authorization Code Flow** with server-side client secret protection and cryptographic CSRF `state` validation.

### Rationale
* **Confidential Backend Client**: SpotifyPulse runs a dedicated server-side FastAPI backend where `SPOTIFY_CLIENT_SECRET` is kept confidential in server environment variables and encrypted vaults. It is never exposed to the client browser or mobile devices.
* **Official Recommendation**: Spotify's official authorization guide specifically designates the standard Authorization Code Flow as the primary, recommended flow for confidential server-side web applications.
* **Security Controls**: CSRF protection via cryptographically generated `state` parameters stored in server-side session cookies; tokens exchanged strictly over TLS directly with Spotify's token endpoint.

---

## ADR 004: PostgreSQL 17 + SQLAlchemy + Alembic for Data Warehousing

### Context
A robust relational database is required to serve as the single source of truth for both staging data and the gold analytical star schema.

### Decision
Deploy **PostgreSQL 17** managed via **SQLAlchemy 2.0** for object-relational mapping and **Alembic** for schema migrations.

### Rationale
* **JSONB Capabilities**: Native JSONB support enables auditing raw payloads and indexing metadata.
* **Cost & Portability**: PostgreSQL is open-source, runs natively locally or in Docker, and scales comfortably to millions of listening events without incurring cloud warehouse charges.
* **PostgreSQL 17 Enhancements**: Features improved query planning, better vacuuming performance, and enhanced partition management.

---

## ADR 005: dbt Core for Warehouse Transformations & Testing

### Context
Transforming raw staging tables into an enterprise dimensional warehouse can be done via imperative Python scripts (Pandas) or declarative SQL modeling.

### Decision
Use **dbt Core** (`dbt-postgres`) for all Gold layer transformations.

### Rationale
* **Declarative Lineage**: Automatically constructs DAGs showing data lineage from staging to fact and dimension tables.
* **Incremental Processing**: Built-in macros (`is_incremental()`) simplify delta processing of continuous listening streams.
* **Automated Data Quality Tests**: Validates unique keys, foreign key referential integrity, and non-null constraints as part of every pipeline run.

---

## ADR 006: Apache Airflow (Containerized via Docker Compose) for Windows Orchestration

### Context
Extraction, staging ingestion, and dbt transformations must run on schedule (hourly for recently played, daily for top snapshots) with dependency tracking and failure alerts. The host development environment is Windows.

### Decision
Run **Apache Airflow** strictly inside **Docker containers via Docker Compose** on Windows, mounting the local DAGs directory.

### Rationale
* **Windows Incompatibility**: Apache Airflow does not officially support native Windows execution due to POSIX process forking and signal dependencies.
* **Parity**: Containerized execution mirrors production deployment environments perfectly.

---

## ADR 007: Streamlit & Plotly for Analytics Dashboard

### Context
The analytical platform requires an interactive dashboard to explore listening habits, track migrations, genre breakdowns, and playlist metrics.

### Decision
Use **Streamlit** coupled with **Plotly** for the analytical user interface.

### Rationale
* **Zero JavaScript / React**: Complies with the core project rule against React/Java and unnecessary frontend build tooling.
* **Python-Native Interactivity**: Plotly charts render seamlessly in Streamlit with native Python callbacks.
* **Rapid Iteration**: Analytical metrics and visualizations can be deployed directly by data engineers.

---

## ADR 008: Dual Execution Model – Live OAuth vs Offline Demo Mode

### Context
The Spotify Web API has strict Development Mode limits (5 allowlisted users, owner Premium required) and requires credentials that external reviewers, recruiters, or CI environments might not have.

### Decision
Build a first-class **Demo Mode** enabled via `SPOTIFY_PULSE_DEMO_MODE=true`.

### Rationale
* The system boots immediately without Spotify API credentials.
* Deterministic synthetic data generator produces realistic listening histories matching official Spotify API response contracts.
* Enables 100% automated testing of the full ETL lifecycle and dashboard presentation in CI and local setups.

---

## ADR 009: Pydantic Settings & Structured JSON Logging

### Context
Configuration and logging must adhere to twelve-factor app principles and enterprise observability standards.

### Decision
Use **Pydantic Settings** (`pydantic-settings`) for configuration management and Python standard library logging configured with structured JSON formatters.

### Rationale
* Type-safe environment variable parsing with validation at startup.
* Prevents silent configuration errors (e.g. invalid port numbers, malformed database URLs).
* Structured JSON logs facilitate debugging and integration with observability platforms.

---

## ADR 010: Compliance with February 2026 Spotify Web API Changes

### Context
The February 2026 Spotify Web API migration guide introduced major field deprecations (popularity, followers, genres, country, subscription tier) and endpoint changes (`GET /v1/playlists/{id}/items` replacing `/tracks`).

### Decision
1. **Field Removal**: Exclude track popularity, artist popularity, artist followers, user country, product tier, and artist genres from all warehouse dimensions and fact tables.
2. **Rank Assignment**: Rank top tracks and artists (1 to 50) based strictly on the ordered array index returned by Spotify's affinity endpoints.
3. **Endpoint Migration**: Use `GET /v1/playlists/{id}/items` exclusively for playlist item extraction.
4. **Quota Mode Rules**: Document development mode restrictions (owner must have Premium, maximum 5 allowlisted users, 25 Client IDs per developer account).

---

## ADR 011: Multi-Tier Data Retention, Disconnect Flow & Revocation Reality

### Context
Spotify Developer Terms require developers not to retain Spotify data indefinitely and to delete data when a user disconnects. Spotify's API does not offer a server-side token revocation endpoint.

### Decision
1. **Multi-Tier Retention Schedule**:
   * Bronze raw JSON: 14 days TTL.
   * Staging tables: 30 days rolling window.
   * Gold facts: 730 days (2 years).
   * Snapshots: 365 days (charts) / 90 days (playlists).
2. **Disconnect Protocol (`POST /auth/disconnect`)**:
   * Stop all future API calls immediately.
   * Permanently delete tokens and encryption keys from local storage.
   * Stop scheduled ingestion DAGs.
   * Cascade deletion of all user records across Bronze, Staging, and Gold tables.
   * Present direct deep link to [Spotify Account Apps Management](https://www.spotify.com/account/apps/) for user-side revocation.

---

## ADR 012: Event Deduplication via `source_event_fingerprint` & Episode Exclusion (Option A)

### Context
Using `(user_key, played_at_utc, track_key)` creates collision risks when `track_key = -1` for multiple local/unresolvable tracks. Furthermore, playlist endpoints return podcast episodes alongside songs.

### Decision
1. **Deterministic Fingerprint**: Generate `source_event_fingerprint` (SHA-256) directly from original source metadata (user ID, timestamp, and canonical track identity), preventing surrogate key collisions.
2. **Episode Exclusion (Option A)**: Filter out podcast episodes (`type == 'episode'`) at the Staging boundary and log excluded counts in ingestion quality metadata, preserving schema simplicity and Gold music analytical purity.

---

## ADR 013: Strict Prohibition on AI/ML Model Training on Spotify Data

### Context
Spotify Developer Terms strictly forbid using Spotify-provided content or user listening data to train artificial intelligence or machine learning models.

### Decision
Explicitly prohibit any AI/ML model training or feature generation on Spotify data in the codebase and architectural documentation.

---

## ADR 014: Six-Month Refresh Token Lifecycle and `invalid_grant` Protocol

### Context
In June 2026, Spotify implemented a mandatory 6-month expiration policy on refresh tokens. Refreshing access tokens does not extend this window.

### Decision
1. **Clock Tracking**: Record `authorized_at_utc` in the token vault and compute `refresh_token_expires_at_utc` (180 days).
2. **`invalid_grant` Handling**: If a token refresh returns `error: invalid_grant`, the backend must **never retry**. It immediately deletes the expired credentials, halts scheduled extractions for that user, flags user status as `REAUTHORIZATION_REQUIRED`, and prompts for re-authentication.

---

## ADR 015: Shared Developer Account Quota and Distinguishing `429 QUOTA_EXCEEDED`

### Context
In July 2026, Spotify consolidated developer quotas: all Client IDs (up to 25) belonging to the same developer account share a single pooled quota allocation.

### Decision
Differentiate standard temporary burst rate limits (`HTTP 429` with `Retry-After`) from account quota exhaustion (`429 QUOTA_EXCEEDED`):
* Burst limit: Pause for `Retry-After + jitter` and retry up to 5 times.
* Account Quota Exceeded: Immediately abort extractions without looping, alert the operator, and sleep until the next calendar quota window.
