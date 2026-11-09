"""
Host Lock Manager - Permission validation for queue control.
Extracted from QueueService for modularity.
"""

from __future__ import annotations

from typing import List, Optional

from app.models.schema import QueueItemModel
from app.security.validators import can_control_queue

from .state import GuildQueueState


class HostLockManager:
    """Manages Host Lock permissions for queue control operations."""

    @staticmethod
    def check_permission(
        state: GuildQueueState,
        user_id: str,
        user_roles: List[str],
        is_admin: bool,
        is_owner: bool,
        dj_role_id: str,
        action: str,
        target_item_requester_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Check if user has permission for queue action."""
        return can_control_queue(
            user_id=user_id,
            user_roles=user_roles,
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action=action,
            target_item_requester_id=target_item_requester_id,
        )

    @staticmethod
    def validate_or_raise(
        state: GuildQueueState,
        user_id: str,
        user_roles: List[str],
        is_admin: bool,
        is_owner: bool,
        dj_role_id: str,
        action: str,
        target_item_requester_id: Optional[str] = None,
    ) -> None:
        """Check permission and raise PermissionError if not allowed."""
        allowed, reason = can_control_queue(
            user_id=user_id,
            user_roles=user_roles,
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=state.host_user_id,
            dj_role_id=dj_role_id,
            action=action,
            target_item_requester_id=target_item_requester_id,
        )
        if not allowed:
            raise PermissionError(reason)

    @staticmethod
    def assign_host_if_empty(state: GuildQueueState, user_id: str, username: str) -> None:
        """Assign session host if no host is set."""
        if not state.host_user_id:
            state.host_user_id = user_id
            state.host_username = username

    @staticmethod
    def reset_session_if_idle(state: GuildQueueState) -> None:
        """Reset session state when idle (no current track, no queue)."""
        if not state.current_track and not state.queue:
            state.is_playing = False
            state.is_paused = False
            state.position_sec = 0
            state.host_user_id = ""
            state.host_username = ""
            state.active_radio_name = ""

    @staticmethod
    def handle_host_left(
        state: GuildQueueState,
        departing_user_id: str = "",
        members: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """Handle host leaving voice channel - transfer to next member."""
        if departing_user_id and state.host_user_id and departing_user_id != state.host_user_id:
            return state.host_user_id

        raw_members = members or []

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
            return new_id

        state.host_user_id = ""
        state.host_username = ""
        return ""