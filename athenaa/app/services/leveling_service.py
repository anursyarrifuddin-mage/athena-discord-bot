"""
Modul RPG Leveling & Sistem AFK.
- Formula kebutuhan EXP dinamis: max_exp = 100 + (level * 25)
- Pencegahan EXP farming: cooldown per anggota per server (default 60 detik),
  mengabaikan pesan bot dan pesan kosong/terlalu pendek.
- Leaderboard Top 15 per server Discord.
- Penyimpanan status AFK persisten di database.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.database import DatabaseManager, db_manager


def calculate_max_exp(level: int) -> int:
    """Formula resmi Athenaa: max_exp = 100 + (level * 25)."""
    return 100 + (max(1, int(level)) * 25)


@dataclass
class _ExpBufferEntry:
    """In-memory buffer entry for a user's EXP gains."""
    guild_id: str
    user_id: str
    username: str
    display_name: str
    level: int
    current_exp: int
    total_messages: int
    last_exp_at: str  # ISO format
    accumulated_exp: int = 0
    message_count: int = 0


class LevelingService:
    """Layanan pengelolaan EXP, Level-Up, Leaderboard Top 15, dan Status AFK."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager
        self._exp_buffer: Dict[Tuple[str, str], _ExpBufferEntry] = {}

    def _flush_exp_buffer(self) -> None:
        """Flush accumulated EXP gains to database in a single transaction."""
        if not self._exp_buffer:
            return

        # Flush all buffered entries
        with self.db.transaction() as conn:
            for key, entry in self._exp_buffer.items():
                # Compute level-ups from accumulated EXP
                level = entry.level
                current_exp = entry.current_exp + entry.accumulated_exp
                total_messages = entry.total_messages + entry.message_count
                max_exp = calculate_max_exp(level)
                while current_exp >= max_exp:
                    current_exp -= max_exp
                    level += 1
                    max_exp = calculate_max_exp(level)

                # Use INSERT OR REPLACE to handle both new and existing users
                conn.execute(
                    """
                    INSERT OR REPLACE INTO level_profiles (
                        guild_id, user_id, username, display_name, level, current_exp,
                        total_messages, last_exp_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.guild_id,
                        entry.user_id,
                        entry.username,
                        entry.display_name,
                        level,
                        current_exp,
                        total_messages,
                        entry.last_exp_at,
                        entry.last_exp_at,
                    ),
                )

        self._exp_buffer.clear()

    def process_message_activity(
        self,
        guild_id: str,
        user_id: str,
        username: str,
        display_name: str,
        message_content: str,
        is_bot: bool = False,
        cooldown_seconds: int = 60,
        exp_gain: int = 15,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, int, int, int]:
        """
        Memproses aktivitas pesan anggota.
        Mengembalikan (leveled_up, level_sekarang, current_exp, max_exp).
        """
        if is_bot or len(message_content.strip()) < 3:
            profile = self.get_profile(guild_id, user_id, username, display_name)
            return False, profile["level"], profile["current_exp"], calculate_max_exp(profile["level"])

        current_time = now or datetime.now(timezone.utc)
        now_iso = current_time.isoformat()
        buffer_key = (guild_id, user_id)

        # Check if user has existing buffer entry
        entry = self._exp_buffer.get(buffer_key)
        if entry is not None:
            # User has buffered state - check cooldown against buffered last_exp_at
            last_dt = datetime.fromisoformat(entry.last_exp_at)
            if (current_time - last_dt).total_seconds() < cooldown_seconds:
                # Cooldown not passed - return current buffered state
                max_exp = calculate_max_exp(entry.level)
                return False, entry.level, entry.current_exp + entry.accumulated_exp, max_exp

            # Cooldown passed - accumulate EXP in buffer
            entry.accumulated_exp += exp_gain
            entry.message_count += 1
            entry.last_exp_at = now_iso
            entry.username = username
            entry.display_name = display_name

            # Check for level-up in buffer
            level = entry.level
            current_exp = entry.current_exp + entry.accumulated_exp
            leveled_up = False
            max_exp = calculate_max_exp(level)
            while current_exp >= max_exp:
                current_exp -= max_exp
                level += 1
                leveled_up = True
                max_exp = calculate_max_exp(level)

            # Try to flush
            self._flush_exp_buffer()
            return leveled_up, level, current_exp, max_exp

        # No buffer entry - read from DB
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT level, current_exp, total_messages, last_exp_at FROM level_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()

            if row is None:
                # New user - create buffer entry with initial state
                level = 1
                current_exp = exp_gain
                leveled_up = False
                max_exp = calculate_max_exp(level)
                while current_exp >= max_exp:
                    current_exp -= max_exp
                    level += 1
                    leveled_up = True
                    max_exp = calculate_max_exp(level)

                self._exp_buffer[buffer_key] = _ExpBufferEntry(
                    guild_id=guild_id,
                    user_id=user_id,
                    username=username,
                    display_name=display_name,
                    level=level,
                    current_exp=current_exp,
                    total_messages=1,
                    last_exp_at=now_iso,
                    accumulated_exp=0,
                    message_count=0,
                )
                self._flush_exp_buffer()
                return leveled_up, level, current_exp, max_exp

            # Existing user - check cooldown
            level = int(row["level"])
            current_exp = int(row["current_exp"])
            total_messages = int(row["total_messages"])
            last_exp_at = row["last_exp_at"]

            if last_exp_at:
                last_dt = datetime.fromisoformat(last_exp_at)
                if (current_time - last_dt).total_seconds() < cooldown_seconds:
                    return False, level, current_exp, calculate_max_exp(level)

            # Cooldown passed - create buffer entry with DB state + new EXP
            current_exp += exp_gain
            leveled_up = False
            max_exp = calculate_max_exp(level)
            while current_exp >= max_exp:
                current_exp -= max_exp
                level += 1
                leveled_up = True
                max_exp = calculate_max_exp(level)

            self._exp_buffer[buffer_key] = _ExpBufferEntry(
                guild_id=guild_id,
                user_id=user_id,
                username=username,
                display_name=display_name,
                level=level,
                current_exp=current_exp,
                total_messages=total_messages + 1,
                last_exp_at=now_iso,
                accumulated_exp=0,
                message_count=0,
            )
            self._flush_exp_buffer()
            return leveled_up, level, current_exp, max_exp

    def process_voice_activity(
        self,
        guild_id: str,
        user_id: str,
        username: str,
        display_name: str,
        activity_type: str = "voice_listen",  # voice_join | voice_speak | voice_listen | voice_stream | minigame
        is_bot: bool = False,
        cooldown_seconds: int = 45,
        exp_gain: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, int, int, int]:
        """
        Memberikan EXP dari aktivitas Voice Channel (Join Voice, Speak, Listening, Streaming)
        atau Minigames/Utilitas Mahasiswa di Discord.
        """
        if is_bot:
            return False, 1, 0, calculate_max_exp(1)

        default_gains = {
            "voice_join": 20,
            "voice_speak": 15,
            "voice_listen": 10,
            "voice_stream": 25,
            "minigame": 20,
            "pomodoro": 30,
        }
        gain = exp_gain if exp_gain is not None else default_gains.get(activity_type, 15)
        current_time = now or datetime.now(timezone.utc)
        now_iso = current_time.isoformat()
        buffer_key = (guild_id, user_id)

        # Check if user has existing buffer entry
        entry = self._exp_buffer.get(buffer_key)
        if entry is not None:
            # User has buffered state - check cooldown against buffered last_exp_at
            if cooldown_seconds > 0:
                last_dt = datetime.fromisoformat(entry.last_exp_at)
                if (current_time - last_dt).total_seconds() < cooldown_seconds:
                    # Cooldown not passed - return current buffered state
                    max_exp = calculate_max_exp(entry.level)
                    return False, entry.level, entry.current_exp + entry.accumulated_exp, max_exp

            # Cooldown passed - accumulate EXP in buffer
            entry.accumulated_exp += gain
            entry.message_count += 1
            entry.last_exp_at = now_iso
            entry.username = username
            entry.display_name = display_name

            # Check for level-up in buffer
            level = entry.level
            current_exp = entry.current_exp + entry.accumulated_exp
            leveled_up = False
            max_exp = calculate_max_exp(level)
            while current_exp >= max_exp:
                current_exp -= max_exp
                level += 1
                leveled_up = True
                max_exp = calculate_max_exp(level)

            # Try to flush
            self._flush_exp_buffer()
            return leveled_up, level, current_exp, max_exp

        # No buffer entry - read from DB
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT level, current_exp, total_messages, last_exp_at FROM level_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()

            if row is None:
                # New user - create buffer entry with initial state
                level = 1
                current_exp = gain
                leveled_up = False
                max_exp = calculate_max_exp(level)
                while current_exp >= max_exp:
                    current_exp -= max_exp
                    level += 1
                    leveled_up = True
                    max_exp = calculate_max_exp(level)

                self._exp_buffer[buffer_key] = _ExpBufferEntry(
                    guild_id=guild_id,
                    user_id=user_id,
                    username=username,
                    display_name=display_name,
                    level=level,
                    current_exp=current_exp,
                    total_messages=1,
                    last_exp_at=now_iso,
                    accumulated_exp=0,
                    message_count=0,
                )
                self._flush_exp_buffer()
                return leveled_up, level, current_exp, max_exp

            # Existing user - check cooldown
            level = int(row["level"])
            current_exp = int(row["current_exp"])
            total_messages = int(row["total_messages"])
            last_exp_at = row["last_exp_at"]

            if last_exp_at and cooldown_seconds > 0:
                last_dt = datetime.fromisoformat(last_exp_at)
                if (current_time - last_dt).total_seconds() < cooldown_seconds:
                    return False, level, current_exp, calculate_max_exp(level)

            # Cooldown passed - create buffer entry with DB state + new EXP
            current_exp += gain
            leveled_up = False
            max_exp = calculate_max_exp(level)
            while current_exp >= max_exp:
                current_exp -= max_exp
                level += 1
                leveled_up = True
                max_exp = calculate_max_exp(level)

            self._exp_buffer[buffer_key] = _ExpBufferEntry(
                guild_id=guild_id,
                user_id=user_id,
                username=username,
                display_name=display_name,
                level=level,
                current_exp=current_exp,
                total_messages=total_messages + 1,
                last_exp_at=now_iso,
                accumulated_exp=0,
                message_count=0,
            )
            self._flush_exp_buffer()
            return leveled_up, level, current_exp, max_exp

    def get_profile(self, guild_id: str, user_id: str, username: str = "User", display_name: str = "User") -> Dict:
        # Check buffer first for latest state
        buffer_key = (guild_id, user_id)
        entry = self._exp_buffer.get(buffer_key)
        if entry is not None:
            current_exp = entry.current_exp + entry.accumulated_exp
            level = entry.level
            max_exp = calculate_max_exp(level)
            while current_exp >= max_exp:
                current_exp -= max_exp
                level += 1
                max_exp = calculate_max_exp(level)
            return {
                "guild_id": guild_id,
                "user_id": user_id,
                "username": entry.username,
                "display_name": entry.display_name,
                "level": level,
                "current_exp": current_exp,
                "max_exp": max_exp,
                "total_messages": entry.total_messages + entry.message_count,
            }

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM level_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if row is None:
                return {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "username": username,
                    "display_name": display_name,
                    "level": 1,
                    "current_exp": 0,
                    "max_exp": calculate_max_exp(1),
                    "total_messages": 0,
                }
            lvl = int(row["level"])
            return {
                "guild_id": row["guild_id"],
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "level": lvl,
                "current_exp": int(row["current_exp"]),
                "max_exp": calculate_max_exp(lvl),
                "total_messages": int(row["total_messages"]),
            }

    def get_leaderboard(self, guild_id: str, limit: int = 15) -> List[Dict]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT guild_id, user_id, username, display_name, level, current_exp, total_messages
                FROM level_profiles
                WHERE guild_id = ?
                ORDER BY level DESC, current_exp DESC, total_messages DESC
                LIMIT ?
                """,
                (guild_id, max(1, min(limit, 15))),
            ).fetchall()
            result = []
            for idx, r in enumerate(rows, start=1):
                lvl = int(r["level"])
                result.append(
                    {
                        "rank": idx,
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "display_name": r["display_name"],
                        "level": lvl,
                        "current_exp": int(r["current_exp"]),
                        "max_exp": calculate_max_exp(lvl),
                        "total_messages": int(r["total_messages"]),
                    }
                )
            return result

    def set_afk(self, guild_id: str, user_id: str, username: str, reason: str = "Sedang AFK") -> Dict:
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_reason = reason.strip() or "Sedang AFK"
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO afk_statuses (guild_id, user_id, username, reason, started_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    username = excluded.username,
                    reason = excluded.reason,
                    started_at = excluded.started_at
                """,
                (guild_id, user_id, username, clean_reason, now_iso),
            )
        return {"guild_id": guild_id, "user_id": user_id, "username": username, "reason": clean_reason, "started_at": now_iso}
    
    def get_afk(self, guild_id: str, user_id: str) -> Optional[Dict[str, str]]:
        """Mengambil status AFK seorang anggota di server tertentu jika sedang AFK."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM afk_statuses WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            ).fetchone()
        if not row:
            return None
        return {
            "guild_id": str(row["guild_id"]),
            "user_id": str(row["user_id"]),
            "username": str(row["username"]),
            "reason": str(row["reason"] or "Sedang AFK"),
            "started_at": str(row["started_at"] or ""),
        }
    
    def clear_afk(self, guild_id: str, user_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM afk_statuses WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            return cur.rowcount > 0

    def list_afk(self, guild_id: str) -> List[Dict]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT guild_id, user_id, username, reason, started_at FROM afk_statuses WHERE guild_id = ? ORDER BY started_at DESC",
                (guild_id,),
            ).fetchall()
            return [dict(r) for r in rows]

