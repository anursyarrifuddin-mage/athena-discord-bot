"""
Config Loader for YAML-based Configuration with Hot Reload Support.
Loads radio_stations.yaml, constants.yaml and provides typed access with safe fallbacks.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

CONFIG_DIR = Path(__file__).parent / "config_data"


class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""
    pass


def _safe_load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        alt = Path(__file__).parent.parent / "config_data" / path.name
        if alt.exists():
            path = alt
        else:
            return {}
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass
class RadioStation:
    id: str
    name: str
    artist: str
    genre: str
    stream_url: str
    enabled: bool = True


@dataclass
class MusicConfig:
    min_single_duration_sec: int = 35
    max_single_duration_sec: int = 540
    min_viral_views_threshold: int = 25000
    autoplay_limit: int = 5
    autoplay_candidate_pool: int = 18
    search_result_limit: int = 25
    search_cache_ttl_sec: int = 900
    search_cache_max_size: int = 500
    yt_search_timeout_sec: float = 5.5
    yt_mix_timeout_sec: float = 5.5
    ytdlp_timeout_sec: int = 14
    ytdlp_format: str = (
        "bestaudio[acodec=opus][abr<=160]/"
        "bestaudio[ext=webm][abr<=160]/"
        "bestaudio[ext=m4a][abr<=160]/"
        "bestaudio/best"
    )
    stream_cache_ttl_sec: int = 1800
    stream_cache_max_size: int = 300


@dataclass
class DiscordConfig:
    exp_per_message: int = 15
    exp_cooldown_sec: int = 60
    voice_exp_cooldown_sec: int = 45
    exp_gains: Dict[str, int] = field(default_factory=dict)
    exp_formula_base: int = 100
    exp_formula_increment: int = 25
    leaderboard_limit: int = 15
    max_sessions_per_user: int = 5
    host_lock_cooldown_sec: int = 60


@dataclass
class AcademicConfig:
    reminder_stages: List[Dict[str, Any]] = field(default_factory=list)
    default_reminder_days: int = 3
    max_attachment_mb: int = 15
    allowed_extensions: List[str] = field(default_factory=list)
    auto_sync_interval_sec: int = 3600
    purge_expired_interval_sec: int = 300
    ics_request_timeout_sec: int = 12
    moodle_ws_timeout_sec: int = 12


@dataclass
class BackupConfig:
    encryption_algorithm: str = "fernet"
    pbkdf2_iterations: int = 100000
    gzip_compress_level: int = 6
    max_local_backups: int = 50
    discord_dm_size_limit_mb: int = 8


@dataclass
class DatabaseConfig:
    journal_mode: str = "WAL"
    foreign_keys: bool = True
    busy_timeout_ms: int = 15000
    pool_size: int = 5
    max_overflow: int = 10


@dataclass
class QueueConfig:
    cleanup_interval_sec: int = 3600
    inactivity_threshold_sec: int = 7200
    max_history_keys: int = 2000
    history_ttl_sec: int = 3600
    max_recent_tracks: int = 30


@dataclass
class RateLimitConfig:
    auth_requests_per_minute: int = 10
    auth_window_sec: int = 60
    api_requests_per_minute: int = 90
    api_window_sec: int = 60
    search_requests_per_minute: int = 30
    search_window_sec: int = 60


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"
    include_correlation_id: bool = True


@dataclass
class AppConfig:
    music: MusicConfig = field(default_factory=MusicConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    academic: AcademicConfig = field(default_factory=AcademicConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    radio_stations: List[RadioStation] = field(default_factory=list)


class ConfigLoader:
    """Loads and watches YAML config files with hot reload capability."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or CONFIG_DIR
        self._config: Optional[AppConfig] = None
        self._lock = threading.RLock()
        self._mtimes: Dict[str, float] = {}
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_watch = threading.Event()
        self._callbacks: List[Callable] = []

    def load(self) -> AppConfig:
        with self._lock:
            self._config = AppConfig()
            self._load_radio_stations()
            self._load_constants()
            self._update_mtimes()
            return self._config

    def _load_radio_stations(self) -> None:
        data = _safe_load_yaml(self.config_dir / "radio_stations.yaml")
        stations = []
        raw_stations = data.get("stations") or data.get("radio_stations") or []
        if isinstance(raw_stations, list):
            for s in raw_stations:
                if isinstance(s, dict) and s.get("enabled", True):
                    stations.append(
                        RadioStation(
                            id=str(s.get("id") or s.get("key") or ""),
                            name=str(s.get("name") or s.get("title") or ""),
                            artist=str(s.get("artist") or "Live Radio"),
                            genre=str(s.get("genre") or "Pop"),
                            stream_url=str(s.get("stream_url") or ""),
                            enabled=bool(s.get("enabled", True)),
                        )
                    )
        if self._config:
            self._config.radio_stations = stations

    def _load_constants(self) -> None:
        data = _safe_load_yaml(self.config_dir / "constants.yaml")
        if not self._config or not data:
            return
        m = data.get("music", {})
        if isinstance(m, dict):
            self._config.music = MusicConfig(
                min_single_duration_sec=int(m.get("min_single_duration_sec", 35)),
                max_single_duration_sec=int(m.get("max_single_duration_sec", 540)),
                min_viral_views_threshold=int(m.get("min_viral_views_threshold", 25000)),
                autoplay_limit=int(m.get("autoplay_limit", 5)),
                autoplay_candidate_pool=int(m.get("autoplay_candidate_pool", 18)),
                search_result_limit=int(m.get("search_result_limit", 25)),
                search_cache_ttl_sec=int(m.get("search_cache_ttl_sec", 900)),
                search_cache_max_size=int(m.get("search_cache_max_size", 500)),
                yt_search_timeout_sec=float(m.get("yt_search_timeout_sec", 5.5)),
                yt_mix_timeout_sec=float(m.get("yt_mix_timeout_sec", 5.5)),
                ytdlp_timeout_sec=int(m.get("ytdlp_timeout_sec", 14)),
                ytdlp_format=str(
                    m.get(
                        "ytdlp_format",
                        "bestaudio[acodec=opus][abr<=160]/bestaudio[ext=webm][abr<=160]/bestaudio[ext=m4a][abr<=160]/bestaudio/best",
                    )
                ),
                stream_cache_ttl_sec=int(m.get("stream_cache_ttl_sec", 1800)),
                stream_cache_max_size=int(m.get("stream_cache_max_size", 300)),
            )

    def _update_mtimes(self) -> None:
        for name in ["radio_stations.yaml", "constants.yaml"]:
            path = self.config_dir / name
            if path.exists():
                self._mtimes[name] = path.stat().st_mtime

    def get_config(self) -> AppConfig:
        if self._config is None:
            return self.load()
        return self._config

    def get_radio_stations(self) -> List[RadioStation]:
        return self.get_config().radio_stations

    def get_enabled_radio_stations(self) -> List[RadioStation]:
        return [s for s in self.get_radio_stations() if s.enabled]

    def get_music_config(self) -> MusicConfig:
        return self.get_config().music

    def get_discord_config(self) -> DiscordConfig:
        return self.get_config().discord

    def get_academic_config(self) -> AcademicConfig:
        return self.get_config().academic

    def get_backup_config(self) -> BackupConfig:
        return self.get_config().backup

    def get_database_config(self) -> DatabaseConfig:
        return self.get_config().database

    def get_queue_config(self) -> QueueConfig:
        return self.get_config().queue

    def get_rate_limits(self) -> RateLimitConfig:
        return self.get_config().rate_limits

    def get_logging_config(self) -> LoggingConfig:
        return self.get_config().logging


_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
        _config_loader.load()
    return _config_loader


def load_constants() -> Dict[str, Any]:
    return _safe_load_yaml(CONFIG_DIR / "constants.yaml")


def load_radio_stations() -> Dict[str, Any]:
    return _safe_load_yaml(CONFIG_DIR / "radio_stations.yaml")


def reload_all_configs() -> None:
    get_config_loader().load()


def get_curated_catalog() -> List[Dict[str, Any]]:
    data = load_constants()
    cat = data.get("curated_catalog")
    return cat if isinstance(cat, list) else []


def get_curated_radio_pools() -> Dict[str, List[Tuple[str, str, int]]]:
    data = load_constants()
    pools = data.get("curated_radio_pools")
    if isinstance(pools, dict):
        result: Dict[str, List[Tuple[str, str, int]]] = {}
        for k, items in pools.items():
            if isinstance(items, list):
                parsed = []
                for it in items:
                    if isinstance(it, dict):
                        parsed.append((str(it.get("title", "")), str(it.get("artist", "")), int(it.get("duration_sec", 210))))
                    elif isinstance(it, (list, tuple)) and len(it) >= 3:
                        parsed.append((str(it[0]), str(it[1]), int(it[2])))
                if parsed:
                    result[k] = parsed
        return result
    return {}


def get_indonesian_artists() -> Set[str]:
    data = load_constants()
    artists = data.get("indonesian_artists")
    if isinstance(artists, list):
        return {str(a).lower().strip() for a in artists if a}
    return set()


def get_western_artists() -> Set[str]:
    data = load_constants()
    artists = data.get("western_artists")
    if isinstance(artists, list):
        return {str(a).lower().strip() for a in artists if a}
    return set()


def get_all_known_artists() -> Set[str]:
    return get_indonesian_artists() | get_western_artists()


def get_genre_keywords() -> Dict[str, List[str]]:
    data = load_constants()
    gk = data.get("genre_keywords")
    return gk if isinstance(gk, dict) else {}


def get_Artist_similarity_map() -> Dict[str, List[str]]:
    data = load_constants()
    sm = data.get("artist_similarity_map")
    return sm if isinstance(sm, dict) else {}


def get_block_patterns() -> List[str]:
    data = load_constants()
    bp = data.get("block_patterns")
    return bp if isinstance(bp, list) else []


def get_strip_patterns() -> List[str]:
    data = load_constants()
    sp = data.get("strip_patterns")
    return sp if isinstance(sp, list) else []


def get_duration_limits() -> Tuple[int, int]:
    mc = get_config_loader().get_music_config()
    return mc.min_single_duration_sec, mc.max_single_duration_sec


def get_viral_views_threshold() -> int:
    return get_config_loader().get_music_config().min_viral_views_threshold


def get_radio_stations() -> List[Dict[str, Any]]:
    data = load_radio_stations()
    raw = data.get("radio_stations") or data.get("stations")
    if isinstance(raw, list) and raw:
        out = []
        for s in raw:
            if isinstance(s, dict):
                out.append({
                    "key": str(s.get("key") or s.get("id") or ""),
                    "title": str(s.get("title") or s.get("name") or ""),
                    "artist": str(s.get("artist") or "Live Radio"),
                    "genre": str(s.get("genre") or "Pop"),
                    "stream_url": str(s.get("stream_url") or ""),
                    "thumbnail_url": str(s.get("thumbnail_url") or "/logo.png"),
                })
        return out
    return []


def get_radio_station_by_key(key: str) -> Optional[Dict[str, Any]]:
    k = (key or "").lower().strip()
    for st in get_radio_stations():
        if str(st.get("key", "")).lower() == k:
            return st
    return None


def get_radio_stations_by_genre(genre: str) -> List[Dict[str, Any]]:
    g = (genre or "").lower().strip()
    return [st for st in get_radio_stations() if g in str(st.get("genre", "")).lower()]


def get_default_fallback_radio() -> Dict[str, Any]:
    stations = get_radio_stations()
    if stations:
        return stations[0]
    return {
        "key": "prambors",
        "title": "Prambors FM 102.2 Jakarta",
        "artist": "Indonesian & Global Top 40 Hits",
        "genre": "Top 40 / Pop",
        "stream_url": "https://s2.cloudmu.id/listen/prambors/radio.mp3",
        "thumbnail_url": "/logo.png",
    }


def get_enabled_radio_stations() -> List[RadioStation]:
    return get_config_loader().get_enabled_radio_stations()


def get_music_config() -> MusicConfig:
    return get_config_loader().get_music_config()