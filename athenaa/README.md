# Athenaa — Multi-Function Discord Bot & Real-Time Web Dashboard

**Athenaa** adalah aplikasi bot Discord multifungsi berbasis **Python (`discord.py`, `FastAPI`, `SQLite`, `yt-dlp`, `FFmpeg`)** yang dilengkapi **Web Dashboard real-time bergaya Spotify**. Aplikasi ini menggabungkan sistem pemutar musik dengan pencarian dropdown lagu beserta penyanyi, lirik otomatis tersinkronisasi (`LRCLIB`), manajemen antrean berizin (**Host Lock System**), pengingat tugas akademik (**Moodle `.ics` & Google Classroom**), sistem **RPG Leveling & AFK**, serta **Super-Admin Hub** yang dirancang hemat resource untuk hosting **Pterodactyl** maupun **VPS**.

---

## 1. Gambaran Umum Aplikasi

Athenaa dirancang dengan prinsip tanpa biaya langganan API berbayar:
- **Pencarian Lagu + Penyanyi Instan:** Saat pengguna mengetik judul atau penyanyi di kotak pencarian Web Dashboard, muncul dropdown interaktif berisi daftar lagu, nama penyanyi (*singer*), album, durasi, dan sampul album dengan tombol **Putar Sekarang**, **Tambah Antrean**, dan **Favorit**.
- **Sinkronisasi Real-Time WebSocket:** Seluruh perubahan status musik di voice channel Discord maupun di Web Dashboard (judul aktif, posisi detik, pause/playing, volume, loop, autoplay, mode 24/7, dan daftar antrean) disinkronkan secara langsung.
- **Lirik Otomatis LRCLIB:** Mengambil `syncedLyrics` (lirik ber-timestamp per baris) dan `plainLyrics` dari API publik `https://lrclib.net` tanpa API key.
- **Akademik & Reminder 3 Tahap:** Mendukung tugas manual, impor/sinkronisasi kalender `.ics` Moodle (dengan deduplikasi `UID` dan konversi zona waktu `Asia/Jakarta`), koneksi OAuth2 Google Classroom, dan pengingat otomatis **H-3 hari, H-6 jam, dan H-1 jam** yang persisten di database.
- **RPG Leveling & AFK:** Formula progresif `max_exp = 100 + (level * 25)` dengan cooldown anti-spam 60 detik per anggota per server dan Top 15 Leaderboard.
- **Super-Admin Hub:** Pemantauan RAM/CPU proses kontainer, ukuran SQLite, pembuatan snapshot backup SQLite terkompresi & terenkripsi (`sqlite3.backup()`), serta manajemen worker `yt-dlp`.

---

## 2. Arsitektur Sistem

```text
athenaa/
├── app/
│   ├── main.py                  # Entrypoint single-instance (Bot Discord + Uvicorn Web)
│   ├── config.py                # Konfigurasi environment & pemeriksaan kesiapan fitur
│   ├── database.py              # Manajer SQLite (WAL mode) & migrasi 15 tabel idempoten
│   ├── models/
│   │   └── schema.py            # Dataclass domain untuk musik, sesi, dan tugas akademik
│   ├── security/
│   │   └── validators.py        # Host Lock, SSRF blocker, validasi file modul, enkripsi HMAC, rate limit
│   ├── services/
│   │   ├── music_service.py     # Pencarian lagu+penyanyi, pencocokan metadata Spotify, radio, yt-dlp
│   │   ├── queue_service.py     # Queue manager per-server, Host Lock, Loop, Autoplay, Mode 24/7
│   │   ├── lyrics_service.py    # Integrasi LRCLIB (syncedLyrics & plainLyrics + cache + 429 handler)
│   │   ├── academy_service.py   # CRUD tugas, parser VEVENT .ics Moodle, reminder H-3d/H-6h/H-1h
│   │   ├── leveling_service.py  # Kalkulasi EXP RPG, cooldown anti-farming, Top 15, AFK
│   │   └── backup_service.py    # Online backup SQLite aman (.sqlite.gz.enc) & cek versi yt-dlp
│   ├── bot/
│   │   └── client.py            # discord.py Bot, Slash Commands, Voice Host Transfer, EXP event
│   └── web/
│       └── routes/
│           └── api.py           # Endpoint REST API & metrik Super-Admin
├── tests/
│   └── test_athenaa.py          # Automated tests (unittest / pytest)
├── requirements.txt             # Daftar dependensi Python
└── start.sh                     # Skrip startup untuk VPS & Pterodactyl
```

---

## 3. Fitur yang Sudah Selesai dan Batasannya

### Fitur Selesai
- Pencarian lagu real-time dengan dropdown daftar musik beserta penyanyi (*singer*), album, durasi, dan pemutaran audio nyata.
- Queue Manager per-server Discord dengan identitas unik per item (`UUID`), *Play Now*, *Move to Top*, *Shuffle*, *Remove*, *Clear*, *Loop* (`off`/`one`/`queue`), *Volume* (`1–100%`), *Autoplay* anti-duplikat, dan *Mode 24/7*.
- **Host Lock System** lengkap (Session Host, Role DJ, Admin Server, serta perpindahan otomatis saat host keluar dari voice channel).
- Integrasi lirik otomatis **LRCLIB** (`syncedLyrics` ber-timestamp dan `plainLyrics`).
- Radio internet terverifikasi (Prambors FM, Hard Rock FM, Gen FM, Lofi Radio) + dukungan custom stream URL dengan validasi anti-SSRF.
- Manajemen tugas akademik, parser kalender `.ics` Moodle bebas duplikat, evaluasi reminder 3 tahap (`H-3d`, `H-6h`, `H-1h`), dan validasi lampiran modul (`.pdf`, `.doc`, `.docx`, maks 15 MB, pemeriksaan *magic bytes*).
- Sistem RPG Leveling (`max_exp = 100 + (level * 25)`), cooldown anti-spam, Leaderboard Top 15, dan sistem AFK persisten.
- Panel Super-Admin dengan metrik resource nyata, backup SQLite terenkripsi, dan pemeriksaan worker `yt-dlp`.

### Batasan Teknis & Layanan Eksternal
- **Spotify DRM:** Audio tidak pernah diambil secara ilegal dari stream DRM Spotify. Tautan Spotify diambil metadatanya melalui endpoint publik lalu dicocokkan dengan sumber audio terbuka yang dapat diputar.
- **Mode 24/7 & Hosting:** Bot mempertahankan koneksi voice channel selama proses berjalan, namun tidak dapat tetap aktif apabila kontainer Pterodactyl dimatikan atau koneksi jaringan host terputus.
- **Google Classroom:** Memerlukan konfigurasi `GOOGLE_CLIENT_ID` dan `GOOGLE_CLIENT_SECRET` dari Google Cloud Console. Apabila belum diisi, status ditampilkan sebagai **Belum Dikonfigurasi** dan pengguna tetap dapat memakai sinkronisasi `.ics` atau input tugas manual.

---

## 4. Daftar Dependensi & Persyaratan Sistem

- **Python:** 3.10, 3.11, atau 3.12
- **FFmpeg:** Wajib terpasang di sistem (`apt install ffmpeg`) untuk streaming audio ke Discord Voice Channel.
- **Paket Python (`requirements.txt`):** `discord.py[voice]`, `PyNaCl`, `yt-dlp`, `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `aiosqlite`, `httpx`, `python-dotenv`, `psutil`, `icalendar`, `python-dateutil`, `cryptography`, `pytest`.

---

## 5. Cara Membuat Discord Bot & Konfigurasi OAuth2 Dashboard

1. Buka [Discord Developer Portal](https://discord.com/developers/applications) dan klik **New Application**.
2. Pada menu **Bot**:
   - Klik **Reset Token** dan salin ke variabel `DISCORD_TOKEN` pada file `.env`.
   - Aktifkan **Message Content Intent**, **Server Members Intent**, dan **Presence Intent**.
3. Pada menu **OAuth2**:
   - Salin **Client ID** ke `DISCORD_CLIENT_ID` dan **Client Secret** ke `DISCORD_CLIENT_SECRET`.
   - Tambahkan Redirect URI: `https://domain-anda.com/auth/callback` (atau `http://localhost:10031/auth/callback` untuk lokal).
4. Undang bot ke server Discord menggunakan URL Generator dengan scope `bot` dan `applications.commands` serta izin `Connect`, `Speak`, `Send Messages`, `Embed Links`, dan `Attach Files`.

---

## 6. Konfigurasi Google Classroom & Kalender Moodle (.ics)

### Kalender Moodle (`.ics`)
1. Buka halaman **Calendar** pada Moodle kampus Anda, lalu klik **Export Calendar**.
2. Pilih **All events** (atau **Events related to courses**) dan rentang waktu **Recent and next 60 days**, lalu klik **GetCalendar URL**.
3. Tempel URL `.ics` tersebut pada halaman **Pengaturan Server** atau **Akademik & Tugas** di Dashboard Athenaa. URL disimpan secara terenkripsi di database.

### Google Classroom OAuth2
1. Buka [Google Cloud Console](https://console.cloud.google.com/), buat project baru, dan aktifkan **Google Classroom API**.
2. Konfigurasikan **OAuth Consent Screen** dengan scope baca-saja:
   - `https://www.googleapis.com/auth/classroom.courses.readonly`
   - `https://www.googleapis.com/auth/classroom.coursework.me.readonly`
3. Buat **OAuth 2.0 Client ID (Web application)**, tambahkan Redirect URI sesuai `GOOGLE_REDIRECT_URI`, lalu masukkan kredensial ke `.env`.

---

## 7. Menjalankan Aplikasi Secara Lokal & Pada Pterodactyl

### Menjalankan Secara Lokal
```bash
cd athenaa
cp ../.env.example .env
pip install -r requirements.txt
chmod +x start.sh
./start.sh
```

### Menjalankan Pada Pterodactyl Hosting
1. Unggah seluruh isi direktori `athenaa/` (atau unduh bundel `.zip` langsung dari tab **Kode Bot Python** pada dashboard).
2. Alokasikan port jaringan pada panel Pterodactyl (default konfigurasi menggunakan port **`10031`**, sesuaikan `WEB_PORT` dengan port alokasi kontainer Anda).
3. Gunakan **Startup Command** berikut pada panel Pterodactyl:
   ```bash
   bash start.sh
   ```
   atau:
   ```bash
   python3 -m app.main
   ```
4. Pastikan hanya **1 worker** yang dijalankan agar bot tidak membuka koneksi Gateway Discord ganda.

---

## 8. Backup, Restore, dan Pengujian

- **Backup Database:** Buka menu **Super-Admin Hub** lalu klik **Buat Backup SQLite Sekarang**. Sistem menggunakan API `sqlite3.backup()` untuk menghasilkan snapshot konsisten tanpa mengunci database, mengompresinya dengan `gzip`, dan mengenkripsinya dengan `BACKUP_ENCRYPTION_KEY`.
- **Menjalankan Automated Tests:**
  ```bash
  cd athenaa
  python3 -m unittest discover -s tests -p "test_*.py" -v
  ```
