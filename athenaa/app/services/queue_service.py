"""
Modul Queue Manager, SQLite Play History & Free-Flowing Autoplay per Server Discord.
Mengelola antrean musik terisolasi per guild, mencegah pemutaran ganda (race condition),
mencatat riwayat lagu ke SQLite untuk perhitungan kemiripan (Lagu A + Lagu B -> Lagu C),
tanpa pembatasan penyanyi yang kaku (hanya mencegah judul lagu yang sama terulang kembali).
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from app.models.schema import QueueItemModel
from app.security.validators import can_control_queue


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_track_history(
    state: "GuildQueueState",
    item: QueueItemModel,
) -> None:
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
    guild_id: str
    voice_channel_id: str = "general-voice"
    voice_channel_name: str = "General Voice"
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
    autoplay: bool = False
    mode_247: bool = False
    active_radio_name: str = ""
    audio_filter: str = "normal"
    is_loading_stream: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.time)


class QueueService:
    """Layanan manajemen antrean musik per-server Discord dengan Host Lock System & Real-Time Sync."""

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
            self.prefetched_autoplay[guild_id] = list(items)

    def register_active_guild(self, guild_id: str, guild_name: str) -> None:
        gid = str(guild_id or "").strip()
        if gid:
            self.active_guilds[gid] = (guild_name or f"Server {gid}").strip()

    def unregister_active_guild(self, guild_id: str) -> None:
        gid = str(guild_id or "").strip()
        self.active_guilds.pop(gid, None)

    @property
    def listeners(self) -> List[Callable[[str, GuildQueueState, str], None]]:
        return self._state_listeners

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
        if not state.host_user_id and user_id and user_id != "system-autoplay":
            state.host_user_id = user_id
            state.host_username = username

    def _reindex(self, state: GuildQueueState) -> None:
        for idx, item in enumerate(state.queue, start=1):
            item.position = idx

    def add_track(
        self,
        guild_id: str,
        title: str,
        artist: str,
        duration_sec: int,
        source_type: str,
        source_url: str,
        requester_id: str,
        requester_name: str,
        album: str = "",
        stream_url: str = "",
        thumbnail_url: str = "",
        play_now: bool = False,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
        is_autoplay: bool = False,
    ) -> Tuple[QueueItemModel, bool]:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        auto_flag = bool(
            is_autoplay
            or source_type == "autoplay"
            or requester_id in ("system", "system-autoplay")
            or requester_name == "Autoplay"
        )

        if play_now and state.current_track is not None:
            allowed, reason = can_control_queue(
                user_id=requester_id,
                user_roles=user_roles or [],
                is_admin=is_admin,
                session_host_id=state.host_user_id,
                action="play_now",
                is_owner=is_owner,
                dj_role_id=dj_role_id,
            )
            if not allowed:
                raise PermissionError(reason)

        try:
            from app.services.music_service import _clean_youtube_title_and_artist

            clean_title, clean_artist = _clean_youtube_title_and_artist(title, artist)
        except Exception:
            clean_title, clean_artist = title, artist

        resolved_source_type = source_type
        if resolved_source_type not in ("radio", "youtube", "spotify_matched"):
            resolved_source_type = "spotify_matched"
        elif resolved_source_type == "youtube":
            s_url_low = (source_url or "").lower()
            if auto_flag or "results?search_query=" in s_url_low or "open.spotify.com" in s_url_low:
                resolved_source_type = "spotify_matched"

        item = QueueItemModel(
            item_id=f"trk-{uuid.uuid4().hex[:12]}",
            guild_id=guild_id,
            position=len(state.queue) + 1,
            title=clean_title,
            artist=clean_artist,
            album=album or ("YouTube Music Autoplay" if auto_flag else "YouTube Music"),
            duration_sec=max(0, int(duration_sec)),
            source_type=resolved_source_type,
            source_url=source_url,
            stream_url=stream_url,
            thumbnail_url=thumbnail_url,
            requester_id=requester_id,
            requester_name=requester_name,
            added_at=_utc_now(),
            is_autoplay=auto_flag,
        )

        self._assign_host_if_empty(state, requester_id, requester_name)

        if play_now or state.current_track is None:
            state.current_track = item
            state.last_played_track = item
            self.prefetched_autoplay.pop(guild_id, None)
            if not auto_flag and requester_id:
                state.host_user_id = requester_id
                state.host_username = requester_name
            state.is_playing = True
            state.is_paused = False
            state.position_sec = 0
            state.active_radio_name = item.title if item.source_type == "radio" else ""
            _record_track_history(state, item)
            self._reindex(state)
            self.notify_listeners(guild_id, "track_started")
            return item, True

        if not auto_flag:
            first_auto_idx = next(
                (
                    i
                    for i, q_it in enumerate(state.queue)
                    if getattr(q_it, "is_autoplay", False)
                    or q_it.source_type == "autoplay"
                    or q_it.requester_id in ("system", "system-autoplay")
                ),
                None,
            )
            if first_auto_idx is not None:
                state.queue.insert(first_auto_idx, item)
            else:
                state.queue.append(item)
        else:
            state.queue.append(item)

        self._reindex(state)
        self.notify_listeners(guild_id, "track_queued")
        return item, False

    def _build_default_autoplay_candidates(
        self,
        guild_id: str,
        seed_track: Optional[QueueItemModel] = None,
        allow_network: bool = True,
    ) -> List[QueueItemModel]:
        """
        Membangun kandidat Autoplay Mengalir Bebas (Pure Viral Radio Mix):
        - Mengutamakan Radio Mix dari lagu terakhir jika jaringan aktif.
        - Fallback ke katalog kurasi jika jaringan tidak tersedia.
        """
        candidates: List[QueueItemModel] = []
        state = self.get_state(guild_id)

        if seed_track is not None:
            try:
                from app.services.music_service import (
                    _is_album_or_compilation,
                    CURATED_YOUTUBE_SPOTIFY_CATALOG,
                    normalize_title_only,
                    recommend_autoplay_tracks,
                    search_youtube_http,
                )

                seed_norm_t = normalize_title_only(seed_track.title)
                prev_context: List[Tuple[str, str]] = []
                for r_trk in reversed(state.recent_tracks):
                    if normalize_title_only(r_trk.title) != seed_norm_t:
                        prev_context.append((r_trk.title, r_trk.artist))
                    if len(prev_context) >= 2:
                        break

                dynamic = []
                if allow_network:
                    dynamic = recommend_autoplay_tracks(
                        seed_title=seed_track.title,
                        seed_artist=seed_track.artist,
                        exclude_keys=state.history_keys,
                        limit=6,
                        guild_id=guild_id,
                        previous_tracks=prev_context,
                    )

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
                            album="YouTube Music Autoplay",
                            duration_sec=int(d_item.duration_sec or 205),
                            source_type="spotify_matched",
                            source_url=d_item.source_url,
                            stream_url=d_item.stream_url or "",
                            thumbnail_url=d_item.thumbnail_url or "",
                            requester_id="system-autoplay",
                            requester_name="Autoplay",
                            added_at=_utc_now(),
                            is_autoplay=True,
                        )
                    )

                if not candidates:
                    for c in CURATED_YOUTUBE_SPOTIFY_CATALOG:
                        if len(candidates) >= 6:
                            break
                        if _is_album_or_compilation(c["title"], int(c["duration_sec"] or 0)):
                            continue
                        if normalize_title_only(c["title"]) == seed_norm_t:
                            continue
                        if _is_in_track_history(state.history_keys, c["title"], c["artist"]):
                            continue
                        candidates.append(
                            QueueItemModel(
                                item_id=f"trk-auto-{uuid.uuid4().hex[:10]}",
                                guild_id=guild_id,
                                position=len(candidates) + 1,
                                title=c["title"],
                                artist=c["artist"],
                                album="YouTube Music Autoplay",
                                duration_sec=int(c["duration_sec"] or 205),
                                source_type="spotify_matched",
                                source_url=str(c.get("source_url") or ""),
                                stream_url="",
                                thumbnail_url=c["thumbnail_url"],
                                requester_id="system-autoplay",
                                requester_name="Autoplay",
                                added_at=_utc_now(),
                                is_autoplay=True,
                            )
                        )
            except Exception:
                try:
                    from app.services.music_service import (
                        _is_album_or_compilation,
                        CURATED_YOUTUBE_SPOTIFY_CATALOG,
                        normalize_title_only,
                    )
                    seed_norm_t = normalize_title_only(seed_track.title) if seed_track else ""
                    for c in CURATED_YOUTUBE_SPOTIFY_CATALOG:
                        if len(candidates) >= 6:
                            break
                        if _is_album_or_compilation(c["title"], int(c["duration_sec"] or 0)):
                            continue
                        if normalize_title_only(c["title"]) == seed_norm_t:
                            continue
                        if _is_in_track_history(state.history_keys, c["title"], c["artist"]):
                            continue
                        candidates.append(
                            QueueItemModel(
                                item_id=f"trk-auto-{uuid.uuid4().hex[:10]}",
                                guild_id=guild_id,
                                position=len(candidates) + 1,
                                title=c["title"],
                                artist=c["artist"],
                                album="YouTube Music Autoplay",
                                duration_sec=int(c["duration_sec"] or 205),
                                source_type="spotify_matched",
                                source_url=str(c.get("source_url") or ""),
                                stream_url="",
                                thumbnail_url=c["thumbnail_url"],
                                requester_id="system-autoplay",
                                requester_name="Autoplay",
                                added_at=_utc_now(),
                                is_autoplay=True,
                            )
                        )
                except Exception:
                    pass

        return candidates

    def advance_track(
        self,
        guild_id: str,
        autoplay_candidates: Optional[List[QueueItemModel]] = None,
    ) -> Optional[QueueItemModel]:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        previous = state.current_track
        if previous is not None:
            state.last_played_track = previous
            _record_track_history(state, previous)

        if previous and state.loop_mode == "one":
            state.position_sec = 0
            state.is_playing = True
            state.is_paused = False
            self.notify_listeners(guild_id, "track_started")
            return previous

        if previous and state.loop_mode == "queue" and not getattr(previous, "is_autoplay", False):
            cloned = QueueItemModel(
                item_id=f"trk-{uuid.uuid4().hex[:12]}",
                guild_id=guild_id,
                position=len(state.queue) + 1,
                title=previous.title,
                artist=previous.artist,
                album=previous.album,
                duration_sec=previous.duration_sec,
                source_type=previous.source_type,
                source_url=previous.source_url,
                stream_url=previous.stream_url,
                thumbnail_url=previous.thumbnail_url,
                requester_id=previous.requester_id,
                requester_name=previous.requester_name,
                added_at=_utc_now(),
                is_autoplay=False,
            )
            state.queue.append(cloned)

        if state.queue:
            user_req_idx = next(
                (
                    i
                    for i, q_it in enumerate(state.queue)
                    if not getattr(q_it, "is_autoplay", False)
                    and q_it.source_type != "autoplay"
                    and q_it.requester_id not in ("system", "system-autoplay")
                ),
                0,
            )
            nxt = state.queue.pop(user_req_idx)
            state.current_track = nxt
            state.last_played_track = nxt
            self.prefetched_autoplay.pop(guild_id, None)
            state.is_playing = True
            state.is_paused = False
            state.position_sec = 0
            state.active_radio_name = nxt.title if nxt.source_type == "radio" else ""
            _record_track_history(state, nxt)
            self._reindex(state)
            self.notify_listeners(guild_id, "track_started")
            return nxt

        if state.autoplay or autoplay_candidates is not None:
            seed_ref = previous or state.last_played_track

            if autoplay_candidates is not None:
                candidates = list(autoplay_candidates)
            else:
                prefetched_list = self.prefetched_autoplay.pop(guild_id, [])
                if prefetched_list:
                    candidates = list(prefetched_list)
                else:
                    candidates = self._build_default_autoplay_candidates(
                        guild_id, seed_track=seed_ref, allow_network=True
                    )

            for cand in candidates:
                if _is_in_track_history(state.history_keys, cand.title, cand.artist):
                    continue
                cand.is_autoplay = True
                cand.source_type = "spotify_matched"
                state.current_track = cand
                state.last_played_track = cand
                state.is_playing = True
                state.is_paused = False
                state.position_sec = 0
                _record_track_history(state, cand)
                self.notify_listeners(guild_id, "track_started")
                return cand

            if autoplay_candidates is None:
                state.history_keys.clear()
                if seed_ref:
                    _record_track_history(state, seed_ref)
                if not candidates:
                    candidates = self._build_default_autoplay_candidates(
                        guild_id, seed_track=seed_ref, allow_network=False
                    )
                for cand in candidates:
                    if not _is_in_track_history(state.history_keys, cand.title, cand.artist) or len(candidates) == 1:
                        cand.is_autoplay = True
                        cand.source_type = "spotify_matched"
                        state.current_track = cand
                        state.last_played_track = cand
                        state.is_playing = True
                        state.is_paused = False
                        state.position_sec = 0
                        _record_track_history(state, cand)
                        self.notify_listeners(guild_id, "track_started")
                        return cand

        state.current_track = None
        state.is_playing = False
        state.is_paused = False
        state.position_sec = 0
        self.notify_listeners(guild_id, "stopped")
        return None

    def play_queue_item(
        self,
        guild_id: str,
        item_id: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
    ) -> QueueItemModel:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            session_host_id=state.host_user_id,
            action="play_now",
            is_owner=is_owner,
            dj_role_id=dj_role_id,
        )
        if not allowed:
            raise PermissionError(reason)

        state.queue = [it for it in state.queue if it.item_id != item_id]
        state.current_track = target
        state.last_played_track = target
        self.prefetched_autoplay.pop(guild_id, None)
        state.is_playing = True
        state.is_paused = False
        state.position_sec = 0
        state.active_radio_name = target.title if target.source_type == "radio" else ""
        _record_track_history(state, target)
        self._reindex(state)
        self.notify_listeners(guild_id, "track_started")
        return target

    def remove_item(
        self,
        guild_id: str,
        item_id: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
    ) -> QueueItemModel:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            session_host_id=state.host_user_id,
            action="remove_item",
            target_item_requester_id=target.requester_id,
            is_owner=is_owner,
            dj_role_id=dj_role_id,
        )
        if not allowed:
            raise PermissionError(reason)

        state.queue = [it for it in state.queue if it.item_id != item_id]
        self._reindex(state)
        self.notify_listeners(guild_id, "queue_updated")
        return target

    def move_to_top(
        self,
        guild_id: str,
        item_id: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
    ) -> QueueItemModel:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            session_host_id=state.host_user_id,
            action="move_to_top",
            is_owner=is_owner,
            dj_role_id=dj_role_id,
        )
        if not allowed:
            raise PermissionError(reason)

        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        remaining = [it for it in state.queue if it.item_id != item_id]
        state.queue = [target, *remaining]
        self._reindex(state)
        self.notify_listeners(guild_id, "queue_updated")
        return target

    def control_session(
        self,
        guild_id: str,
        action: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
        value: Optional[Union[int, float, str, bool]] = None,
    ) -> GuildQueueState:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            session_host_id=state.host_user_id,
            action=action,
            is_owner=is_owner,
            dj_role_id=dj_role_id,
        )
        if not allowed:
            raise PermissionError(reason)

        event_type = "state_update"
        if action == "pause":
            if state.current_track:
                state.is_paused = True
                state.is_playing = False
                event_type = "paused"
        elif action == "resume":
            if state.current_track:
                state.is_paused = False
                state.is_playing = True
                event_type = "resumed"
        elif action == "skip":
            self.advance_track(guild_id)
            return state
        elif action == "stop":
            state.current_track = None
            state.queue.clear()
            state.is_playing = False
            state.is_paused = False
            state.position_sec = 0
            state.active_radio_name = ""
            if not state.mode_247:
                state.host_user_id = ""
                state.host_username = ""
            self.notify_listeners(guild_id, "stopped")
            return state
        elif action == "clear":
            state.queue.clear()
            event_type = "queue_updated"
        elif action == "shuffle":
            random.shuffle(state.queue)
            self._reindex(state)
            event_type = "queue_updated"
        elif action == "volume":
            vol = int(float(value if value is not None else 80))
            if vol < 1 or vol > 100:
                raise ValueError("Volume harus berada pada rentang 1% hingga 100%.")
            state.volume = vol
            event_type = "volume_changed"
        elif action == "loop":
            mode = str(value or "off").lower()
            if mode not in ("off", "one", "queue"):
                raise ValueError("Mode loop tidak valid. Gunakan off, one, atau queue.")
            state.loop_mode = mode
        elif action == "autoplay":
            state.autoplay = bool(value)
        elif action == "mode_247":
            state.mode_247 = bool(value)
        elif action == "seek":
            if state.current_track:
                pos = max(0, min(state.current_track.duration_sec, int(float(value or 0))))
                state.position_sec = pos
                event_type = "seeked"
        else:
            raise ValueError(f"Aksi kontrol '{action}' tidak dikenali.")

        self.notify_listeners(guild_id, event_type)
        return state

    control_playback = control_session

    def handle_host_left_voice(
        self,
        guild_id: str,
        arg2: object = None,
        arg3: object = None,
    ) -> str:
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        if arg3 is not None:
            departing_user_id = str(arg2 or "")
            raw_members = arg3 if isinstance(arg3, list) else []
        else:
            departing_user_id = state.host_user_id
            raw_members = arg2 if isinstance(arg2, list) else []

        if departing_user_id and state.host_user_id and departing_user_id != state.host_user_id:
            return state.host_user_id

        normalized: List[Tuple[str, str]] = []
        for item in raw_members:
            if isinstance(item, dict):
                uid = str(item.get("id", ""))
                uname = str(item.get("name", "Member"))
                if uid:
                    normalized.append((uid, uname))
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                normalized.append((str(item[0]), str(item[1])))

        if normalized:
            next_id, next_name = normalized[0]
            state.host_user_id = next_id
            state.host_username = next_name
            self.notify_listeners(guild_id, "host_transferred")
            return next_id

        state.host_user_id = ""
        state.host_username = ""
        if not state.mode_247:
            state.current_track = None
            state.queue.clear()
            state.is_playing = False
            state.is_paused = False
            state.position_sec = 0
        self.notify_listeners(guild_id, "host_cleared")
        return ""


GuildQueueService = QueueService
queue_service = QueueService()