"""
Queue State Management - GuildQueueState and history tracking.
Extracted from QueueService for modularity.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set, Tuple, Any

from app.models.schema import QueueItemModel


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_track_history(
    state: "GuildQueueState",
    item: QueueItemModel,
) -> None:
    """Record track in history for deduplication and play history."""
    title = item.title or ""
    artist = item.artist or ""
    raw_k = f"{title.lower().strip()}::{artist.lower().strip()}"
    state.history_keys.add(raw_k)

    try:
        from app.services.music_service import (
            normalize_song_identity,
            normalize_title_only,
            record_play_history_db,
        )

        t_norm = normalize_title_only(title)
        ident = normalize_song_identity(title, artist)
        if t_norm:
            state.history_keys.add(t_norm)
        if ident:
            state.history_keys.add(ident)

        if not state.recent_tracks or normalize_title_only(state.recent_tracks[-1].title) != t_norm:
            state.recent_tracks.append(item)
            if len(state.recent_tracks) > 30:
                state.recent_tracks = state.recent_tracks[-30:]

        record_play_history_db(
            guild_id=state.guild_id,
            title=title,
            artist=artist,
            source_url=item.source_url,
            thumbnail_url=item.thumbnail_url,
            duration_sec=item.duration_sec,
            is_autoplay=bool(getattr(item, "is_autoplay", False)),
        )
    except Exception:
        pass


def _is_in_track_history(history_keys: Set[str], title: str, artist: str) -> bool:
    """Check if a track is in history (for deduplication)."""
    raw_k = f"{(title or '').lower().strip()}::{(artist or '').lower().strip()}"
    if raw_k in history_keys:
        return True
    try:
        from app.services.music_service import normalize_song_identity, normalize_title_only

        t_norm = normalize_title_only(title)
        ident = normalize_song_identity(title, artist)
        if t_norm and t_norm in history_keys:
            return True
        if ident and ident in history_keys:
            return True
    except Exception:
        pass
    return False


@dataclass
class GuildQueueState:
    """Per-guild queue state with all playback and history data."""
    guild_id: str
    voice_channel_id: str = "1428666547701809167"
    voice_channel_name: str = "NyolBar"
    host_user_id: str = ""
    host_username: str = ""
    current_track: Optional[QueueItemModel] = None
    last_played_track: Optional[QueueItemModel] = None
    queue: List[QueueItemModel] = field(default_factory=list)
    history_keys: Set[str] = field(default_factory=set)
    recent_tracks: List[QueueItemModel] = field(default_factory=list)
    is_playing: bool = False
    is_paused: bool = False
    position_sec: int = 0
    volume: int = 80
    loop_mode: str = "off"  # off | one | queue
    autoplay: bool = True
    mode_247: bool = True
    active_radio_name: str = ""
    is_loading_stream: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.time)


class QueueStateManager:
    """Manages GuildQueueState instances with cleanup and listeners."""
    
    # Konfigurasi cleanup guild inactive
    CLEANUP_INTERVAL_SEC = 3600      # Cek cleanup tiap 1 jam
    INACTIVITY_THRESHOLD_SEC = 7200  # Hapus state guild inactive > 2 jam

    def __init__(self) -> None:
        self._states: Dict[str, GuildQueueState] = {}
        self._state_listeners: List[Callable[[str, GuildQueueState, str], None]] = []
        self.voice_bot_active: bool = False
        self.active_guilds: Dict[str, str] = {}
        self.prefetched_autoplay: Dict[str, List[QueueItemModel]] = {}
        self._last_cleanup: float = 0.0

    def _maybe_cleanup_inactive_guilds(self) -> int:
        """Hapus GuildQueueState untuk guild yang inactive > threshold."""
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL_SEC:
            return 0

        removed = 0
        inactive_guilds = [
            gid for gid, state in self._states.items()
            if now - state.last_activity > self.INACTIVITY_THRESHOLD_SEC
        ]
        for gid in inactive_guilds:
            del self._states[gid]
            removed += 1

        self._last_cleanup = now
        return removed

    def _touch_activity(self, guild_id: str) -> None:
        """Update last_activity timestamp untuk guild."""
        state = self._states.get(guild_id)
        if state:
            state.last_activity = time.time()

    def set_prefetched_autoplay(self, guild_id: str, items: List[QueueItemModel]) -> None:
        if guild_id:
            self.prefetched_autoplay[str(guild_id)] = list(items)

    def register_active_guild(self, guild_id: str, guild_name: str) -> None:
        gid = str(guild_id or "").strip()
        gname = str(guild_name or "").strip()
        if gid:
            self.active_guilds[gid] = gname or f"Server {gid}"
            self.get_state(gid)

    def unregister_active_guild(self, guild_id: str) -> None:
        gid = str(guild_id or "").strip()
        self.active_guilds.pop(gid, None)

    def register_listener(self, listener: Callable[[str, GuildQueueState, str], None]) -> None:
        if listener not in self._state_listeners:
            self._state_listeners.append(listener)

    def notify_listeners(self, guild_id: str, event_type: str = "state_update") -> None:
        state = self.get_state(guild_id)
        for listener in list(self._state_listeners):
            try:
                listener(guild_id, state, event_type)
            except Exception:
                pass

    def get_state(self, guild_id: str) -> GuildQueueState:
        self._maybe_cleanup_inactive_guilds()
        if guild_id not in self._states:
            st = GuildQueueState(guild_id=guild_id)
            try:
                from app.services.music_service import get_recent_play_history_db

                for row in get_recent_play_history_db(guild_id, limit=50):
                    nt = str(row.get("norm_title") or "")
                    na = str(row.get("norm_artist") or "")
                    if nt:
                        st.history_keys.add(nt)
                        st.history_keys.add(f"{nt}::{na}")
            except Exception:
                pass
            self._states[guild_id] = st
        self._touch_activity(guild_id)
        return self._states[guild_id]

    def _assign_host_if_empty(self, state: GuildQueueState, user_id: str, username: str) -> None:
        if not state.host_user_id:
            state.host_user_id = user_id
            state.host_username = username

    def _reset_session_if_idle(self, state: GuildQueueState) -> None:
        if not state.current_track and not state.queue:
            state.is_playing = False
            state.is_paused = False
            state.position_sec = 0
            state.host_user_id = ""
            state.host_username = ""
            state.active_radio_name = ""

    @staticmethod
    def _reindex(state: GuildQueueState) -> None:
        for idx, item in enumerate(state.queue, start=1):
            item.position = idx