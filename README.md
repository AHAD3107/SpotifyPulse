# SpotifyPulse 🎵

**Personal Music Analytics & Data Engineering Platform**

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v0.json)](https://github.com/astral-sh/ruff)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-336791.svg)](https://www.postgresql.org/)
[![dbt Core](https://img.shields.io/badge/dbt-Core-FF694B.svg)](https://www.getdbt.com/)

---

## 1. Project Overview

**SpotifyPulse** is a personal music analytics and data engineering platform engineered to extract music listening history, user taste profiles, and playlist evolutions from the Spotify Web API, land them into a transient Bronze landing area, normalize them into Staging tables, transform them into a Kimball Star Schema data warehouse (Gold), and deliver interactive visual insights through a pure-Python Streamlit and Plotly dashboard.

### Core Engineering Highlights
* **Layered Data Architecture**: Modular Medallion-inspired processing pipeline:
  * **Bronze**: Transient raw landing buffer for immutable JSON snapshots with automated retention pruning (14-day TTL).
  * **Staging**: Cleaned, normalized, and deduplicated relational tables in PostgreSQL 17 (30-day rolling window).
  * **Gold**: Kimball Star Schema dimensional data warehouse optimized for analytical queries (2-year facts retention).
* **2026 Spotify Developer Policy & API Compliance**:
  * **February 2026 Migration**: Omission of deprecated fields (popularity, followers, genres, country, subscription tier) and migration to `GET /v1/playlists/{id}/items`.
  * **June 2026 Token Lifecycle**: Strict handling of 6-month refresh token expiration and `invalid_grant` protocols without retries.
  * **July 2026 Quota Consolidation**: Handling shared account-level quotas across Client IDs and differentiating burst 429 from `QUOTA_EXCEEDED`.
* **Deterministic Event Fingerprinting**: Ingestion deduplication is decoupled from dimension surrogates via SHA-256 `source_event_fingerprint` hashing, preventing collisions for local and unresolvable tracks.
* **Pure Music Analytics (Episode Exclusion Option A)**: Non-music podcast episodes are cleanly filtered at the staging boundary and recorded in audit metadata, keeping Gold models 100% focused on music analytics.
* **Deterministic Offline Demo Mode**: Runs out of the box without requiring live Spotify developer API credentials or allowlisted accounts.
* **Dockerized Airflow on Windows**: Containerized Apache Airflow via Docker Compose to ensure reliable orchestration in Windows environments.
* **Privacy & Disconnect Protocol**: Complete account disconnection flow that deletes tokens, halts ingestion, cascades user data deletion across all layers, and guides user self-service revocation.

---

## 2. Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language & Runtime** | Python 3.12 | Core development language |
| **Package Management** | `uv` (Astral) | Lightning-fast virtualenv and dependency resolution |
| **Backend & OAuth** | FastAPI | Confidential server-side REST server for Authorization Code Flow and triggers |
| **HTTP Client** | HTTPX | Asynchronous API client with rate-limiting backoff and quota detection |
| **Data Processing** | Pandas & Pydantic V2 | Ingestion cleaning, normalization, and strict schema validation |
| **Data Warehouse** | PostgreSQL 17 | Central relational and dimensional data warehouse |
| **ORM & Migrations** | SQLAlchemy 2.0 & Alembic | Schema provisioning and database migrations |
| **Data Transformation** | dbt Core (`dbt-postgres`) | Declarative SQL dimensional modeling (Star Schema) |
| **Workflow Orchestration**| Apache Airflow (Docker) | Containerized batch extractions and dbt run execution |
| **Analytics Dashboard** | Streamlit | Pure Python interactive dashboard |
| **Data Visualization** | Plotly | Dynamic heatmaps, time-series, and rank trajectory charts |
| **Containerization** | Docker & Docker Compose | Multi-service local and deployment virtualization |
| **Testing & Quality** | Pytest & Ruff | Automated unit/integration tests and high-performance linting |

---

## 3. High-Level Architecture

```
[ Spotify Web API ] ──(HTTPX Async)──► [ Bronze Landing (Transient JSON, 14-day TTL) ]
         │                                                     │
  (OAuth 2.0 Auth Code)                                  (Pydantic V2 & Pandas)
         │                                                     │
  [ FastAPI Auth ]                                             ▼
                                                     [ Staging (PostgreSQL 17) ]
                                                               │
                                                          (dbt Core)
                                                               │
                                                               ▼
                                                     [ Gold Warehouse (Star Schema) ]
                                                               │
                                                          (SQLAlchemy)
                                                               │
                                                               ▼
                                                     [ Streamlit + Plotly Dashboard ]
```

---

## 4. Repository Structure

```
SpotifyPulse/
│
├── docs/                        # Architecture & Technical Design Documents
│   ├── ARCHITECTURE.md          # System architecture, layered pipeline & components
│   ├── DATABASE_SCHEMA.md       # Kimball Star Schema, dimensions & explicit grains
│   ├── ETL_PIPELINE.md          # Bronze-Staging-Gold processing & retention lifecycle
│   ├── SPOTIFY_API.md           # API endpoints, 2026 availability matrix & limits
│   └── TECHNICAL_DECISIONS.md   # Architectural Decision Records (ADRs 001–015)
│
├── src/
│   └── spotify_pulse/           # Core Python Application Package
│       ├── __init__.py
│       ├── api/                 # FastAPI REST routes and API controllers
│       ├── auth/                # Spotify OAuth 2.0 & token lifecycle manager
│       ├── ingestion/           # Bronze extractors & synthetic demo generator
│       ├── processing/          # Staging validators, normalizers & deduplication
│       ├── warehouse/           # Database connections, models & Alembic migrations
│       ├── orchestration/       # Airflow DAG integration & triggers
│       ├── dashboard/           # Streamlit dashboard pages & visual components
│       ├── config/              # Pydantic Settings & environment validation
│       │   ├── __init__.py
│       │   └── settings.py
│       └── utils/               # Structured logging & shared utilities
│           ├── __init__.py
│           └── logging.py
│
├── tests/                       # Automated Test Suite
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures & test environment overrides
│   ├── unit/                    # Unit tests (Settings, Logging, Schema Rules)
│   ├── integration/             # Integration tests (Pipelines, Database)
│   └── fixtures/                # Mock Spotify API payloads
│
├── dbt/                         # dbt Core Dimensional Transformation Project
├── airflow/                     # Apache Airflow DAGs & Plugins (Dockerized)
├── scripts/                     # Operational scripts & data generators
├── data/                        # Local Layered Data Storage
│   ├── bronze/                  # Transient raw JSON responses (TTL-pruned)
│   ├── staging/                 # Intermediate normalized files
│   └── demo/                    # Synthetic demo datasets
│
├── docker/                      # Dockerfile & Docker Compose configurations
├── .env.example                 # Environment variables template
├── .gitignore                   # Comprehensive Git exclusion rules
├── pyproject.toml               # PEP 621 dependencies, Ruff & Pytest config
└── README.md                    # Project documentation
```

---

## 5. Quick Start & Setup Commands

### Prerequisites
* Python 3.12+
* [uv](https://docs.astral.sh/uv/) installed on your machine (`curl -LsSf https://astral.sh/uv/install.sh` or `winget install --id=astral-sh.uv`)

### 1. Initialize Virtual Environment & Dependencies
```bash
# Clone the repository
git clone https://github.com/AHAD3107/SpotifyPulse.git
cd SpotifyPulse

# Create virtual environment and install all dependencies using uv
uv sync
```

### 2. Configure Environment Variables
```bash
# Copy example configuration
cp .env.example .env

# By default, SPOTIFY_PULSE_DEMO_MODE=true is enabled, allowing execution without Spotify credentials.
```

### 3. Run Quality Verification Commands
```bash
# Execute linting and formatting checks with Ruff
uv run ruff check .

# Execute automated unit tests with Pytest
uv run pytest -v
```
