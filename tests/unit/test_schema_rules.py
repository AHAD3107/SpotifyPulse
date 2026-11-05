"""Unit tests for database schema business rules and modeling contracts.

Tests the architectural constraints:
1. Deterministic source_event_fingerprint generation for listening events.
2. Handling null/local track IDs without surrogate key collisions.
3. Playlist item snapshot grain supporting duplicate tracks at distinct positions.
4. Top track and artist ranking assignment derived strictly from API array ordering.
5. Episode exclusion filter (Option A) for pure music analytics.
"""

import hashlib
from typing import Any


def compute_source_event_fingerprint(
    user_id: str,
    played_at_utc: str,
    spotify_track_id: str | None = None,
    track_name: str | None = None,
    artist_name: str | None = None,
    album_name: str | None = None,
    duration_ms: int | None = None,
) -> str:
    """Generate deterministic SHA-256 fingerprint for a listening event.

    Uses Spotify track ID when present, or normalized source metadata for local/missing tracks.
    """
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


def generate_playlist_item_key(
    playlist_id: str,
    snapshot_id: str,
    position: int,
) -> str:
    """Generate unique key for a playlist item snapshot based on sequence position."""
    return f"{playlist_id}::{snapshot_id}::pos_{position}"


def filter_playlist_items_for_music_analytics(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Filter playlist items to music tracks only (Option A), counting excluded episodes."""
    tracks = []
    episodes_excluded_count = 0
    for item in items:
        item_type = item.get("type", "track")
        if item_type == "episode":
            episodes_excluded_count += 1
        else:
            tracks.append(item)
    return tracks, episodes_excluded_count


def assign_ranking_from_api_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign rank 1..N based on API array ordering without popularity fields."""
    ranked = []
    for idx, item in enumerate(items):
        ranked.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "rank": idx + 1,
        })
    return ranked


def calculate_rank_change(prior_rank: int | None, current_rank: int) -> int | None:
    """Calculate rank shift between snapshots."""
    if prior_rank is None:
        return None
    return prior_rank - current_rank


# ==============================================================================
# Deduplication Tests
# ==============================================================================

def test_source_event_fingerprint_distinguishes_different_local_tracks_at_same_timestamp() -> None:
    """Test that two different local tracks at identical timestamp produce distinct hashes."""
    ts = "2026-11-05T08:00:00.000Z"
    user_id = "user_456"

    # Both tracks have no Spotify ID (local files), but different metadata
    fp1 = compute_source_event_fingerprint(
        user_id=user_id,
        played_at_utc=ts,
        spotify_track_id=None,
        track_name="Acoustic Demo A",
        artist_name="Independent Artist",
        album_name="Home Recordings",
        duration_ms=180000,
    )
    fp2 = compute_source_event_fingerprint(
        user_id=user_id,
        played_at_utc=ts,
        spotify_track_id=None,
        track_name="Acoustic Demo B",
        artist_name="Independent Artist",
        album_name="Home Recordings",
        duration_ms=210000,
    )

    assert fp1 != fp2
    assert len(fp1) == 64
    assert len(fp2) == 64


def test_source_event_fingerprint_identical_event_ingested_twice() -> None:
    """Test that identical event data produces the identical deterministic SHA-256 fingerprint."""
    fp1 = compute_source_event_fingerprint(
        user_id="user_789",
        played_at_utc="2026-11-05T08:15:30.123Z",
        spotify_track_id="spotify_track_xyz",
    )
    fp2 = compute_source_event_fingerprint(
        user_id="user_789",
        played_at_utc="2026-11-05T08:15:30.123Z",
        spotify_track_id="spotify_track_xyz",
    )

    assert fp1 == fp2


def test_source_event_fingerprint_same_track_at_different_timestamps() -> None:
    """Test that the same track played at different timestamps produces distinct fingerprints."""
    fp1 = compute_source_event_fingerprint(
        user_id="user_789",
        played_at_utc="2026-11-05T08:00:00.000Z",
        spotify_track_id="spotify_track_xyz",
    )
    fp2 = compute_source_event_fingerprint(
        user_id="user_789",
        played_at_utc="2026-11-05T09:00:00.000Z",
        spotify_track_id="spotify_track_xyz",
    )

    assert fp1 != fp2


def test_source_event_fingerprint_missing_track_identifiers() -> None:
    """Test graceful handling when Spotify track ID and metadata are partially null."""
    fp = compute_source_event_fingerprint(
        user_id="user_unknown",
        played_at_utc="2026-11-05T10:00:00Z",
        spotify_track_id=None,
        track_name="Untitled Stream",
        artist_name=None,
        album_name=None,
        duration_ms=None,
    )

    assert isinstance(fp, str)
    assert len(fp) == 64


# ==============================================================================
# Playlist & Episode Filtering Tests
# ==============================================================================

def test_playlist_item_grain_allows_duplicate_tracks() -> None:
    """Test that duplicate tracks at distinct positions produce unique keys."""
    playlist_id = "playlist_party_mix"
    snapshot_id = "snap_v1_abc"

    key_pos_0 = generate_playlist_item_key(playlist_id, snapshot_id, position=0)
    key_pos_4 = generate_playlist_item_key(playlist_id, snapshot_id, position=4)

    assert key_pos_0 != key_pos_4
    assert key_pos_0 == "playlist_party_mix::snap_v1_abc::pos_0"
    assert key_pos_4 == "playlist_party_mix::snap_v1_abc::pos_4"


def test_playlist_episode_exclusion_option_a() -> None:
    """Test that Option A filters out podcast episodes and tracks exclusion count."""
    mock_items = [
        {"id": "t1", "name": "Song 1", "type": "track"},
        {"id": "e1", "name": "Podcast Episode 101", "type": "episode"},
        {"id": "t2", "name": "Song 2", "type": "track"},
        {"id": "e2", "name": "News Daily", "type": "episode"},
    ]

    music_tracks, excluded_count = filter_playlist_items_for_music_analytics(mock_items)

    assert len(music_tracks) == 2
    assert excluded_count == 2
    assert [t["id"] for t in music_tracks] == ["t1", "t2"]


# ==============================================================================
# Ranking Tests
# ==============================================================================

def test_ranking_assignment_derived_from_array_order() -> None:
    """Test that top items are assigned ranks 1..N purely from response array order."""
    mock_api_items = [
        {"id": "track_top_1", "name": "First Song"},
        {"id": "track_top_2", "name": "Second Song"},
        {"id": "track_top_3", "name": "Third Song"},
    ]
    ranked = assign_ranking_from_api_order(mock_api_items)

    assert len(ranked) == 3
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2
    assert ranked[2]["rank"] == 3


def test_rank_change_calculation() -> None:
    """Test rank change calculation logic."""
    assert calculate_rank_change(prior_rank=5, current_rank=2) == 3
    assert calculate_rank_change(prior_rank=1, current_rank=4) == -3
    assert calculate_rank_change(prior_rank=None, current_rank=1) is None
