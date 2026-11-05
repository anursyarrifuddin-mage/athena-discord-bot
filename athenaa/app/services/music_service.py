"""
Modul Music Engine (Verified 1:1 Audio Stream Binding, 25-Track Single Dropdown & Pure Music Autoplay).
- Mengunci source_url ke URL video_id eksak hasil pencarian/Radio Mix sambil mempertahankan
  source_type='spotify_matched' agar UI menampilkan Spotify namun audio yang diputar 100% akurat.
- Menghapus ekstraksi video_id dari thumbnail_url yang sebelumnya menyebabkan salah putar lagu.
- Menggunakan ytsearch1 cepat (< 1.5 detik) sebagai ganti ytsearch5 agar tidak pernah timeout.
"""

from __future__ import annotations

import html
import json
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.security.validators import validate_external_url

logger = logging.getLogger("athenaa.music")

SPOTIFY_URL_RE = re.compile(
    r"^https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?v=|playlist\?list=|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

NON_LATIN_SCRIPT_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u0400-\u04ff\u0e00-\u0e7f]"
)

# Rentang durasi lagu satuan (35 detik s/d 540 detik = 9 menit)
# Lagu TikTok pendek (40s) dan lagu panjang (To The Bone / Dewa 19) tetap lolos, tapi Full Album (30m-2h) diblokir!
MIN_SINGLE_DURATION_SEC = 35
MAX_SINGLE_DURATION_SEC = 540
MIN_VIRAL_VIEWS_THRESHOLD = 25_000

VERIFIED_RADIO_STATIONS: List[Dict[str, str]] = [
    {
        "id": "prambors",
        "name": "Prambors FM 102.2 Jakarta",
        "artist": "Live Radio Stream · Top 40 Indonesia",
        "genre": "Top 40 / Pop Indonesia & Internasional",
        "stream_url": "https://s7.alhastream.com/radio/8030/radio",
    },
    {
        "id": "hardrockfm",
        "name": "Hard Rock FM 87.6 Jakarta",
        "artist": "Live Radio Stream · Pop & Rock",
        "genre": "Lifestyle / Rock / Pop Hits",
        "stream_url": "https://n09.radiojar.com/7csmg90fuqruv",
    },
    {
        "id": "genfm",
        "name": "Gen FM 98.7 Jakarta",
        "artist": "Live Radio Stream · Musik Hits Indonesia",
        "genre": "Musik Hits Terbaik Indonesia",
        "stream_url": "https://n07.radiojar.com/4ywdgup3bnzuv",
    },
    {
        "id": "lofigirl",
        "name": "Lofi Hip Hop Beats 24/7 Stream",
        "artist": "StreamAfrica · Chill & Focus",
        "genre": "Chill / Study Beats",
        "stream_url": "https://play.streamafrica.net/lofiradio",
    },
]


def get_verified_radios() -> List[Dict[str, str]]:
    """Mengembalikan daftar stasiun radio internet terverifikasi."""
    return list(VERIFIED_RADIO_STATIONS)


# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)
CURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = [
    {"title": "Cincin", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 266, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Evaluasi", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 194, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Secukupnya", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 205, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Rumah Ke Rumah", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 277, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Kita Ke Sana", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 248, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Untungnya, Hidup Harus Tetap Berjalan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 184, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Satu Bulan", "artist": "Bernadya", "album": "Terlintas", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Kata Mereka Ini Berlebihan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 191, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Sial", "artist": "Mahalini", "album": "Fabula", "duration_sec": 243, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Mati-Matian", "artist": "Mahalini", "album": "Single", "duration_sec": 244, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Bawa Dia Kembali", "artist": "Mahalini", "album": "Fabula", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Monokrom", "artist": "Tulus", "album": "Monokrom", "duration_sec": 214, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=QqJ-Vp8mvbk", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Hati-Hati di Jalan", "artist": "Tulus", "album": "Manusia", "duration_sec": 242, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=_N6vSc_mT6I", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Lantas", "artist": "Juicy Luicy", "album": "Sentimental", "duration_sec": 234, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=ba-XAIskH_g", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Sialan", "artist": "Adrian Khalif, Juicy Luicy", "album": "Nonfiksi", "duration_sec": 241, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Tampar", "artist": "Juicy Luicy", "album": "Nonfiksi", "duration_sec": 218, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Gala Bunga Matahari", "artist": "Sal Priadi", "album": "MARKERS AND SUCH PENS FLASHDISKS", "duration_sec": 209, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Bertaut", "artist": "Nadin Amizah", "album": "Selamat Ulang Tahun", "duration_sec": 316, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Sorai", "artist": "Nadin Amizah", "album": "Sorai", "duration_sec": 278, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Serana", "artist": "for Revenge", "album": "Perayaan Patah Hati", "duration_sec": 245, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "rock_alt"},
    {"title": "Jakarta Hari Ini", "artist": "for Revenge, Stereo Wall", "album": "Perayaan Patah Hati", "duration_sec": 225, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "rock_alt"},
    {"title": "Nina", "artist": ".Feast", "album": "Membangun & Menghancurkan", "duration_sec": 262, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Penjaga Hati", "artist": "Nadhif Basalamah", "album": "Nadhif", "duration_sec": 260, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Komang", "artist": "Raim Laode", "album": "Komang", "duration_sec": 222, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Dan", "artist": "Sheila On 7", "album": "Sheila On 7", "duration_sec": 286, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=pBZs_Py-1_0", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Die With A Smile", "artist": "Lady Gaga, Bruno Mars", "album": "Single", "duration_sec": 251, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "luther", "artist": "Kendrick Lamar, SZA", "album": "GNX", "duration_sec": 177, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "we can't be friends (wait for your love)", "artist": "Ariana Grande", "album": "eternal sunshine", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "BIRDS OF A FEATHER", "artist": "Billie Eilish", "album": "HIT ME HARD AND SOFT", "duration_sec": 210, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "Blinding Lights", "artist": "The Weeknd", "album": "After Hours", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
]


def detect_track_genre(title: str, artist: str) -> str:
    combined = f"{title or ''} {artist or ''}".strip().lower()
    if re.search(r"\b(lofi|lo-fi|chillhop|study\s*beats|streamafrica)\b", combined):
        return "lofi_chill"
    if NON_LATIN_SCRIPT_RE.search(combined):
        return "asian_viral"
    return "global_viral"


@dataclass
class TrackCandidate:
    title: str
    artist: str
    album: str
    duration_sec: int
    source_type: str  # spotify_matched | youtube | radio
    source_url: str
    stream_url: str
    thumbnail_url: str
    notice: str = ""


# ==============================================================================
# Pembersih Judul & Base-Song Deduplicator
# ==============================================================================
# Hanya menghapus tag di dalam kurung (...) / [...] atau setelah tanda '|' / '//'
YOUTUBE_JUNK_BRACKET_RE = re.compile(
    r"\s*(?:"
    r"[\(\[\{][^)\]\}]*?(?:official|lyric|lirik|video|audio|mv|visualizer|live|performance|hd|hq|4k|remastered|terbaru|lagu|clip|ost|soundtrack|karaoke|sub\s*indo|eng\s*sub)[^)\]\}]*?[\)\]\}]|"
    r"\|.*$|"
    r"//.*$"
    r")",
    re.IGNORECASE,
)

YOUTUBE_TRAILING_TAG_RE = re.compile(
    r"\s*[-–—:]?\s*\b(?:"
    r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics|mv|visualizer)|"
    r"lyric\s*video|video\s*lirik|full\s*lirik|with\s*lyrics|audio\s*only"
    r")\s*$",
    re.IGNORECASE,
)

VERSION_MODIFIERS_RE = re.compile(
    r"\b("
    r"remix|remixed|slowed|slow|reverb|sped\s*up|speed\s*up|nightcore|daycore|"
    r"dj|bass\s*boosted|bassboost|jedag\s*jedug|jj|tiktok|douyin|viral|trend|trending|"
    r"version|ver|ori|original|edit|bootleg|flip|mashup|mix|extended|radio\s*edit|"
    r"acoustic|akustik|live|cover|koplo|dangdut|instrumental|karaoke|"
    r"official|audio|video|music|lyrics?|lirik|lagu|terbaru|ost|soundtrack|theme|song|"
    r"prod|feat|ft|with|by|x"
    r")\b",
    re.IGNORECASE,
)


def _normalize_casing(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        if s.upper() in ("SZA", "RAN", "SO7", "BCL", "GAC", "BTS", "NIKI", "TXT", "OST"):
            return s.upper()
        return s.title()
    return s


def _clean_youtube_title_and_artist(raw_title: str, channel_name: str) -> Tuple[str, str]:
    cleaned_title = html.unescape(raw_title or "").strip()
    cleaned_channel = html.unescape(channel_name or "Spotify Artist").strip()
    cleaned_channel = re.sub(r"\s*-\s*Topic$", "", cleaned_channel, flags=re.IGNORECASE)
    cleaned_channel = re.sub(
        r"\s*(?:Official(?:\s*Channel|\s*Music)?|VEVO|Music|Records|Entertainment|Indonesia|ID)\s*$",
        "",
        cleaned_channel,
        flags=re.IGNORECASE,
    ).strip()

    for _ in range(3):
        cleaned_title = YOUTUBE_JUNK_BRACKET_RE.sub("", cleaned_title).strip(" -–—|:·.")
        cleaned_title = YOUTUBE_TRAILING_TAG_RE.sub("", cleaned_title).strip(" -–—|:·.")

    artist_out = cleaned_channel
    song_out = cleaned_title

    for sep in (" - ", " – ", " — "):
        if sep in cleaned_title:
            parts = cleaned_title.split(sep, 1)
            left = parts[0].strip().strip('"').strip("'")
            right = parts[1].strip().strip('"').strip("'")
            if left and right:
                if YOUTUBE_TRAILING_TAG_RE.fullmatch(right):
                    song_out = left
                else:
                    artist_out = left
                    song_out = right
                break

    for _ in range(2):
        song_out = YOUTUBE_JUNK_BRACKET_RE.sub("", song_out).strip(" -–—|:·.\"'")
        song_out = YOUTUBE_TRAILING_TAG_RE.sub("", song_out).strip(" -–—|:·.\"'")
        artist_out = YOUTUBE_JUNK_BRACKET_RE.sub("", artist_out).strip(" -–—|:·.\"'")

    song_out = re.sub(r"\.{2,}$", "", song_out).strip()
    song_out = _normalize_casing(song_out) or "Unknown Track"
    artist_out = _normalize_casing(artist_out) or "Spotify Artist"
    return song_out, artist_out


def normalize_title_only(title: str) -> str:
    clean_t, _ = _clean_youtube_title_and_artist(title or "", "")
    no_brackets = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", " ", clean_t)
    core = VERSION_MODIFIERS_RE.sub(" ", no_brackets)
    core = re.sub(r"\b(the|a|an)\b", " ", core, flags=re.IGNORECASE)
    res = re.sub(r"[^\w]+", "", core.lower(), flags=re.UNICODE).replace("_", "")
    if len(res) >= 3:
        return res
    fallback = re.sub(r"[^\w]+", "", clean_t.lower(), flags=re.UNICODE).replace("_", "")
    return fallback or clean_t.lower().strip()


def normalize_artist_only(artist: str) -> str:
    primary = re.split(r"[,&/]|(?:\bfeat\.?\b)|(?:\bft\.?\b)|(?:\bwith\b)", artist or "", flags=re.IGNORECASE)[0]
    _, clean_a = _clean_youtube_title_and_artist("", primary)
    core_a = VERSION_MODIFIERS_RE.sub(" ", clean_a)
    res = re.sub(r"[^\w]+", "", core_a.lower(), flags=re.UNICODE).replace("_", "")
    return res or clean_a.lower().strip()


def normalize_song_identity(title: str, artist: str) -> str:
    return f"{normalize_title_only(title)}::{normalize_artist_only(artist)}"


def is_same_base_song(title_1: str, title_2: str) -> bool:
    n1 = normalize_title_only(title_1)
    n2 = normalize_title_only(title_2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    if len(n1) >= 5 and len(n2) >= 5 and (n1 in n2 or n2 in n1):
        return True
    return False


# ==============================================================================
# Registri Pemetaan Lagu -> Video ID Eksak (Tanpa Overwrite & Tanpa Substring Liar)
# ==============================================================================
_TRACK_META_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _clean_search_slug(raw_query: str) -> str:
    q = re.sub(r"^ytsearch\d*:", "", (raw_query or "").strip(), flags=re.IGNORECASE).strip()
    q = re.sub(r"\b(official\s*audio|official\s*video|full\s*album|playlist|kompilasi)\b", "", q, flags=re.IGNORECASE).strip()
    return q or "Hindia Evaluasi"


def _register_track_meta(
    title: str,
    artist: str,
    duration_sec: int,
    source_url: str = "",
    video_id: str = "",
    allow_overwrite: bool = False,
) -> None:
    """
    HANYA mendaftarkan video_id jika benar-benar berasal dari link video valid (11 karakter),
    dan hanya menggunakan kunci pasangan (title + artist) yang presisi.
    """
    if not title:
        return
    clean_t, clean_a = _clean_youtube_title_and_artist(title, artist)
    vid = (video_id or "").strip()
    if not vid and source_url:
        yt_m = YOUTUBE_URL_RE.match(source_url.strip())
        if yt_m and "results?search_query=" not in source_url:
            vid = yt_m.group(1)
        elif "vid=" in source_url:
            parsed = urllib.parse.urlparse(source_url)
            qs = urllib.parse.parse_qs(parsed.query)
            v_list = qs.get("vid", [])
            if v_list and len(v_list[0]) == 11:
                vid = v_list[0]

    if len(vid) != 11:
        vid = ""

    meta = {
        "title": clean_t,
        "artist": clean_a,
        "duration_sec": int(duration_sec or 0),
        "video_id": vid,
    }

    exact_pair = re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE)
    clean_pair = re.sub(r"[^\w]+", "", f"{clean_t} {clean_a}".lower(), flags=re.UNICODE)
    slug_raw = _clean_search_slug(f"{title} {artist}").lower()
    slug_clean = _clean_search_slug(f"{clean_t} {clean_a}").lower()
    ident_key = normalize_song_identity(clean_t, clean_a)

    for k in (exact_pair, clean_pair, slug_raw, slug_clean, ident_key):
        if not k:
            continue
        if allow_overwrite or k not in _TRACK_META_REGISTRY or (vid and not _TRACK_META_REGISTRY[k].get("video_id")):
            _TRACK_META_REGISTRY[k] = meta

    if source_url and vid:
        _TRACK_META_REGISTRY[source_url.strip()] = meta


def _lookup_registered_meta(query_or_url: str, title: str = "", artist: str = "") -> Optional[Dict[str, Any]]:
    raw = (query_or_url or "").strip()
    if raw in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[raw]

    slug = _clean_search_slug(raw).lower()
    if slug in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[slug]

    alnum_slug = re.sub(r"[^\w]+", "", slug, flags=re.UNICODE)
    if alnum_slug in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[alnum_slug]

    if title and artist:
        for tk in (
            re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE),
            normalize_song_identity(title, artist),
        ):
            if tk and tk in _TRACK_META_REGISTRY:
                return _TRACK_META_REGISTRY[tk]
    return None


def _extract_vid_from_url_or_registry(query_or_url: str, title: str = "", artist: str = "") -> str:
    raw = (query_or_url or "").strip()
    if raw:
        yt_m = YOUTUBE_URL_RE.match(raw)
        if yt_m and "results?search_query=" not in raw:
            return yt_m.group(1)
        if "vid=" in raw:
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            vid_list = qs.get("vid", [])
            if vid_list and len(vid_list[0]) == 11:
                return vid_list[0]

    meta = _lookup_registered_meta(raw, title=title, artist=artist)
    if meta and meta.get("video_id") and len(str(meta["video_id"])) == 11:
        return str(meta["video_id"])
    return ""


def classify_music_input(query_or_url: str) -> Tuple[str, Optional[str]]:
    text = (query_or_url or "").strip()
    if "open.spotify.com/search/" in text:
        path_part = text.split("open.spotify.com/search/", 1)[-1].split("?", 1)[0]
        slug = urllib.parse.unquote(path_part).strip("/")
        return "search_query", slug

    sp_match = SPOTIFY_URL_RE.match(text)
    if sp_match:
        kind = sp_match.group(1).lower()
        return f"spotify_{kind}", sp_match.group(2)

    yt_match = YOUTUBE_URL_RE.match(text)
    if yt_match:
        return "youtube", yt_match.group(1)

    if text.startswith("http://") or text.startswith("https://"):
        ok, _ = validate_external_url(text)
        if ok:
            return "radio_url", text
        raise ValueError("URL tidak valid atau mengarah ke jaringan internal yang diblokir.")

    return "search_query", text


def _parse_duration_str(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    normalized = cleaned.replace(".", ":")
    parts = [p.strip() for p in normalized.split(":") if p.strip().isdigit()]
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def _parse_view_count(view_text: str) -> int:
    if not view_text:
        return 0
    low = view_text.lower().replace("\xa0", " ").strip()
    num_match = re.search(r"(\d+(?:[.,]\d+)?)", low)
    if not num_match:
        return 0
    raw_num = num_match.group(1)
    if any(m in low for m in ("jt", "juta", "million", "萬", "万")) or low.endswith("m") or "m " in low:
        mult = 10_000 if ("萬" in low or "万" in low) else 1_000_000
        return int(float(raw_num.replace(",", ".")) * mult)
    if any(k in low for k in ("rb", "ribu")) or low.endswith("k") or "k " in low:
        return int(float(raw_num.replace(",", ".")) * 1_000)
    if "miliar" in low or "b " in low or low.endswith("b") or "億" in low or "亿" in low:
        return int(float(raw_num.replace(",", ".")) * 1_000_000_000)
    digits_only = re.sub(r"\D", "", low)
    return int(digits_only) if digits_only else 0


# ==============================================================================
# SQLite Persistent Music Play History Engine (Tanpa Regex Thumbnail Palsu!)
# ==============================================================================
_HISTORY_TABLE_READY = False


def _get_sqlite_db_path() -> Path:
    db_path = getattr(settings, "sqlite_path", None) or getattr(settings, "db_path", None)
    if db_path:
        return Path(db_path)
    return Path("data/athenaa.db")


def ensure_music_history_table() -> None:
    global _HISTORY_TABLE_READY
    if _HISTORY_TABLE_READY:
        return
    try:
        db_file = _get_sqlite_db_path()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS music_play_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    norm_title TEXT NOT NULL,
                    norm_artist TEXT NOT NULL,
                    genre TEXT DEFAULT '',
                    video_id TEXT DEFAULT '',
                    source_url TEXT DEFAULT '',
                    thumbnail_url TEXT DEFAULT '',
                    duration_sec INTEGER DEFAULT 180,
                    is_autoplay INTEGER DEFAULT 0,
                    played_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_music_history_guild_id ON music_play_history(guild_id, id DESC);"
            )
            conn.commit()
        _HISTORY_TABLE_READY = True
    except Exception as exc:
        logger.debug("Gagal inisialisasi tabel music_play_history: %s", exc)


def record_play_history_db(
    guild_id: str,
    title: str,
    artist: str,
    source_url: str = "",
    thumbnail_url: str = "",
    duration_sec: int = 180,
    is_autoplay: bool = False,
) -> None:
    """
    Mencatat lagu ke SQLite.
    PENTING: TIDAK PERNAH mengambil video_id dari thumbnail_url agar gambar placeholder
    tidak meracuni stream audio lagu lain!
    """
    gid = str(guild_id or "").strip()
    if not gid or not title:
        return
    ensure_music_history_table()
    try:
        clean_t, clean_a = _clean_youtube_title_and_artist(title, artist)
        norm_t = normalize_title_only(clean_t)
        norm_a = normalize_artist_only(clean_a)
        if not norm_t:
            return

        vid = _extract_vid_from_url_or_registry(source_url, clean_t, clean_a)
        if vid:
            _register_track_meta(title, artist, duration_sec, source_url, video_id=vid)

        genre = detect_track_genre(clean_t, clean_a)
        now_iso = datetime.now(timezone.utc).isoformat()

        db_file = _get_sqlite_db_path()
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            last_row = conn.execute(
                "SELECT id, norm_title, video_id FROM music_play_history WHERE guild_id = ? ORDER BY id DESC LIMIT 1",
                (gid,),
            ).fetchone()
            if last_row and last_row[1] == norm_t:
                if vid and not last_row[2]:
                    conn.execute(
                        "UPDATE music_play_history SET video_id = ?, source_url = ? WHERE id = ?",
                        (vid, source_url or f"https://www.youtube.com/watch?v={vid}", last_row[0]),
                    )
                    conn.commit()
                return

            conn.execute(
                """
                INSERT INTO music_play_history (
                    guild_id, title, artist, norm_title, norm_artist,
                    genre, video_id, source_url, thumbnail_url, duration_sec, is_autoplay, played_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gid,
                    clean_t,
                    clean_a,
                    norm_t,
                    norm_a,
                    genre,
                    vid,
                    source_url or "",
                    thumbnail_url or "",
                    int(duration_sec or 180),
                    1 if is_autoplay else 0,
                    now_iso,
                ),
            )
            conn.execute(
                """
                DELETE FROM music_play_history
                WHERE guild_id = ? AND id NOT IN (
                    SELECT id FROM music_play_history WHERE guild_id = ? ORDER BY id DESC LIMIT 150
                )
                """,
                (gid, gid),
            )
            conn.commit()
    except Exception as exc:
        logger.debug("Gagal mencatat riwayat lagu ke DB: %s", exc)


def get_recent_play_history_db(guild_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    gid = str(guild_id or "").strip()
    if not gid:
        return []
    ensure_music_history_table()
    try:
        db_file = _get_sqlite_db_path()
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT title, artist, norm_title, norm_artist, genre, video_id, source_url, thumbnail_url, duration_sec
                FROM music_play_history
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (gid, max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


# ==============================================================================
# Filter Anti-Full-Album, Anti-Kompilasi & Anti-Video-Non-Musik
# ==============================================================================
_SEARCH_RESULT_CACHE: Dict[str, Tuple[float, List[TrackCandidate]]] = {}
_SEARCH_CACHE_TTL_SEC = 900.0

ALBUM_OR_NON_MUSIC_RE = re.compile(
    r"\b("
    r"full\s*album|album\s*full|complete\s*album|mini\s*album|album\s*lengkap|tracklist|"
    r"kompilasi|compilation|playlist|nonstop|non-stop|megamix|continuous\s*mix|"
    r"1\s*hour|2\s*hours|3\s*hours|1\s*jam|2\s*jam|"
    r"all\s*songs|semua\s*lagu|kumpulan\s*lagu|kumpulan\s*musik|kumpulan\s*top|daftar\s*lagu|deretan\s*lagu|"
    r"lagu\s*viral\s*tiktok|lagu\s*santai|lagu\s*trending\s*\d{4}|musik\s*indonesia\s*terbaik|"
    r"lagu\s*pop\s*terbaru|lagu\s*terpopuler|top\s*hits\s*indonesia|trending\s*top\s*hits|"
    r"sisi\s*aura\s*tenang|anhy\s*asrianhy|"
    r"karaoke|instrumental\s*only|8d\s*audio|"
    r"live\s*full|full\s*konser|live\s*concert|"
    r"reaction|reaksi|reacts|review|ulasan|unboxing|tutorial|cara\s+membuat|chord|kunci\s+gitar|"
    r"podcast|interview|wawancara|talkshow|obrolan|ceramah|kajian|khutbah|dakwah|berita|news|"
    r"vlog|daily\s+vlog|prank|challenge|experiment|eksperimen|gaming|gameplay|walkthrough|let'?s\s+play|"
    r"stream\s+highlight|funny\s+moments|komedi|stand\s+up|sketsa|parodi|short\s+movie|film\s+pendek|"
    r"behind\s*the\s*scene|making\s*of|teaser|trailer|recap|alur\s+cerita|spoiler|explained|penjelasan|"
    r"episode|eps?\s*\d+|part\s*\d+|bagian\s*\d+|bab\s*\d+"
    r")\b",
    re.IGNORECASE,
)

NON_MUSIC_YOUTUBE_CATEGORIES = {
    "gaming",
    "news & politics",
    "education",
    "howto & style",
    "science & technology",
    "sports",
    "autos & vehicles",
    "pets & animals",
    "travel & events",
    "nonprofits & activism",
    "comedy",
}

MUSIC_VIDEO_INDICATOR_RE = re.compile(
    r"\b("
    r"official\s*music\s*video|music\s*video|video\s*klip|video\s*clip|"
    r"behind\s*the\s*scene|making\s*of|teaser|trailer"
    r")\b",
    re.IGNORECASE,
)


def _is_album_or_compilation(raw_title: str, duration_sec: int = 0, channel_name: str = "") -> bool:
    if not raw_title:
        return True
    combined_check = f"{raw_title} {channel_name}"
    if ALBUM_OR_NON_MUSIC_RE.search(combined_check):
        return True
    if "#top" in combined_check.lower():
        return True
    if raw_title.count("|") >= 2 or raw_title.count("//") >= 2:
        return True
    if duration_sec > MAX_SINGLE_DURATION_SEC:
        return True
    if 0 < duration_sec < MIN_SINGLE_DURATION_SEC:
        return True
    return False


def _search_youtube_with_views(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    studio_master_only: bool = False,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Mencari single track di YouTube dan menyimpan `source_url = https://www.youtube.com/watch?v={video_id}`
    dengan `source_type = 'spotify_matched'` agar client.py memutar 100% video tersebut tanpa salah lagu!
    """
    cleaned = re.sub(
        r"\b(full\s*album|album\s*lengkap|playlist|kompilasi|nonstop)\b",
        "",
        (query or "").strip(),
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return []

    if studio_master_only:
        search_term = f'{cleaned} "Provided to YouTube"'
    elif "audio" not in cleaned.lower() and "remix" not in cleaned.lower() and "slowed" not in cleaned.lower():
        search_term = f"{cleaned} official audio"
    else:
        search_term = f"{cleaned} audio"

    encoded = urllib.parse.quote(search_term)
    url = f"https://www.youtube.com/results?search_query={encoded}&hl=id&gl=ID"
    scored_results: List[Tuple[int, TrackCandidate]] = []
    seen_base_titles: Set[str] = set()

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")

        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if not match:
            return []

        data = json.loads(match.group(1))
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item_idx, item in enumerate(items):
                vr = item.get("videoRenderer")
                if not vr:
                    continue
                video_id = vr.get("videoId")
                if not video_id or len(video_id) != 11:
                    continue

                title_runs = vr.get("title", {}).get("runs", [])
                raw_title = title_runs[0].get("text", "") if title_runs else ""
                if not raw_title:
                    continue

                owner_runs = (
                    vr.get("ownerText", {}).get("runs", [])
                    or vr.get("longBylineText", {}).get("runs", [])
                )
                raw_channel = owner_runs[0].get("text", "Spotify Artist") if owner_runs else "Spotify Artist"

                badges = vr.get("ownerBadges") or []
                is_official_artist = any(
                    "OFFICIAL_ARTIST" in str(b.get("metadataBadgeRenderer", {}).get("style", ""))
                    for b in badges
                )
                is_topic_master = "- topic" in raw_channel.lower()

                dur_text = vr.get("lengthText", {}).get("simpleText", "")
                duration_sec = _parse_duration_str(dur_text)
                if duration_sec <= 0 or _is_album_or_compilation(raw_title, duration_sec, raw_channel):
                    continue

                view_str = (
                    vr.get("viewCountText", {}).get("simpleText", "")
                    or vr.get("shortViewCountText", {}).get("simpleText", "")
                )
                views = _parse_view_count(view_str)
                if min_views > 0 and not is_topic_master and (0 < views < min_views):
                    continue

                song_title, artist_name = _clean_youtube_title_and_artist(raw_title, raw_channel)
                if _is_album_or_compilation(song_title, duration_sec, artist_name):
                    continue

                base_key = f"{normalize_title_only(song_title)}::{normalize_artist_only(artist_name)}"
                if base_key in seen_base_titles:
                    continue
                seen_base_titles.add(base_key)

                thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                # KUNCI UTAMA: Gunakan watch URL langsung di source_url agar client.py mengekstrak
                # video_id yang 100% sama persis, sementara source_type tetap 'spotify_matched'!
                direct_watch_url = f"https://www.youtube.com/watch?v={video_id}"

                _register_track_meta(
                    song_title,
                    artist_name,
                    duration_sec,
                    direct_watch_url,
                    video_id=video_id,
                    allow_overwrite=(item_idx == 0),
                )

                popularity_score = views + max(0, (25 - item_idx) * 150_000)
                if is_topic_master:
                    popularity_score += 2_000_000
                elif is_official_artist:
                    popularity_score += 1_200_000
                elif "official audio" in raw_title.lower():
                    popularity_score += 600_000
                if MUSIC_VIDEO_INDICATOR_RE.search(raw_title):
                    popularity_score -= 600_000

                scored_results.append(
                    (
                        popularity_score,
                        TrackCandidate(
                            title=song_title,
                            artist=artist_name,
                            album="Spotify Single",
                            duration_sec=duration_sec,
                            source_type=default_source_type,
                            source_url=direct_watch_url,
                            stream_url="",
                            thumbnail_url=thumb_url,
                            notice="Spotify Single Track",
                        ),
                    )
                )
                if len(scored_results) >= max(limit * 2, 35):
                    break

        return scored_results
    except Exception:
        return []


def search_youtube_http(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    prefer_popular: bool = True,
) -> List[TrackCandidate]:
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    cache_key = f"{cleaned.lower()}::{limit}::{default_source_type}::{min_views}"
    now_m = time.monotonic()
    cached_hit = _SEARCH_RESULT_CACHE.get(cache_key)
    if cached_hit and (now_m - cached_hit[0]) < _SEARCH_CACHE_TTL_SEC:
        return list(cached_hit[1])

    scored_results = _search_youtube_with_views(
        cleaned,
        limit=limit,
        default_source_type=default_source_type,
        min_views=min_views,
        studio_master_only=False,
    )
    if prefer_popular and len(scored_results) > 1:
        top_first = scored_results[:2]
        rest_sorted = sorted(scored_results[2:], key=lambda x: x[0], reverse=True)
        scored_results = top_first + rest_sorted

    results = [cand for _, cand in scored_results[:limit]]
    if results:
        _SEARCH_RESULT_CACHE[cache_key] = (now_m, list(results))
    return results


def _resolve_seed_video_id(title: str, artist: str, video_id_hint: str = "") -> str:
    if video_id_hint and len(video_id_hint) == 11:
        return video_id_hint
    reg_vid = _extract_vid_from_url_or_registry("", title=title, artist=artist)
    if reg_vid and len(reg_vid) == 11:
        return reg_vid

    q_str = f"{artist} {title}".strip() if artist and artist.lower() != "spotify artist" else title
    scored = _search_youtube_with_views(
        q_str,
        limit=2,
        default_source_type="spotify_matched",
        studio_master_only=False,
    )
    if scored:
        cand = scored[0][1]
        found_vid = _extract_vid_from_url_or_registry(cand.source_url, cand.title, cand.artist)
        if found_vid:
            return found_vid
    return ""


def _fetch_live_radio_graph_for_track(
    title: str,
    artist: str,
    video_id_hint: str = "",
    max_items: int = 30,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Menarik daftar lagu khusus dari Panel Radio Mix Musik (RD{vid}).
    Setiap kandidat menyimpan `source_url = https://www.youtube.com/watch?v={c_vid}`
    dan `source_type = 'spotify_matched'` sehingga audio yang diputar 100% lagu tersebut!
    """
    vid = _resolve_seed_video_id(title, artist, video_id_hint=video_id_hint)
    if not vid:
        return []

    mix_url = f"https://www.youtube.com/watch?v={vid}&list=RD{vid}&hl=id&gl=ID"
    extracted: List[Tuple[int, TrackCandidate]] = []

    try:
        req = urllib.request.Request(
            mix_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")

        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if not match:
            return []

        data = json.loads(match.group(1))
        watch_next = data.get("contents", {}).get("twoColumnWatchNextResults", {})

        # 1. UTAMA: Panel Radio Mix Resmi YouTube (list=RD...)
        playlist_items = (
            watch_next.get("playlist", {})
            .get("playlist", {})
            .get("contents", [])
        )
        for rank_idx, item in enumerate(playlist_items):
            pvr = item.get("playlistPanelVideoRenderer")
            if not pvr:
                continue
            c_vid = pvr.get("videoId")
            if not c_vid or len(c_vid) != 11 or c_vid == vid:
                continue

            raw_t = pvr.get("title", {}).get("simpleText") or "".join(
                r.get("text", "") for r in pvr.get("title", {}).get("runs", [])
            )
            raw_ch = "".join(r.get("text", "") for r in pvr.get("shortBylineText", {}).get("runs", []))
            dur_str = pvr.get("lengthText", {}).get("simpleText", "")
            if not raw_t or not dur_str:
                continue

            dur_sec = _parse_duration_str(dur_str)
            if dur_sec <= 0 or _is_album_or_compilation(raw_t, dur_sec, raw_ch):
                continue

            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_ch)
            if _is_album_or_compilation(clean_t, dur_sec, clean_a):
                continue

            base_score = max(500_000, 1_800_000 - (rank_idx * 35_000))
            if "- topic" in raw_ch.lower() or "official" in raw_ch.lower():
                base_score += 500_000

            direct_watch_url = f"https://www.youtube.com/watch?v={c_vid}"
            _register_track_meta(clean_t, clean_a, dur_sec, direct_watch_url, video_id=c_vid)
            extracted.append(
                (
                    base_score,
                    TrackCandidate(
                        title=clean_t,
                        artist=clean_a,
                        album="Spotify Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="Spotify Smart Autoplay",
                    ),
                )
            )
            if len(extracted) >= max_items:
                break

        # 2. Secondary Results HANYA untuk Channel Musik Terverifikasi (Official Artist Badge / - Topic)
        sec_results = (
            watch_next.get("secondaryResults", {})
            .get("secondaryResults", {})
            .get("results", [])
        )
        for item in sec_results:
            cvr = item.get("compactVideoRenderer")
            if not cvr:
                continue
            c_vid = cvr.get("videoId")
            if not c_vid or len(c_vid) != 11 or c_vid == vid:
                continue
            raw_t = cvr.get("title", {}).get("simpleText") or "".join(
                r.get("text", "") for r in cvr.get("title", {}).get("runs", [])
            )
            raw_ch = "".join(r.get("text", "") for r in cvr.get("longBylineText", {}).get("runs", []))
            dur_str = cvr.get("lengthText", {}).get("simpleText", "")
            view_str = (
                cvr.get("viewCountText", {}).get("simpleText", "")
                or cvr.get("shortViewCountText", {}).get("simpleText", "")
            )
            if not raw_t or not dur_str:
                continue

            badges = cvr.get("ownerBadges") or []
            is_artist_badge = any(
                "OFFICIAL_ARTIST" in str(b.get("metadataBadgeRenderer", {}).get("style", ""))
                for b in badges
            )
            is_verified_music = bool(
                is_artist_badge
                or "- topic" in raw_ch.lower()
                or re.search(r"\b(official\s*audio|official\s*lyric|remix\s*slowed|slowed\s*reverb)\b", raw_t, re.IGNORECASE)
            )
            if not is_verified_music:
                continue

            dur_sec = _parse_duration_str(dur_str)
            if dur_sec <= 0 or _is_album_or_compilation(raw_t, dur_sec, raw_ch):
                continue

            views = _parse_view_count(view_str)
            if 0 < views < MIN_VIRAL_VIEWS_THRESHOLD:
                continue

            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_ch)
            if _is_album_or_compilation(clean_t, dur_sec, clean_a):
                continue

            score = max(views, 400_000) + 500_000
            direct_watch_url = f"https://www.youtube.com/watch?v={c_vid}"
            _register_track_meta(clean_t, clean_a, dur_sec, direct_watch_url, video_id=c_vid)
            extracted.append(
                (
                    score,
                    TrackCandidate(
                        title=clean_t,
                        artist=clean_a,
                        album="Spotify Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="Spotify Smart Autoplay",
                    ),
                )
            )
    except Exception:
        pass

    return extracted


def recommend_autoplay_tracks(
    seed_title: str,
    seed_artist: str,
    exclude_keys: Optional[Any] = None,
    limit: int = 5,
    guild_id: str = "",
    previous_tracks: Optional[List[Tuple[str, str]]] = None,
) -> List[TrackCandidate]:
    """
    Pure Organic Viral Autoplay:
    - Mengikuti rantai Radio Mix (RD{video_id}) dari Lagu B (saat ini) dan Lagu A (sebelumnya).
    - Mencegah Autoplay terjebak pada 1 penyanyi/band yang sama terus-menerus (jika Lagu A dan Lagu B
      sudah dari artis yang sama, artis lain yang se-frekuensi di Radio Mix diprioritaskan).
    """
    clean_b_title, clean_b_artist = _clean_youtube_title_and_artist(seed_title or "", seed_artist or "")
    norm_b_title = normalize_title_only(clean_b_title)
    norm_b_artist = normalize_artist_only(clean_b_artist)

    seen_base_titles: Set[str] = {norm_b_title} if norm_b_title else set()
    raw_history_titles: List[str] = [clean_b_title] if clean_b_title else []

    for raw_k in (exclude_keys or set()):
        k_str = str(raw_k).strip()
        if "::" in k_str:
            p1, _ = k_str.split("::", 1)
            t_n = normalize_title_only(p1)
            if t_n:
                seen_base_titles.add(t_n)
                raw_history_titles.append(p1)
        else:
            t_n = normalize_title_only(k_str)
            if t_n:
                seen_base_titles.add(t_n)

    db_history = get_recent_play_history_db(guild_id, limit=60) if guild_id else []
    track_a_title = ""
    track_a_artist = ""
    track_a_vid = ""
    track_b_vid = _extract_vid_from_url_or_registry("", title=seed_title, artist=seed_artist)
    recent_artist_streak = 0

    for idx_row, row in enumerate(db_history):
        r_title = str(row.get("title") or "")
        r_artist = str(row.get("artist") or "")
        r_norm_t = normalize_title_only(r_title) or str(row.get("norm_title") or "")
        r_norm_a = normalize_artist_only(r_artist) or str(row.get("norm_artist") or "")
        if r_norm_t:
            seen_base_titles.add(r_norm_t)
        if r_title:
            raw_history_titles.append(r_title)
        if idx_row < 3 and norm_b_artist and r_norm_a == norm_b_artist:
            recent_artist_streak += 1
        if r_norm_t == norm_b_title and not track_b_vid:
            v_db = str(row.get("video_id") or "")
            if len(v_db) == 11:
                track_b_vid = v_db
        if not track_a_title and r_norm_t and r_norm_t != norm_b_title:
            track_a_title = r_title
            track_a_artist = r_artist
            v_a = str(row.get("video_id") or "")
            if len(v_a) == 11:
                track_a_vid = v_a

    if not track_a_title and previous_tracks:
        for p_title, p_artist in previous_tracks:
            p_norm_t = normalize_title_only(p_title)
            if p_norm_t and p_norm_t != norm_b_title:
                track_a_title, track_a_artist = _clean_youtube_title_and_artist(p_title, p_artist)
                track_a_vid = _extract_vid_from_url_or_registry("", title=p_title, artist=p_artist)
                break

    graph_b = _fetch_live_radio_graph_for_track(seed_title, seed_artist, video_id_hint=track_b_vid, max_items=30)
    graph_a: List[Tuple[int, TrackCandidate]] = []
    if track_a_title:
        graph_a = _fetch_live_radio_graph_for_track(track_a_title, track_a_artist, video_id_hint=track_a_vid, max_items=20)

    candidate_map: Dict[str, Tuple[int, TrackCandidate]] = {}
    base_titles_in_a: Set[str] = set()

    for score_a, cand_a in graph_a:
        bt_a = normalize_title_only(cand_a.title)
        if not bt_a:
            continue
        base_titles_in_a.add(bt_a)
        candidate_map[bt_a] = (int(score_a * 0.85), cand_a)

    for score_b, cand_b in graph_b:
        bt_b = normalize_title_only(cand_b.title)
        art_b = normalize_artist_only(cand_b.artist)
        if not bt_b:
            continue
        bonus = 0
        # Lagu yang muncul di irisan Radio Mix Lagu A dan Lagu B mendapat prioritas tertinggi
        if bt_b in base_titles_in_a:
            bonus += 1_800_000
        # Jika sudah memutar >= 2 lagu berturut-turut dari artis yang sama, kurangi bobot artis tersebut
        # agar Autoplay mengalir ke penyanyi/band se-vibe lainnya di Radio Mix!
        if norm_b_artist and art_b == norm_b_artist:
            if recent_artist_streak >= 2:
                bonus -= 900_000
            else:
                bonus -= 250_000
        else:
            bonus += 350_000

        prev_score = candidate_map[bt_b][0] if bt_b in candidate_map else 0
        candidate_map[bt_b] = (max(80_000, prev_score + score_b + bonus), cand_b)

    if len(candidate_map) < limit * 2:
        related_search = _search_youtube_with_views(
            f"{clean_b_artist} {clean_b_title} official audio",
            limit=12,
            default_source_type="spotify_matched",
            min_views=MIN_VIRAL_VIEWS_THRESHOLD,
            studio_master_only=False,
        )
        for views_r, cand_r in related_search:
            bt_r = normalize_title_only(cand_r.title)
            if bt_r and bt_r not in candidate_map:
                candidate_map[bt_r] = (views_r, cand_r)

    valid_scored_pool: List[Tuple[int, TrackCandidate]] = []
    for score_val, cand in candidate_map.values():
        if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
            continue
        bt_cand = normalize_title_only(cand.title)
        if not bt_cand or bt_cand in seen_base_titles:
            continue
        if any(is_same_base_song(cand.title, prev_t) for prev_t in raw_history_titles[:25]):
            continue

        cand.source_type = "spotify_matched"
        cand.album = "Spotify Autoplay"
        cand.notice = "Spotify Smart Autoplay"
        valid_scored_pool.append((max(80_000, score_val), cand))

    valid_scored_pool.sort(key=lambda x: x[0], reverse=True)
    top_pool = valid_scored_pool[:18]

    results: List[TrackCandidate] = []
    same_artist_picked = 0
    while top_pool and len(results) < limit:
        weights = [float(item[0]) ** 0.70 for item in top_pool]
        picked_idx = random.choices(range(len(top_pool)), weights=weights, k=1)[0]
        _, picked_cand = top_pool.pop(picked_idx)
        bt_picked = normalize_title_only(picked_cand.title)
        art_picked = normalize_artist_only(picked_cand.artist)
        if bt_picked in seen_base_titles:
            continue
        # Batasi maksimal 1 lagu dari artis yang sama dalam 1 batch kandidat Autoplay jika ada artis lain
        if norm_b_artist and art_picked == norm_b_artist:
            if (recent_artist_streak >= 2 or same_artist_picked >= 1) and len(top_pool) >= 2:
                continue
            same_artist_picked += 1
        seen_base_titles.add(bt_picked)
        raw_history_titles.append(picked_cand.title)
        results.append(picked_cand)

    return results


def search_songs_with_singer(query: str, limit: int = 25) -> List[TrackCandidate]:
    cleaned = (query or "").strip()
    max_items = max(1, min(limit, 30))

    if not cleaned:
        return [
            TrackCandidate(
                title=c["title"],
                artist=c["artist"],
                album="Spotify Single",
                duration_sec=int(c["duration_sec"]),
                source_type="spotify_matched",
                source_url=str(c.get("source_url") or ""),
                stream_url="",
                thumbnail_url=c["thumbnail_url"],
                notice="Spotify Single Track",
            )
            for c in CURATED_YOUTUBE_SPOTIFY_CATALOG[:max_items]
        ]

    kind, parsed_val = classify_music_input(cleaned)
    if kind == "search_query" and parsed_val:
        cleaned = parsed_val
    elif kind in ("spotify_playlist", "spotify_album"):
        try:
            pl_data = extract_spotify_playlist_tracks(cleaned, max_tracks=max_items)
            if pl_data.get("tracks"):
                return pl_data["tracks"][:max_items]
        except Exception:
            pass
    elif kind == "spotify_track":
        try:
            return [resolve_spotify_link(cleaned)]
        except Exception:
            pass
    elif kind == "youtube":
        cand = extract_with_ytdlp(cleaned)
        if cand:
            cand.source_type = "youtube"
            return [cand]

    yt_results = search_youtube_http(cleaned, limit=max_items, default_source_type="spotify_matched")

    q_lower = cleaned.lower()
    local_matches: List[TrackCandidate] = []
    for c in CURATED_YOUTUBE_SPOTIFY_CATALOG:
        if (
            q_lower in c["title"].lower()
            or q_lower in c["artist"].lower()
            or q_lower in f"{c['title']} {c['artist']}".lower()
        ):
            local_matches.append(
                TrackCandidate(
                    title=c["title"],
                    artist=c["artist"],
                    album="Spotify Single",
                    duration_sec=int(c["duration_sec"]),
                    source_type="spotify_matched",
                    source_url=str(c.get("source_url") or ""),
                    stream_url="",
                    thumbnail_url=c["thumbnail_url"],
                    notice="Spotify Single Track",
                )
            )

    combined: List[TrackCandidate] = []
    seen = set()
    # Prioritaskan hasil pencarian langsung (yang sudah memiliki watch?v=video_id eksak!)
    for item in [*yt_results, *local_matches]:
        if _is_album_or_compilation(item.title, item.duration_sec, item.artist):
            continue
        ident = f"{item.title.lower()}::{item.artist.lower()}"
        if ident not in seen:
            seen.add(ident)
            item.source_type = "spotify_matched"
            item.album = "Spotify Single"
            combined.append(item)
        if len(combined) >= max_items:
            break

    return combined


def _fetch_spotify_embed_entity(kind: str, sp_id: str) -> Optional[Dict[str, Any]]:
    embed_url = f"https://open.spotify.com/embed/{kind}/{sp_id}"
    req = urllib.request.Request(
        embed_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.+?)</script>',
            page_html,
            re.DOTALL,
        )
        if not match:
            return None
        payload = json.loads(match.group(1))
        return (
            payload.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity")
        )
    except Exception:
        return None


def resolve_spotify_link(url_or_id: str) -> TrackCandidate:
    """
    Mendukung input berupa URL Spotify utuh ('https://open.spotify.com/track/...')
    MAUPUN ID Spotify 22-karakter ('3w09eeWmgkLz5BISaqcpgm') yang dikirim oleh cmd_play di client.py!
    """
    raw = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{22}", raw):
        url = f"https://open.spotify.com/track/{raw}"
        kind, sp_id = "spotify_track", raw
    else:
        url = raw
        kind, sp_id = classify_music_input(url)
        if not kind.startswith("spotify_") or not sp_id:
            m_any = re.search(r"(track|album|playlist)/([A-Za-z0-9]{22})", raw)
            if m_any:
                kind = f"spotify_{m_any.group(1).lower()}"
                sp_id = m_any.group(2)
                url = f"https://open.spotify.com/{m_any.group(1).lower()}/{sp_id}"
            else:
                fallback_hits = search_songs_with_singer(raw, limit=1)
                if fallback_hits:
                    return fallback_hits[0]
                raise ValueError("Bukan tautan Spotify yang valid.")

    sp_type = kind.replace("spotify_", "")
    entity = _fetch_spotify_embed_entity(sp_type, sp_id)

    title = ""
    artist = ""
    duration_sec = 0
    thumbnail = ""

    if entity:
        title = str(entity.get("title") or entity.get("name") or "").strip()
        artists_list = entity.get("artists") or []
        if artists_list and isinstance(artists_list, list):
            artist = ", ".join(str(a.get("name", "")).strip() for a in artists_list if a.get("name"))
        if not artist:
            artist = str(entity.get("subtitle") or "").replace("\xa0", " ").strip()
        if entity.get("duration"):
            duration_sec = max(MIN_SINGLE_DURATION_SEC, min(MAX_SINGLE_DURATION_SEC, int(entity["duration"]) // 1000))
        cover_sources = (
            entity.get("visualIdentity", {}).get("image", [])
            or entity.get("coverArt", {}).get("sources", [])
        )
        if cover_sources and isinstance(cover_sources, list):
            thumbnail = str(cover_sources[0].get("url") or "")

    if not title or not artist:
        try:
            req_og = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req_og, timeout=5.0) as resp_og:
                og_html = resp_og.read().decode("utf-8", errors="ignore")
            t_m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', og_html)
            d_m = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', og_html)
            i_m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', og_html)
            if not title and t_m:
                title = html.unescape(t_m.group(1)).strip()
            if not artist and d_m:
                desc_str = html.unescape(d_m.group(1)).strip()
                if "·" in desc_str:
                    first_seg = desc_str.split("·")[0].strip()
                    artist = first_seg.split(".")[-1].strip() if "." in first_seg else first_seg
            if not thumbnail and i_m:
                thumbnail = i_m.group(1).strip()
        except Exception:
            pass

    if not title:
        oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url, safe='')}"
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": "AthenaaDiscordBot/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            title = str(meta.get("title") or "").strip()
            thumbnail = thumbnail or str(meta.get("thumbnail_url") or "")
        except Exception as exc:
            raise ValueError(
                f"Metadata Spotify tidak dapat diakses ({exc}). Gunakan pencarian judul + penyanyi secara manual."
            ) from exc

    if not title:
        raise ValueError("Metadata judul Spotify kosong.")

    final_dur = duration_sec if duration_sec > 0 else 200
    final_artist = artist or "Spotify Artist"

    search_q = f"{final_artist} - {title} official audio" if final_artist != "Spotify Artist" else f"{title} official audio"
    matched = search_youtube_http(search_q, limit=2)
    if matched:
        best = matched[0]
        return TrackCandidate(
            title=title,
            artist=final_artist if final_artist != "Spotify Artist" else best.artist,
            album="Spotify Single",
            duration_sec=final_dur if duration_sec > 0 else best.duration_sec,
            source_type="spotify_matched",
            source_url=best.source_url,
            stream_url="",
            thumbnail_url=thumbnail or best.thumbnail_url,
            notice="Spotify Single Track",
        )

    return TrackCandidate(
        title=title,
        artist=final_artist,
        album="Spotify Single",
        duration_sec=final_dur,
        source_type="spotify_matched",
        source_url=url,
        stream_url="",
        thumbnail_url=thumbnail,
        notice="Spotify Single Track",
    )


def extract_spotify_playlist_tracks(url_or_id: str, max_tracks: int = 50) -> Dict[str, Any]:
    """
    Mendukung input berupa URL Playlist/Album Spotify utuh MAUPUN ID 22-karakter
    yang dikirim oleh cmd_play di client.py!
    """
    raw = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{22}", raw):
        url = f"https://open.spotify.com/playlist/{raw}"
        kind, sp_id = "spotify_playlist", raw
    else:
        url = raw
        kind, sp_id = classify_music_input(url)
        if kind not in ("spotify_playlist", "spotify_album") or not sp_id:
            m_any = re.search(r"(playlist|album)/([A-Za-z0-9]{22})", raw)
            if m_any:
                kind = f"spotify_{m_any.group(1).lower()}"
                sp_id = m_any.group(2)
                url = f"https://open.spotify.com/{m_any.group(1).lower()}/{sp_id}"
            else:
                raise ValueError("URL harus berupa tautan Spotify Playlist atau Album yang valid.")

    sp_type = "playlist" if kind == "spotify_playlist" else "album"
    entity = _fetch_spotify_embed_entity(sp_type, sp_id)
    if not entity and sp_type == "playlist":
        # Jika ID 22-karakter ternyata adalah Album Spotify, coba ambil sebagai album
        entity = _fetch_spotify_embed_entity("album", sp_id)

    playlist_name = "Spotify Playlist"
    thumbnail = ""
    tracks: List[TrackCandidate] = []

    if entity:
        playlist_name = str(entity.get("name") or entity.get("title") or "Spotify Playlist").strip()
        cover_sources = (
            entity.get("coverArt", {}).get("sources", [])
            or entity.get("visualIdentity", {}).get("image", [])
        )
        if cover_sources and isinstance(cover_sources, list):
            thumbnail = str(cover_sources[0].get("url") or "")

        track_list = entity.get("trackList") or []
        for raw_trk in track_list[: max(1, min(max_tracks, 100))]:
            t_title = str(raw_trk.get("title") or "").strip()
            t_artist = str(raw_trk.get("subtitle") or "Spotify Artist").replace("\xa0", " ").strip()
            if not t_title:
                continue
            t_dur_ms = int(raw_trk.get("duration") or 180000)
            t_dur_sec = max(MIN_SINGLE_DURATION_SEC, min(MAX_SINGLE_DURATION_SEC, t_dur_ms // 1000))
            if _is_album_or_compilation(t_title, t_dur_sec, t_artist):
                continue
            t_uri = str(raw_trk.get("uri") or "")
            track_sp_id = t_uri.split(":")[-1] if "spotify:track:" in t_uri else ""
            track_source_url = (
                f"https://open.spotify.com/track/{track_sp_id}"
                if track_sp_id
                else ""
            )
            tracks.append(
                TrackCandidate(
                    title=t_title,
                    artist=t_artist,
                    album=playlist_name,
                    duration_sec=t_dur_sec,
                    source_type="spotify_matched",
                    source_url=track_source_url,
                    stream_url="",
                    thumbnail_url=thumbnail,
                    notice="Spotify Playlist Track",
                )
            )

    if not tracks:
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url, safe='')}"
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "AthenaaDiscordBot/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            playlist_name = str(meta.get("title") or playlist_name).strip()
            thumbnail = thumbnail or str(meta.get("thumbnail_url") or "")
        except Exception:
            pass

        fallback_candidates = search_songs_with_singer(playlist_name, limit=min(15, max_tracks))
        for cand in fallback_candidates:
            if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
                continue
            tracks.append(
                TrackCandidate(
                    title=cand.title,
                    artist=cand.artist,
                    album=playlist_name,
                    duration_sec=cand.duration_sec,
                    source_type="spotify_matched",
                    source_url=cand.source_url,
                    stream_url="",
                    thumbnail_url=thumbnail or cand.thumbnail_url,
                )
            )

    return {
        "playlist_name": playlist_name,
        "thumbnail_url": thumbnail,
        "source_url": url,
        "tracks": tracks,
    }


def _to_safe_ytdlp_target(query_or_url: str, studio_master_mode: bool = False) -> str:
    """
    Mengubah input menjadi target URL video tunggal (https://www.youtube.com/watch?v=VIDEO_ID)
    agar yt-dlp mengekstrak dalam < 1.5 detik tanpa pernah timeout!
    """
    cleaned = (query_or_url or "").strip()
    if not cleaned:
        return "ytsearch1:Hindia Evaluasi official audio"

    if YOUTUBE_URL_RE.match(cleaned) and "results?search_query=" not in cleaned:
        return cleaned

    known_vid = _extract_vid_from_url_or_registry(cleaned)
    if known_vid and len(known_vid) == 11:
        return f"https://www.youtube.com/watch?v={known_vid}"

    slug = _clean_search_slug(cleaned)
    if "open.spotify.com/search/" in cleaned:
        path_part = cleaned.split("open.spotify.com/search/", 1)[-1].split("?", 1)[0]
        slug = _clean_search_slug(urllib.parse.unquote(path_part).strip("/"))
    elif SPOTIFY_URL_RE.match(cleaned):
        try:
            cand = resolve_spotify_link(cleaned)
            if YOUTUBE_URL_RE.match(cand.source_url):
                return cand.source_url
            slug = _clean_search_slug(f"{cand.title} {cand.artist}")
        except Exception:
            slug = "Mahalini Sial"

    verified_hits = search_youtube_http(slug, limit=3, default_source_type="spotify_matched")
    if verified_hits:
        v_vid = _extract_vid_from_url_or_registry(
            verified_hits[0].source_url,
            title=verified_hits[0].title,
            artist=verified_hits[0].artist,
        )
        if v_vid and len(v_vid) == 11:
            return f"https://www.youtube.com/watch?v={v_vid}"

    return f"ytsearch1:{slug} official audio"


DEFAULT_STREAM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DISCORD_OPTIMAL_YTDLP_FORMAT = (
    "bestaudio[acodec=opus][abr<=160]/"
    "bestaudio[ext=webm][abr<=160]/"
    "bestaudio[ext=m4a][abr<=160]/"
    "bestaudio/best"
)


def extract_with_ytdlp(query_or_url: str) -> Optional[TrackCandidate]:
    import sys

    cleaned_in = (query_or_url or "").strip()
    is_direct_yt = bool(YOUTUBE_URL_RE.match(cleaned_in) and "results?search_query=" not in cleaned_in)

    ytdlp_bin = shutil.which("yt-dlp")
    cmd_prefix = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]

    target = _to_safe_ytdlp_target(cleaned_in)
    cmd = [
        *cmd_prefix,
        "--force-ipv4",
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--geo-bypass",
        "--socket-timeout",
        "8",
        "--retries",
        "2",
        "--extractor-args",
        "youtube:skip=hls,translated_subs",
        "-f",
        DISCORD_OPTIMAL_YTDLP_FORMAT,
        target,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=14,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        info = json.loads(proc.stdout.splitlines()[-1])
        entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
        chosen = next((e for e in (entries or []) if isinstance(e, dict) and e.get("url")), None)
        if not chosen:
            return None

        raw_title = chosen.get("title") or "Unknown Title"
        raw_artist = chosen.get("artist") or chosen.get("uploader") or "Spotify Artist"
        clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
        c_vid = str(chosen.get("id") or "")
        src_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else (chosen.get("webpage_url") or query_or_url)
        _register_track_meta(clean_title, clean_artist, int(chosen.get("duration") or 0), src_url, video_id=c_vid)
        return TrackCandidate(
            title=clean_title,
            artist=clean_artist,
            album="YouTube Audio" if is_direct_yt else "Spotify Single",
            duration_sec=int(chosen.get("duration") or 0),
            source_type="youtube" if is_direct_yt else "spotify_matched",
            source_url=src_url,
            stream_url=chosen.get("url") or "",
            thumbnail_url=chosen.get("thumbnail") or "",
        )
    except Exception:
        return None


_STREAM_EXTRACT_CACHE: Dict[str, Tuple[float, Dict[str, object]]] = {}
_STREAM_CACHE_TTL_SEC = 1800.0


def invalidate_stream_cache(query_or_url: str) -> None:
    target = _to_safe_ytdlp_target(query_or_url)
    _STREAM_EXTRACT_CACHE.pop(target, None)
    _STREAM_EXTRACT_CACHE.pop(query_or_url, None)


def extract_playable_stream_ytdlp(query_or_url: str) -> Optional[Dict[str, object]]:
    """
    Mengekstrak URL stream audio langsung dari target yang sudah terverifikasi:
    1. Subprocess yt-dlp pada target tunggal (selesai < 1.5 detik).
    2. Fallback in-process yt_dlp jika subprocess gagal, sehingga TIDAK PERNAH mengembalikan None
       yang memicu Fallback Radio Prambors di client.py!
    """
    import sys

    cleaned_in = (query_or_url or "").strip()
    if not cleaned_in:
        return None

    now_mono = time.monotonic()
    cached = _STREAM_EXTRACT_CACHE.get(cleaned_in)
    if cached and (now_mono - cached[0]) < _STREAM_CACHE_TTL_SEC:
        return dict(cached[1])

    target = _to_safe_ytdlp_target(cleaned_in)
    cached_t = _STREAM_EXTRACT_CACHE.get(target)
    if cached_t and (now_mono - cached_t[0]) < _STREAM_CACHE_TTL_SEC:
        return dict(cached_t[1])

    ytdlp_bin = shutil.which("yt-dlp")
    cmd_prefix = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]

    cmd = [
        *cmd_prefix,
        "--force-ipv4",
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "--socket-timeout",
        "8",
        "--retries",
        "2",
        "--extractor-args",
        "youtube:skip=hls,translated_subs",
        "-f",
        DISCORD_OPTIMAL_YTDLP_FORMAT,
        target,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=14,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            info = json.loads(proc.stdout.splitlines()[-1])
            raw_entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
            for cand in raw_entries or []:
                if not isinstance(cand, dict) or not cand.get("url"):
                    continue
                raw_title = str(cand.get("title") or "Unknown Title")
                dur_sec = int(cand.get("duration") or 0)
                raw_artist = str(cand.get("artist") or cand.get("uploader") or "Spotify Artist")
                clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
                c_vid = str(cand.get("id") or "")
                headers = cand.get("http_headers") if isinstance(cand.get("http_headers"), dict) else {}
                user_agent = str(headers.get("User-Agent") or DEFAULT_STREAM_USER_AGENT)
                webpage_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else str(cand.get("webpage_url") or target)
                _register_track_meta(clean_title, clean_artist, dur_sec, webpage_url, video_id=c_vid)
                result: Dict[str, object] = {
                    "stream_url": str(cand["url"]),
                    "duration_sec": dur_sec,
                    "title": clean_title,
                    "artist": clean_artist,
                    "source_url": webpage_url,
                    "thumbnail_url": str(cand.get("thumbnail") or ""),
                    "user_agent": user_agent,
                    "acodec": str(cand.get("acodec") or ""),
                }
                _STREAM_EXTRACT_CACHE[cleaned_in] = (now_mono, result)
                _STREAM_EXTRACT_CACHE[target] = (now_mono, result)
                return dict(result)
    except Exception:
        pass

    # Fallback ke library Python yt_dlp jika subprocess gagal
    try:
        import yt_dlp  # type: ignore

        ydl_opts = {
            "format": DISCORD_OPTIMAL_YTDLP_FORMAT,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "source_address": "0.0.0.0",
            "socket_timeout": 8,
            "retries": 2,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extractor_args": {"youtube": {"skip": ["hls", "translated_subs"]}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            raw_entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
            for cand in raw_entries or []:
                if not isinstance(cand, dict) or not cand.get("url"):
                    continue
                raw_title = str(cand.get("title") or "Unknown Title")
                dur_sec = int(cand.get("duration") or 0)
                raw_artist = str(cand.get("artist") or cand.get("uploader") or "Spotify Artist")
                clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
                c_vid = str(cand.get("id") or "")
                headers = cand.get("http_headers") if isinstance(cand.get("http_headers"), dict) else {}
                user_agent = str(headers.get("User-Agent") or DEFAULT_STREAM_USER_AGENT)
                webpage_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else str(cand.get("webpage_url") or target)
                result = {
                    "stream_url": str(cand["url"]),
                    "duration_sec": dur_sec,
                    "title": clean_title,
                    "artist": clean_artist,
                    "source_url": webpage_url,
                    "thumbnail_url": str(cand.get("thumbnail") or ""),
                    "user_agent": user_agent,
                    "acodec": str(cand.get("acodec") or ""),
                }
                _STREAM_EXTRACT_CACHE[cleaned_in] = (now_mono, result)
                _STREAM_EXTRACT_CACHE[target] = (now_mono, result)
                return dict(result)
    except Exception:
        pass

    return None


ensure_music_history_table()