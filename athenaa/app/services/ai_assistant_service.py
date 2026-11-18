"""
Layanan AI Assistant, Multi-Key Gemini Rotator (Model-First), Typo Fixer Lokal,
Wait-State Database (Top 5 Lagu Viral & Klarifikasi Ambigu), serta Multi-Action Queue Planner.
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

TYPO_CORRECTION_MAP: Dict[str, str] = {
    "puterim": "puterin",
    "ptuerin": "puterin",
    "putrin": "puterin",
    "putrkan": "putarkan",
    "puterkan": "putarkan",
    "putakan": "putarkan",
    "putakn": "putarkan",
    "setelim": "setelin",
    "stelin": "setelin",
    "stelkan": "setelkan",
    "nyetelim": "nyetelin",
    "quueue": "queue",
    "qeuue": "queue",
    "qeueu": "queue",
    "queu": "queue",
    "antrina": "antrean",
    "antiran": "antrean",
    "antreannya": "antrean",
    "babsboost": "bassboost",
    "basbost": "bassboost",
    "bassbost": "bassboost",
    "nigthcore": "nightcore",
    "nighcore": "nightcore",
    "vaporwav": "vaporwave",
    "skpi": "skip",
    "sikp": "skip",
    "voulme": "volume",
    "vloume": "volume",
    "volum": "volume",
    "tugass": "tugas",
    "tgas": "tugas",
    "tugs": "tugas",
    "lirk": "lirik",
    "lyrcs": "lyrics",
    "autplay": "autoplay",
    "autopliy": "autoplay",
    "shufle": "shuffle",
    "shuflle": "shuffle",
    "puse": "pause",
    "pasue": "pause",
    "resum": "resume",
}

KNOWN_ARTIST_TOKENS = {
    "hindia", "for revenge", "forrevenge", "mahalini", "bernadya", "tulus", "lyodra",
    "sheila on 7", "so7", "dewa 19", "dewa19", "payung teduh", "juicy luicy",
    "nadhif basalamah", "raim laode", "last child", "nidji", "noah", "peterpan",
    "virzha", "pamungkas", "tiara andini", "ziva magnolya", "sal priadi", "feby putri",
    "fourtwnty", "fiersa besari", "reality club", "armada", "ungu", "wali", "kotak",
    "geisha", "rossa", "raisa", "isyana", "rizky febian", "budi doremi", "andmesh",
    "denny caknan", "ndx", "guyon waton", "aftershine", "vierratale", "vierra",
    "lady gaga", "bruno mars", "the weeknd", "taylor swift", "coldplay", "ariana grande",
    "justin bieber", "billie eilish", "ed sheeran", "adele", "eminem", "drake",
    "post malone", "maroon 5", "imagine dragons", "linkin park", "queen", "oasis",
    "radiohead", "arctic monkeys", "the 1975", "lauv", "keshi", "niki", "rich brian",
    "joji", "newjeans", "blackpink", "bts", "twice", "seventeen", "aespa", "ive",
    "yoasobi", "kenshi yonezu", "fujii kaze", "radwimps", "one ok rock", "lisa",
    "britney spears", "adela", "akon", "rihanna", "katy perry", "shawn mendes",
    "charlie puth", "sam smith", "dua lipa", "olivia rodrigo", "sabrina carpenter",
}


def fix_common_command_typos(text: str) -> str:
    """Memperbaiki salah ketik (typo) kata kerja perintah umum tanpa mengubah URL atau isi tanda kutip."""
    if not text:
        return ""
    tokens = text.split(" ")
    fixed: List[str] = []
    for tok in tokens:
        if tok.startswith(("http://", "https://", "<@", "@")):
            fixed.append(tok)
            continue
        m_word = re.match(r"^([^A-Za-z0-9]*)([A-Za-z0-9_]+)([^A-Za-z0-9]*)$", tok)
        if not m_word:
            fixed.append(tok)
            continue
        prefix, core, suffix = m_word.group(1), m_word.group(2), m_word.group(3)
        replacement = TYPO_CORRECTION_MAP.get(core.lower())
        if replacement:
            fixed.append(f"{prefix}{replacement}{suffix}")
        else:
            fixed.append(tok)
    return " ".join(fixed)


RETRY_MUSIC_COMPLAINT_RE = re.compile(
    r"(?:\b(?:mana|kok|knp|kenapa)\b.*\b(?:gak|ga|nggak|enggak|gk|belum|blm)\b.*\b(?:ke\s*play|ke\s*putar|ke\s*puter|diputar|diputer|play|putar|puter|bunyi|nyala|jalan|masuk)\b)"
    r"|(?:\b(?:puterin|putarkan|setelin|setelkan|play|putar|muter)\s+(?:lagu\s+|musik\s+)?(?:yang\s+|yg\s+)?(?:tadi|barusan|di\s*atas)\b)"
    r"|^(?:tolong\s+|coba\s+)?(?:puterin|putarkan|setelin|setelkan|play|putar|muterin)(?:\s+lagu|\s+musik)?(?:\s+dong|\s+ya|\s+yaa|\s+nih|\s+lah|\s+yuk)*[!.?~]*$",
    re.IGNORECASE,
)

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
    r"tolong|coba|permisi|punten|boleh|maksudku|maksudnya|jadi)[\s,!.:;~\-]+",
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

AMBIGUOUS_REQUEST_RE = re.compile(
    r"^(?:tolong\s+|coba\s+)?(?:ganti|ubah|atur|set|hapus|buang|matikan|nyalakan|itu|ini)(?:\s+itu|\s+ini|\s+nya|\s+dong|\s+ya|\s+deh|\s+bos)*[!.?~]*$",
    re.IGNORECASE,
)

CALM_GIRL_GREETINGS = [
    "Halo juga~ Lagi santai aja nih, ada apa?",
    "Haii, iya aku di sini kok~ Kenapa nih?",
    "Halo~ Lagi standby aja nih, mau ngobrol atau ada perlu apa?",
]

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
    """
    Rotator API Key dengan strategi Model-First Across All Keys:
    Menghabiskan kuota model utama (gemini-3.5-flash-lite) di seluruh API Key (Key #1 -> Key #N)
    terlebih dahulu sebelum beralih ke model cadangan berikutnya.
    """

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
        primary = (
            os.environ.get("AI_AUTOPLAY_MODEL", getattr(settings, "ai_autoplay_model", "gemini-3.5-flash-lite")).strip()
            or "gemini-3.5-flash-lite"
        )
        fb_raw = os.environ.get(
            "AI_AUTOPLAY_FALLBACK_MODELS",
            getattr(
                settings,
                "ai_autoplay_fallback_models",
                "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-2.5-flash,gemini-3.8-flash",
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

        req_body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.55, "maxOutputTokens": max_output_tokens},
        }
        if system_instruction:
            req_body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        payload = json.dumps(req_body).encode("utf-8")

        for model_name in models[:5]:
            ordered_indices: List[int] = []
            for offset in range(len(keys)):
                idx = (self._current_idx + offset) % len(keys)
                k = keys[idx]
                if self._cooldown_until.get(f"{k}::{model_name}", 0.0) <= now and self._cooldown_until.get(k, 0.0) <= now:
                    ordered_indices.append(idx)
            if not ordered_indices:
                ordered_indices = list(range(len(keys)))

            for key_idx in ordered_indices:
                api_key = keys[key_idx]
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
                        self._cooldown_until[f"{api_key}::{model_name}"] = time.monotonic() + self.cooldown_sec
                        if http_err.code in (401, 403):
                            self._cooldown_until[api_key] = time.monotonic() + self.cooldown_sec
                        logger.warning(
                            "Gemini API Key #%d terkena limit/error HTTP %d pada model %s, beralih ke API Key berikutnya...",
                            key_idx + 1,
                            http_err.code,
                            model_name,
                        )
                        continue
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


def is_title_only_song_query(song_query: str) -> bool:
    """
    Mendeteksi apakah permintaan lagu hanya menyebutkan judul pendek (1-2 kata) tanpa nama penyanyi
    sehingga bot dapat menawarkan Top 5 lagu terpopuler/viral untuk dipilih user.
    """
    q = (song_query or "").strip()
    if not q or q.startswith(("http://", "https://")):
        return False
    low = q.lower()
    if any(sep in low for sep in (" - ", " – ", " by ", " dari ", " oleh ", " feat", " ft.")):
        return False
    for art in KNOWN_ARTIST_TOKENS:
        if re.search(rf"\b{re.escape(art)}\b", low):
            return False
    words = [w for w in re.split(r"\s+", low) if w]
    return 1 <= len(words) <= 2


def is_ambiguous_mention_request(content: str, bot_id: str) -> bool:
    """Mendeteksi apakah perintah user masih gantung/ambigu sehingga perlu ditanyakan dulu."""
    bid = str(bot_id or "").strip()
    cleaned = re.sub(rf"<@!?{re.escape(bid)}>", " ", str(content or "")).strip()
    cleaned = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", cleaned, flags=re.IGNORECASE).strip()
    cleaned = fix_common_command_typos(cleaned)
    for _ in range(3):
        nxt = LEADING_GREETING_RE.sub("", cleaned).strip()
        if nxt == cleaned:
            break
        cleaned = nxt
    return bool(AMBIGUOUS_REQUEST_RE.match(cleaned))


def _clean_extracted_song_query(raw_song: str) -> str:
    s = (raw_song or "").strip()
    for _ in range(4):
        nxt = TRAILING_SLANG_AND_FILLER_RE.sub("", s).strip(" \"'?!.,~-")
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"^(?:saya|aku|gua|gw|kami|kita)\s+(?:musik|lagu)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"^(?:dari\s+mashup|mashup\s+dari)\s+", "mashup ", s, flags=re.IGNORECASE).strip()

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


MUSIC_OR_PLAYLIST_URL_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?[^\s]+|playlist\?[^\s]+|shorts/[^\s]+)|youtu\.be/[^\s]+|open\.spotify\.com/(?:track|playlist|album)/[^\s]+)",
    re.IGNORECASE,
)


def extract_multi_song_queries(raw_song: str) -> List[str]:
    txt = str(raw_song or "").strip()
    if not txt:
        return []

    txt = re.sub(
        r"^(?:\d+\s+)?(?:lagu|musik|song|track)\s+(?:ini|berikut|di\s+bawah|dibawah)?\s*[:\-]*\s*",
        "",
        txt,
        flags=re.IGNORECASE,
    ).strip()

    urls = MUSIC_OR_PLAYLIST_URL_RE.findall(txt)
    if len(urls) >= 2:
        return [u.strip(" <>.,)") for u in urls if u.strip()]

    numbered_parts = re.split(r"(?:^|\s+)\d+[.)]\s+", txt)
    numbered_items = [p.strip() for p in numbered_parts if p.strip()]
    if len(numbered_items) >= 2:
        cleaned_list = []
        for item in numbered_items:
            c = _clean_extracted_song_query(item)
            if c:
                cleaned_list.append(c)
        if len(cleaned_list) >= 2:
            return cleaned_list[:15]

    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    if len(lines) >= 2:
        cleaned_lines = []
        for ln in lines:
            ln_clean = re.sub(r"^(?:[-*•]+|\d+[.)])\s*", "", ln).strip()
            c = _clean_extracted_song_query(ln_clean)
            if c:
                cleaned_lines.append(c)
        if len(cleaned_lines) >= 2:
            return cleaned_lines[:15]

    natural_parts = re.split(
        r"\s+(?:dan|sama|lalu|terus|trus|serta|kemudian|plus)\s+(?=(?:lagu|musik|song|track|puterin|putarkan|putar|setelin|setelkan|setel|mainkan|nyalain)\b)"
        r"|\s*,\s*(?:(?:dan|sama|serta)\s+)?",
        txt,
        flags=re.IGNORECASE,
    )
    if len(natural_parts) >= 2:
        cleaned_nat: List[str] = []
        for np_item in natural_parts:
            sub_parts = (
                re.split(r"\s+(?:sama|dan|serta)\s+", np_item.strip(), flags=re.IGNORECASE)
                if len(natural_parts) >= 2 and "," in txt
                else [np_item]
            )
            for sp in sub_parts:
                np_clean = re.sub(
                    r"^(?:puterin|putarkan|putar|setelin|setelkan|setel|mainkan|nyalain)\s+",
                    "",
                    sp.strip(),
                    flags=re.IGNORECASE,
                ).strip()
                np_clean = re.sub(r"^(?:musik|lagu|song|track)\s+", "", np_clean, flags=re.IGNORECASE).strip()
                c = _clean_extracted_song_query(np_clean)
                if c:
                    cleaned_nat.append(c)
        if len(cleaned_nat) >= 2:
            return cleaned_nat[:15]

    single = _clean_extracted_song_query(txt)
    return [single] if single else []


def classify_mention_intent(content: str, bot_id: str) -> Tuple[str, str]:
    bid = str(bot_id or "").strip()
    raw_lines = []
    for raw_ln in str(content or "").splitlines():
        ln = re.sub(rf"<@!?{re.escape(bid)}>", " ", raw_ln)
        ln = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", ln, flags=re.IGNORECASE)
        ln = fix_common_command_typos(re.sub(r"[ \t]+", " ", ln).strip())
        if ln:
            raw_lines.append(ln)
    cleaned_multiline = "\n".join(raw_lines).strip()
    cleaned = re.sub(r"\s+", " ", cleaned_multiline).strip()

    if not cleaned or PURE_GREETING_RE.match(cleaned):
        return "greeting", cleaned or "halo"

    for pat, _ in SLANG_BANTER_RESPONSES:
        if pat.match(cleaned):
            return "chat_search", cleaned

    if RETRY_MUSIC_COMPLAINT_RE.search(cleaned):
        return "retry_last_music", ""

    stripped_multiline = cleaned_multiline
    for _ in range(4):
        nxt = LEADING_GREETING_RE.sub("", stripped_multiline).strip()
        if nxt == stripped_multiline:
            break
        stripped_multiline = nxt

    stripped_cmd = re.sub(r"\s+", " ", stripped_multiline).strip()
    low = TRAILING_SLANG_AND_FILLER_RE.sub("", stripped_cmd).lower().strip(" ?!.,")

    if not low or PURE_GREETING_RE.match(low):
        if any(w in cleaned.lower() for w in ("tempek", "memek", "puki", "pukimak", "kontol", "asu", "nyocot")):
            return "chat_search", cleaned
        return "greeting", low or "halo"

    if AMBIGUOUS_REQUEST_RE.match(low):
        return "ambiguous_clarify", stripped_cmd

    found_urls = [u.strip(" <>.,)") for u in MUSIC_OR_PLAYLIST_URL_RE.findall(cleaned_multiline)]
    if found_urls:
        if len(found_urls) >= 2:
            return "play_music_multi", json.dumps(found_urls[:15], ensure_ascii=False)
        return "play_music", found_urls[0]

    if low in ("help", "/help", "!help", "bantuan", "menu", "command", "commands", "daftar command", "fitur") or re.search(
        r"\b(?:buka\s+help|lihat\s+command|apa\s+aja\s+command|bantuan\s+dong|fitur\s+apa\s+aja)\b", low
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

    if (
        low in ("queue", "/queue", "antrean", "antrian", "daftar lagu", "cek antrean", "lihat antrean")
        or re.search(r"\b(?:queue|antrean|antrian)\b", low)
        and re.search(r"\b(?:apa|buka|lihat|liat|cek|tampilkan|tunjukin|daftar|isi|list|ada|dong|nya)\b", low)
        and not re.search(r"\b(?:hapus|bersihkan|clear|acak|shuffle|tambahin|masukin)\b", low)
    ) or re.search(r"\b(?:lagu\s+berikutnya|next\s+song)\s+apa\b", low):
        return "cmd_queue", ""

    if low in ("nowplaying", "/nowplaying", "np", "sedang diputar") or re.search(
        r"\b(?:lagi\s+(?:muter|putar|setel|main)|sekarang\s+lagu|judul\s+lagu\s+(?:ini|sekarang)|lagu\s+apa\s+(?:ini|nih|sekarang))\b",
        low,
    ):
        return "cmd_nowplaying", ""

    if low in ("history", "/history", "riwayat lagu", "lagu terakhir") or re.search(
        r"\b(?:riwayat\s+lagu|history\s*(?:nya|lagu)?|tadi\s+muter\s+apa)\b", low
    ):
        return "cmd_history", ""

    m_skipto = re.search(
        r"\b(?:skipto|lompat\s+ke\s+(?:lagu\s+)?(?:nomor\s+|no\.?\s*)?|langsung\s+ke\s+(?:lagu\s+)?(?:nomor\s+|no\.?\s*)?)(\d+)\b",
        low,
    )
    if m_skipto:
        return "cmd_skipto", m_skipto.group(1)

    m_rem = re.search(r"\b(?:remove|hapus\s+lagu|buang\s+lagu)\s+(?:nomor\s+|no\.?\s*|ke\s*)?(\d+)\b", low)
    if m_rem:
        return "cmd_remove", m_rem.group(1)

    m_skip_n = re.match(r"^(?:tolong\s+)?(?:skip|lewati)\s+(\d+)\s*(?:lagu|musik)?$", low)
    if m_skip_n:
        return "cmd_skip", m_skip_n.group(1)
    if low in (
        "skip", "/skip", "next", "lewati", "ganti lagu", "ganti lagunya", "skip lagu",
        "skip aja", "skip aja deh", "skip lagu ini", "skip musik ini", "lewati lagu ini",
    ) or re.search(
        r"^(?:tolong\s+)?(?:skip|lewati|next|ganti)(?:\s+lagu|\s+lagunya|\s+musik|\s+ini|\s+itu|\s+aja|\s+deh|\s+dong)*$",
        low,
    ):
        return "cmd_skip", "1"

    if low in ("pause", "/pause", "jeda", "pause lagu", "jeda musik", "pause dulu") or re.search(
        r"^(?:tolong\s+)?(?:pause|jeda)(?:\s+lagu|\s+musik|\s+dulu)*$", low
    ):
        return "cmd_pause", ""
    if low in ("resume", "/resume", "lanjut", "lanjutkan", "lanjutkan musik", "unpause", "play lagi") or re.search(
        r"^(?:tolong\s+)?(?:resume|lanjut|lanjutin|lanjutkan)(?:\s+lagu|\s+musik)*$", low
    ):
        return "cmd_resume", ""
    if low in ("stop", "/stop", "berhenti", "matikan musik", "stop musik", "stop lagu", "stop aja") or re.search(
        r"^(?:tolong\s+)?(?:stop|matikan|berhenti)(?:\s+lagu|\s+musik|\s+aja)*$", low
    ):
        return "cmd_stop", ""
    if low in ("leave", "/leave", "disconnect", "keluar voice", "keluar vc", "cabut", "keluar") or re.search(
        r"\b(?:keluar\s+(?:dari\s+)?(?:voice|vc)|disconnect)\b", low
    ):
        return "cmd_leave", ""
    if low in ("shuffle", "/shuffle", "acak", "acak lagu", "acak antrean") or re.search(
        r"\b(?:acak|shuffle)\s+(?:antrean|antrian|lagu|queue)\b", low
    ):
        return "cmd_shuffle", ""
    if low in ("replay", "/replay", "ulang lagu", "putar ulang", "ulangi lagu"):
        return "cmd_replay", ""
    if low in ("previous", "/previous", "lagu sebelumnya", "back lagu") or re.search(
        r"\b(?:balik\s+ke\s+lagu\s+sebelumnya|putar\s+lagu\s+tadi)\b", low
    ):
        return "cmd_previous", ""
    if low in ("clear", "/clear", "bersihkan antrean", "hapus antrean", "clear queue") or re.search(
        r"\b(?:bersihkan|hapus|kosongkan)\s+(?:antrean|antrian|queue)\b", low
    ):
        return "cmd_clear", ""
    if low in ("grab", "/grab", "simpan lagu", "kirim lagu ke dm") or re.search(
        r"\b(?:kirim|simpan)\s+(?:lagu\s+ini\s+)?ke\s+dm\b", low
    ):
        return "cmd_grab", ""

    if re.search(r"\b(?:volume|vol)\s*(?:nya|sekarang)?\s*berapa\b", low):
        return "cmd_volume_info", ""
    if re.search(r"\b(?:besarin|naikin|kerasin|tambah)\s+(?:volume|vol|suara)\b", low):
        return "cmd_volume", "+15"
    if re.search(r"\b(?:kecilin|turunin|pelanin|kurangi)\s+(?:volume|vol|suara)\b", low):
        return "cmd_volume", "-15"
    m_vol = re.search(r"\b(?:volume|vol|suara)(?:\s+ke|\s+jadi)?\s+(\d{1,3})%?\b", low)
    if m_vol:
        return "cmd_volume", m_vol.group(1)

    m_loop = re.search(r"\b(?:loop|ulang)\s+(off|one|queue|mati|satu|antrean)\b", low)
    if m_loop:
        lval = m_loop.group(1)
        lmap = {"mati": "off", "satu": "one", "antrean": "queue"}
        return "cmd_loop", lmap.get(lval, lval)

    m_seek = re.search(r"\b(?:seek|lompat\s+ke\s+(?:detik|menit)?)\s+([0-9:]+)\b", low)
    if m_seek:
        return "cmd_seek", m_seek.group(1)

    m_sleep = re.search(r"\b(?:sleeptimer|timer\s+tidur|matikan\s+musik)\s+(\d+)\s*(?:menit)?\b", low)
    if m_sleep:
        return "cmd_sleeptimer", m_sleep.group(1)

    m_radio = re.search(r"\b(?:putar|puterin|setel|nyalain|dengerin)?\s*radio\s+(.+)$", low)
    if m_radio:
        return "cmd_radio", m_radio.group(1).strip()

    for amb_k in ("rain", "cafe", "lofi", "night_coding", "piano"):
        if low in (f"ambience {amb_k}", f"/ambience {amb_k}", f"suasana {amb_k}"):
            return "cmd_ambience", amb_k

    if re.search(r"\b(?:normalin\s+(?:suara|suaranya|audio)|matikan\s+(?:efek|filter)|reset\s+filter)\b", low):
        return "cmd_filter", "normal"
    for f_preset in ("bassboost", "nightcore", "vaporwave", "8d", "lofi", "karaoke", "treble", "normal"):
        if f"filter {f_preset}" in low or f"efek {f_preset}" in low or f"efek suara {f_preset}" in low or low == f_preset:
            return "cmd_filter", f_preset

    if any(k in low for k in ("reset memory", "hapus memory", "clear memory", "lupakan obrolan", "hapus ingatan")):
        return "cmd_clear_memory", ""

    if low in ("tugas", "/tugas", "cek tugas", "lihat tugas", "daftar tugas", "tugas kuliah") or re.search(
        r"\b(?:tugas|deadline|pr)\b.*\b(?:apa|ada|cek|lihat|liat|daftar|hari\s+ini)\b|\b(?:cek|lihat|liat|daftar|ada)\s+(?:tugas|pr)\b",
        low,
    ):
        return "cmd_tugas", ""
    if low in ("sync waskita", "/sync_waskita", "sinkron waskita") or "sync waskita" in low or "sinkron waskita" in low:
        return  ""
    if low in ("level", "/level", "cek level", "rank", "exp") or re.search(
        r"\b(?:level|rank|exp)\s*(?:ku|saya|aku)?\s*(?:berapa|cek)?\b", low
    ):
        return "cmd_level", ""
    if low in ("leaderboard", "/leaderboard", "top server", "peringkat") or "leaderboard" in low:
        return "cmd_leaderboard", ""
    if low.startswith("afk ") or low in ("afk", "/afk"):
        reason_afk = stripped_cmd[3:].strip() if len(stripped_cmd) > 3 else "Sedang AFK"
        return "cmd_afk", reason_afk or "Sedang AFK"
    if low in ("stats", "/stats", "status bot", "ping", "cek ram") or re.search(
        r"\b(?:ping|ram|status\s+bot)\s*(?:nya)?\s*(?:berapa|gimana)?\b", low
    ):
        return "cmd_stats", ""
    if low in ("ram clean", "/ram_clean", "bersihkan ram", "optimasi ram") or re.search(
        r"\b(?:bersihkan|bersihin|clean|optimasi)\s+ram\b", low
    ):
        return  ""
    if low in ("kuis", "/kuis", "main kuis"):
        return "cmd_kuis", ""
    if low in ("mathbattle", "/mathbattle", "hitung cepat"):
        return "cmd_mathbattle", ""
    if low.startswith("dadu") or low.startswith("/dadu") or "lempar dadu" in low:
        return "cmd_dadu", "6"
    if low.startswith("suit "):
        return "cmd_suit", low.split()[-1]
    if low.startswith("lyrics") or low.startswith("lirik") or re.search(r"\blirik\s+lagu\s+(?:ini|sekarang)\b", low):
        lq = re.sub(
            r"^(?:lyrics|lirik)(?:\s+lagu\s+(?:ini|sekarang)(?:\s+apa)?)?\s*",
            "",
            stripped_cmd,
            flags=re.IGNORECASE,
        ).strip()
        if lq.lower() in ("apa", "nya apa", "lagu ini apa"):
            lq = ""
        return "cmd_lyrics", lq

    m_play = MUSIC_PLAY_INTENT_RE.search(stripped_multiline)
    if m_play:
        raw_payload = m_play.group(1).strip()
        multi_songs = extract_multi_song_queries(raw_payload)
        if len(multi_songs) >= 2:
            return "play_music_multi", json.dumps(multi_songs, ensure_ascii=False)
        song_candidate = multi_songs[0] if multi_songs else _clean_extracted_song_query(raw_payload)
        if song_candidate.lower() in ("nya", "itu", "ini", "lagunya", "musiknya", "lagu", "musik", "tadi", "yg tadi"):
            return "retry_last_music", ""
        if song_candidate and len(song_candidate) >= 1:
            return "play_music", song_candidate

    return "chat_search", cleaned


MULTI_ACTION_SPLIT_RE = re.compile(
    r"(?:\s+(?:lalu|terus|trus|kemudian|habis\s+itu|abis\s+itu|sekalian|dan|sama)\s+|\n+)"
    r"(?=(?:aktifkan|nyalakan|nyalain|matikan|nonaktifkan|set|atur|ganti|ubah|pake|pakai|"
    r"filter|efek|volume|vol|suara|autoplay|24/7|247|loop|normalin|"
    r"skip|skipto|pause|jeda|resume|lanjut|stop|leave|shuffle|acak|replay|previous|clear|remove|hapus|grab|queue|antrean|antrian|"
    r"cek|lihat|liat|buka|tampilkan|tunjukin|tugas|pr|level|rank|leaderboard|stats|ping|ram|bersihkan|bersihin|"
    r"lyrics|lirik|radio|ambience|sleeptimer|seek|dadu|kuis|mathbattle|suit|reset|puterin|putarkan|setelin)\b)",
    re.IGNORECASE,
)

ALLOWED_AI_ACTIONS = {
    "play_music",
    "cmd_help",
    "cmd_autoplay",
    "cmd_247",
    "cmd_queue",
    "cmd_nowplaying",
    "cmd_history",
    "cmd_skip",
    "cmd_skipto",
    "cmd_remove",
    "cmd_pause",
    "cmd_resume",
    "cmd_stop",
    "cmd_leave",
    "cmd_shuffle",
    "cmd_replay",
    "cmd_previous",
    "cmd_clear",
    "cmd_grab",
    "cmd_volume",
    "cmd_volume_info",
    "cmd_loop",
    "cmd_seek",
    "cmd_sleeptimer",
    "cmd_radio",
    "cmd_ambience",
    "cmd_filter",
    "cmd_clear_memory",
    "cmd_tugas",
    
    "cmd_level",
    "cmd_leaderboard",
    "cmd_afk",
    "cmd_stats",
    
    "cmd_kuis",
    "cmd_mathbattle",
    "cmd_dadu",
    "cmd_lyrics",
}


def parse_gemini_action_plan_json(raw_text: str) -> List[Tuple[str, str]]:
    txt = str(raw_text or "").strip()
    if not txt:
        return []
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.IGNORECASE | re.MULTILINE).strip()
    m_arr = re.search(r"\[.*\]", txt, flags=re.DOTALL)
    if not m_arr:
        return []
    try:
        arr = json.loads(m_arr.group(0))
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    result: List[Tuple[str, str]] = []
    for item in arr[:6]:
        if not isinstance(item, dict):
            continue
        act = str(item.get("action") or "").strip()
        arg = str(item.get("arg") or "").strip()
        if act in ALLOWED_AI_ACTIONS:
            result.append((act, arg))
    return result


def format_live_server_state_context(guild_id: str) -> str:
    """Menyusun ringkasan status server aktif (lagu, antrean, volume, tugas) untuk injeksi konteks AI."""
    gid = str(guild_id or "").strip()
    if not gid:
        return ""
    try:
        from app.services.queue_service import queue_service
        st = queue_service.get_state(gid)
        np_str = (
            f"{st.current_track.title} - {st.current_track.artist}"
            if st.current_track
            else "Tidak ada lagu"
        )
        q_preview = ", ".join(
            f"#{i} {t.title} - {t.artist}" for i, t in enumerate(st.queue[:5], 1)
        ) or "Kosong"
        return (
            f"Sedang Diputar: {np_str} | Antrean ({len(st.queue)}): {q_preview} | "
            f"Volume: {st.volume}% | Filter: {getattr(st, 'audio_filter', 'normal')} | Autoplay: {'ON' if st.autoplay else 'OFF'}"
        )
    except Exception:
        return ""


def plan_actions_with_gemini_if_needed(
    content: str,
    bot_id: str,
    guild_id: str = "",
    channel_id: str = "",
) -> Optional[List[Tuple[str, str]]]:
    if not collect_configured_gemini_keys():
        return None
    bid = str(bot_id or "").strip()
    cleaned = re.sub(rf"<@!?{re.escape(bid)}>", " ", str(content or "")).strip()
    cleaned = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", cleaned, flags=re.IGNORECASE).strip()
    cleaned = fix_common_command_typos(cleaned)
    if not cleaned:
        return None

    live_ctx = format_live_server_state_context(guild_id)
    mem_ctx = get_channel_chat_context(channel_id, limit=3) if channel_id else ""
    sys_inst = (
        "Kamu adalah Intent Translator untuk bot Discord Athenaa. "
        "Petakan permintaan user menjadi JSON array berurutan: "
        "[{\"action\": \"<nama_aksi>\", \"arg\": \"<argumen>\"}]. "
        "Daftar action valid: play_music (arg=judul/link), cmd_queue, cmd_nowplaying, cmd_history, "
        "cmd_skip (arg=jumlah), cmd_skipto (arg=nomor), cmd_remove (arg=nomor), cmd_pause, cmd_resume, "
        "cmd_stop, cmd_leave, cmd_shuffle, cmd_replay, cmd_previous, cmd_clear, cmd_grab, "
        "cmd_volume (arg=1-100 atau +15/-15), cmd_volume_info, cmd_loop (arg=off/one/queue), "
        "cmd_autoplay (arg=on/off), cmd_247 (arg=on/off), cmd_filter (arg=normal/bassboost/nightcore/vaporwave/8d/lofi/karaoke/treble), "
        "cmd_ambience (arg=rain/cafe/lofi/night_coding/piano), cmd_radio (arg=nama), cmd_lyrics (arg=judul), "
        "cmd_tugas, cmd_sync_waskita, cmd_level, cmd_leaderboard, cmd_stats, cmd_ram_clean, cmd_help. "
        "Jika user hanya mengobrol atau bertanya berita/umum, balas [] saja. Balas HANYA JSON array."
    )
    prompt_full = f"Status Server: {live_ctx}\nMemori: {mem_ctx}\nPesan User: {cleaned}".strip()
    raw_out, _ = gemini_rotator.generate_response(
        prompt=prompt_full,
        system_instruction=sys_inst,
        timeout=5.0,
        max_output_tokens=220,
    )
    parsed = parse_gemini_action_plan_json(raw_out)
    return parsed if parsed else None


def extract_mention_actions(content: str, bot_id: str) -> List[Tuple[str, str]]:
    bid = str(bot_id or "").strip()
    raw_lines = []
    for raw_ln in str(content or "").splitlines():
        ln = re.sub(rf"<@!?{re.escape(bid)}>", " ", raw_ln)
        ln = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", ln, flags=re.IGNORECASE)
        ln = fix_common_command_typos(re.sub(r"[ \t]+", " ", ln).strip())
        if ln:
            raw_lines.append(ln)
    cleaned_multiline = "\n".join(raw_lines).strip()

    clauses = [c.strip() for c in MULTI_ACTION_SPLIT_RE.split(cleaned_multiline) if c and c.strip()]
    if len(clauses) <= 1:
        return [classify_mention_intent(content, bot_id)]

    merged_clauses: List[str] = []
    for cl in clauses:
        it_type, _it_arg = classify_mention_intent(cl, bot_id)
        if merged_clauses and it_type == "chat_search" and re.match(r"^(?:\d+[.)]|[-*•])\s+", cl):
            merged_clauses[-1] = merged_clauses[-1] + "\n" + cl
        else:
            merged_clauses.append(cl)

    actions: List[Tuple[str, str]] = []
    for cl in merged_clauses:
        it_type, it_arg = classify_mention_intent(cl, bot_id)
        if it_type == "chat_search":
            return [classify_mention_intent(content, bot_id)]
        actions.append((it_type, it_arg))

    return actions or [classify_mention_intent(content, bot_id)]


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_pending_state (
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    pending_type TEXT NOT NULL,
                    original_message TEXT NOT NULL,
                    candidates_json TEXT NOT NULL DEFAULT '[]',
                    remaining_actions_json TEXT NOT NULL DEFAULT '[]',
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (channel_id, user_id)
                )
                """
            )
    except Exception:
        pass


def save_pending_channel_state(
    guild_id: str,
    channel_id: str,
    user_id: str,
    pending_type: str,
    original_message: str,
    candidates: Optional[Sequence[Dict[str, Any]]] = None,
    remaining_actions: Optional[Sequence[Tuple[str, str]]] = None,
    ttl_seconds: float = 300.0,
) -> None:
    """Menyimpan status tunggu (Top 5 pilihan lagu atau klarifikasi perintah ambigu) ke SQLite."""
    ch_id = str(channel_id or "").strip()
    u_id = str(user_id or "").strip()
    if not ch_id or not u_id:
        return
    _ensure_chat_memory_table()
    from app.database import db_manager

    exp = time.time() + float(ttl_seconds)
    cands_str = json.dumps(list(candidates or []), ensure_ascii=False)
    rem_str = json.dumps([list(x) for x in (remaining_actions or [])], ensure_ascii=False)
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_pending_state (
                    channel_id, user_id, guild_id, pending_type, original_message,
                    candidates_json, remaining_actions_json, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, user_id) DO UPDATE SET
                    guild_id = excluded.guild_id,
                    pending_type = excluded.pending_type,
                    original_message = excluded.original_message,
                    candidates_json = excluded.candidates_json,
                    remaining_actions_json = excluded.remaining_actions_json,
                    expires_at = excluded.expires_at
                """,
                (ch_id, u_id, str(guild_id or ""), pending_type, str(original_message or ""), cands_str, rem_str, exp),
            )
    except Exception:
        pass


def clear_pending_channel_state(channel_id: str, user_id: str) -> None:
    ch_id = str(channel_id or "").strip()
    u_id = str(user_id or "").strip()
    if not ch_id or not u_id:
        return
    _ensure_chat_memory_table()
    from app.database import db_manager
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                "DELETE FROM ai_pending_state WHERE channel_id = ? AND user_id = ?",
                (ch_id, u_id),
            )
    except Exception:
        pass


def resolve_pending_channel_state(
    channel_id: str,
    user_id: str,
    user_reply_text: str,
    bot_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Memeriksa apakah balasan user menjawab pertanyaan sebelumnya di ai_pending_state
    (baik pemilihan nomor/penyanyi dari Top 5 lagu viral maupun klarifikasi perintah ambigu).
    """
    ch_id = str(channel_id or "").strip()
    u_id = str(user_id or "").strip()
    if not ch_id or not u_id:
        return None
    _ensure_chat_memory_table()
    from app.database import db_manager

    try:
        with db_manager.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM ai_pending_state WHERE channel_id = ? AND user_id = ?",
                (ch_id, u_id),
            ).fetchone()
    except Exception:
        return None

    if not row:
        return None

    if float(row["expires_at"] or 0.0) < time.time():
        clear_pending_channel_state(ch_id, u_id)
        return None

    p_type = str(row["pending_type"] or "")
    cands: List[Dict[str, Any]] = json.loads(row["candidates_json"] or "[]")
    rem_raw: List[List[str]] = json.loads(row["remaining_actions_json"] or "[]")
    rem_actions: List[Tuple[str, str]] = [(str(x[0]), str(x[1])) for x in rem_raw if len(x) >= 2]

    clean_rep = re.sub(rf"<@!?{re.escape(str(bot_id))}>", " ", str(user_reply_text or "")).strip() if bot_id else str(user_reply_text or "").strip()
    clean_rep = re.sub(r"@athenaa(?:\.my\.id)?|@athena", " ", clean_rep, flags=re.IGNORECASE).strip()
    clean_rep = fix_common_command_typos(clean_rep)
    low_rep = clean_rep.lower()

    if any(b in low_rep for b in ("batal", "gak jadi", "ga jadi", "cancel", "skip aja")):
        clear_pending_channel_state(ch_id, u_id)
        return {"actions": [], "cancelled": True}

    if p_type == "song_choice_top5" and cands:
        picked_indices: List[int] = []
        for m_num in re.finditer(r"\b([1-5])\b", low_rep):
            idx_val = int(m_num.group(1)) - 1
            if 0 <= idx_val < len(cands) and idx_val not in picked_indices:
                picked_indices.append(idx_val)

        if not picked_indices:
            for idx_c, c_item in enumerate(cands):
                art_low = str(c_item.get("artist") or "").lower()
                if art_low and (art_low in low_rep or any(tok in low_rep for tok in art_low.split() if len(tok) >= 3)):
                    picked_indices.append(idx_c)
                    break

        if picked_indices:
            clear_pending_channel_state(ch_id, u_id)
            chosen_queries = [
                str(cands[i].get("query") or f"{cands[i].get('title', '')} {cands[i].get('artist', '')}").strip()
                for i in picked_indices
            ]
            if len(chosen_queries) == 1:
                play_act = [("play_music", chosen_queries[0])]
            else:
                play_act = [("play_music_multi", json.dumps(chosen_queries, ensure_ascii=False))]
            return {
                "actions": play_act + rem_actions,
                "chosen_candidates": [cands[i] for i in picked_indices],
            }

    if p_type == "clarify_intent":
        parsed_actions = extract_mention_actions(clean_rep, bot_id)
        if parsed_actions and parsed_actions[0][0] not in ("chat_search", "ambiguous_clarify", "greeting"):
            clear_pending_channel_state(ch_id, u_id)
            return {
                "actions": parsed_actions + rem_actions,
            }

    return None


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
            headers={"User-Agent": "Mozilla/5.0 (compatible; AthenaaBot/6.0)"},
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
                headers={"User-Agent": "AthenaaDiscordBot/6.0 (https://bot.athenaa.my.id)"},
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
            line = f"`[{idx}]` [{title_s}]({url_s}) ({src_s})"
        else:
            line = f"`[{idx}]` {title_s} ({src_s})"
        if sum(len(x) + 1 for x in lines) + len(line) > 880:
            break
        lines.append(line)
    return "\n".join(lines)[:900]


def _strip_music_push_and_scolding(text: str) -> str:
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
    q_clean = (question or "").strip()

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

    web_snippets = search_realtime_web_context(q_clean, max_items=3)
    safe_sources_str = format_safe_sources_field(web_snippets)

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
    live_state = format_live_server_state_context(guild_id)
    history_section = f"Riwayat Obrolan Channel Ini:\n{ch_history}\n" if ch_history else ""
    state_section = f"Status Server Saat Ini: {live_state}\n" if live_state else ""
    context_lines = [
        f"[{i}] {it['title']} ({it['source']}, {it['date']})"
        for i, it in enumerate(web_snippets, start=1)
    ]
    context_block = "\n".join(context_lines) if context_lines else "Tidak ada berita spesifik di RSS."

    sys_prompt = (
        "Kamu adalah Athena, teman ngobrol cewek Indonesia yang luwes, asik, santai, dan kalem di Discord. "
        "Aturan wajib:\n"
        "1. Jawab langsung, singkat, padat, jelas, dan informatif (1-2 kalimat saja) berdasarkan Fakta/Berita Terkini di bawah.\n"
        "2. Jangan pernah menawarkan atau menyuruh user memutar musik/lagu di akhir kalimat.\n"
        "3. Kalau user ngomong santai, curhat, atau bercanda pakai kata kasar/tongkrongan, jangan menceramahi bahasa mereka; tanggapi dengan santai dan luwes.\n"
        "4. Kalau user bertanya informasi/berita, berikan jawaban faktual langsung dari hasil pencarian berita."
    )
    user_prompt = (
        f"{state_section}{history_section}"
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
            ai_text = "Hmm soal itu aku belum dapet info pastinya nih, gimana menurutmu?"

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

    raw = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", str(content)).strip()
    low = raw.lower()

    if int(guild_cfg.get("automod_badwords_enabled") or 0) == 1:
        custom_raw = str(guild_cfg.get("automod_badwords_list") or "")
        bad_words = set(DEFAULT_BAD_WORDS)
        for w in custom_raw.split(","):
            ws = w.strip().lower()
            if ws:
                bad_words.add(ws)
        for bw in bad_words:
            if not bw:
                continue
            if " " in bw:
                if bw in low:
                    return True, f"Sensor Kata Terlarang ('{bw}')"
            elif re.search(rf"(?<!\w){re.escape(bw)}(?!\w)", low):
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


_AI_MENTION_COOLDOWN_MAP: Dict[str, float] = {}


def check_ai_mention_cooldown(user_id: str, cooldown_sec: float = 3.0) -> Tuple[bool, float]:
    """Cooldown ringan per user untuk mention @Athena agar kuota Gemini API tidak cepat habis."""
    uid = str(user_id or "").strip()
    if not uid:
        return True, 0.0
    now = time.monotonic()
    if len(_AI_MENTION_COOLDOWN_MAP) > 512:
        stale = [k for k, ts in list(_AI_MENTION_COOLDOWN_MAP.items()) if now - ts > 60.0]
        for k in stale:
            _AI_MENTION_COOLDOWN_MAP.pop(k, None)
    last_ts = _AI_MENTION_COOLDOWN_MAP.get(uid, 0.0)
    elapsed = now - last_ts
    if last_ts > 0.0 and elapsed < cooldown_sec:
        return False, round(cooldown_sec - elapsed, 1)
    _AI_MENTION_COOLDOWN_MAP[uid] = now
    return True, 0.0
