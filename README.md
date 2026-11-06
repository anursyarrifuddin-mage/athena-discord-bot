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

## 🎮 Discord Slash Commands (Bot)

### 🎵 Musik
| Command | Description | Permission |
|---------|-------------|------------|
| `/play <query>` | Putar lagu dari judul/penyanyi, URL YouTube, Spotify Track/Playlist, atau Radio | Semua |
| `/search <query>` | Cari lagu beserta nama penyanyi dari katalog YouTube & Spotify | Semua |
| `/nowplaying` | Tampilkan panel lagu yang sedang diputar beserta tombol kontrol interaktif | Semua |
| `/queue [page]` | Tampilkan daftar antrean lagu aktif dengan progress bar modern | Semua |
| `/remove <posisi>` | Hapus lagu tertentu dari daftar antrean berdasarkan nomor urut | Host/DJ/Admin/Owner |
| `/skip` | Lewati lagu saat ini di Voice Channel (Host Lock) | Host/DJ/Admin/Owner |
| `/pause` | Jeda pemutaran lagu aktif (Host Lock) | Host/DJ/Admin/Owner |
| `/resume` | Lanjutkan pemutaran lagu yang dijeda (Host Lock) | Host/DJ/Admin/Owner |
| `/stop` | Hentikan pemutaran dan bersihkan antrean (Host Lock) | Host/DJ/Admin/Owner |
| `/shuffle` | Acak urutan antrean musik (Host Lock) | Host/DJ/Admin/Owner |
| `/volume <1-100>` | Atur volume suara bot antara 1% hingga 100% (Host Lock) | Host/DJ/Admin/Owner |
| `/loop <off|one|queue>` | Atur mode pengulangan lagu atau antrean (Host Lock) | Host/DJ/Admin/Owner |
| `/autoplay <true|false>` | Aktifkan/nonaktifkan pemutaran lagu lanjutan otomatis saat antrean habis (Host Lock) | Host/DJ/Admin/Owner |
| `/247 <true|false>` | Pertahankan koneksi bot di voice channel selama 24/7 (Host Lock) | Host/DJ/Admin/Owner |
| `/lyrics [judul]` | Tampilkan lirik tersinkronisasi atau teks dari LRCLIB | Semua |
| `/leave` | Putuskan koneksi bot dari Voice Channel | Semua |

### 📚 Akademik (Waskita/Moodle)
| Command | Description | Permission |
|---------|-------------|------------|
| `/tugas` | Lihat daftar tugas kuliah aktif beserta countdown deadline WIB & file modul | Semua |
| `/tugas_list` | Alias untuk `/tugas` | Semua |
| `/tugas_add <mata_kuliah> <judul> <deadline_iso> [file_modul]` | Tambahkan tugas akademik baru secara manual beserta lampiran modul | Semua |
| `/tugas_done <task_id>` | Tandai tugas selesai dan hentikan reminder berikutnya | Semua |
| `/tugas_hapus <task_id>` | Hapus tugas dari database berdasarkan ID Tugas | Semua |
| `/sync_waskita [ical_url]` | Sinkronkan tugas Waskita/Moodle (.ics atau Kredensial .env) | Admin/Owner |
| `/sync_moodle [ical_url]` | Alias untuk `/sync_waskita` | Admin/Owner |

### 🎓 Mahasiswa
| Command | Description | Permission |
|---------|-------------|------------|
| `/pomodoro [fokus_menit] [istirahat_menit] [topik]` | Mulai timer fokus belajar Pomodoro interaktif di Discord (+30 EXP) | Semua |
| `/ipk <sks_nilai>` | Hitung simulasi IP/IPK semester dari format SKS:Nilai (mis. 3:A, 4:AB, 3:B+) | Semua |
| `/kelompok <jumlah_kelompok> [daftar_nama]` | Acak pembagian kelompok tugas dari daftar nama atau anggota Voice Channel | Semua |

### ⚔️ RPG Leveling & AFK
| Command | Description | Permission |
|---------|-------------|------------|
| `/level [member]` | Lihat kartu profil Level, progres EXP, dan sumber EXP (Chat & Voice) | Semua |
| `/leaderboard` | Tampilkan Top 15 Leaderboard Server (Chat, Join Voice, Speak, Listen, Stream) | Semua |
| `/afk [alasan]` | Pasang status AFK dengan alasan opsional | Semua |

### 🎮 Minigames
| Command | Description | Permission |
|---------|-------------|------------|
| `/kuis` | Mainkan kuis trivia interaktif untuk mahasiswa & pelajar (+25 EXP) | Semua |
| `/mathbattle` | Tantangan hitung cepat matematika dengan hadiah +20 EXP | Semua |
| `/suit <batu|gunting|kertas>` | Mainkan Batu-Gunting-Kertas melawan Athenaa (+15 EXP jika menang) | Semua |
| `/8ball <pertanyaan>` | Tanyakan pertanyaan ke Kerang Ajaib Athenaa | Semua |
| `/dadu [sisi]` | Lempar dadu keberuntungan (default 6 sisi, mendukung d20 / d100) | Semua |

### 🛠️ Utilitas
| Command | Description | Permission |
|---------|-------------|------------|
| `/invite` | Dapatkan link invite resmi untuk mengundang Athenaa Bot ke server Discord lain | Semua |

> **Catatan**: Fitur favorit, playlist, dan admin commands (backup, test) hanya tersedia via **Web Dashboard** (Super-Admin Hub), bukan sebagai Discord slash command.

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

- **Repository Utama**: GitHub (private/internal)
- **Python Backend**: Folder `athenaa/app/` — FastAPI, discord.py, services, bot client
- **React Frontend**: Folder `src/` — TypeScript, React 19, Vite, Tailwind 4
- **Shared Logic**: `src/lib/athenaaRules.ts` ↔ `athenaa/app/services/*.py` (parity TypeScript/Python)
- **Database Schema**: `athenaa/app/database.py` (15 tabel)
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