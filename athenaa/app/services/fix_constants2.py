import re

with open(r'C:\Users\violi\Downloads\athena-discord-bot\athenaa\app\services\music_service.py', 'r') as f:
    content = f.read()

old = '''NON_LATIN_SCRIPT_RE = re.compile(
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
        "artist": "Live Radio Stream \u00b7 Top 40 Indonesia",
        "genre": "Top 40 / Pop Indonesia & Internasional",
        "stream_url": "https://s7.alhastream.com/radio/8030/radio",
    },
    {
        "id": "hardrockfm",
        "name": "Hard Rock FM 87.6 Jakarta",
        "artist": "Live Radio Stream \u00b7 Pop & Rock",
        "genre": "Lifestyle / Rock / Pop Hits",
        "stream_url": "https://n09.radiojar.com/7csmg90fuqruv",
    },
    {
        "id": "genfm",
        "name": "Gen FM 98.7 Jakarta",
        "artist": "Live Radio Stream \u00b7 Musik Hits Indonesia",
        "genre": "Musik Hits Terbaik Indonesia",
        "stream_url": "https://n07.radiojar.com/4ywdgup3bnzuv",
    },
    {
        "id": "lofigirl",
        "name": "Lofi Hip Hop Beats 24/7 Stream",
        "artist": "StreamAfrica \u00b7 Chill & Focus",
        "genre": "Chill / Study Beats",
        "stream_url": "https://play.streamafrica.net/lofiradio",
    },
]


def get_verified_radios() -> List[Dict[str, str]]:
    """Mengembalikan daftar stasiun radio internet terverifikasi dari config YAML."""
    return VERIFIED_RADIO_STATIONS


# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)
CURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = ['''

new = '''NON_LATIN_SCRIPT_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u0400-\u04ff\u0e00-\u0e7f]"
)

# Constants loaded from config YAML (see app/config/loader.py)
MIN_SINGLE_DURATION_SEC = _music_config.min_single_duration_sec
MAX_SINGLE_DURATION_SEC = _music_config.max_single_duration_sec
MIN_VIRAL_VIEWS_THRESHOLD = _music_config.min_viral_views_threshold

# Radio stations loaded from config YAML
VERIFIED_RADIO_STATIONS = VERIFIED_RADIO_STATIONS  # Already loaded from config above


def get_verified_radios() -> List[Dict[str, str]]:
    """Mengembalikan daftar stasiun radio internet terverifikasi dari config YAML."""
    return VERIFIED_RADIO_STATIONS


# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)
CURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = ['''

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\violi\Downloads\athena-discord-bot\athenaa\app\services\music_service.py', 'w') as f:
        f.write(content)
    print('SUCCESS: Updated constants section')
else:
    print('NOT FOUND: Pattern not matched')