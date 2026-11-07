"""
Playback Controller - Playback control (play/pause/skip/volume/loop/autoplay/247).
Extracted from QueueService for modularity.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from app.models.schema import QueueItemModel
from app.security.validators import can_control_queue

from .state import GuildQueueState, QueueStateManager, _utc_now, _record_track_history, _is_in_track_history
from .manager import QueueManager


class PlaybackController(QueueManager):
    """Controls playback: play/pause/skip/volume/loop/autoplay/247/seek."""

    def _build_default_autoplay_candidates(
        self,
        guild_id: str,
        seed_track: Optional[QueueItemModel] = None,
        allow_network: bool = True,
    ) -> List[QueueItemModel]:
        """Build autoplay candidates from music service recommendations."""
        candidates: List[QueueItemModel] = []
        state = self.get_state(guild_id)

        if seed_track is not None:
            try:
                from app.services.music_service import (
                    _is_album_or_compilation,
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
                            added_at=self._utc_now(),
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
        """
        Play next track when current finishes or is skipped.
        Pure organic viral autoplay - no rigid artist rotation.
        """
        import uuid
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
                guild_id=previous.guild_id,
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
                added_at=self._utc_now(),
                is_autoplay=False,
            )
            state.queue.append(cloned)

        if state.queue:
            user_req_idx = next(
                (
                    i
                    for i, q_item in enumerate(state.queue)
                    if not (
                        getattr(q_item, "is_autoplay", False)
                        or q_item.source_type == "autoplay"
                        or q_item.requester_id in ("autoplay", "system-autoplay")
                    )
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

        if state.autoplay:
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

            # Fallback: clear history and retry once
            if autoplay_candidates is None and candidates:
                state.history_keys.clear()
                if seed_ref:
                    _record_track_history(state, seed_ref)
                for cand in candidates:
                    if not _is_in_track_history(state.history_keys, cand.title, cand.artist):
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
        self._reset_session_if_idle(state)
        self.notify_listeners(guild_id, "stopped")
        return None

    def control_session(
        self,
        guild_id: str,
        action: str,
        actor_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
        is_owner: bool = False,
        dj_role_id: str = "",
        has_dj_role: bool = False,
        value: Optional[int | str | bool] = None,
    ) -> GuildQueueState:
        """Control playback session (pause/resume/seek/volume/loop/autoplay/247/host_transfer)."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)

        allowed, reason = can_control_queue(
            user_id=actor_id,
            user_roles=user_roles or [],
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action=action,
            has_dj_role=has_dj_role,
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
            elif state.autoplay or state.queue:
                self.advance_track(guild_id)
                return state
        elif action == "restart":
            if state.current_track:
                state.position_sec = 0
                state.is_paused = False
                state.is_playing = True
                event_type = "track_started"
        elif action == "seek":
            if state.current_track:
                max_dur = max(0, state.current_track.duration_sec)
                target_sec = max(0, int(value if value is not None else 0))
                state.position_sec = min(max_dur, target_sec) if max_dur > 0 else target_sec
                event_type = "seeked"
        elif action == "stop":
            state.queue.clear()
            self.prefetched_autoplay.pop(guild_id, None)
            state.current_track = None
            state.is_playing = False
            state.is_paused = False
            state.position_sec = 0
            self._reset_session_if_idle(state)
            event_type = "stopped"
        elif action == "clear":
            state.queue.clear()
            event_type = "queue_updated"
        elif action == "shuffle":
            random.shuffle(state.queue)
            self._reindex(state)
            event_type = "queue_updated"
        elif action == "skip":
            saved_loop = state.loop_mode
            if saved_loop == "one":
                state.loop_mode = "off"
            self.advance_track(guild_id)
            state.loop_mode = saved_loop
            return state
        elif action == "volume":
            vol = int(value if value is not None else 80)
            if vol < 1 or vol > 100:
                raise ValueError("Volume harus berada pada rentang 1 hingga 100%.")
            state.volume = vol
            event_type = "volume_changed"
        elif action == "loop":
            mode = str(value or "off").lower()
            if mode not in ("off", "one", "queue"):
                raise ValueError("Mode loop harus 'off', 'one', atau 'queue'.")
            state.loop_mode = mode
        elif action == "autoplay":
            state.autoplay = bool(value)
            if not state.autoplay:
                self.prefetched_autoplay.pop(guild_id, None)
            elif state.current_track is None:
                self.advance_track(guild_id)
                return state
        elif action == "mode_247":
            state.mode_247 = bool(value)
        elif action == "transfer_host":
            state.host_user_id = str(value or "")
            if not state.host_user_id:
                self._reset_session_if_idle(state)
        else:
            raise ValueError(f"Aksi kontrol musik tidak dikenal: {action}")

        self.notify_listeners(guild_id, event_type)
        return state

    control_playback = control_session

    def handle_host_left_voice(
        self,
        guild_id: str,
        arg2: object = None,
        arg3: object = None,
    ) -> str:
        """Handle host leaving voice channel - transfer to next member."""
        state = self.get_state(guild_id)
        self._touch_activity(guild_id)
        
        if arg3 is not None:
            departing_user_id = str(arg2 or "")
            raw_members = arg3 if isinstance(arg3, list) else []
            if state.host_user_id and departing_user_id and departing_user_id != state.host_user_id:
                return state.host_user_id
        else:
            raw_members = arg2 if isinstance(arg2, list) else []

        normalized: List[Tuple[str, str]] = []
        for entry in raw_members:
            if isinstance(entry, tuple) and len(entry) >= 2:
                normalized.append((str(entry[0]), str(entry[1])))
            elif isinstance(entry, dict):
                uid = str(entry.get("id") or entry.get("user_id") or "")
                uname = str(entry.get("name") or entry.get("username") or "Member")
                if uid:
                    normalized.append((uid, uname))

        if normalized:
            new_id, new_name = normalized[0]
            state.host_user_id = new_id
            state.host_username = new_name
            self.notify_listeners(guild_id, "state_update")
            return new_id
        
        state.host_user_id = ""
        state.host_username = ""
        self._reset_session_if_idle(state)
        self.notify_listeners(guild_id, "state_update")
        return ""