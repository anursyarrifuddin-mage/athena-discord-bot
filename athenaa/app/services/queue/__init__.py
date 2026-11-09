"""
Queue Service Package - Re-exports the unified QueueService from app.services.queue_service
while maintaining modular class exports for backward compatibility.
"""

from __future__ import annotations

from app.services.queue_service import (
    GuildQueueService,
    GuildQueueState,
    QueueService,
    queue_service,
)
from .autoplay import AutoplayEngine
from .host_lock import HostLockManager
from .manager import QueueManager
from .playback import PlaybackController
from .state import QueueStateManager

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