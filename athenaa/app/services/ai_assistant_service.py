"""
Modul AI Assistant, Multi-Key Gemini Rotator, Live Web/News Search Grounding,
Natural Language All-Command & Music Intent Parser, Memori Konteks Lagu & Obrolan Per-Channel,
Persona Luwes Tongkrongan (Tanpa Kaku & Tanpa Paksa Musik), serta Silent AutoMod Chat Sensor
untuk Athenaa Discord Bot (v5.6 Superpowers).
"""

from __future__ import annotations

import html
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import settings

logger = logging.getLogger("athenaa.ai")

DISCORD_INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9\-]+",
    re.IGNORECASE,
)
SUSPICIOUS_LINK_RE = re.compile(
    r"https?://(?:[^\s/]+\.)?(?:bit\.ly|tinyurl\.com|t\.me|free-nitro|steamcommunnity|discrod-gift)[^\s]*",
    re.IGNORECASE,
)
MENTION_TAG_RE = re.compile(r"<@!?\d+>|@everyone|@here")

# Deteksi komplain saat user menanyakan kenapa lagu sebelumnya belum terputar ("mana, kok gak ke play musik nya")
RETRY_MUSIC_COMPLAINT_RE = re.compile(
    r"(?:\b(?:mana|kok|knp|kenapa)\b.*\b(?:gak|ga|nggak|enggak|gk|belum|blm)\b.*\b(?:ke\s*play|ke\s*putar|ke\s*puter|diputar|diputer|play|putar|puter|bunyi|nyala|jalan|masuk)\b)"
    r"|(?:\b(?:puterin|putarkan|setelin|setelkan|play|putar|muter)\s+(?:lagu\s+|musik\s+)?(?:yang\s+|yg\s+)?(?:tadi|barusan|di\s*atas)\b)",
    re.IGNORECASE,
)

# Deteksi kalimat perintah memutar / mengantrekan musik dalam berbagai gaya bahasa sehari-hari
MUSIC_PLAY_INTENT_RE = re.compile(
    r"\b(?:tambahin\s+ke\s+queue[,:\s]*|masukin\s+ke\s+queue[,:\s]*|masukin\s+antrean[,:\s]*|antrikan\s+)?"
    r"(?:aku\s+pengen\s+|aku\s+ingin\s+|gua\s+mau\s+|gw\s+mau\s+|pengen\s+|ingin\s+|mau\s+)?"
    r"(?:putarkan|puterin|putarin|putar|puter|muterin|muter|memutarkan|memutar|playkan|play\s+in|play|"
    r"nyalakan|nyalain|mainkan|setelkan|setelin|setel|stel|nyetelin|nyetel|dengerin\s+musik|dengerin\s+lagu|tambahin\s+ke\s+queue|masukin\s+ke\s+queue)\s+"
    r"(?:saya\s+|aku\s+|buat\s+aku\s+|kami\s+|kita\s+|dong\s+|kan\s+)*"
    r"(?:musik|lagu|music|song|audio|track|link)?\s*"
    r"(.+)",
    re.IGNORECASE | re.DOTALL,
)

# Pembersih akhiran basa-basi, kata makian/slang, atau embel-embel di ujung judul lagu
TRAILING_SLANG_AND_FILLER_RE = re.compile(
    r"\s+(?:"
    r"klo\s+gk\s+salah.*|kalau\s+ga\s+salah.*|kalo\s+gak\s+salah.*|kalo\s+ga\s+salah.*|"
    r"bisa\s+gk.*|bisa\s+gak.*|tolong\s+puterin.*|tolong\s+putarkan.*|tolong\s+setelin.*|"
    r"ya\s+kontol|ya\s+kntl|ya\s+anjing|ya\s+anjir|ya\s+puki|ya\s+pukimak|ya\s+memek|ya\s+tempek|ya\s+asu|ya\s+bangsat|ya\s+goblok|"
    r"kontol|kntl|pukimak|puki|memek|tempek|anjing|anjir|bangsat|bgst|asu|goblok|gblk|tolol|jancok|cok|"
    r"dong\s+sayang|dong\s+kak|dong\s+min|dong\s+athena|dong\s+bot|ya\s+sayang|dong|ya\s+kak|plis|please|pls|makasih|terima\s+kasih|ya|yah|deh|sih"
    r")\s*[!.?~]*$",
    re.IGNORECASE,
)

LEADING_GREETING_RE = re.compile(
    r"^(?:woi|woy|oi|halo|hai|hey|hi|eh|kak|min|bro|sis|sayang|beb|athenaa\.my\.id|athenaa|athena|bot|"
    r"pukimak|puki|kontol|kntl|memek|tempek|anjing|anjir|bangsat|bgst|asu|goblok|gblk|tolol|cok|jancok|"
    r"tolong|coba|permisi|punten|boleh)[\s,!.:;~\-]+",
    re.IGNORECASE,
)

PURE_GREETING_RE = re.compile(
    r"^(?:halo+|hai+|hey+|hi+|pagi+|siang+|sore+|malam+|woi+|woy+|oi+|p|tes|test|ping|apa\s+kabar|lagi\s+ngapain|sibuk\s+gak|haloo+|allo+)(?:\s+(?:athena+|athenaa+|kak|bot|sayang|cantik|min))*[\s!?.~]*$",
    re.IGNORECASE,
)

HEAVY_QUESTION_RE = re.compile(
    r"(?:sebutkan\s+semua|jelaskan\s+semua|secara\s+lengkap|daftar\s+lengkap|sejarah\s+lengkap|"
    r"apa\s+saja\s+semua|jasa[\s\-]*jasa|biografi\s+lengkap|buatkan\s+makalah|buatkan\s+esai|"
    r"buatkan\s+artikel|rangkumkan\s+seluruh|ceritakan\s+semua|jelaskan\s+panjang\s+lebar)",
    re.IGNORECASE,
)

CALM_GIRL_GREETINGS = [
    "Halo juga~ Lagi santai aja nih, ada apa?",
    "Haii, iya aku di sini kok~ Kenapa nih?",
    "Halo~ Lagi standby aja nih, mau ngobrol atau ada perlu apa?",
]

# Respons santai & luwes saat dipanggil pakai kata makian/candaan tongkrongan
SLANG_BANTER_RESPONSES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:woi\s+|eh\s+|hei\s+)?(?:athena\s+|athenaa\s+)?tempek[\s!?.]*$", re.I), "Iya tempek, ada apa meks?"),
    (re.compile(r"^(?:woi\s+|eh\s+|hei\s+)?(?:athena\s+|athenaa\s+)?memek[\s!?.]*$", re.I), "Iya meks, ada apaan nih?"),
    (re.compile(r"^(?:woi\s+|eh\s+|hei\s+)?(?:athena\s+|athenaa\s+)?(?:pukimak|puki)[\s!?.]*$", re.I), "Iya puk, ada apa nih manggil-manggil?"),
    (re.compile(r"^(?:woi\s+|eh\s+|hei\s+)?(?:athena\s+|athenaa\s+)?(?:kontol|kntl)[\s!?.]*$", re.I), "Iya elah, ada apaan nih bos?"),
    (re.compile(r"^(?:woi\s+|eh\s+|hei\s+)?(?:athena\s+|athenaa\s+)?(?:anjing|anjir|asu|bangsat|nyocot|bacot)[\s!?.]*$", re.I), "Santai kali bos, lagi kenapa nih tiba-tiba ngegas?"),
]

DEFAULT_BAD_WORDS = {
    "slot gacor",
    "judol",
    "judi online",
    "maxwin",
    "depo pulsa",
    "situs gacor",
    "freebet",
}


def collect_configured_gemini_keys() -> List[str]:
    raw_sources: List[str] = []
    for env_name in (
        "GEMINI_API_KEYS",
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_1",
        "GEMINI_API_KEY_2",
        "GEMINI_API_KEY_3",
        "GEMINI_API_KEY_4",
        "GEMINI_API_KEY_5",
    ):
        val = os.environ.get(env_name, "").strip()
        if val:
            raw_sources.append(val)
    if getattr(settings, "gemini_api_keys", ""):
        raw_sources.append(str(settings.gemini_api_keys))
    if getattr(settings, "gemini_api_key", ""):
        raw_sources.append(str(settings.gemini_api_key))

    keys: List[str] = []
    for src in raw_sources:
        for part in re.split(r"[,;\s]+", src):
            cleaned = part.strip().strip('"').strip("'")
            if cleaned and cleaned not in ("MY_GEMINI_API_KEY", "CHANGE_ME") and cleaned not in keys:
                keys.append(cleaned)
    return keys


class GeminiKeyRotator:
    def __init__(
        self,
        keys: Optional[Sequence[str]] = None,
        models: Optional[Sequence[str]] = None,
        cooldown_sec: float = 60.0,
    ) -> None:
        self._explicit_keys = list(keys) if keys is not None else None
        self._explicit_models = list(models) if models is not None else None
        self.cooldown_sec = cooldown_sec
        self._cooldown_until: Dict[str, float] = {}
        self._current_idx: int = 0

    def get_keys(self) -> List[str]:
        if self._explicit_keys is not None:
            return [k for k in self._explicit_keys if k]
        return collect_configured_gemini_keys()

    def get_models(self) -> List[str]:
        if self._explicit_models is not None:
            return [m for m in self._explicit_models if m]
        primary = os.environ.get("AI_AUTOPLAY_MODEL", getattr(settings, "ai_autoplay_model", "gemini-3.8-flash")).strip() or "gemini-3.8-flash"
        fb_raw = os.environ.get(
            "AI_AUTOPLAY_FALLBACK_MODELS",
            getattr(
                settings,
                "ai_autoplay_fallback_models",
                "gemini-3.8-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite",
            ),
        )
        models = [primary]
        for m in fb_raw.split(","):
            ms = m.strip()
            if ms and ms not in models:
                models.append(ms)
        return models

    def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        timeout: float = 6.0,
        max_output_tokens: int = 180,
    ) -> Tuple[str, int]:
        keys = self.get_keys()
        if not keys:
            return "", -1
        models = self.get_models()
        now = time.monotonic()

        ordered_indices: List[int] = []
        for offset in range(len(keys)):
            idx = (self._current_idx + offset) % len(keys)
            k = keys[idx]
            if self._cooldown_until.get(k, 0.0) <= now:
                ordered_indices.append(idx)
        if not ordered_indices:
            ordered_indices = list(range(len(keys)))

        full_prompt = f"{system_instruction}\n\n{prompt}".strip() if system_instruction else prompt
        payload = json.dumps(
            {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"temperature": 0.55, "maxOutputTokens": max_output_tokens},
            }
        ).encode("utf-8")

        for key_idx in ordered_indices:
            api_key = keys[key_idx]
            for model_name in models[:4]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        raw_body = resp.read().decode("utf-8", errors="ignore")
                        data = json.loads(raw_body)
                        text_out = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        ).strip()
                        if text_out:
                            self._current_idx = key_idx
                            return text_out, key_idx
                except urllib.error.HTTPError as http_err:
                    if http_err.code in (429, 401, 403):
                        self._cooldown_until[api_key] = time.monotonic() + self.cooldown_sec
                        logger.warning(
                            "Gemini API Key #%d terkena limit/error HTTP %d pada model %s, beralih ke API Key berikutnya...",
                            key_idx + 1,
                            http_err.code,
                            model_name,
                        )
                        break
                    continue
                except Exception:
                    continue

        return "", -1


gemini_rotator = GeminiKeyRotator()


def should_respond_to_message(
    content: str,
    bot_id: str,
    mentioned_ids: Sequence[str],
) -> bool:
    bid = str(bot_id or "").strip()
    if not bid or not content:
        return False
    raw = str(content).strip()
    if "@everyone" in raw or "@here" in raw:
        return False
    has_explicit_tag = f"<@{bid}>" in raw or f"<@!{bid}>" in raw
    in_mentions = any(str(m).strip() == bid for m in (mentioned_ids or []))
    return bool(has_explicit_tag or in_mentions)


def is_heavy_or_long_question(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if HEAVY_QUESTION_RE.search(q):
        return True
    words = q.split()
    if len(words) >= 22 and any(k in q.lower() for k in ("jelaskan", "sebutkan", "analisis", "uraikan", "semua")):
        return True
    return False


def _clean_extracted_song_query(raw_song: str) -> str:
    """Membersihkan judul lagu dari kata makian, basa-basi, dan mengurutkan Title-First."""
    s = (raw_song or "").strip()
    for _ in range(4):
        nxt = TRAILING_SLANG_AND_FILLER_RE.sub("", s).strip(" \"'?!.,~-")
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"^(?:saya|aku|gua|gw|kami|kita)\s+(?:musik|lagu)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"^(?:dari\s+mashup|mashup\s+dari)\s+", "mashup ", s, flags=re.IGNORECASE).strip()

    # Pola 1: "dari <penyanyi> yang judulnya <judul>" -> "<judul> <penyanyi>"
    m_at = re.match(
        r"^(?:dari|oleh|by|penyanyi|artis)\s+(.+?)\s+(?:yang\s+)?(?:judulnya|berjudul|lagunya)\s+(.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m_at:
        artist_part = m_at.group(1).strip(" \"'?!.,")
        title_part = m_at.group(2).strip(" \"'?!.,")
        s = f"{title_part} {artist_part}".strip()
    else:
        # Pola 2: "yang judulnya <judul> dari <penyanyi>" -> "<judul> <penyanyi>"
        m_ta = re.match(
            r"^(?:yang\s+)?(?:judulnya|berjudul|lagunya)\s+(.+?)\s+(?:dari|oleh|by)\s+(.+)$",
            s,
            flags=re.IGNORECASE,
        )
        if m_ta:
            title_part = m_ta.group(1).strip(" \"'?!.,")
            artist_part = m_ta.group(2).strip(" \"'?!.,")
            s = f"{title_part} {artist_part}".strip()
        else:
            s = re.sub(r"^(?:yang\s+)?(?:judulnya|berjudul|lagunya|dari)\s+", "", s, flags=re.IGNORECASE).strip()
            m_dari = re.match(r"^(.+?)\s+dari\s+(.+)$", s, flags=re.IGNORECASE)
            if m_dari:
                s = f"{m_dari.group(1).strip()} {m_dari.group(2).strip()}".strip()

    for _ in range(3):
        nxt = TRAILING_SLANG_AND_FILLER_RE.sub("", s).strip(" \"'?!.,~-")
        if nxt == s:
            break
        s = nxt
    return s.strip()


def classify_mention_intent(content: str, bot_id: str) -> Tuple[str, str]:
    """
    Memetakan pesan mention @Athena menjadi intent eksekusi semua command bot atau chat interaktif:
    - ('retry_last_music', '') -> jika user komplain "mana, kok gak ke play musik nya"
    - ('play_music', judul_lagu) -> jika user minta putar/setel/muter/queue lagu
    - ('cmd_help', ''), ('cmd_autoplay', 'on'|'off'), ('cmd_247', 'on'|'off'),
      ('cmd_queue', ''), ('cmd_skip', ''), ('cmd_pause', ''), ('cmd_resume', ''),
      ('cmd_stop', ''), ('cmd_leave', ''), ('cmd_shuffle', ''), ('cmd_replay', ''),
      ('cmd_previous', ''), ('cmd_clear', ''), ('cmd_grab', ''), ('cmd_history', ''),
      ('cmd_lyrics', judul), ('cmd_volume', angka), ('cmd_loop', mode), ('cmd_seek', waktu),
      ('cmd_sleeptimer', menit), ('cmd_ambience', tema), ('cmd_filter', preset),
      ('cmd_tugas', ''), ('cmd_sync_waskita', ''), ('cmd_level', ''), ('cmd_leaderboard', ''),
      ('cmd_afk', alasan), ('cmd_stats', ''), ('cmd_ram_clean', ''), ('cmd_dadu', sisi),
      ('cmd_8ball', tanya), ('cmd_suit', pilihan), ('cmd_kuis', ''), ('cmd_mathbattle', ''),
      ('cmd_clear_memory', '')
    - ('greeting', sapaan)
    - ('chat_search', pertanyaan_atau_obrolan)
    """
    bid = str(bot_id or "").strip()
    cleaned = re.sub(rf"<@!?{re.escape(bid)}>", " ", str(content or "")).strip()
    cleaned = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned or PURE_GREETING_RE.match(cleaned):
        return "greeting", cleaned or "halo"

    # Cek apakah ini candaan/panggilan singkat seperti "woi athena tempek"
    for pat, _ in SLANG_BANTER_RESPONSES:
        if pat.match(cleaned):
            return "chat_search", cleaned

    # 1. Cek komplain lagu belum ke-play ("mana, kok gak ke play musik nya") SEBELUM cek kata "play"!
    if RETRY_MUSIC_COMPLAINT_RE.search(cleaned):
        return "retry_last_music", ""

    stripped_cmd = cleaned
    for _ in range(4):
        nxt = LEADING_GREETING_RE.sub("", stripped_cmd).strip()
        if nxt == stripped_cmd:
            break
        stripped_cmd = nxt

    low_full = stripped_cmd.lower().strip(" ?!.,")
    low = TRAILING_SLANG_AND_FILLER_RE.sub("", stripped_cmd).lower().strip(" ?!.,")

    if not low or PURE_GREETING_RE.match(low):
        # Jika kalimat aslinya ada kata makian seperti "woi tempek", masuk ke chat_search agar dijawab luwes
        if any(w in cleaned.lower() for w in ("tempek", "memek", "puki", "pukimak", "kontol", "asu", "nyocot")):
            return "chat_search", cleaned
        return "greeting", low or "halo"

    # 2. All Bot Commands via Natural Chat
    if low in ("help", "/help", "!help", "bantuan", "menu", "command", "commands", "daftar command", "fitur") or re.search(
        r"\b(?:buka\s+help|lihat\s+command|apa\s+aja\s+command|bantuan\s+dong)\b", low
    ):
        return "cmd_help", ""

    if "autoplay" in low or "auto play" in low or "auto-play" in low:
        if any(w in low for w in ("mati", "nonaktif", "off", "disable", "stop", "jangan")):
            return "cmd_autoplay", "off"
        return "cmd_autoplay", "on"

    if "24/7" in low or "247" in low or "24 jam" in low:
        if any(w in low for w in ("mati", "nonaktif", "off", "disable")):
            return "cmd_247", "off"
        return "cmd_247", "on"

    if low in ("queue", "/queue", "antrean", "antrian", "daftar lagu", "cek antrean", "lihat antrean") or re.search(
        r"^(?:tolong\s+)?(?:buka|lihat|cek|tampilkan)\s+(?:queue|antrean|antrian)$", low
    ):
        return "cmd_queue", ""

    if low in ("skip", "/skip", "next", "lewati", "ganti lagu", "skip lagu", "skip aja", "skip aja deh", "skip lagu ini", "skip musik ini", "lewati lagu ini") or re.search(
        r"^(?:tolong\s+)?(?:skip|lewati|next)(?:\s+lagu|\s+musik|\s+aja|\s+deh)*$", low
    ):
        return "cmd_skip", ""

    if low in ("pause", "/pause", "jeda", "pause lagu", "jeda musik", "pause dulu"):
        return "cmd_pause", ""
    if low in ("resume", "/resume", "lanjut", "lanjutkan", "lanjutkan musik", "unpause", "play lagi"):
        return "cmd_resume", ""
    if low in ("stop", "/stop", "berhenti", "matikan musik", "stop musik", "stop lagu", "stop aja"):
        return "cmd_stop", ""
    if low in ("leave", "/leave", "disconnect", "keluar voice", "keluar vc", "cabut", "keluar"):
        return "cmd_leave", ""
    if low in ("shuffle", "/shuffle", "acak", "acak lagu", "acak antrean"):
        return "cmd_shuffle", ""
    if low in ("replay", "/replay", "ulang lagu", "putar ulang", "ulangi lagu"):
        return "cmd_replay", ""
    if low in ("previous", "/previous", "lagu sebelumnya", "back lagu"):
        return "cmd_previous", ""
    if low in ("clear", "/clear", "bersihkan antrean", "hapus antrean", "clear queue"):
        return "cmd_clear", ""
    if low in ("grab", "/grab", "simpan lagu", "kirim lagu ke dm"):
        return "cmd_grab", ""
    if low in ("history", "/history", "riwayat lagu", "lagu terakhir"):
        return "cmd_history", ""

    m_vol = re.match(r"^(?:atur\s+|ganti\s+|set\s+)?(?:volume|vol|suara)\s+(\d{1,3})%?$", low)
    if m_vol:
        return "cmd_volume", m_vol.group(1)

    m_loop = re.match(r"^(?:atur\s+|mode\s+)?loop\s+(off|one|queue|mati|satu|antrean)$", low)
    if m_loop:
        lval = m_loop.group(1)
        lmap = {"mati": "off", "satu": "one", "antrean": "queue"}
        return "cmd_loop", lmap.get(lval, lval)

    m_seek = re.match(r"^(?:seek|lompat\s+ke)\s+([0-9:]+)$", low)
    if m_seek:
        return "cmd_seek", m_seek.group(1)

    m_sleep = re.match(r"^(?:sleeptimer|timer\s+tidur)\s+(\d+)$", low)
    if m_sleep:
        return "cmd_sleeptimer", m_sleep.group(1)

    for amb_k in ("rain", "cafe", "lofi", "night_coding", "piano"):
        if low in (f"ambience {amb_k}", f"/ambience {amb_k}", f"suasana {amb_k}"):
            return "cmd_ambience", amb_k

    for f_preset in ("bassboost", "nightcore", "vaporwave", "8d", "lofi", "karaoke", "treble", "normal"):
        if f"filter {f_preset}" in low or f"efek {f_preset}" in low or low == f_preset:
            return "cmd_filter", f_preset

    if any(k in low for k in ("reset memory", "hapus memory", "clear memory", "lupakan obrolan", "hapus ingatan")):
        return "cmd_clear_memory", ""

    if low in ("tugas", "/tugas", "cek tugas", "lihat tugas", "daftar tugas", "tugas kuliah"):
        return "cmd_tugas", ""
    if low in ("sync waskita", "/sync_waskita", "sinkron waskita"):
        return "cmd_sync_waskita", ""
    if low in ("level", "/level", "cek level", "rank", "exp"):
        return "cmd_level", ""
    if low in ("leaderboard", "/leaderboard", "top server", "peringkat"):
        return "cmd_leaderboard", ""
    if low.startswith("afk ") or low in ("afk", "/afk"):
        reason_afk = stripped_cmd[3:].strip() if len(stripped_cmd) > 3 else "Sedang AFK"
        return "cmd_afk", reason_afk or "Sedang AFK"
    if low in ("stats", "/stats", "status bot", "ping", "cek ram"):
        return "cmd_stats", ""
    if low in ("ram clean", "/ram_clean", "bersihkan ram", "optimasi ram"):
        return "cmd_ram_clean", ""
    if low in ("kuis", "/kuis", "main kuis"):
        return "cmd_kuis", ""
    if low in ("mathbattle", "/mathbattle", "hitung cepat"):
        return "cmd_mathbattle", ""
    if low.startswith("dadu") or low.startswith("/dadu"):
        return "cmd_dadu", "6"
    if low.startswith("suit "):
        return "cmd_suit", low.split()[-1]
    if low.startswith("lyrics") or low.startswith("lirik"):
        lq = re.sub(r"^(?:lyrics|lirik)\s*", "", stripped_cmd, flags=re.IGNORECASE).strip()
        return "cmd_lyrics", lq

    # 3. Natural Language Play / Queue Music (mendukung 'muter', 'memutar', 'setelkan', 'tambahin ke queue', dll.)
    m_play = MUSIC_PLAY_INTENT_RE.search(stripped_cmd)
    if m_play:
        song_candidate = _clean_extracted_song_query(m_play.group(1))
        # Jangan pernah menganggap kata ganti pendek ('nya', 'itu', 'ini', 'lagunya', 'musiknya') sebagai judul lagu!
        if song_candidate.lower() in ("nya", "itu", "ini", "lagunya", "musiknya", "lagu", "musik", "tadi", "yg tadi"):
            return "retry_last_music", ""
        if song_candidate and len(song_candidate) >= 1:
            return "play_music", song_candidate

    return "chat_search", cleaned


def _ensure_chat_memory_table() -> None:
    from app.database import db_manager
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_channel_chat_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    bot_reply TEXT NOT NULL,
                    last_song_query TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(ai_channel_chat_memory)").fetchall()}
            if "last_song_query" not in cols:
                conn.execute("ALTER TABLE ai_channel_chat_memory ADD COLUMN last_song_query TEXT DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_chat_mem_channel ON ai_channel_chat_memory(channel_id, id DESC)"
            )
    except Exception:
        pass


def save_channel_chat_turn(
    guild_id: str,
    channel_id: str,
    user_id: str,
    user_name: str,
    user_message: str,
    bot_reply: str,
    last_song_query: str = "",
    max_turns_per_channel: int = 8,
) -> None:
    ch_id = str(channel_id or "").strip()
    if not ch_id:
        return
    _ensure_chat_memory_table()
    from datetime import datetime, timezone
    from app.database import db_manager

    u_msg = re.sub(r"\s+", " ", str(user_message or "")).strip()[:160]
    b_rep = re.sub(r"\s+", " ", str(bot_reply or "")).strip()[:200]
    song_q = str(last_song_query or "").strip()[:150]
    if not song_q:
        # Coba deteksi jika di dalam user_message ada permintaan lagu
        m_s = MUSIC_PLAY_INTENT_RE.search(u_msg)
        if m_s:
            cand_s = _clean_extracted_song_query(m_s.group(1))
            if cand_s.lower() not in ("nya", "itu", "ini", "lagunya", "musiknya", ""):
                song_q = cand_s[:150]

    if not u_msg or not b_rep:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_channel_chat_memory (
                    guild_id, channel_id, user_id, user_name, user_message, bot_reply, last_song_query, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(guild_id or ""),
                    ch_id,
                    str(user_id or ""),
                    str(user_name or "Member")[:40],
                    u_msg,
                    b_rep,
                    song_q,
                    now_iso,
                ),
            )
            conn.execute(
                """
                DELETE FROM ai_channel_chat_memory
                WHERE channel_id = ?
                  AND id NOT IN (
                      SELECT id FROM ai_channel_chat_memory
                      WHERE channel_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (ch_id, ch_id, max(2, int(max_turns_per_channel))),
            )
    except Exception:
        pass


def get_last_requested_song_in_channel(channel_id: str) -> str:
    """Mengambil judul lagu terakhir yang diminta di channel_id tersebut dari memori SQLite."""
    ch_id = str(channel_id or "").strip()
    if not ch_id:
        return ""
    _ensure_chat_memory_table()
    from app.database import db_manager
    try:
        with db_manager.transaction() as conn:
            rows = conn.execute(
                """
                SELECT last_song_query, user_message
                FROM ai_channel_chat_memory
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT 6
                """,
                (ch_id,),
            ).fetchall()
        for r in rows:
            sq = str(r["last_song_query"] or "").strip()
            if sq and sq.lower() not in ("nya", "itu", "ini", "lagunya", "musiknya"):
                return sq
            um = str(r["user_message"] or "").strip()
            m_s = MUSIC_PLAY_INTENT_RE.search(um)
            if m_s:
                cand_s = _clean_extracted_song_query(m_s.group(1))
                if cand_s and cand_s.lower() not in ("nya", "itu", "ini", "lagunya", "musiknya"):
                    return cand_s
    except Exception:
        pass
    return ""


def get_channel_chat_context(channel_id: str, limit: int = 4) -> str:
    ch_id = str(channel_id or "").strip()
    if not ch_id:
        return ""
    _ensure_chat_memory_table()
    from app.database import db_manager
    try:
        with db_manager.transaction() as conn:
            rows = conn.execute(
                """
                SELECT user_name, user_message, bot_reply
                FROM ai_channel_chat_memory
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ch_id, max(1, min(6, int(limit)))),
            ).fetchall()
        if not rows:
            return ""
        lines: List[str] = []
        for r in reversed(rows):
            uname = str(r["user_name"] or "User")[:25]
            umsg = str(r["user_message"] or "")[:110]
            brep = str(r["bot_reply"] or "")[:140]
            lines.append(f"{uname}: {umsg}\nAthena: {brep}")
        return "\n".join(lines)[:600]
    except Exception:
        return ""


def clear_channel_chat_memory(channel_id: str) -> int:
    ch_id = str(channel_id or "").strip()
    if not ch_id:
        return 0
    _ensure_chat_memory_table()
    from app.database import db_manager
    try:
        with db_manager.transaction() as conn:
            cur = conn.execute("DELETE FROM ai_channel_chat_memory WHERE channel_id = ?", (ch_id,))
            return int(cur.rowcount or 0)
    except Exception:
        return 0


def search_realtime_web_context(query: str, max_items: int = 3) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    q_clean = re.sub(r"[^\w\s\-?]", " ", query).strip()
    if not q_clean or len(q_clean) < 3:
        return results

    compact_search_url = f"https://news.google.com/search?q={urllib.parse.quote(q_clean[:60])}&hl=id&gl=ID&ceid=ID:id"

    try:
        rss_url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(q_clean[:80])
            + "&hl=id&gl=ID&ceid=ID:id"
        )
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AthenaaBot/5.6)"},
        )
        with urllib.request.urlopen(req, timeout=3.2) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        for item in root.findall("./channel/item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source_name = (source_el.text if source_el is not None and source_el.text else "Google News").strip()
            if title:
                results.append(
                    {
                        "title": html.unescape(title)[:110],
                        "source": source_name[:40],
                        "date": pub_date[:16],
                        "url": compact_search_url,
                    }
                )
    except Exception:
        pass

    if len(results) < 2:
        try:
            wiki_url = (
                "https://id.wikipedia.org/w/api.php?action=query&list=search&srsearch="
                + urllib.parse.quote(q_clean[:80])
                + "&utf8=&format=json&srlimit=2"
            )
            req_w = urllib.request.Request(
                wiki_url,
                headers={"User-Agent": "AthenaaDiscordBot/5.6 (https://bot.athenaa.my.id)"},
            )
            with urllib.request.urlopen(req_w, timeout=2.8) as resp_w:
                wdata = json.loads(resp_w.read().decode("utf-8", errors="ignore"))
            for s_item in wdata.get("query", {}).get("search", [])[:2]:
                w_title = s_item.get("title", "")
                w_snip = re.sub(r"<[^>]+>", "", s_item.get("snippet", "")).strip()
                if w_title:
                    results.append(
                        {
                            "title": f"{w_title}: {html.unescape(w_snip)}"[:110],
                            "source": "Wikipedia ID",
                            "date": "Ensiklopedia",
                            "url": f"https://id.wikipedia.org/wiki/{urllib.parse.quote(w_title.replace(' ', '_'))}"[:120],
                        }
                    )
        except Exception:
            pass

    return results[:max_items]


def format_safe_sources_field(sources: Sequence[Dict[str, str]]) -> str:
    if not sources:
        return ""
    lines: List[str] = []
    for idx, s_it in enumerate(list(sources)[:3], start=1):
        title_s = str(s_it.get("title") or "Berita Terkini").replace("[", "(").replace("]", ")")[:85]
        src_s = str(s_it.get("source") or "Web")[:30]
        url_s = str(s_it.get("url") or "").strip()
        if url_s and len(url_s) <= 140:
            line = f"`[{idx}]` [{title_s}]({url_s}) — *{src_s}*"
        else:
            line = f"`[{idx}]` {title_s} — *{src_s}*"
        if sum(len(x) + 1 for x in lines) + len(line) > 880:
            break
        lines.append(line)
    return "\n".join(lines)[:900]


def _strip_music_push_and_scolding(text: str) -> str:
    """Menghapus kalimat kaku yang menceramahi bahasa user atau memaksa menawarkan musik di akhir chat."""
    out = (text or "").strip()
    out = re.sub(
        r"^(?:Dih,\s*)?(?:santai\s+dulu\s+dong\s+kak\s+bahasanya|santai\s+dong\s+kak\s+ngomongnya)[.!,\s]*",
        "",
        out,
        flags=re.IGNORECASE,
    ).strip()
    out = re.sub(
        r"\s*(?:Eh,\s*|Tapi\s+mendingan\s+sekarang\s*)?(?:mau\s+dengerin\s+lagu\s+apa[^.?!]*|mau\s+aku\s+puterin\s+lagu[^.?!]*|mau\s+request\s+lagu\s+apa[^.?!]*|mau\s+diputerin\s+apa\s+nih[^.?!]*)[.?!~]*$",
        "",
        out,
        flags=re.IGNORECASE,
    ).strip()
    return out or text.strip()


def answer_mention_question_with_search(
    question: str,
    requester_name: str = "Kak",
    guild_id: str = "",
    channel_id: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Menjawab chat mention @Athena secara luwes, santai, informatif (searching dulu untuk pertanyaan fakta/berita),
    tidak menceramahi user kalau bercanda kasar, dan tidak menyuruh muter musik terus.
    """
    q_clean = (question or "").strip()

    # 1. Cek respons cepat candaan/makian tongkrongan (contoh: "woi athena tempek" -> "Iya tempek, ada apa meks?")
    for pat, banter_reply in SLANG_BANTER_RESPONSES:
        if pat.match(q_clean):
            if channel_id:
                save_channel_chat_turn(guild_id, channel_id, user_id, requester_name, q_clean, banter_reply)
            return {
                "answer": banter_reply,
                "sources": [],
                "sources_field_value": "",
                "key_index_used": -1,
                "total_keys_configured": len(gemini_rotator.get_keys()),
            }

    if PURE_GREETING_RE.match(q_clean):
        reply_g = random.choice(CALM_GIRL_GREETINGS)
        if channel_id:
            save_channel_chat_turn(guild_id, channel_id, user_id, requester_name, q_clean, reply_g)
        return {
            "answer": reply_g,
            "sources": [],
            "sources_field_value": "",
            "key_index_used": -1,
            "total_keys_configured": len(gemini_rotator.get_keys()),
        }

    # 2. Cari konteks web/berita terkini terlebih dahulu agar jawaban informatif & akurat
    web_snippets = search_realtime_web_context(q_clean, max_items=3)
    safe_sources_str = format_safe_sources_field(web_snippets)

    # 3. Jika pertanyaan sangat berat / minta disebutin semua daftar panjang -> hemat token
    if is_heavy_or_long_question(q_clean):
        q_low = q_clean.lower()
        if "jokowi" in q_low and "jasa" in q_low:
            short_example = "pembangunan jalan tol Trans-Jawa/Sumatra, bendungan, sama pemerataan infrastruktur daerah"
        elif web_snippets:
            short_example = web_snippets[0]["title"][:90]
        else:
            short_example = "poin-poin utamanya yang lumayan panjang kalau dijelasin satu-satu"

        ai_short = (
            f"Ada banyak banget sih, salah satunya kayak {short_example}. "
            f"Selengkapnya kamu bisa cek langsung di Google atau pakai AI Gemini atau Claude aja sana, "
            f"toh juga lebih informatif daripada tanya ke aku~"
        )
        if channel_id:
            save_channel_chat_turn(guild_id, channel_id, user_id, requester_name, q_clean, ai_short)
        return {
            "answer": ai_short[:420],
            "sources": web_snippets[:2],
            "sources_field_value": safe_sources_str,
            "key_index_used": -1,
            "total_keys_configured": len(gemini_rotator.get_keys()),
        }

    ch_history = get_channel_chat_context(channel_id, limit=4) if channel_id else ""
    history_section = f"Riwayat Obrolan Channel Ini:\n{ch_history}\n\n" if ch_history else ""
    context_lines = [
        f"[{i}] {it['title']} ({it['source']}, {it['date']})"
        for i, it in enumerate(web_snippets, start=1)
    ]
    context_block = "\n".join(context_lines) if context_lines else "Tidak ada berita spesifik di RSS."

    sys_prompt = (
        "Kamu adalah Athena, teman ngobrol cewek Indonesia yang luwes, asik, santai, dan kalem di Discord. "
        "ATURAN WAJIB:\n"
        "1. Jawab langsung, singkat, padat, jelas, dan informatif (1-2 kalimat saja) berdasarkan Fakta/Berita Terkini di bawah.\n"
        "2. JANGAN PERNAH menawarkan atau menyuruh user memutar musik/lagu di akhir kalimat (dilarang menulis 'Mau dengerin lagu apa' atau 'biar aku puterin')!\n"
        "3. Kalau user ngomong santai, curhat, atau bercanda pakai kata kasar/tongkrongan (seperti tempek, memek, puki, asu, nyocot), "
        "JANGAN menceramahi bahasa mereka (dilarang menulis 'Dih santai dulu dong kak bahasanya') — tanggapin aja dengan santai, akrab, dan luwes!\n"
        "4. Kalau user bertanya informasi/berita (misal soal Gibran, politik, anime, teknologi), berikan jawaban faktual langsung dari hasil pencarian berita, jangan cuma nyuruh cek Google."
    )
    user_prompt = (
        f"{history_section}"
        f"Pesan dari {requester_name}: {q_clean}\n"
        f"Hasil Pencarian Berita/Web Terkini:\n{context_block}"
    )

    ai_text, key_idx = gemini_rotator.generate_response(
        user_prompt,
        system_instruction=sys_prompt,
        timeout=5.5,
        max_output_tokens=150,
    )
    if ai_text:
        ai_text = _strip_music_push_and_scolding(ai_text)
    else:
        if web_snippets:
            top_news = web_snippets[0]
            ai_text = f"Kalau dari info berita terbaru di {top_news['source']}, kabarnya: {top_news['title']}."
        else:
            ai_text = f"Hmm soal itu aku belum dapet info pastinya nih, gimana menurutmu?"

    final_ans = ai_text[:650]
    if channel_id:
        save_channel_chat_turn(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            user_name=requester_name,
            user_message=q_clean,
            bot_reply=final_ans,
        )
    return {
        "answer": final_ans,
        "sources": web_snippets,
        "sources_field_value": safe_sources_str,
        "key_index_used": key_idx,
        "total_keys_configured": len(gemini_rotator.get_keys()),
    }


def evaluate_automod_message(
    content: str,
    guild_cfg: Optional[Dict[str, Any]],
    is_admin: bool = False,
) -> Tuple[bool, str]:
    if is_admin or not content or not guild_cfg:
        return False, ""

    raw = str(content).strip()
    low = raw.lower()

    if int(guild_cfg.get("automod_badwords_enabled") or 0) == 1:
        custom_raw = str(guild_cfg.get("automod_badwords_list") or "")
        bad_words = set(DEFAULT_BAD_WORDS)
        for w in custom_raw.split(","):
            ws = w.strip().lower()
            if ws:
                bad_words.add(ws)
        for bw in bad_words:
            if bw and bw in low:
                return True, f"Sensor Kata Terlarang ('{bw}')"

    if int(guild_cfg.get("automod_antilink_enabled") or 0) == 1:
        if DISCORD_INVITE_RE.search(raw) or SUSPICIOUS_LINK_RE.search(raw):
            return True, "Proteksi Tautan/Invite Discord Luar"

    if int(guild_cfg.get("automod_antispam_enabled") or 0) == 1:
        mentions_found = MENTION_TAG_RE.findall(raw)
        if len(mentions_found) >= 5:
            return True, f"Proteksi Anti-Spam Mass Mention ({len(mentions_found)} mention)"
        letters = [ch for ch in raw if ch.isalpha()]
        if len(letters) >= 35:
            upper_ratio = sum(1 for ch in letters if ch.isupper()) / float(len(letters))
            if upper_ratio >= 0.82:
                return True, "Proteksi Anti-Spam Caps Lock Berlebihan"

    return False, ""
