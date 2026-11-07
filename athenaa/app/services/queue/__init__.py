"""
Queue Service Package - Modular Queue Management System.

This package splits the original monolithic QueueService into focused modules:
- state: GuildQueueState and QueueStateManager
- manager: QueueManager (add/remove/reorder tracks)
- playback: PlaybackController (play/pause/skip/volume/loop/autoplay)
- autoplay: AutoplayEngine (recommendations)
- host_lock: HostLockManager (permissions)
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from app.models.schema import QueueItemModel
from app.security.validators import can_control_queue

from .state import GuildQueueState, QueueStateManager, _utc_now
from .manager import QueueManager
from .playback import PlaybackController
from .autoplay import AutoplayEngine
from .host_lock import HostLockManager


class QueueService:
    """
    Main Queue Service - composes all modular components using delegation.
    
    This maintains the same public API as the original QueueService
    but internally uses composition of focused modules.
    """
    
    def __init__(self) -> None:
        # Composition: instantiate each component as attribute
        self._state_manager = QueueStateManager()
        self._manager = QueueManager()
        self._playback = PlaybackController()
        self._autoplay = AutoplayEngine()
        self._host_lock = HostLockManager()
        
        # Additional QueueService-specific attributes
        self.voice_bot_active: bool = False
        self.active_guilds: Dict[str, str] = {}
        self.prefetched_autoplay: Dict[str, List[QueueItemModel]] = {}
    
    # ==================== Delegation to components ====================
    
    # State management
    def get_state(self, guild_id: str):
        return self._state_manager.get_state(guild_id)
    
    def register_active_guild(self, guild_id: str, guild_name: str) -> None:
        return self._state_manager.register_active_guild(guild_id, guild_name)
    
    def unregister_active_guild(self, guild_id: str) -> None:
        return self._state_manager.unregister_active_guild(guild_id)
    
    def register_listener(self, listener) -> None:
        return self._state_manager.register_listener(listener)
    
    def notify_listeners(self, guild_id: str, event_type: str = "state_update") -> None:
        return self._state_manager.notify_listeners(guild_id, event_type)
    
    def set_prefetched_autoplay(self, guild_id: str, items) -> None:
        return self._state_manager.set_prefetched_autoplay(guild_id, items)
    
    # Queue management
    def add_track(self, *args, **kwargs):
        return self._manager.add_track(*args, **kwargs)
    
    def remove_item(self, *args, **kwargs):
        return self._manager.remove_item(*args, **kwargs)
    
    def move_to_top(self, *args, **kwargs):
        return self._manager.move_to_top(*args, **kwargs)
    
    def play_queue_item(self, *args, **kwargs):
        return self._manager.play_queue_item(*args, **kwargs)
    
    # Playback control
    def advance_track(self, *args, **kwargs):
        return self._playback.advance_track(*args, **kwargs)
    
    def control_session(self, *args, **kwargs):
        return self._playback.control_session(*args, **kwargs)
    
    control_playback = control_session
    
    def handle_host_left_voice(self, *args, **kwargs):
        return self._playback.handle_host_left_voice(*args, **kwargs)
    
    # Autoplay
    def _build_default_autoplay_candidates(self, *args, **kwargs):
        return self._autoplay.build_candidates(*args, **kwargs)
    
    # Host lock
    def check_permission(self, *args, **kwargs):
        return self._host_lock.check_permission(*args, **kwargs)
    
    def validate_or_raise(self, *args, **kwargs):
        return self._host_lock.validate_or_raise(*args, **kwargs)
    
    def assign_host_if_empty(self, *args, **kwargs):
        return self._host_lock.assign_host_if_empty(*args, **kwargs)
    
    def reset_session_if_idle(self, *args, **kwargs):
        return self._host_lock.reset_session_if_idle(*args, **kwargs)
    
    def handle_host_left(self, *args, **kwargs):
        return self._host_lock.handle_host_left(*args, **kwargs)
    
    # Properties for backward compatibility
    @property
    def _states(self):
        return self._state_manager._states
    
    @property
    def _state_listeners(self):
        return self._state_manager._state_listeners
    
    @property
    def voice_bot_active(self):
        return self._voice_bot_active
    
    @voice_bot_active.setter
    def voice_bot_active(self, value):
        self._voice_bot_active = value
    
    @property
    def active_guilds(self):
        return self._active_guilds
    
    @active_guilds.setter
    def active_guilds(self, value):
        self._active_guilds = value
    
    @property
    def prefetched_autoplay(self):
        return self._prefetched_autoplay
    
    @prefetched_autoplay.setter
    def prefetched_autoplay(self, value):
        self._prefetched_autoplay = value


# Backward compatibility aliases
GuildQueueService = QueueService
queue_service = QueueService()


__all__ = [
    "QueueService",
    "GuildQueueService",
    "queue_service",
    "GuildQueueState",
    "QueueStateManager",
    "QueueManager",
    "PlaybackController",
    "AutoplayEngine",
    "HostLockManager",
]