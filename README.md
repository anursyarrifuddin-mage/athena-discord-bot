<div align="center">
  <img width="1200" height="475" alt="Athenaa Banner" src="https://assets.athenaa.internal/banner.png" />
</div>

# Athenaa — Multi-Function Discord Bot & Web Dashboard

**Athenaa** adalah bot Discord multifungsi + dashboard web real-time yang dibangun untuk server **TK1GACORKINK** (dan dapat dikonfigurasi untuk server lain). Menggabungkan pemutaran musik, manajemen tugas akademik (Moodle/Waskita), sistem RPG leveling, dan super-admin hub dalam satu paket deployable single-instance.

> **Tech Stack**: Python 3.12 (FastAPI + discord.py + yt-dlp + FFmpeg) + Node.js/TypeScript (React 19 + Vite 8 + Tailwind 4 + WebSocket) + SQLite WAL

---

## ✨ Fitur Utama

### 🎵 Music System (Voice + Web Dashboard)
- **Pencarian Real-time**: YouTube (HTML scraping) + Spotify oEmbed metadata matching
- **Radio Internet Terverifikasi**: Prambors FM, Hard Rock FM, Gen FM, Lofi Girl 24/7
- **Queue Manager per-Guild**: Host Lock System (Owner/Admin/DJ/Session Host), Loop modes (off/one/queue), Autoplay genre-aware, Mode 24/7
- **LRCLIB Synced Lyrics**: Lirik real-time ber-timestamp (syncedLines) + plain lyrics fallback
- **Spotify Import**: Import playlist/album via link (open.spotify.com/playlist/... atau /album/...)
- **Favorites & Playlists**: Simpan lagu favorit, buat playlist dari antrean, putar playlist
- **WebSocket Live Sync**: Update posisi detik, state antrean, now-playing tanpa polling berat

### 📚 Academy & Modules (Waskita/Moodle)
- **Kalender .ics Parser**: Parsing iCal Moodle/Waskita dengan deduplikasi UID (hindari duplikat tugas)
- **Filter Cerdas**: Hanya tugas *submittable* (assign/quiz/workshop/turnitin) — exclude materi, presensi, modul, "activity opens"
- **3-Stage Reminders**: H-3 hari, H-6 jam, H-1 jam (otomatis via Discord channel)
- **Lampiran Modul**: Upload/download `.pdf`, `.doc`, `.docx` (max 15 MB, validasi magic bytes)
- **Sinkronisasi Manual & Otomatis**: Endpoint `/sync-ics` + kredensial Moodle di `.env`

### ⚔️ RPG Leveling & AFK
- **Formula EXP**: `max_exp = 100 + (level × 25)` — skala progresif
- **Aktivitas**: Chat (25 EXP), Voice join/speak/listen/stream (10–25 EXP), Minigame (20 EXP)
- **Anti-Spam Cooldown**: 60 detik per user per guild
- **Leaderboard Top 15**: Level, EXP, total pesan
- **AFK System**: Set reason, auto-clear saat chat, list AFK members

### 🛡️ Super-Admin Hub (Khusus Bot Owner)
- **Metrics Real-time**: RAM, Heap, CPU load, uptime, DB size, backup list
- **SQLite Backup**: Online backup (SQLite `backup()`), gzip compress, enkripsi AES-GCM terpisah
- **yt-dlp Manager**: Cek versi, update binary
- **Test Runner**: Jalankan `pytest` suite Python
- **Source Code Inspector**: Baca file Python (`app/main.py`, `app/services/*.py`, dll) di dashboard
- **One-Click ZIP Download**: Paket seluruh source code Python untuk deploy/migrasi

### 🔐 Autentikasi & Keamanan
- **Discord OAuth2 Wajib**: Popup authorization + BroadcastChannel + Cookie + Redirect fallback
- **Single-Session Enforcement**: 1 Discord User ID = 1 active session token (revoke otomatis session lama)
- **Host Lock System**: Validasi role (Owner/Admin/DJ/Session Host) untuk kontrol musik
- **SSRF Blocker**: Validasi URL eksternal (block localhost, 10.x, 192.168.x, 169.254.x)
- **File Validation**: Ekstensi allowlist, ukuran max, path traversal protection

---

## 📁 Struktur Proyek

```
athena-discord-bot/
├── athenaa/                          # Python Backend (FastAPI + discord.py)
│   ├── app/
│   │   ├── main.py                   # Entrypoint: Bot + Uvicorn (single worker)
│   │   ├── config.py                 # Load .env, feature flags, validation
│   │   ├── database.py               # SQLite WAL, migrasi 15 tabel idempoten
│   │   ├── cli_bridge.py             # CLI untuk backup, yt-dlp, test, zip
│   │   ├── models/schema.py          # Dataclass: MusicSession, QueueItem, Task
│   │   ├── security/validators.py    # Host Lock, SSRF, file validation, HMAC
│   │   ├── services/
│   │   │   ├── music_service.py      # Search YouTube/Spotify, radio, yt-dlp extract
│   │   │   ├── queue_service.py      # QueueManager, race-condition guard
│   │   │   ├── lyrics_service.py     # LRCLIB client (synced + plain, 429 handling)
│   │   │   ├── academy_service.py    # .ics parser, UID dedup, reminder evaluator
│   │   │   ├── leveling_service.py   # EXP formula, cooldown, leaderboard, AFK
│   │   │   └── backup_service.py     # Snapshot, gzip, encrypt, rotate
│   │   ├── bot/client.py             # discord.py Bot, slash commands, voice, EXP events
│   │   └── web/routes/api.py         # FastAPI REST endpoints (music, academy, rpg, admin)
│   ├── requirements.txt              # Python deps (VPS/Pterodactyl ready)
│   ├── start.sh                      # Production startup script (single-instance)
│   └── data/                         # SQLite DB, backups, modules (gitignored)
│
├── src/                              # React Frontend (TypeScript + Vite)
│   ├── components/                   # MusicAndLyricsView, AcademyAndModulesView, RpgAndSettingsView, SearchDropdownBar, SpotifyBottomPlayer
│   ├── lib/athenaaRules.ts           # Pure domain logic (EXP, Host Lock, LRC parser, .ics parser, validators)
│   ├── types/athenaa.ts              # TypeScript interfaces (TrackItem, GuildMusicState, AcademicTask, LevelProfile, etc.)
│   ├── utils/audioSynth.ts           # Browser audio engine (Web Audio API fallback)
│   ├── App.tsx                       # Main app: 3-island layout (Library + Stage + Now Playing), OAuth2 modal, WS sync
│   └── main.tsx                      # Entry point
│
├── server.ts                         # Node/Express + Vite dev server + WebSocket relay (dev only)
├── package.json                      # npm scripts: dev, build, start, lint
├── tsconfig.json, vite.config.ts
├── .env                              # Production secrets (GITIGNORED)
├── .env.example                      # Template (this file)
├── .gitignore                        # Updated for deployment
└── README.md                         # This file
```

---

## 🎮 Command & API Reference

### Discord Slash Commands (Bot)
| Command | Description | Permission |
|---------|-------------|------------|
| `/play <query>` | Cari & putar lagu (YouTube/Spotify/Radio) | Semua |
| `/queue` | Lihat antrean musik | Semua |
| `/skip` | Skip lagu (Host Lock) | Host/DJ/Admin/Owner |
| `/pause` / `/resume` | Pause/resume | Host/DJ/Admin/Owner |
| `/stop` | Stop & clear queue | Host/DJ/Admin/Owner |
| `/volume <1-100>` | Set volume | Host/DJ/Admin/Owner |
| `/loop <off/one/queue>` | Set loop mode | Host/DJ/Admin/Owner |
| `/autoplay <on/off>` | Toggle autoplay | Host/DJ/Admin/Owner |
| `/radio <id>` | Putar radio (prambors/hardrockfm/genfm/lofigirl) | Semua |
| `/lyrics` | Lirik sinkron LRCLIB | Semua |
| `/search <query>` | Dropdown search lagu | Semua |
| `/favorite add` | Simpan ke favorit | Semua |
| `/playlist save` | Simpan antrean jadi playlist | Semua |
| `/playlist play <id>` | Putar playlist | Semua |
| `/task add` | Tambah tugas manual | Semua |
| `/task list` | Lihat tugas aktif | Semua |
| `/task sync` | Sync kalender Moodle .ics | Admin/Owner |
| `/level` | Lihat level & EXP | Semua |
| `/leaderboard` | Top 15 server | Semua |
| `/afk <reason>` | Set status AFK | Semua |
| `/admin backup` | Buat backup SQLite | Owner only |
| `/admin test` | Jalankan test suite | Owner only |

### REST API Endpoints (Web Dashboard)

#### Auth & Session
- `GET /api/auth/session` — Cek session (Bearer token / cookie / query)
- `POST /api/auth/logout` — Revoke session
- `GET /api/auth/discord/url` — Dapatkan Discord OAuth2 authorize URL
- `GET /auth/callback` — OAuth2 callback handler (popup + redirect)

#### Guilds & Settings
- `GET /api/guilds` — List guild settings
- `GET /api/guilds/:guildId/settings` — Get settings
- `PATCH /api/guilds/:guildId/settings` — Update settings (admin only)

#### Music
- `GET /api/guilds/:guildId/music/state` — Full player state + radios
- `GET /api/music/search?q=` — Search YouTube + curated catalog
- `GET /api/music/lyrics?title=&artist=` — LRCLIB synced/plain lyrics
- `POST /api/guilds/:guildId/music/play` — Add to queue / play now
- `POST /api/guilds/:guildId/music/control` — pause/resume/skip/stop/clear/shuffle/play_item/remove_item/move_to_top/seek/volume/loop/autoplay/mode_247/host_transfer

#### Library
- `GET /api/guilds/:guildId/library` — Favorites + Playlists (with items)
- `POST /api/favorites` — Add favorite
- `DELETE /api/favorites/:id` — Remove favorite
- `POST /api/guilds/:guildId/playlists/save-queue` — Save queue as playlist
- `POST /api/guilds/:guildId/playlists/import-spotify` — Import Spotify playlist/album
- `POST /api/guilds/:guildId/playlists/:id/play` — Play playlist
- `DELETE /api/guilds/:guildId/playlists/:id` — Delete playlist

#### Academy
- `GET /api/guilds/:guildId/tasks` — Tasks, reminders, attachments, moodle_env
- `POST /api/guilds/:guildId/tasks` — Create manual task
- `POST /api/tasks/:id/toggle` — Toggle complete
- `DELETE /api/tasks/:id` — Delete task
- `POST /api/guilds/:guildId/tasks/sync-ics` — Sync Moodle .ics (UID dedup)
- `POST /api/guilds/:guildId/modules/upload` — Upload module (validated)
- `GET /api/modules/:id/download` — Download module

#### RPG & AFK
- `GET /api/guilds/:guildId/rpg` — Leaderboard + AFK list
- `POST /api/guilds/:guildId/rpg/activity` — Simulate activity & gain EXP (owner only)
- `POST /api/guilds/:guildId/afk` — Set AFK
- `DELETE /api/guilds/:guildId/afk/:userId` — Clear AFK

#### Super-Admin (Owner Only, strict session verification)
- `GET /api/admin/metrics` — System metrics, backups, audit logs
- `POST /api/admin/backup` — Create encrypted backup
- `POST /api/admin/yt-dlp` — Check/update yt-dlp
- `POST /api/admin/run-tests` — Run pytest suite
- `GET /api/python-codebase?file=` — View Python source file
- `GET /api/python-codebase/download-zip` — Download full source ZIP

### WebSocket Events (Real-time)
- `MUSIC_STATE_UPDATE` — Full state broadcast (guild_id, state)
- `POSITION_TICK` — Lightweight position_sec update (every 250ms server clock)

---

## 💻 Kode & Logika Inti (Ringkasan)

### 1. RPG EXP Formula (`src/lib/athenaaRules.ts`, `athenaa/app/services/leveling_service.py`)
```typescript
// max_exp = 100 + (level * 25)
export function calculateMaxExp(level: number): number {
  return 100 + Math.max(1, Math.floor(level)) * 25;
}

export function applyExpGain(currentLevel, currentExp, expGain) {
  // loop while exp >= maxExp, level++, exp -= maxExp, recalc maxExp
  return { leveledUp, level, currentExp, maxExp };
}
```

### 2. Host Lock System (`src/lib/athenaaRules.ts`, `athenaa/app/security/validators.py`)
```typescript
export function canControlQueue(ctx: HostLockContext) {
  if (ctx.isOwner || ctx.isAdmin) return { allowed: true, reason: 'Administrator/Owner' };
  if (ctx.userRoles.includes(ctx.djRoleId)) return { allowed: true, reason: 'DJ Role' };
  if (!ctx.sessionHostId || ctx.sessionHostId === ctx.userId) return { allowed: true, reason: 'Session Host' };
  if (ctx.action === 'remove_item' && ctx.targetItemRequesterId === ctx.userId) return { allowed: true, reason: 'Own track' };
  return { allowed: false, reason: 'Host Lock: hanya Session Host/DJ/Admin/Owner' };
}
```

### 3. LRCLIB Synced Lyrics Parser (`src/lib/athenaaRules.ts`, `athenaa/app/services/lyrics_service.py`)
```typescript
export function parseLrcLyrics(rawLrc: string): SyncedLyricLine[] {
  // Regex: [mm:ss.xxx]text → { timeSec, text }
  // Sort by timeSec ascending
}

export function getActiveLyricIndex(lines, positionSec) {
  // Binary search / linear scan untuk current line index
}
```

### 4. Moodle .ics Parser & Filter (`src/lib/athenaaRules.ts`, `athenaa/app/services/academy_service.py`)
```typescript
export function isSubmittableOrDueTask({ summary, description, url, hasDueOrEndProp }) {
  // EXCLUDE: /mod/resource/, /mod/folder/, /mod/page/, /mod/book/, /mod/label/
  // EXCLUDE: "opens" tanpa "due/closes/kumpul"
  // EXCLUDE: attendance/presensi tanpa task keywords
  // EXCLUDE: materi/slide/bahan ajar tanpa turn-in keywords
  // INCLUDE: /mod/assign/, /mod/quiz/, /mod/workshop/, /mod/turnitintool/
  // INCLUDE: explicit keywords: "is due", "deadline", "tugas", "kumpul", "submit", "laporan", "praktikum", "kuis", "uts", "uas", "proyek", "tubes"
}

export function parseIcsEvents(icsText): ParsedIcsEvent[] {
  // Unfold lines, parse VEVENT blocks, extract UID, SUMMARY, DTEND/DUE, DESCRIPTION, URL, CATEGORIES
  // Filter via isSubmittableOrDueTask
  // Return structured events with deadlineIso (UTC)
}
```

### 5. 3-Stage Reminder Evaluator
```typescript
export function evaluateReminderStage(deadlineIso, nowMs, isCompleted, daysBefore=3) {
  if (isCompleted) return null;
  const hoursLeft = (deadlineMs - nowMs) / 3.6e6;
  if (hoursLeft <= 1) return 'H-1h';
  if (hoursLeft <= 6) return 'H-6h';
  if (hoursLeft <= daysBefore * 24) return `H-${daysBefore}d`;
  return null;
}
```

### 6. Single-Session Discord Enforcement (`server.ts`, `athenaa/app/security/validators.py`)
```typescript
export function enforceSingleDiscordSession(activeByUserId, discordUserId, newSessionToken) {
  const previousToken = activeByUserId.get(discordUserId) || null;
  activeByUserId.set(discordUserId, newSessionToken);
  return { previousTokenRevoked: previousToken !== newSessionToken ? previousToken : null, activeToken: newSessionToken };
}
```

### 7. SQLite Backup + Encryption (`athenaa/app/services/backup_service.py`)
```python
# Online backup (non-blocking): sqlite3.backup()
# Compress: gzip
# Encrypt: AES-GCM (cryptography.fernet or custom)
# Filename: athenaa_backup_YYYYMMDD_HHMMSS.sqlite.gz.enc
```

---

## 🚀 Installation & Deployment Guide

### Prasyarat
- **Python 3.12+** dengan `venv` support
- **FFmpeg** (wajib untuk voice Discord): `apt install ffmpeg` / `brew install ffmpeg` / `winget install ffmpeg`
- **Node.js 20+** & **npm/bun** (untuk build frontend)
- **Git**
- **VPS / Pterodactyl Panel** dengan port allocation (default: 10031)

---

### 1. Clone & Setup Repository
```bash
git clone https://github.com/your-username/athena-discord-bot.git
cd athena-discord-bot
```

---

### 2. Backend Python (athenaa/)

#### A. Install Dependencies
```bash
cd athenaa
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### B. Konfigurasi Environment
```bash
cp ../.env.example .env  # atau copy dari root .env.example
# Edit .env dengan kredensial Anda (lihat bagian .env.example di bawah)
nano .env
```

**Variabel Wajib di `.env` (athenaa/.env):**
```env
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback
MAIN_GUILD_ID=your_guild_id
OWNER_DISCORD_ID=your_user_id
DJ_ROLE_ID=your_dj_role_id
TASK_REMINDER_CHANNEL_ID=your_channel_id
WEB_HOST=0.0.0.0
WEB_PORT=10031
WEB_BASE_URL=https://your-domain.com
SESSION_SECRET=generate_64_hex_chars
ENCRYPTION_KEY=generate_64_hex_chars
BACKUP_ENCRYPTION_KEY=generate_64_hex_chars
MOODLE_BASE_URL=https://waskita.amikom.ac.id/
MOODLE_ICAL_URL=your_ical_export_url
MOODLE_USERNAME=your_student_id
MOODLE_PASSWORD=your_password
```

> **Generate secret keys**: `openssl rand -hex 32` (64 hex chars)

---

### 3. Frontend Build (Production)

```bash
cd ..  # back to root
npm install  # atau bun install
npm run build  # outputs to dist/, copies to athenaa/app/web/static/
```

> **Note**: `npm run build` menjalankan Vite build + copy `dist/` → `athenaa/app/web/static/` untuk serving static files oleh Python backend.

---

### 4. Deploy dengan `start.sh` (Production Single-Instance)

Script `athenaa/start.sh` dirancang untuk **Pterodactyl / VPS single-worker**:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data logs modules

# Auto-copy .env from root if missing
if [ ! -f ".env" ] && [ -f "../.env" ]; then
  cp "../.env" ".env"
fi

echo "[Athenaa] Checking Python & FFmpeg..."
python3 --version
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -n 1
else
  echo "[WARNING] FFmpeg not found. Discord voice requires FFmpeg."
fi

# Single worker only (prevent duplicate Discord Gateway connections)
export WEB_HOST="${WEB_HOST:-0.0.0.0}"
export WEB_PORT="${SERVER_PORT:-${WEB_PORT:-10031}}"

echo "[Athenaa] Starting on ${WEB_HOST}:${WEB_PORT}..."
exec python3 -m app.main
```

#### Jalankan Manual (Testing)
```bash
cd athenaa
chmod +x start.sh
./start.sh
```

#### Pterodactyl Egg Configuration
- **Startup Command**: `./start.sh`
- **Working Directory**: `/mnt/server/athenaa` (atau root project)
- **Port Allocation**: `10031` (HTTP + WebSocket)
- **Environment Variables**: Set di panel Pterodactyl (akan override `.env`)

#### Systemd Service (VPS Bare Metal)
```ini
# /etc/systemd/system/athenaa.service
[Unit]
Description=Athenaa Discord Bot & Dashboard
After=network.target

[Service]
Type=simple
User=athenaa
WorkingDirectory=/opt/athena-discord-bot/athenaa
ExecStart=/opt/athena-discord-bot/athenaa/start.sh
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/athena-discord-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now athenaa
sudo journalctl -u athenaa -f
```

---

### 5. Development Mode (Hot Reload)

```bash
# Terminal 1: Backend (Python) - optional, frontend proxies to it
cd athenaa
source venv/bin/activate
python3 -m app.main

# Terminal 2: Frontend (Vite + Express + WS)
cd ..  # root
npm run dev  # runs server.ts on :3000, proxies /api/* to Python backend
```

Akses: `http://localhost:3000` → Login via Discord OAuth2 popup.

---

### 6. Discord Developer Portal Setup

1. **New Application** → Bot → **Reset Token** → Copy ke `DISCORD_TOKEN`
2. **OAuth2** → General → **Client ID** + **Client Secret** → Copy ke `.env`
3. **OAuth2** → Redirects → Add: `https://your-domain.com/auth/callback`
4. **Bot** → Privileged Gateway Intents → Enable **Message Content**, **Server Members**, **Presence**
5. **Install ke Server** → OAuth2 URL Generator → `bot` + `applications.commands` + `identify` + `guilds` → Copy URL → Buka di browser → Authorize

---

## 🔧 Konfigurasi Lanjutan

### Moodle/Waskita .ics Sync Otomatis
- Set `MOODLE_ICAL_URL` di `.env` (dapatkan dari Moodle: Calendar → Export → iCal link dengan authtoken)
- Atau set `MOODLE_USERNAME` + `MOODLE_PASSWORD` untuk login-based sync
- Dashboard: tab **Akademik** → **Sinkronisasi Sekarang** (manual) atau cron job panggil `POST /api/guilds/:id/tasks/sync-ics`

### Google Classroom (Opsional)
```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-domain.com/auth/callback
```
Fitur: OAuth2 Classroom → sync coursework (belum full-implemented di kode saat ini).

### Custom Branding
```env
CUSTOM_LOGO_URL=https://your-cdn.com/logo.png
```
Logo akan muncul di dashboard (top bar, login modal, sidebar).

---

## 📦 Backup & Restore

### Manual Backup (Dashboard → Super-Admin Hub → Buat Cadangan)
- File: `athenaa/data/backups/athenaa_backup_YYYYMMDD_HHMMSS.sqlite.gz.enc`
- Terkripsi AES-GCM dengan `BACKUP_ENCRYPTION_KEY`

### Restore (Manual)
```bash
cd athenaa
# Decrypt + decompress
python3 -c "
from cryptography.fernet import Fernet
import gzip, os
key = os.environ['BACKUP_ENCRYPTION_KEY'].encode()
f = Fernet(key)
with open('data/backups/athenaa_backup_20261103_122420.sqlite.gz.enc', 'rb') as enc:
    decrypted = f.decrypt(enc.read())
with gzip.open('data/athenaa_restored.db', 'wb') as out:
    out.write(decrypted)
"
# Stop bot, replace data/athenaa.db, restart
```

---

## 🧪 Testing

```bash
cd athenaa
source venv/bin/activate
python3 -m pytest tests/ -v
# atau via dashboard Super-Admin Hub → Jalankan Test
```

Test suite mencakup: EXP formula, Host Lock, LRC parser, .ics parser, reminder stages, validators, backup encrypt/decrypt.

---

## 🐛 Troubleshooting

| Issue | Solusi |
|-------|--------|
| `FFmpeg not found` | Install FFmpeg & pastikan di `PATH` |
| `Discord Gateway: 4004/4009` (duplicate session) | Pastikan hanya **1 worker** (start.sh / systemd / Pterodactyl single instance) |
| `OAuth2 redirect_uri mismatch` | Samakan `DISCORD_REDIRECT_URI` di `.env` & Discord Developer Portal |
| `WebSocket connection failed` | Reverse proxy (nginx/Caddy) harus support WS upgrade: `proxy_http_version 1.1; proxy_set_header Upgrade \$http_upgrade; proxy_set_header Connection "upgrade";` |
| `LRCLIB 429 Too Many Requests` | Cache lyrics di `lyricsCache` Map (sudah diimplementasi), rate limit otomatis |
| `SQLite database is locked` | Pastikan WAL mode aktif (sudah di `database.py`), jangan buka DB manual saat bot jalan |
| `Module upload rejected` | Cek ekstensi (.pdf/.doc/.docx), ukuran ≤ 15MB, nama file tanpa path traversal |

---

## 📄 Sumber Kode & Lisensi

Proyek internal untuk server **TK1GACORKINK**. Kode sumber Python tersedia via dashboard (Owner only) atau ZIP download.

**Sumber Kode (Source Code):**
- **Repository Utama**: GitHub (private/internal)
- **Python Backend**: Folder `athenaa/app/` — FastAPI, discord.py, services, bot client
- **React Frontend**: Folder `src/` — TypeScript, React 19, Vite, Tailwind 4
- **Shared Logic**: `src/lib/athenaaRules.ts` ↔ `athenaa/app/services/*.py` (parity TypeScript/Python)
- **Database Schema**: `athenaa/app/database.py` (15 tabel: guild_settings, queue_items, favorites, playlists, tasks, task_attachments, reminder_deliveries, level_profiles, afk_statuses, audit_logs, discord_sessions, dll)
- **Startup Script**: `athenaa/start.sh` (production single-instance)
- **Dependencies**: `athenaa/requirements.txt` (Python), `package.json` (Node.js)

---

## 🙏 Credits & Dependencies

- **discord.py** — Discord API wrapper
- **FastAPI** + **Uvicorn** — Web framework
- **yt-dlp** — YouTube audio extraction
- **FFmpeg** — Audio processing
- **LRCLIB** — Free synced lyrics database
- **React 19** + **Vite 8** + **Tailwind 4** — Frontend
- **lucide-react** — Icons
- **motion** — Animations
- **node:sqlite** — SQLite sync driver (Node)
- **better-sqlite3 / aiosqlite** — Python SQLite async

---

<div align="center">
  <sub>Dibangun dengan ❤️ untuk komunitas TK1GACORKINK · Athenaa v1.1</sub>
</div>