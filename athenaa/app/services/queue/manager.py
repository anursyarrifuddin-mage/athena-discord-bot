"""
Queue Manager - Track addition, removal, and queue ordering.
Extracted from QueueService for modularity.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from app.models.schema import QueueItemModel
from app.security.validators import can_control_queue

from .state import GuildQueueState, QueueStateManager, _utc_now, _record_track_history


class QueueManager(QueueStateManager):
    """Manages queue operations: add, remove, reorder tracks."""

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
        has_dj_role: bool = False,
    ) -> Tuple[QueueItemModel, bool]:
        """Add a track to the queue. Returns (item, started_immediately)."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)

        auto_flag = bool(
            is_autoplay
            or source_type == "autoplay"
            or requester_id in ("autoplay", "system-autoplay")
        )
        if not auto_flag:
            self._assign_host_if_empty(state, requester_id, requester_name)

        if play_now and state.current_track and not getattr(state.current_track, "is_autoplay", False):
            allowed, reason = can_control_queue(
                user_id=requester_id,
                user_roles=user_roles or [],
                is_admin=is_admin,
                is_owner=is_owner,
                session_host_id=state.host_user_id,
                dj_role_id=dj_role_id,
                action="play_now",
                has_dj_role=has_dj_role,
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
            album=album or ("Spotify Autoplay" if auto_flag else "Spotify Single"),
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
                    for i, q_item in enumerate(state.queue)
                    if getattr(q_item, "is_autoplay", False)
                    or q_item.source_type == "autoplay"
                    or q_item.requester_id in ("autoplay", "system-autoplay")
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
        self.notify_listeners(guild_id, "queue_updated")
        return item, False

    def remove_item(
        self,
        guild_id: str,
        item_id: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
        has_dj_role: bool = False,
    ) -> QueueItemModel:
        """Remove a track from the queue."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)

        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action="remove_item",
            target_item_requester_id=target.requester_id,
            has_dj_role=has_dj_role,
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
        has_dj_role: bool = False,
    ) -> QueueItemModel:
        """Move a track to the top of the queue."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action="move_to_top",
            has_dj_role=has_dj_role,
        )
        if not allowed:
            raise PermissionError(reason)

        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        state.queue = [target] + [it for it in state.queue if it.item_id != item_id]
        self._reindex(state)
        self.notify_listeners(guild_id, "queue_updated")
        return target

    def play_queue_item(
        self,
        guild_id: str,
        item_id: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
        has_dj_role: bool = False,
    ) -> QueueItemModel:
        """Play a specific queue item immediately."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)

        target = next((it for it in state.queue if it.item_id == item_id), None)
        if not target:
            raise KeyError("Item antrean tidak ditemukan.")

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action="play_now",
            has_dj_role=has_dj_role,
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