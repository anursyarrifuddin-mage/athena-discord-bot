"""
Autoplay Engine - Pure organic viral autoplay recommendations.
Extracted from QueueService for modularity.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from app.models.schema import QueueItemModel
from app.services.music_service import (
    _is_album_or_compilation,
    normalize_title_only,
    normalize_artist_only,
    normalize_song_identity,
    recommend_autoplay_tracks,
    search_youtube_http,
    get_recent_play_history_db,
    is_same_base_song,
)

from .state import GuildQueueState, _utc_now, _record_track_history, _is_in_track_history


class AutoplayEngine:
    """Generates pure organic viral autoplay recommendations using Radio Mix chain."""

    def build_candidates(
        self,
        guild_id: str,
        seed_track: Optional[QueueItemModel] = None,
        allow_network: bool = True,
    ) -> List[QueueItemModel]:
        """Build autoplay candidates from music service recommendations."""
        candidates: List[QueueItemModel] = []
        state = self._get_state(guild_id)

        if seed_track is not None:
            try:
                seed_norm_t = normalize_title_only(seed_track.title)
                prev_context: List[Tuple[str, str]] = []
                for r_trk in reversed(state.recent_tracks):
                    if normalize_title_only(r_trk.title) != seed_norm_t:
                        prev_context.append((r_trk.title, r_trk.artist))
                    if len(prev_context) >= 2:
                        break

                dynamic = recommend_autoplay_tracks(
                    seed_title=seed_track.title,
                    seed_artist=seed_track.artist,
                    exclude_keys=state.history_keys,
                    limit=6,
                    guild_id=guild_id,
                    previous_tracks=prev_context,
                )

                # If Radio Mix still empty, search for similar tracks (NOT static catalog!)
                if not dynamic:
                    dynamic = search_youtube_http(
                        f"{seed_track.title} {seed_track.artist}",
                        limit=6,
                        default_source_type="spotify_matched",
                    )

                for idx, d_item in enumerate(dynamic, start=1):
                    if _is_album_or_compilation(d_item.title, int(d_item.duration_sec or 0)):
                        continue
                    if normalize_title_only(d_item.title) == seed_norm_t:
                        continue
                    candidates.append(
                        QueueItemModel(
                            item_id=f"trk-auto-{uuid.uuid4().hex[:10]}",
                            guild_id=guild_id,
                            position=idx,
                            title=d_item.title,
                            artist=d_item.artist,
                            album="Spotify Autoplay",
                            duration_sec=int(d_item.duration_sec or 205),
                            source_type="spotify_matched",
                            source_url=d_item.source_url,
                            stream_url=d_item.stream_url or "",
                            thumbnail_url=d_item.thumbnail_url or "",
                            requester_id="system-autoplay",
                            requester_name="Spotify Autoplay",
                            added_at=_utc_now(),
                            is_autoplay=True,
                        )
                    )
            except Exception:
                pass

        return candidates

    def select_next_autoplay(
        self,
        state: GuildQueueState,
        candidates: List[QueueItemModel],
        seed_track: Optional[QueueItemModel] = None,
        previous_tracks: Optional[List[Tuple[str, str]]] = None,
        limit: int = 5,
    ) -> Optional[QueueItemModel]:
        """Select next autoplay track using weighted random from candidate pool."""
        if not candidates:
            return None

        # Filter candidates
        clean_b_title = ""
        clean_b_artist = ""
        norm_b_title = ""
        norm_b_artist = ""
        if seed_track:
            clean_b_title, clean_b_artist = self._clean_seed(seed_track.title, seed_track.artist)
            norm_b_title = normalize_title_only(clean_b_title)
            norm_b_artist = normalize_artist_only(clean_b_artist)

        seen_base_titles: Set[str] = {norm_b_title} if norm_b_title else set()
        raw_history_titles: List[str] = [clean_b_title] if clean_b_title else []

        for raw_k in state.history_keys:
            k_str = str(raw_k).strip()
            if "::" in k_str:
                p1, _ = k_str.split("::", 1)
                t_n = normalize_title_only(p1)
                if t_n:
                    seen_base_titles.add(t_n)
                    raw_history_titles.append(p1)
            else:
                t_n = normalize_title_only(k_str)
                if t_n:
                    seen_base_titles.add(t_n)

        db_history = get_recent_play_history_db(guild_id=state.guild_id, limit=60) if state.guild_id else []
        track_a_title = ""
        track_a_artist = ""
        track_a_vid = ""
        track_b_vid = ""
        recent_artist_streak = 0

        for idx_row, row in enumerate(db_history):
            r_title = str(row.get("title") or "")
            r_artist = str(row.get("artist") or "")
            r_norm_t = normalize_title_only(r_title) or str(row.get("norm_title") or "")
            r_norm_a = normalize_artist_only(r_artist) or str(row.get("norm_artist") or "")
            if r_norm_t:
                seen_base_titles.add(r_norm_t)
            if r_title:
                raw_history_titles.append(r_title)
            if idx_row < 3 and norm_b_artist and r_norm_a == norm_b_artist:
                recent_artist_streak += 1
            if r_norm_t == norm_b_title and not track_b_vid:
                v_db = str(row.get("video_id") or "")
                if len(v_db) == 11:
                    track_b_vid = v_db
            if not track_a_title and r_norm_t and r_norm_t != norm_b_title:
                track_a_title = r_title
                track_a_artist = r_artist
                v_a = str(row.get("video_id") or "")
                if len(v_a) == 11:
                    track_a_vid = v_a

        if not track_a_title and previous_tracks:
            for p_title, p_artist in previous_tracks:
                p_norm_t = normalize_title_only(p_title)
                if p_norm_t and p_norm_t != norm_b_title:
                    track_a_title, track_a_artist = self._clean_seed(p_title, p_artist)
                    track_a_vid = ""  # Would extract from registry
                    break

        # This is a simplified version - the full logic is in recommend_autoplay_tracks
        # Here we just pick from candidates using weighted random
        valid_candidates = []
        for cand in candidates:
            if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
                continue
            bt_cand = normalize_title_only(cand.title)
            if not bt_cand or bt_cand in seen_base_titles:
                continue
            if any(is_same_base_song(cand.title, prev_t) for prev_t in raw_history_titles[:25]):
                continue
            valid_candidates.append(cand)

        if not valid_candidates:
            return None

        # Weighted random selection
        weights = [float(i + 1) ** 0.70 for i in range(len(valid_candidates))]
        picked_idx = random.choices(range(len(valid_candidates)), weights=weights, k=1)[0]
        picked = valid_candidates.pop(picked_idx)
        
        return picked

    def _clean_seed(self, title: str, artist: str) -> Tuple[str, str]:
        """Clean title and artist using music service cleaner."""
        try:
            from app.services.music_service import _clean_youtube_title_and_artist
            return _clean_youtube_title_and_artist(title, artist)
        except Exception:
            return title, artist

    def _get_state(self, guild_id: str) -> "GuildQueueState":
        """Get guild state - to be implemented by parent class."""
        raise NotImplementedError