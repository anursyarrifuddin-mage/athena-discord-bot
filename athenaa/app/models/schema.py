"""
Definisi Dataclass Model Domain untuk seluruh entitas Athenaa.
Dapat digunakan bersama SQLAlchemy ORM maupun repositori SQLite langsung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class QueueItemModel:
    item_id: str
    guild_id: str
    position: int
    title: str
    artist: str
    album: str
    duration_sec: int
    source_type: str  # youtube | spotify_matched | radio
    source_url: str
    stream_url: str
    thumbnail_url: str
    requester_id: str
    requester_name: str
    added_at: str
    is_autoplay: bool = False

    @property
    def id(self) -> str:
        return self.item_id



@dataclass
class MusicSessionModel:
    guild_id: str
    voice_channel_id: str
    voice_channel_name: str
    host_user_id: str
    host_username: str
    current_item_id: str
    is_playing: bool
    is_paused: bool
    position_sec: int
    volume: int
    loop_mode: str  # off | one | queue
    autoplay: bool
    mode_247: bool
    active_radio_name: str
    updated_at: str
    current_track: Optional[QueueItemModel] = None


@dataclass
class TaskModel:
    task_id: str
    guild_id: str
    external_uid: str
    course_name: str
    title: str
    description: str
    source_type: str  # manual | moodle_ics | google_classroom
    deadline_iso: str
    timezone: str
    source_url: str
    is_completed: bool
    completed_by: str
    completed_at: str
    created_by: str
    last_synced_at: str
    updated_at: str
