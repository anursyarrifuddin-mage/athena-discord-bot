"""
Modul Lirik Otomatis dengan API Publik LRCLIB (Tanpa API Key).
- Mendukung syncedLyrics (LRC dengan timestamp [mm:ss.xx]) dan plainLyrics.
- Mematuhi rate limit HTTP 429 & header Retry-After.
- Menggunakan User-Agent resmi aplikasi dan cache di memori untuk menghemat request.
- Kegagalan mengambil lirik tidak pernah menghentikan pemutaran musik.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

LRC_LINE_RE = re.compile(r"^\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\](.*)$")
USER_AGENT = "AthenaaDiscordBot/1.0 (https://github.com/athenaa-bot)"


@dataclass
class SyncedLyricLine:
    time_sec: float
    text: str


@dataclass
class LyricsResult:
    status: str  # synced | plain | not_found | rate_limited | error
    track_name: str
    artist_name: str
    synced_lines: List[SyncedLyricLine] = field(default_factory=list)
    plain_lyrics: str = ""
    message: str = ""

    @property
    def found(self) -> bool:
        return self.status in ("synced", "plain")


def parse_lrc_timestamps(synced_lrc: str) -> List[SyncedLyricLine]:
    """Mem-parsing format LRC menjadi daftar baris ber-timestamp akurat."""
    lines: List[SyncedLyricLine] = []
    for raw in synced_lrc.splitlines():
        match = LRC_LINE_RE.match(raw.strip())
        if not match:
            continue
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        frac_str = match.group(3) or "0"
        frac = int(frac_str) / (10 ** len(frac_str))
        text = match.group(4).strip()
        lines.append(SyncedLyricLine(time_sec=round(minutes * 60 + seconds + frac, 2), text=text or "♪"))
    lines.sort(key=lambda x: x.time_sec)
    return lines


class LyricsService:
    """Layanan pencarian lirik otomatis ke https://lrclib.net/api dengan cache & penanganan 429."""

    def __init__(self) -> None:
        self._cache: Dict[str, LyricsResult] = {}
        self._rate_limited_until: float = 0.0

    def get_lyrics(self, title: str, artist: str, album: str = "", duration_sec: int = 0) -> LyricsResult:
        cache_key = f"{title.strip().lower()}::{artist.strip().lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        now = time.time()
        if now < self._rate_limited_until:
            wait_sec = int(self._rate_limited_until - now)
            return LyricsResult(
                status="rate_limited",
                track_name=title,
                artist_name=artist,
                message=f"Rate limit LRCLIB aktif. Coba lagi dalam {wait_sec} detik.",
            )

        query = urllib.parse.urlencode({"track_name": title.strip(), "artist_name": artist.strip()})
        url = f"https://lrclib.net/api/search?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                items = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429:
                retry_after = int(http_err.headers.get("Retry-After", "30"))
                self._rate_limited_until = time.time() + max(5, retry_after)
                return LyricsResult(
                    status="rate_limited",
                    track_name=title,
                    artist_name=artist,
                    message=f"LRCLIB mengembalikan HTTP 429. Menunggu {retry_after} detik.",
                )
            return LyricsResult(
                status="error",
                track_name=title,
                artist_name=artist,
                message=f"Layanan lirik mengembalikan kode HTTP {http_err.code}.",
            )
        except Exception:
            return LyricsResult(
                status="error",
                track_name=title,
                artist_name=artist,
                message="Layanan LRCLIB sedang tidak dapat dijangkau.",
            )

        if not items or not isinstance(items, list):
            res = LyricsResult(
                status="not_found",
                track_name=title,
                artist_name=artist,
                message="Lirik belum tersedia di LRCLIB untuk lagu ini.",
            )
            self._cache[cache_key] = res
            return res

        # Pilih hasil terbaik (utamakan yang memiliki syncedLyrics dan durasi mendekati)
        best = items[0]
        for candidate in items:
            if candidate.get("syncedLyrics"):
                if duration_sec > 0 and candidate.get("duration"):
                    if abs(int(candidate["duration"]) - duration_sec) <= 8:
                        best = candidate
                        break
                best = candidate
                break

        synced_raw = (best.get("syncedLyrics") or "").strip()
        plain_raw = (best.get("plainLyrics") or "").strip()

        if synced_raw:
            parsed_lines = parse_lrc_timestamps(synced_raw)
            res = LyricsResult(
                status="synced",
                track_name=best.get("trackName") or title,
                artist_name=best.get("artistName") or artist,
                synced_lines=parsed_lines,
                plain_lyrics=plain_raw,
                message="Lirik tersinkronisasi per baris dari LRCLIB.",
            )
        elif plain_raw:
            res = LyricsResult(
                status="plain",
                track_name=best.get("trackName") or title,
                artist_name=best.get("artistName") or artist,
                plain_lyrics=plain_raw,
                message="Hanya lirik teks biasa (plainLyrics) yang tersedia.",
            )
        else:
            res = LyricsResult(
                status="not_found",
                track_name=title,
                artist_name=artist,
                message="Lagu ini merupakan instrumental atau belum memiliki teks lirik.",
            )

        self._cache[cache_key] = res
        return res


lyrics_service = LyricsService()
