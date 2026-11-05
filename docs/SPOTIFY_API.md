# Spotify Web API Specification & Limitations (2026 Architecture Audit)

## 1. Overview & Authentication Model

SpotifyPulse interfaces with the **Spotify Web API** using the **OAuth 2.0 Authorization Code Flow** designed for server-side confidential applications.

* **Base URL**: `https://api.spotify.com/v1`
* **Accounts Base URL**: `https://accounts.spotify.com`
* **Access Token Expiration**: Access tokens expire in approximately **3,600 seconds (1 hour)**.
* **Refresh Token Expiration (June 2026 Policy Update)**:
  * In June 2026, Spotify instituted a strict **six-month refresh token expiration policy**.
  * A refresh token is valid for exactly **6 months (180 days) from the original user authorization date**.
  * **Critical Rule**: Refreshing an access token does **NOT** reset or extend the 6-month refresh token lifetime. The 6-month expiration window remains tied strictly to the initial authorization timestamp.
  * When a refresh token expires, the token exchange endpoint responds with:
    ```json
    {
      "error": "invalid_grant",
      "error_description": "Refresh token expired"
    }
    ```
  * **Application Rule**: When `invalid_grant` is received, the client must **never retry** the token exchange. The backend must immediately mark the stored credentials as expired/invalid, purge the expired token from the vault, stop active ingestion schedules, and prompt the user for full interactive reauthorization.
  * **Token Metadata Tracking**: The token store must record `authorized_at_utc` and compute `refresh_token_expires_at_utc` (`authorized_at_utc + 180 days`) to proactively alert users before expiration.
* **Official References**:
  * [Spotify Web API Reference](https://developer.spotify.com/documentation/web-api/)
  * [February 2026 Web API Migration Guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
  * [June 18, 2026 Refresh Token Expiration Announcement](https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration)
  * [July 23, 2026 Web API Quota Updates](https://developer.spotify.com/blog/2026-07-23-web-api-quota-updates)
  * [Spotify Developer Quota Modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
  * [Spotify Developer Terms & Policy](https://developer.spotify.com/terms)

---

## 2. OAuth Architecture: Authorization Code Flow for Confidential Clients

### 2.1 Protocol Selection Rationale
Spotify supports multiple OAuth 2.0 grant types:
1. **Authorization Code Flow** (Confidential Server-Side Clients).
2. **Authorization Code Flow with PKCE** (Public Clients, e.g. Single Page Apps, Mobile).
3. **Client Credentials Flow** (Server-to-Server, no user context).

**Chosen Protocol**: **Authorization Code Flow**.
* **Context**: SpotifyPulse operates with a dedicated server-side FastAPI backend. The application credentials (`SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`) are securely stored in server environment variables and encrypted storage. They are never exposed to browser or client code.
* **Official Recommendation**: Spotify's official documentation designates the standard Authorization Code Flow as the primary, recommended grant type for confidential server-side backends where client secrets can be strictly protected.
* **Security Controls**:
  * **CSRF Mitigation**: Generation of high-entropy, cryptographically secure `state` parameters stored in ephemeral server-side sessions and verified upon redirect.
  * **Direct Server-to-Server Token Exchange**: The authorization `code` is exchanged for tokens over TLS directly between FastAPI and `https://accounts.spotify.com/api/token` using HTTP Basic authentication with client credentials.
  * **Encrypted Token Vault**: All received tokens are encrypted at rest using symmetric authenticated encryption (`cryptography.fernet`).

### 2.2 Disconnect & Token Revocation Architecture
* **Revocation Endpoint Reality**: Spotify's official OAuth 2.0 implementation **does not provide an RFC 7009 server-side token revocation endpoint** (such as `/api/token/revoke`). Applications cannot programmatically revoke granted access on Spotify's servers via an API call.
* **Designed Disconnect Protocol**:
  To guarantee full user privacy and stop data collection, the platform implements a comprehensive local disconnect flow (`POST /auth/disconnect`):
  1. **Stop API Requests**: Instantly invalidate the user's active session and abort all outbound Spotify HTTP requests.
  2. **Purge Token Vault**: Delete locally stored access tokens, refresh tokens, and encryption metadata for that user.
  3. **Halt Scheduled Ingestion**: Cancel and deregister all scheduled Airflow/ingestion jobs for the user.
  4. **Cascade User Data Purge**: Delete all Spotify-derived data for that user across Bronze raw files, Staging tables, and Gold warehouse tables.
  5. **User Self-Service Revocation Guidance**: Present clear instructions and direct deep links to Spotify's Account Management portal ([https://www.spotify.com/account/apps/](https://www.spotify.com/account/apps/)) where users can manually remove the application's third-party access permissions from Spotify's authorization server.

---

## 3. Verified Developer Quotas & Rate Limiting (July 2026 Policy)

The July 23, 2026 Spotify Developer policy update established strict quota consolidation and limits across developer accounts:

### 3.1 Developer Quota Rules
1. **Up to 25 Client IDs per Developer Account**: A developer account is permitted a maximum of 25 Client IDs across all registered applications.
2. **Shared Quota Across Client IDs**: **Crucial architectural reality**: Rate limits and API call quotas are **shared across all Client IDs belonging to the same developer account**. Registering multiple applications under the same account does **not** multiply rate limits; all apps draw from a single, shared quota pool.
3. **App Owner Premium Requirement**: The owner of an application in Development Mode **must maintain an active Spotify Premium subscription**. If Premium lapses, Development Mode access is suspended.
4. **5 Allowlisted Users in Development Mode**: Applications in Development Mode can authenticate a maximum of **5 explicitly allowlisted Spotify user accounts**. Unlisted users receive an `access_denied` error during OAuth consent.
5. **Mitigation via Demo Mode**: SpotifyPulse provides an offline **Demo Mode** (`SPOTIFY_PULSE_DEMO_MODE=true`) with synthetic data generation so that reviewers, interviewers, and automated CI pipelines can exercise the full data platform without consuming developer allowlist slots.

### 3.2 Distinguishing Rate Limits: Burst 429 vs `QUOTA_EXCEEDED`
Spotify returns HTTP status `429 Too Many Requests` under two distinct scenarios that must be handled separately:

| Error Type | Response Characteristics | Meaning | Ingestion Client Action |
| :--- | :--- | :--- | :--- |
| **Burst Rate Limit** | HTTP 429 with `Retry-After: <seconds>` header | Temporary volume threshold reached (short window). | Pause execution for `Retry-After + jitter` seconds, then retry up to `rate_limit_max_retries` (default 5). |
| **`QUOTA_EXCEEDED`** | HTTP 429 with error message `"QUOTA_EXCEEDED"` or missing/extreme `Retry-After` | The entire developer account has exhausted its 24-hour or rolling quota allocation across all Client IDs. | **Do not loop retries**. Immediately suspend all pipeline extractions, log an error alert, and pause ingestion until the quota reset window passes. |

---

## 4. February 2026 Field Availability Matrix

| Entity | Field Name | Status (Feb 2026) | Impact on SpotifyPulse Architecture |
| :--- | :--- | :--- | :--- |
| **Track** | `popularity` | **REMOVED / DEPRECATED** | Omitted from `dim_track` and facts. Metrics use observed event frequency and API ranking orders. |
| **Track** | `preview_url` | **DEPRECATED / NULLABLE** | Treated as optional/nullable; not relied upon for core analytics. |
| **Track** | `id`, `name`, `duration_ms` | **SUPPORTED** | Retained in `dim_track`. `duration_ms` is catalog metadata only (NOT actual listening duration). |
| **Artist** | `popularity` | **REMOVED / DEPRECATED** | Omitted from `dim_artist` and snapshot facts. |
| **Artist** | `followers.total` | **REMOVED / DEPRECATED** | Omitted from `dim_artist` and snapshot facts. |
| **Artist** | `genres` | **REMOVED / DEPRECATED** | Omitted from `dim_artist`. Platform avoids legacy genre taxonomies. |
| **Artist** | `id`, `name`, `images` | **SUPPORTED** | Retained in `dim_artist` for creator identification and dashboard attribution. |
| **User Profile**| `country` | **REMOVED / DEPRECATED** | Omitted from `dim_user`. Geographic assumptions are omitted. |
| **User Profile**| `product` (tier) | **REMOVED / DEPRECATED** | Omitted from `dim_user`. Application behavior is uniform across tiers. |
| **User Profile**| `id`, `display_name`, `images` | **SUPPORTED** | Retained in `dim_user` for user identification and personalization. |
| **Recently Played**| `played_at`, `track`, `context`| **SUPPORTED** | Retained in `fact_listening_event`. `played_at` provides exact event occurrence timestamp. |
| **Recently Played**| *Listening duration* | **NOT PROVIDED BY API** | Spotify does not expose play duration per scrobble. Recorded as `observed_event_count = 1`. |
| **Playlists** | `GET /playlists/{id}/tracks` | **DEPRECATED** | **MIGRATED**: Use `GET /playlists/{id}/items` exclusively. |
| **Playlists** | `GET /playlists/{id}/items` | **SUPPORTED** | Official endpoint for fetching playlist entries (tracks, episodes, local files). |

---

## 5. Playlist Items & Episode Handling Decision

The official `GET /v1/playlists/{id}/items` endpoint returns heterogeneous items (tracks, podcast episodes, audiobooks).

### Architectural Decision: Option A (Explicit Exclusion with Quality Metadata)
* **Chosen Approach**: Filter out podcast episodes (`item.type == 'episode'`) at the Staging ingestion boundary and record excluded episode metrics in ingestion quality metadata (`episodes_excluded_count`).
* **Rationale**:
  * SpotifyPulse is specifically a **personal music analytics platform**.
  * Podcast episodes possess fundamentally distinct schemas and semantics (shows, publishers, season numbers, long durations) that would dilute music-focused dimensional models.
  * Option A maintains schema simplicity and analytical purity in the Gold layer while maintaining complete transparency through audit quality tracking.

---

## 6. Detailed Endpoint Contracts

### 6.1 Get Current User Profile
* **Endpoint**: `GET /v1/me`
* **OAuth Scope**: `user-read-private`, `user-read-email`
* **Supported Fields**: `id`, `display_name`, `email`, `images`, `uri`, `external_urls`.

### 6.2 Get Recently Played Tracks
* **Endpoint**: `GET /v1/me/player/recently-played`
* **OAuth Scope**: `user-read-recently-played`
* **Parameters**: `limit` (1–50, default 20), `after` (Unix ms), `before` (Unix ms).
* **Constraints**:
  * Max 50 items per response.
  * No guaranteed 30-day retention window; heavy listening can cycle through 50 tracks in a single day.
  * Ingestion requires hourly polling using `after={cursor}`.

### 6.3 Get Top Tracks & Top Artists
* **Endpoints**: `GET /v1/me/top/tracks`, `GET /v1/me/top/artists`
* **OAuth Scope**: `user-top-read`
* **Parameters**: `time_range` (`'short_term'`, `'medium_term'`, `'long_term'`), `limit` (1–50), `offset` (0–49).
* **Ranking Logic**: Items are ranked 1 to 50 based strictly on the ordered array index (`index + 1`).

### 6.4 Get User Playlists & Items
* **Endpoints**: `GET /v1/me/playlists`, `GET /v1/playlists/{playlist_id}/items`
* **OAuth Scope**: `playlist-read-private`, `playlist-read-collaborative`
* **Scope Boundary**: Restricted to playlists owned by the user or where they are an active collaborator.
