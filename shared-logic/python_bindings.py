"""
Python bindings for Athenaa Shared Logic.
This module provides access to the shared Rust/WASM logic from Python.
Can be used via:
1. wasmer (WebAssembly runtime) - for WASM
2. Direct Rust extension (maturin) - for native performance
3. JSON-RPC over stdin/stdout - for subprocess communication
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict

# Try to import wasmer for WASM execution
try:
    from wasmer import Store, Module, Instance
    from wasmer.compiler_cranelift import Compiler
    WASMER_AVAILABLE = True
except ImportError:
    WASMER_AVAILABLE = False

# Try to import native extension (built with maturin)
try:
    import athenaa_shared_native as native
    NATIVE_AVAILABLE = True
except ImportError:
    NATIVE_AVAILABLE = False


@dataclass
class SyncedLyricLine:
    time_sec: float
    text: str


@dataclass
class HostLockContext:
    user_id: str
    user_roles: List[str]
    is_admin: bool
    is_owner: bool
    session_host_id: str
    dj_role_id: str
    action: str
    target_item_requester_id: Optional[str] = None


@dataclass
class ParsedIcsEvent:
    uid: str
    course_name: str
    title: str
    description: str
    deadline_iso: str
    source_url: str


@dataclass
class ExpResult:
    leveled_up: bool
    level: int
    current_exp: int
    max_exp: int


@dataclass
class HostLockResult:
    allowed: bool
    reason: str


@dataclass
class ReminderStageResult:
    stage: Optional[str]


@dataclass
class ValidationResult:
    valid: bool
    reason: str


@dataclass
class SingleSessionResult:
    previous_token_revoked: Optional[str]
    active_token: str


@dataclass
class OwnerAccessResult:
    allowed: bool
    reason: str


class SharedLogicError(Exception):
    """Exception raised when shared logic execution fails."""
    pass


class SharedLogic:
    """
    Main interface for accessing shared logic.
    Supports multiple backends: native (maturin), wasmer (WASM), or subprocess.
    """
    
    def __init__(self, backend: str = "auto"):
        """
        Initialize shared logic with specified backend.
        
        Args:
            backend: "native" (maturin), "wasmer" (WASM), "auto" (try native first, then wasmer)
        """
        self.backend = backend
        self._instance = None
        self._store = None
        self._wasm_module = None
        
        if backend == "auto":
            if NATIVE_AVAILABLE:
                self.backend = "native"
            elif WASMER_AVAILABLE:
                self.backend = "wasmer"
            else:
                raise SharedLogicError("No backend available. Install wasmer or build native extension.")
        else:
            self.backend = backend
        
        self._init_backend()
    
    def _init_backend(self):
        """Initialize the selected backend."""
        if self.backend == "native":
            self._init_native()
        elif self.backend == "wasmer":
            self._init_wasmer()
        else:
            raise SharedLogicError(f"Unknown backend: {self.backend}")
    
    def _init_native(self):
        """Initialize native Rust extension."""
        # Native functions are available directly via the imported module
        pass
    
    def _init_wasmer(self):
        """Initialize WASM module via wasmer."""
        # Look for WASM file in standard locations
        wasm_paths = [
            Path(__file__).parent / "pkg" / "athenaa_shared_bg.wasm",
            Path(__file__).parent.parent / "shared-logic" / "pkg" / "athenaa_shared_bg.wasm",
            Path.cwd() / "shared-logic" / "pkg" / "athenaa_shared_bg.wasm",
        ]
        
        wasm_path = None
        for path in wasm_paths:
            if path.exists():
                wasm_path = path
                break
        
        if wasm_path is None:
            raise SharedLogicError("WASM file not found. Run 'wasm-pack build' in shared-logic directory.")
        
        self._store = Store(Compiler)
        self._wasm_module = Module(self._store, wasm_path.read_bytes())
        self._instance = Instance(self._store, self._wasm_module, {})
    
    # ========================================================================
    # EXP Formula
    # ========================================================================
    
    def calculate_max_exp(self, level: int) -> int:
        """Calculate max EXP for a given level."""
        if self.backend == "native":
            return native.calculate_max_exp(level)
        elif self.backend == "wasmer":
            return self._instance.exports.calculate_max_exp(level)
        raise SharedLogicError("No backend initialized")
    
    def apply_exp_gain(self, current_level: int, current_exp: int, exp_gain: int) -> ExpResult:
        """Apply EXP gain and calculate level-ups."""
        if self.backend == "native":
            result = native.apply_exp_gain(current_level, current_exp, exp_gain)
            return ExpResult(**result)
        elif self.backend == "wasmer":
            result = self._instance.exports.apply_exp_gain(current_level, current_exp, exp_gain)
            return ExpResult(**json.loads(result))
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Host Lock System
    # ========================================================================
    
    def can_control_queue(self, ctx: HostLockContext) -> HostLockResult:
        """Check if user can control queue (Host Lock)."""
        if self.backend == "native":
            result = native.can_control_queue(asdict(ctx))
            return HostLockResult(**result)
        elif self.backend == "wasmer":
            # WASM needs JSON serialization for complex types
            input_json = json.dumps(asdict(ctx))
            result = self._instance.exports.can_control_queue(input_json)
            return HostLockResult(**json.loads(result))
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Lyrics Parser
    # ========================================================================
    
    def parse_lrc_lyrics(self, raw_lrc: str) -> List[SyncedLyricLine]:
        """Parse LRC format lyrics into timestamped lines."""
        if self.backend == "native":
            result = native.parse_lrc_lyrics(raw_lrc)
            return [SyncedLyricLine(**line) for line in result]
        elif self.backend == "wasmer":
            result = self._instance.exports.parse_lrc_lyrics(raw_lrc)
            return [SyncedLyricLine(**line) for line in json.loads(result)]
        raise SharedLogicError("No backend initialized")
    
    def get_active_lyric_index(self, lines: List[SyncedLyricLine], position_sec: float) -> int:
        """Get active lyric line index for playback position."""
        if self.backend == "native":
            return native.get_active_lyric_index([asdict(l) for l in lines], position_sec)
        elif self.backend == "wasmer":
            input_json = json.dumps([asdict(l) for l in lines])
            return self._instance.exports.get_active_lyric_index(input_json, position_sec)
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Reminder Evaluation
    # ========================================================================
    
    def evaluate_reminder_stage(self, deadline_iso: str, now_ms: int, is_completed: bool, days_before: int = 3) -> Optional[str]:
        """Evaluate which reminder stage applies."""
        if self.backend == "native":
            result = native.evaluate_reminder_stage(deadline_iso, now_ms, is_completed, days_before)
            return result.get("stage")
        elif self.backend == "wasmer":
            result = self._instance.exports.evaluate_reminder_stage(deadline_iso, now_ms, is_completed, days_before)
            return json.loads(result).get("stage")
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Moodle .ics Parser
    # ========================================================================
    
    def is_submittable_or_due_task(self, summary: str, description: str, url: str, has_due_prop: bool, event_type: str) -> bool:
        """Check if a calendar event is a submittable task."""
        if self.backend == "native":
            return native.is_submittable_or_due_task(summary, description, url, has_due_prop, event_type)
        elif self.backend == "wasmer":
            return self._instance.exports.is_submittable_or_due_task(summary, description, url, has_due_prop, event_type)
        raise SharedLogicError("No backend initialized")
    
    def parse_ics_events(self, ics_text: str) -> List[ParsedIcsEvent]:
        """Parse Moodle/Waskita .ics content into tasks."""
        if self.backend == "native":
            result = native.parse_ics_events(ics_text)
            return [ParsedIcsEvent(**event) for event in result]
        elif self.backend == "wasmer":
            result = self._instance.exports.parse_ics_events(ics_text)
            return [ParsedIcsEvent(**event) for event in json.loads(result)]
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Attachment Validation
    # ========================================================================
    
    def validate_attachment_meta(self, filename: str, size_bytes: int, max_mb: int = 15) -> ValidationResult:
        """Validate module attachment metadata."""
        if self.backend == "native":
            result = native.validate_attachment_meta(filename, size_bytes, max_mb)
            return ValidationResult(**result)
        elif self.backend == "wasmer":
            result = self._instance.exports.validate_attachment_meta(filename, size_bytes, max_mb)
            return ValidationResult(**json.loads(result))
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    def enforce_single_discord_session(self, active_by_user_id: Dict[str, str], discord_user_id: str, new_session_token: str) -> SingleSessionResult:
        """Enforce single session per Discord user."""
        if self.backend == "native":
            result = native.enforce_single_discord_session(active_by_user_id, discord_user_id, new_session_token)
            return SingleSessionResult(**result)
        elif self.backend == "wasmer":
            input_json = json.dumps(active_by_user_id)
            result = self._instance.exports.enforce_single_discord_session(input_json, discord_user_id, new_session_token)
            return SingleSessionResult(**json.loads(result))
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Owner Access Control
    # ========================================================================
    
    def can_access_owner_resources(self, is_owner: bool, session_token: Optional[str]) -> OwnerAccessResult:
        """Check if user can access owner-only resources."""
        if self.backend == "native":
            result = native.can_access_owner_resources(is_owner, session_token)
            return OwnerAccessResult(**result)
        elif self.backend == "wasmer":
            result = self._instance.exports.can_access_owner_resources(is_owner, session_token or "")
            return OwnerAccessResult(**json.loads(result))
        raise SharedLogicError("No backend initialized")
    
    # ========================================================================
    # Song Identity Normalization
    # ========================================================================
    
    def normalize_title_only(self, title: str) -> str:
        if self.backend == "native":
            return native.normalize_title_only(title)
        elif self.backend == "wasmer":
            return self._instance.exports.normalize_title_only(title)
        raise SharedLogicError("No backend initialized")
    
    def normalize_artist_only(self, artist: str) -> str:
        if self.backend == "native":
            return native.normalize_artist_only(artist)
        elif self.backend == "wasmer":
            return self._instance.exports.normalize_artist_only(artist)
        raise SharedLogicError("No backend initialized")
    
    def normalize_song_identity(self, title: str, artist: str) -> str:
        if self.backend == "native":
            return native.normalize_song_identity(title, artist)
        elif self.backend == "wasmer":
            return self._instance.exports.normalize_song_identity(title, artist)
        raise SharedLogicError("No backend initialized")
    
    def is_same_base_song(self, title_1: str, title_2: str) -> bool:
        if self.backend == "native":
            return native.is_same_base_song(title_1, title_2)
        elif self.backend == "wasmer":
            return self._instance.exports.is_same_base_song(title_1, title_2)
        raise SharedLogicError("No backend initialized")


# Global instance
_shared_logic: Optional[SharedLogic] = None


def get_shared_logic(backend: str = "auto") -> SharedLogic:
    """Get global shared logic instance."""
    global _shared_logic
    if _shared_logic is None or _shared_logic.backend != backend:
        _shared_logic = SharedLogic(backend)
    return _shared_logic


# Convenience functions (matching existing Python API)
def calculate_max_exp(level: int) -> int:
    return get_shared_logic().calculate_max_exp(level)


def apply_exp_gain(current_level: int, current_exp: int, exp_gain: int) -> ExpResult:
    return get_shared_logic().apply_exp_gain(current_level, current_exp, exp_gain)


def can_control_queue(ctx: HostLockContext) -> HostLockResult:
    return get_shared_logic().can_control_queue(ctx)


def parse_lrc_lyrics(raw_lrc: str) -> List[SyncedLyricLine]:
    return get_shared_logic().parse_lrc_lyrics(raw_lrc)


def get_active_lyric_index(lines: List[SyncedLyricLine], position_sec: float) -> int:
    return get_shared_logic().get_active_lyric_index(lines, position_sec)


def evaluate_reminder_stage(deadline_iso: str, now_ms: int, is_completed: bool, days_before: int = 3) -> Optional[str]:
    return get_shared_logic().evaluate_reminder_stage(deadline_iso, now_ms, is_completed, days_before)


def is_submittable_or_due_task(summary: str, description: str, url: str, has_due_prop: bool, event_type: str) -> bool:
    return get_shared_logic().is_submittable_or_due_task(summary, description, url, has_due_prop, event_type)


def parse_ics_events(ics_text: str) -> List[ParsedIcsEvent]:
    return get_shared_logic().parse_ics_events(ics_text)


def validate_attachment_meta(filename: str, size_bytes: int, max_mb: int = 15) -> ValidationResult:
    return get_shared_logic().validate_attachment_meta(filename, size_bytes, max_mb)


def enforce_single_discord_session(active_by_user_id: Dict[str, str], discord_user_id: str, new_session_token: str) -> SingleSessionResult:
    return get_shared_logic().enforce_single_discord_session(active_by_user_id, discord_user_id, new_session_token)


def can_access_owner_resources(is_owner: bool, session_token: Optional[str]) -> OwnerAccessResult:
    return get_shared_logic().can_access_owner_resources(is_owner, session_token)


def normalize_title_only(title: str) -> str:
    return get_shared_logic().normalize_title_only(title)


def normalize_artist_only(artist: str) -> str:
    return get_shared_logic().normalize_artist_only(artist)


def normalize_song_identity(title: str, artist: str) -> str:
    return get_shared_logic().normalize_song_identity(title, artist)


def is_same_base_song(title_1: str, title_2: str) -> bool:
    return get_shared_logic().is_same_base_song(title_1, title_2)