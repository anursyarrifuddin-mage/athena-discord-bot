"""
Config Loader for YAML-based Configuration with Hot Reload Support.
Loads radio_stations.yaml, constants.yaml and provides typed access.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CONFIG_DIR = Path(__file__).parent / "config_data"


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
    ytdlp_format: str = "bestaudio[acodec=opus][abr<=160]/bestaudio[ext=webm][abr<=160]/bestaudio[ext=m4a][abr<=160]/bestaudio/best"
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
        self._callbacks: List[callable] = []
    
    def load(self) -> AppConfig:
        """Load all config files."""
        with self._lock:
            self._config = AppConfig()
            self._load_radio_stations()
            self._load_constants()
            self._update_mtimes()
            return self._config
    
    def _load_radio_stations(self) -> None:
        path = self.config_dir / "radio_stations.yaml"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        stations = []
        for s in data.get("stations", []):
            if s.get("enabled", True):
                stations.append(RadioStation(
                    id=s["id"],
                    name=s["name"],
                    artist=s["artist"],
                    genre=s["genre"],
                    stream_url=s["stream_url"],
                    enabled=s.get("enabled", True),
                ))
        if self._config:
            self._config.radio_stations = stations
    
    def _load_constants(self) -> None:
        path = self.config_dir / "constants.yaml"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if not self._config:
            return
            
        # Music
        m = data.get("music", {})
        self._config.music = MusicConfig(
            min_single_duration_sec=m.get("min_single_duration_sec", 35),
            max_single_duration_sec=m.get("max_single_duration_sec", 540),
            min_viral_views_threshold=m.get("min_viral_views_threshold", 25000),
            autoplay_limit=m.get("autoplay_limit", 5),
            autoplay_candidate_pool=m.get("autoplay_candidate_pool", 18),
            search_result_limit=m.get("search_result_limit", 25),
            search_cache_ttl_sec=m.get("search_cache_ttl_sec", 900),
            search_cache_max_size=m.get("search_cache_max_size", 500),
            yt_search_timeout_sec=m.get("yt_search_timeout_sec", 5.5),
            yt_mix_timeout_sec=m.get("yt_mix_timeout_sec", 5.5),
            ytdlp_timeout_sec=m.get("ytdlp_timeout_sec", 14),
            ytdlp_format=m.get("ytdlp_format", "bestaudio[acodec=opus][abr<=160]/bestaudio[ext=webm][abr<=160]/bestaudio[ext=m4a][abr<=160]/bestaudio/best"),
            stream_cache_ttl_sec=m.get("stream_cache_ttl_sec", 1800),
            stream_cache_max_size=m.get("stream_cache_max_size", 300),
        )
        
        # Discord
        d = data.get("discord", {})
        self._config.discord = DiscordConfig(
            exp_per_message=d.get("exp_per_message", 15),
            exp_cooldown_sec=d.get("exp_cooldown_sec", 60),
            voice_exp_cooldown_sec=d.get("voice_exp_cooldown_sec", 45),
            exp_gains=d.get("exp_gains", {
                "voice_join": 20,
                "voice_speak": 15,
                "voice_listen": 10,
                "voice_stream": 25,
                "minigame": 20,
                "pomodoro": 30,
            }),
            exp_formula_base=d.get("exp_formula_base", 100),
            exp_formula_increment=d.get("exp_formula_increment", 25),
            leaderboard_limit=d.get("leaderboard_limit", 15),
            max_sessions_per_user=d.get("max_sessions_per_user", 5),
            host_lock_cooldown_sec=d.get("host_lock_cooldown_sec", 60),
        )
        
        # Academic
        a = data.get("academic", {})
        self._config.academic = AcademicConfig(
            reminder_stages=a.get("reminder_stages", [
                {"name": "H-3d", "hours_before": 72},
                {"name": "H-6h", "hours_before": 6},
                {"name": "H-1h", "hours_before": 1},
            ]),
            default_reminder_days=a.get("default_reminder_days", 3),
            max_attachment_mb=a.get("max_attachment_mb", 15),
            allowed_extensions=a.get("allowed_extensions", [".pdf", ".doc", ".docx"]),
            auto_sync_interval_sec=a.get("auto_sync_interval_sec", 3600),
            purge_expired_interval_sec=a.get("purge_expired_interval_sec", 300),
            ics_request_timeout_sec=a.get("ics_request_timeout_sec", 12),
            moodle_ws_timeout_sec=a.get("moodle_ws_timeout_sec", 12),
        )
        
        # Backup
        b = data.get("backup", {})
        self._config.backup = BackupConfig(
            encryption_algorithm=b.get("encryption_algorithm", "fernet"),
            pbkdf2_iterations=b.get("pbkdf2_iterations", 100000),
            gzip_compress_level=b.get("gzip_compress_level", 6),
            max_local_backups=b.get("max_local_backups", 50),
            discord_dm_size_limit_mb=b.get("discord_dm_size_limit_mb", 8),
        )
        
        # Database
        db = data.get("database", {})
        self._config.database = DatabaseConfig(
            journal_mode=db.get("journal_mode", "WAL"),
            foreign_keys=db.get("foreign_keys", True),
            busy_timeout_ms=db.get("busy_timeout_ms", 15000),
            pool_size=db.get("pool_size", 5),
            max_overflow=db.get("max_overflow", 10),
        )
        
        # Queue
        q = data.get("queue", {})
        self._config.queue = QueueConfig(
            cleanup_interval_sec=q.get("cleanup_interval_sec", 3600),
            inactivity_threshold_sec=q.get("inactivity_threshold_sec", 7200),
            max_history_keys=q.get("max_history_keys", 2000),
            history_ttl_sec=q.get("history_ttl_sec", 3600),
            max_recent_tracks=q.get("max_recent_tracks", 30),
        )
        
        # Rate Limits
        r = data.get("rate_limits", {})
        self._config.rate_limits = RateLimitConfig(
            auth_requests_per_minute=r.get("auth_requests_per_minute", 10),
            auth_window_sec=r.get("auth_window_sec", 60),
            api_requests_per_minute=r.get("api_requests_per_minute", 90),
            api_window_sec=r.get("api_window_sec", 60),
            search_requests_per_minute=r.get("search_requests_per_minute", 30),
            search_window_sec=r.get("search_window_sec", 60),
        )
        
        # Logging
        l = data.get("logging", {})
        self._config.logging = LoggingConfig(
            level=l.get("level", "INFO"),
            format=l.get("format", "json"),
            include_correlation_id=l.get("include_correlation_id", True),
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
    
    def register_reload_callback(self, callback: callable) -> None:
        """Register a callback to be called on config reload."""
        with self._lock:
            self._callbacks.append(callback)
    
    def _check_and_reload(self) -> bool:
        """Check if any config file changed and reload if needed."""
        reloaded = False
        with self._lock:
            for name in ["radio_stations.yaml", "constants.yaml"]:
                path = self.config_dir / name
                if not path.exists():
                    continue
                mtime = path.stat().st_mtime
                if self._mtimes.get(name) != mtime:
                    print(f"[ConfigLoader] Detected change in {name}, reloading...")
                    self._load_radio_stations() if name == "radio_stations.yaml" else self._load_constants()
                    self._mtimes[name] = mtime
                    reloaded = True
            if reloaded:
                for callback in self._callbacks:
                    try:
                        callback(self._config)
                    except Exception as e:
                        print(f"[ConfigLoader] Callback error: {e}")
        return reloaded
    
    def start_watching(self, interval_sec: float = 5.0) -> None:
        """Start background thread to watch for config changes."""
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._stop_watch.clear()
        self._watch_thread = threading.Thread(target=self._watch_loop, args=(interval_sec,), daemon=True)
        self._watch_thread.start()
        print(f"[ConfigLoader] Started watching config dir: {self.config_dir}")
    
    def stop_watching(self) -> None:
        """Stop the config watch thread."""
        self._stop_watch.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=2.0)
    
    def _watch_loop(self, interval_sec: float) -> None:
        while not self._stop_watch.is_set():
            time.sleep(interval_sec)
            if not self._stop_watch.is_set():
                self._check_and_reload()


# Global instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
        _config_loader.load()
    return _config_loader


def init_config(config_dir: Optional[Path] = None, watch: bool = True) -> ConfigLoader:
    """Initialize global config loader."""
    global _config_loader
    _config_loader = ConfigLoader(config_dir)
    _config_loader.load()
    if watch:
        _config_loader.start_watching()
    return _config_loader


# Convenience functions
def get_radio_stations() -> List[RadioStation]:
    return get_config_loader().get_radio_stations()


def get_enabled_radio_stations() -> List[RadioStation]:
    return get_config_loader().get_enabled_radio_stations()


def get_music_config() -> MusicConfig:
    return get_config_loader().get_music_config()


def get_discord_config() -> DiscordConfig:
    return get_config_loader().get_discord_config()


def get_academic_config() -> AcademicConfig:
    return get_config_loader().get_academic_config()


def get_backup_config() -> BackupConfig:
    return get_config_loader().get_backup_config()


def get_database_config() -> DatabaseConfig:
    return get_config_loader().get_database_config()


def get_queue_config() -> QueueConfig:
    return get_config_loader().get_queue_config()


def get_rate_limits() -> RateLimitConfig:
    return get_config_loader().get_rate_limits()


def get_logging_config() -> LoggingConfig:
    return get_config_loader().get_logging_config()