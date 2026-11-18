# Laporan Riset & Audit Keamanan Serta Logika Kode — Athenaa Discord Bot & Web Dashboard

**Tanggal Audit:** 18 November 2026  
**Target Audit:** `/tmp/bot_src/athenaa/app/` (FastAPI Web Dashboard, Discord Bot `discord.py`, AI Assistant, Music/Queue Engine, Academic Sync, Validators, & SQLite Database)  
**Metodologi:** Inspeksi *primary-source* langsung terhadap 8 berkas kode sumber inti dan pemetaan terhadap standar keamanan resmi ([OWASP API Security Top 10 2023](https://owasp.org/projects/api-security-project), [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/), [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/), [RFC 6749 OAuth 2.0](https://www.rfc-editor.org/info/rfc6749/), serta [FastAPI Documentation](https://fastapi.tiangolo.com/tutorial/cors/)).

---

## Ringkasan Eksekutif

Audit menemukan **17 temuan utama** (12 temuan **Kategori A** yang aman diperbaiki langsung tanpa beban RAM/UX, dan 5 temuan **Kategori B** yang memiliki *trade-off* RAM, performa, atau kenyamanan UX sehingga perlu didiskusikan dengan pemilik bot sebelum diterapkan).

Temuan paling kritis meliputi:
1. **Authentication Bypass & IDOR Lintas Server** pada `PATCH /api/guilds/{guild_id}/settings`, seluruh endpoint `/tasks`, `/modules`, `/playlists`, `/favorites`, dan `/afk` akibat pola pemeriksaan `if sess:` yang justru meloloskan permintaan tanpa token sesi.
2. **Arbitrary Local File Read & SSRF** pada kombinasi `POST /api/guilds/{guild_id}/music/play` + `GET /api/guilds/{guild_id}/music/stream` yang memungkinkan pembacaan file lokal kontainer (termasuk `.env`) atau akses jaringan internal.
3. **Privilege Escalation Global via `isAdmin`** di `_verify_owner_or_admin()` sehingga pengguna yang menjadi admin di server pribadi mana pun dapat mengakses endpoint `/api/admin/*` dan `/api/guilds/{guild_id}/rpg/activity` di server lain.
4. **Celah OAuth2 (Tanpa `state`/CSRF, `postMessage('*')`, Reflected XSS, Cookie tanpa `HttpOnly`/`Secure`)** dan **CORS `allow_origins=["*"]` + `allow_credentials=True`**.
5. **Cross-Guild Data Leak via WebSocket `/ws`** tanpa autentikasi yang menyiarkan status musik dan `user_voice_map` seluruh server ke semua klien.
6. **Bug Logika & Memory Leak**: fungsi pembersih cache `clear_music_memory_caches()` gagal total karena `NameError`/`AttributeError` yang tertelan `except Exception`, `decrypt_secret()` dipanggil kurang argumen, AutoMod dapat di-bypass cukup dengan men-tag `@Athena`, serta Host Lock dimatikan di semua jalur karena hardcode `is_admin=True`.

---

## Matriks Klasifikasi Temuan

| ID | Kategori | Tingkat Risiko | Komponen Utama | Ringkasan Masalah | Estimasi Dampak RAM / UX |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A-01** | **Kategori A** | **KRITIS** | `api.py:2220-2288` | `PATCH /settings` tanpa auth meloloskan request anonim | 0 MB RAM / Tidak mengganggu UX |
| **A-02** | **Kategori A** | **KRITIS** | `api.py:2717-3364` | IDOR & missing auth pada Tasks, Modules, Playlists, Favorites, AFK, & GET Settings | 0 MB RAM / Tidak mengganggu UX |
| **A-03** | **Kategori A** | **KRITIS** | `api.py:1594-1609, 3273-3395` | Eskalasi hak akses `/api/admin/*` & RPG via flag `isAdmin` global | 0 MB RAM / Tidak mengganggu UX |
| **A-04** | **Kategori A** | **KRITIS** | `api.py:2014-2189, 2541` | SSRF & Arbitrary Local File Read pada `/music/stream` proxy | **Hemat RAM & Bandwidth** / Tidak dipakai Web Player |
| **A-05** | **Kategori A** | **KRITIS** | `api.py:789-810, 1792-2009` | OAuth2 tanpa `state` (CSRF), `postMessage('*')`, Reflected XSS, cookie tidak aman | 0 MB RAM / Tidak mengganggu UX |
| **A-06** | **Kategori A** | **TINGGI** | `api.py:1324-1365, 1550-1679` | WebSocket `/ws` tanpa auth + kebocoran `user_voice_map` lintas server | **Hemat RAM & Trafik** / Tidak mengganggu UX |
| **A-07** | **Kategori A** | **TINGGI** | `validators.py:80-112`, `academy_service.py:659,677-730`, `music_service.py:2676` | SSRF bypass (DNS `resolve_dns=False` & HTTP 302), `--no-check-certificates`, bug `decrypt_secret()` | 0 MB RAM / Tidak mengganggu UX |
| **A-08** | **Kategori A** | **TINGGI** | `api.py:1315-1322` | CORS wildcard `*` digabung `allow_credentials=True` | 0 MB RAM / Tidak mengganggu UX |
| **A-09** | **Kategori A** | **TINGGI** | `api.py:3129-3169`, `client.py:3971-3978` | Upload modul memvalidasi byte dummy (bukan payload asli) + baca file ke RAM sebelum cek ukuran | **Cegah lonjakan RAM & disk** / Zero UX friction |
| **A-10** | **Kategori A** | **TINGGI** | `music_service.py:2837-2855`, `client.py:2411,2470,2479,3007`, `validators.py:210-228` | `/ram_clean` rusak (`NameError`/`AttributeError`), View `timeout=None` leak, rate limiter unbounded, mention lirik/radio/history rusak | **Menurunkan RAM** / Memperbaiki fitur rusak |
| **A-11** | **Kategori A** | **TINGGI** | `client.py:2236-2253`, `ai_assistant_service.py:1508-1532` | Bypass AutoMod cukup dengan mention `@Athena` + substring false positive | 0 MB RAM / Moderasi akurat |
| **A-12** | **Kategori A** | **SEDANG-TINGGI** | `client.py:2224, 5153, 5377, 5442, 5486` | `/ai_model` global tanpa cek Owner, spam `/ram_clean`, `sleeptimer 0` tidak membatalkan task lama | **Cegah task/CPU leak** / Zero UX friction |
| **B-01** | **Kategori B** | **KRITIS** | `api.py:2432-2613`, `client.py:2331-2558, 2932, 3037, 3774-5061` | Hardcode `is_admin=True`/`is_owner=True` & spoofing `actor_id` mematikan Host Lock | Trade-off: Kebebasan kontrol musik di server pertemanan |
| **B-02** | **Kategori B** | **TINGGI** | `ai_assistant_service.py:286, 832, 866-905, 1439-1468` | Prompt Injection (LLM01) & multi-command abuse (hingga 12 aksi) + tanpa rate limit AI | Trade-off: Cooldown & pembatasan aksi AI via mention |
| **B-03** | **Kategori B** | **TINGGI** | `queue_service.py:207-321`, `api.py:120`, `music_service.py:2666` | Tanpa batas antrean (`MAX_QUEUE_SIZE`), rate limit 1000 req/menit terlalu longgar, cache audio 20 file di `/tmp` | Trade-off: Batas impor playlist panjang & efisiensi RAM/disk |
| **B-04** | **Kategori B** | **SEDANG** | `client.py:3946-4149` | Semua member bisa hapus tugas (`/tugas_hapus`), tandai selesai (`/tugas_done`), & ubah URL `/sync_waskita` | Trade-off: Kebijakan kolaborasi kelas vs integritas data |
| **B-05** | **Kategori B** | **SEDANG** | `api.py:1005-1225, 1970-2006` | Token sesi tidak pernah kedaluwarsa & disimpan di `localStorage` | Trade-off: Re-login berkala & migrasi auth frontend SPA |

---

## Kategori A — Aman, Ringan, Zero RAM Overhead, Tidak Menghambat UX (Dapat Langsung Diperbaiki)

### A-01. [KRITIS] Authentication Bypass pada `PATCH /api/guilds/{guild_id}/settings`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `2220–2288`.
- **Analisis Kode:**
  Pada baris `2222–2240`, pemeriksaan otorisasi admin server dibungkus di dalam kondisi `if sess and sess.get("user"):`. Apabila klien mengirimkan permintaan `PATCH` **tanpa** header `Authorization`, tanpa cookie, dan tanpa query `session_token`, maka `sess` bernilai `None`, seluruh blok pemeriksaan dilewati, dan kode langsung memperbarui tabel `guild_settings` pada baris `2282–2286`.
- **Skenario Eksploitasi (Konseptual):**
  Penyerang eksternal yang mengetahui ID server Discord target (publik bagi siapa pun yang berada di server) dapat mengirim permintaan `PATCH` anonim ke `/api/guilds/{guild_id}/settings` untuk:
  1. Mematikan seluruh filter AutoMod (`automod_badwords_enabled=0`, `automod_antilink_enabled=0`).
  2. Mengubah `autorole_id` menjadi Role ID bernilai tinggi (mis. Moderator/Admin) sehingga akun baru penyerang otomatis mendapat role tersebut saat bergabung (`client.py:2150–2157`).
  3. Menyuntikkan URL berbahaya ke `moodle_ics_url_encrypted` atau mengubah pesan sambutan (`welcome_message`) menjadi tautan penipuan.
- **Rekomendasi Perbaikan:**
  Tolak segera dengan `HTTPException(status_code=401)` apabila `sess is None` sebelum melakukan evaluasi `admin_user_ids`. Validasi juga bahwa `autorole_id` yang disetel tidak memiliki hak `administrator` / `manage_guild` di Discord.
- **Estimasi Dampak RAM & UX:** 0 MB RAM; tidak menghambat UX karena seluruh administrator yang sah sudah memiliki sesi login aktif di dashboard.
- **Sumber Primer:** [OWASP API2:2023 Broken Authentication](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/), [OWASP API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

---

### A-02. [KRITIS] IDOR & Missing Authentication pada Endpoint Tasks, Modules, Playlists, Favorites, AFK, dan `GET /settings`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `2212–2218`, `2717–2990`, `2994–3264`, `3328–3364`; `/tmp/bot_src/athenaa/app/services/academy_service.py`, baris `585–619`.
- **Analisis Kode:**
  1. **Fallback ke Identitas Owner:** Jika `sess is None`, endpoint `/library` (`2720`), `/favorites` (`2746, 2759`), `/playlists/save-queue` (`2809`), `/playlists/import-spotify` (`2868`), `/playlists/{id}/play` (`2961`), `/tasks/{id}/toggle` (`3059`), `/modules/upload` (`3125`), dan `/afk` (`3336`) secara diam-diam memakai `settings.owner_discord_id` atau `"Aetheriaaa"`.
  2. **Bypass Kondisi `if sess:`:** Pada `DELETE /api/guilds/{guild_id}/afk/{user_id}` (`3357–3359`), pengecekan `if sess and ...` dilewati sepenuhnya jika permintaan dikirim tanpa token!
  3. **Endpoint Tanpa Auth & Tanpa Isolasi `guild_id`:** `GET /api/guilds/{guild_id}/settings` (`2212`), `DELETE /api/favorites/{favorite_id}` (`2784`), `DELETE /api/guilds/{guild_id}/playlists/{playlist_id}` (`2985`), `GET/POST/PATCH/DELETE /api/guilds/{guild_id}/tasks*` (`2994–3089`), `POST /api/guilds/{guild_id}/tasks/sync-moodle` (`3091`), dan `GET /api/modules/{attachment_id}/download` (`3217`) tidak memverifikasi sesi maupun keanggotaan user pada `guild_id`. Khusus `POST /api/tasks/{task_id}/toggle` (`3052`) dan `DELETE /api/tasks/{task_id}` (`3080`), pemanggilan `academy_service.toggle_task()` dan `delete_task("", task_id)` sama sekali tidak memeriksa kepemilikan `guild_id`.
- **Skenario Eksploitasi (Konseptual):**
  Pengguna anonim dapat membaca konfigurasi internal server lain (termasuk `moodle_ics_url_encrypted` dan daftar kata sensor), menghapus seluruh tugas kuliah atau playlist milik server lain, mengunduh file modul PDF/DOCX privat lewat IDOR `attachment_id`, atau memicu sinkronisasi Moodle berulang-ulang tanpa batas.
- **Rekomendasi Perbaikan:**
  Buat FastAPI Dependency tunggal `require_guild_member(guild_id)` (memverifikasi sesi aktif + keanggotaan user di `guild_id`) dan `require_guild_admin(guild_id)` untuk seluruh endpoint `/api/guilds/{guild_id}/*`. Hapus seluruh fallback ke `settings.owner_discord_id` saat `sess is None`, serta wajibkan pengecekan `guild_id` pada `/api/tasks/{task_id}/*` dan `/api/modules/{attachment_id}/download`.
- **Estimasi Dampak RAM & UX:** 0 MB RAM; tidak mengganggu UX karena dashboard web selalu mengirim `Authorization: Bearer` / cookie sesi setelah login.
- **Sumber Primer:** [OWASP API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/), [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

---

### A-03. [KRITIS] Privilege Escalation Global ke `/api/admin/*` & `/rpg/activity` via Flag `isAdmin`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `1594–1627`, `1908–1949`, `3273–3286`, `3369–3395`.
- **Analisis Kode:**
  Pada proses callback OAuth2 (`1909–1917`), setiap kali pengguna memiliki izin `owner`, `administrator` (`0x8`), atau `manage_guild` (`0x20`) pada **server Discord mana pun** di akunnya (termasuk server kosong yang baru dibuat sendiri oleh pengguna tersebut), variabel `is_admin` disetel menjadi `True` secara global di tabel `discord_user_sessions`. Selanjutnya, `_verify_owner_or_admin()` (`1599`) dan `api_rpg_activity()` (`3280`) langsung meloloskan siapa pun dengan `u.get("isAdmin") == True`.
- **Skenario Eksploitasi (Konseptual):**
  Pengguna biasa di Server Utama cukup membuat server Discord pribadi miliknya sendiri (otomatis berstatus Owner), login ke dashboard Athenaa, lalu memperoleh `isAdmin=True` global. Dengan sesi tersebut, ia dapat:
  - Mengeksekusi `POST /api/admin/yt-dlp` (memicu pembaruan/subprocess paket sistem), `POST /api/admin/run-tests` (menjalankan *test suite* yang membebani CPU/RAM produksi), `POST /api/admin/backup` (membuat file backup berulang hingga disk penuh), dan membaca `GET /api/admin/metrics`.
  - Memanggil `POST /api/guilds/{main_guild_id}/rpg/activity` dengan `bypass_cooldown=True` untuk menaikkan level/EXP akunnya secara instan di server tempat ia hanyalah member biasa.
- **Rekomendasi Perbaikan:**
  1. Untuk semua endpoint `/api/admin/*` (`metrics`, `backup`, `yt-dlp`, `run-tests`), wajibkan **khusus Bot Owner** (`isOwner == True` dan `uid == settings.owner_discord_id`), bukan admin server biasa.
  2. Untuk `/api/guilds/{guild_id}/rpg/activity`, evaluasi status admin secara ketat **per-server** menggunakan `guild_id` terkait (sama seperti logika isolasi per-server pada `_list_synchronized_guilds`), bukan flag `isAdmin` global.
- **Estimasi Dampak RAM & UX:** 0 MB RAM; tidak berdampak pada Owner maupun Admin sah.
- **Sumber Primer:** [OWASP API5:2023 Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/), [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

---

### A-04. [KRITIS] Arbitrary Local File Read & SSRF pada Audio Stream Proxy `/api/guilds/{guild_id}/music/stream`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `959–960`, `2014–2189`, `2541`, `2580`.
- **Analisis Kode:**
  1. Endpoint `/api/guilds/{guild_id}/music/stream` tidak memiliki autentikasi maupun validasi `validate_external_url()`.
  2. Pada baris `2056` dan `2096–2107`, jika `raw_stream_url` cocok dengan path file lokal (`Path(raw_stream_url).is_file()`), server langsung melayani file tersebut lewat `FileResponse(path=raw_stream_url)`.
  3. Di sisi lain, `POST /api/guilds/{guild_id}/music/play` (`2541, 2580`) menerima `body.stream_url` langsung dari input klien tanpa sanitasi saat `source_type == "radio"`, dan menyimpannya ke `target_track.stream_url`.
  4. Selain itu, bila `raw_stream_url` berupa URL internal (mis. layanan lokal atau metadata cloud), `urllib.request.urlopen()` di baris `2124` langsung mem-proxy responsnya ke klien dengan `Access-Control-Allow-Origin: *`.
  5. Catatan arsitektur pada baris `959` bahkan menyatakan bahwa Web Dashboard kini hanya berfungsi sebagai Remote Control (audio keluar di Discord Voice, `safe_web_stream = ""`), sehingga endpoint ini menjadi permukaan serangan berisiko tinggi tanpa manfaat aktif.
- **Skenario Eksploitasi (Konseptual):**
  Penyerang mendaftarkan track bertipe `radio` melalui `/music/play` dengan mengisi `stream_url` mengarah ke path berkas sensitif kontainer (seperti `.env` berisi `DISCORD_TOKEN` dan `GEMINI_API_KEY`, atau database SQLite) maupun alamat layanan internal `127.0.0.1`, lalu mengakses `GET /api/guilds/{guild_id}/music/stream` untuk membaca isi berkas atau respons layanan internal secara utuh.
- **Rekomendasi Perbaikan:**
  - Nonaktifkan endpoint `/api/guilds/{guild_id}/music/stream` apabila memang tidak lagi digunakan oleh Web Player; **atau** jika ingin dipertahankan: (a) wajibkan autentikasi keanggotaan guild, (b) tolak `body.stream_url` dari input klien pada `/music/play` (hanya izinkan URL dari allowlist `VERIFIED_RADIO_STATIONS` atau hasil ekstraksi server), (c) pastikan `FileResponse` hanya boleh mengakses file di dalam direktori `_LOCAL_AUDIO_CACHE_DIR.resolve()`, dan (d) terapkan validasi SSRF penuh sebelum `urlopen`.
- **Estimasi Dampak RAM & UX:** **Menghemat RAM dan bandwidth keluar**; tidak memengaruhi UX karena Web Player tidak memutar audio lewat endpoint ini.
- **Sumber Primer:** [OWASP Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html), [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

---

### A-05. [KRITIS] Celah Keamanan Alur OAuth2: Tanpa `state` (Login CSRF), Token Leak via `postMessage('*')`, Reflected XSS, & Host Spoofing
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `789–810`, `1792–1817`, `1856–2009`.
- **Analisis Kode:**
  1. **Absennya Parameter `state` (Login CSRF):** `api_discord_oauth_url` (`1804–1812`) tidak menyertakan parameter `state`, dan `discord_oauth_callback` (`1858`) tidak memverifikasi `state`.
  2. **Kebocoran Token lewat `postMessage('*')`:** Baris `1981` mengeksekusi `window.opener.postMessage(payload, '*')` yang membawa `session_token` ke *origin* mana pun yang membuka popup login.
  3. **Kebocoran Token lewat Query URL & Cookie Tidak Aman:** Baris `1959` mengarahkan ke `/?session_token=...` (tercatat di riwayat browser, log proxy, dan header `Referer`), sedangkan baris `2000–2006` menyetel cookie tanpa atribut `httponly=True` dan `secure=True`.
  4. **Reflected HTML/XSS Injection:** Baris `1995` menyisipkan `{uname}` dan `{utag}` langsung ke HTML tanpa `html.escape()` (display name Discord dapat memuat tag HTML), dan baris `2009` menyisipkan `{exc}` mentah ke `HTMLResponse` (juga membocorkan detail error internal).
  5. **Host Header Injection pada Redirect URI:** Baris `804` memeriksa `"athenaa.my.id" in fwd_host` menggunakan substring, bukan *exact match*, sehingga host seperti `athenaa.my.id.evil.tld` lolos pengecekan.
- **Skenario Eksploitasi (Konseptual):**
  - *Login CSRF:* Penyerang memaksa korban mengunjungi `/auth/callback?code=<kode_milik_penyerang>` sehingga sesi korban tertaut ke akun penyerang.
  - *Token Theft:* Situs berbahaya membuka jendela popup ke flow OAuth Athenaa dan mencegat `session_token` dari `window.opener.postMessage(payload, '*')`.
  - *XSS:* Akun Discord dengan `global_name` mengandung markup HTML/script memicu eksekusi skrip di domain `bot.athenaa.my.id` saat halaman callback dirender.
- **Rekomendasi Perbaikan:**
  - Terbitkan nonce `state` acak (`secrets.token_urlsafe(24)`), simpan dalam cookie `HttpOnly; SameSite=Lax; Max-Age=300`, lalu verifikasi menggunakan `hmac.compare_digest()` di `/auth/callback`.
  - Ganti target `postMessage` dari `'*'` menjadi origin eksplisit `window.location.origin` (atau `https://bot.athenaa.my.id`).
  - Gunakan `html.escape()` untuk `uname`, `utag`, dan tampilkan pesan error generik di baris `2009` (catat detail exception hanya di server log).
  - Gunakan *exact allowlist* host di `_resolve_oauth_redirect_uri()` (`fwd_host in {"bot.athenaa.my.id", "localhost:10031", "127.0.0.1:10031"}`) dan aktifkan `secure=True` pada cookie saat HTTPS.
- **Estimasi Dampak RAM & UX:** 0 MB RAM (cookie *stateless* untuk `state`); tidak mengubah alur login pengguna.
- **Sumber Primer:** [RFC 6749 Section 10.12 (OAuth 2.0 CSRF)](https://www.rfc-editor.org/info/rfc6749/), [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).

---

### A-06. [TINGGI] Kebocoran Data Lintas Server melalui WebSocket `/ws` Tanpa Autentikasi & `user_voice_map` Global
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `1324–1365`, `1550–1572`, `1634–1679`, `2194–2210`, `2394–2422`.
- **Analisis Kode:**
  1. `websocket_endpoint()` (`1636–1638`) langsung memanggil `await ws.accept()` tanpa memeriksa sesi login maupun keanggotaan server.
  2. `_broadcast_guild_state(guild_id)` (`1550–1571`) mengirim pembaruan status antrean musik suatu server ke **seluruh** klien di `ws_clients` tanpa memfilter server mana yang diizinkan untuk klien tersebut.
  3. `_build_user_voice_map()` (`1324–1365`) merangkum seluruh anggota yang sedang berada di Voice Channel dari **semua server Discord** (`live_bot.guilds`) — lengkap dengan `user_id`, `guild_id`, `guild_name`, dan `voice_channel_name` — lalu menyisipkannya ke setiap pesan WebSocket, respons `GET /api/guilds`, dan `GET /api/guilds/{guild_id}/music/state`.
- **Skenario Eksploitasi (Konseptual):**
  Pihak luar tanpa akun login dapat membuka koneksi WebSocket ke `/ws` dan mengumpulkan data privasi secara real-time: daftar nama server privat yang memakai Athenaa, aktivitas mendengarkan musik tiap server, serta pelacakan keberadaan *user ID* di Voice Channel tertentu lintas server.
- **Rekomendasi Perbaikan:**
  - Verifikasi sesi (via cookie atau token awal) pada koneksi `/ws` dan simpan pemetaan `ws -> (user_id, allowed_guild_ids, subscribed_guild_id)`.
  - Kirim broadcast `_broadcast_guild_state(guild_id)` **hanya** kepada klien yang terdaftar di `guild_id` tersebut.
  - Saring `_build_user_voice_map(allowed_guild_ids)` agar hanya memuat entri dari server yang benar-benar diikuti oleh pengguna terkait (atau cukup status voice milik `uid` sendiri).
- **Estimasi Dampak RAM & UX:** **Mengurangi beban CPU, memori serialisasi JSON, dan trafik WebSocket**; UX pengguna tidak berubah.
- **Sumber Primer:** [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html), [FastAPI WebSockets Documentation](https://fastapi.tiangolo.com/advanced/websockets/).

---

### A-07. [TINGGI] Bypass Filter SSRF (`resolve_dns=False` & HTTP Redirect), `--no-check-certificates`, & Bug `decrypt_secret()`
- **Lokasi:** `/tmp/bot_src/athenaa/app/security/validators.py`, baris `60–78`, `80–112`; `/tmp/bot_src/athenaa/app/services/academy_service.py`, baris `657–660`, `677–730`; `/tmp/bot_src/athenaa/app/services/music_service.py`, baris `662–666`, `2676`, `2733`, `2798`.
- **Analisis Kode:**
  1. **DNS Resolution Nonaktif Secara Default:** `validate_external_url(url, resolve_dns=False)` (`validators.py:80`) tidak menyelesaikan nama domain secara default. Baik `academy_service.py:678, 694` maupun `music_service.py:663` tidak mengaktifkan `resolve_dns=True`. Selain itu, `socket.gethostbyname()` hanya memeriksa 1 alamat IPv4 (mengabaikan IPv6 dan *multi-record DNS*).
  2. **Redirect SSRF Bypass:** `urllib.request.urlopen()` mengikuti redirect HTTP 301/302/307 secara otomatis tanpa memvalidasi ulang lokasi redirect tujuan.
  3. **TLS Verification Dimatikan pada `yt-dlp`:** `music_service.py` menyertakan `--no-check-certificates` (`2676, 2733`) dan `nocheckcertificate: True` (`2798`), membuka risiko serangan *Man-in-the-Middle*.
  4. **Bug Dekripsi Kredensial ICS:** `academy_service.py:659` memanggil `decrypt_secret(raw_val)` hanya dengan **1 argumen**, padahal definisi fungsi di `validators.py:60` membutuhkan 2 argumen wajib (`token: str, key: str`). Akibatnya, setiap URL ICS terenkripsi yang disimpan di database akan selalu gagal didekripsi (`TypeError`) dan diam-diam mengembalikan string kosong.
- **Skenario Eksploitasi (Konseptual):**
  Penyerang memasukkan URL dengan nama domain yang me-resolve ke IP internal (`127.0.0.1` / jaringan privat kontainer) atau URL publik yang merespons `302 Found` menuju alamat internal pada fitur sinkronisasi Waskita/Moodle maupun URL radio, sehingga menembus filter SSRF.
- **Rekomendasi Perbaikan:**
  - Ubah default `resolve_dns=True`, gunakan `socket.getaddrinfo()` untuk memeriksa **semua** alamat IPv4 & IPv6 hasil resolusi (tolak `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`), dan pasang *custom* `urllib.request.HTTPRedirectHandler` yang memvalidasi ulang URL tujuan setiap hop redirect.
  - Hapus flag `--no-check-certificates` / `nocheckcertificate: True` pada `yt-dlp`.
  - Perbaiki pemanggilan di `academy_service.py:659` menjadi `decrypt_secret(raw_val, settings.encryption_key)` (sesuai kunci konfigurasi di `settings`).
- **Estimasi Dampak RAM & UX:** 0 MB RAM; tidak mengganggu URL Waskita/Moodle, YouTube, maupun radio yang sah.
- **Sumber Primer:** [OWASP Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

---

### A-08. [TINGGI] Konfigurasi CORS Berbahaya (`allow_origins=["*"]` + `allow_credentials=True`)
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `1315–1322`.
- **Analisis Kode:**
  Middleware CORS dikonfigurasi dengan `allow_origins=["*"]` bersamaan dengan `allow_credentials=True`. Menurut dokumentasi resmi FastAPI/Starlette, kombinasi ini tidak diperbolehkan secara spesifikasi karena saat `allow_credentials=True`, middleware memantulkan header `Origin` dari situs asing mana pun.
- **Skenario Eksploitasi (Konseptual):**
  Jika pengguna yang sedang login di `bot.athenaa.my.id` mengunjungi situs web berbahaya, skrip dari situs tersebut dapat mengirim permintaan lintas-origin dengan kredensial cookie `athenaa_session_token` ke API Athenaa dan membaca seluruh data responsnya.
- **Rekomendasi Perbaikan:**
  Tetapkan daftar *origin* eksplisit: `allow_origins=["https://bot.athenaa.my.id"]` (ditambah origin lokal hanya saat mode pengembangan), serta batasi `allow_methods` dan `allow_headers` sesuai kebutuhan aplikasi.
- **Estimasi Dampak RAM & UX:** 0 MB RAM; tidak memengaruhi akses normal melalui `https://bot.athenaa.my.id`.
- **Sumber Primer:** [FastAPI CORS (Cross-Origin Resource Sharing) Documentation](https://fastapi.tiangolo.com/tutorial/cors/).

---

### A-09. [TINGGI] Validasi File Upload Modul Menggunakan Byte Dummy & Risiko OOM di `/tugas_add`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `3129–3169`; `/tmp/bot_src/athenaa/app/bot/client.py`, baris `3971–3978`.
- **Analisis Kode:**
  1. Pada `api_upload_module()` (`3130–3139`), `sanitize_and_validate_attachment()` memvalidasi variabel `sample_magic` (byte PDF/DOCX dummy yang dibuat sendiri oleh server!), **bukan** `file_bytes` hasil decode `body.content_base64`. Kemudian pada baris `3156–3167`, `file_bytes` asli dari klien langsung ditulis ke **dua direktori sekaligus** (`settings.modules_dir` dan `Path("modules")`) tanpa pemeriksaan magic bytes maupun batas ukuran 15 MB atas data hasil decode.
  2. Pada `/tugas_add` (`client.py:3972`), `raw_bytes = await file_modul.read()` memuat seluruh lampiran Discord ke memori terlebih dahulu sebelum memeriksa apakah ukurannya melebihi 15 MB.
- **Skenario Eksploitasi (Konseptual):**
  Penyerang mengunggah payload `content_base64` berukuran besar atau berisi file non-dokumen (skrip/biner/HTML) berkedok ekstensi `.pdf`, yang lolos validasi dummy dan memenuhi disk dua kali lipat; atau mengirim lampiran Discord Nitro besar ke `/tugas_add` untuk memicu lonjakan memori (OOM).
- **Rekomendasi Perbaikan:**
  - Di `api.py`, decode `content_base64` terlebih dahulu (dengan batas panjang string Base64 ~20 MB sebelum decode), lalu validasi `file_bytes` aktual menggunakan `sanitize_and_validate_attachment(body.filename, file_bytes, max_mb=15)`. Simpan file ke **satu** direktori kanonik saja (`settings.modules_dir`).
  - Di `client.py`, periksa `if file_modul.size > 15 * 1024 * 1024:` **sebelum** memanggil `await file_modul.read()`.
- **Estimasi Dampak RAM & UX:** **Mencegah lonjakan RAM dan duplikasi ruang disk 50%**; tidak mengubah UX bagi pengunggah dokumen `.pdf`/`.doc`/`.docx` yang valid.
- **Sumber Primer:** [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html), [OWASP API4:2023 Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/).

---

### A-10. [TINGGI] Bug Memori & Fungsi Rusak: `/ram_clean` Gagal Total, `MusicPlayerControlView(timeout=None)` Leak, Rate Limiter Unbounded, & Mention Musik Error
- **Lokasi:**
  - `/tmp/bot_src/athenaa/app/services/music_service.py`, baris `2837–2855` (dipanggil `client.py:503–506`).
  - `/tmp/bot_src/athenaa/app/bot/client.py`, baris `2411, 2457, 2470, 2479, 3007`.
  - `/tmp/bot_src/athenaa/app/security/validators.py`, baris `210–228`.
- **Analisis Kode:**
  1. **`clear_music_memory_caches()` Selalu Crash Diam-diam:** Baris `2841` merujuk variabel `_YTDLP_STREAM_CACHE` yang **tidak ada** (nama sebenarnya `_STREAM_EXTRACT_CACHE`), memanggil `.items()` dan `.keys()` pada instance `LRUCache` (yang tidak memiliki method tersebut), serta memanggil `_prune_audio_cache()` yang **tidak pernah didefinisikan**. Karena `client.py:505` menangkap `except Exception: pass`, perintah `/ram_clean` tidak pernah membersihkan cache musik maupun file audio `/tmp/athenaa_audio_cache`.
  2. **Memory Leak `MusicPlayerControlView(timeout=None)`:** Baris `3007` membuat setiap panel tombol interaktif NowPlaying/Queue tidak pernah kedaluwarsa, sehingga seluruh objek View tetap tersimpan di `_view_store` milik `discord.py` hingga kontainer restart.
  3. **Memory Leak `SlidingWindowRateLimiter._hits`:** Di `validators.py:216–227`, entri dictionary per IP/token tidak pernah dihapus meski seluruh timestamp-nya sudah kedaluwarsa.
  4. **Fitur Mention `@Athena` Rusak (`NameError`/`AttributeError`):** `client.py:2470` memanggil `fetch_synced_lyrics` (tidak diimpor), `client.py:2479` merujuk `VERIFIED_RADIO_STATIONS` (tidak diimpor; yang diimpor adalah `get_verified_radios`), dan `client.py:2411, 2457` memanggil `queue_service.get_history()` (method tidak ada di `QueueService`).
- **Rekomendasi Perbaikan:**
  - Perbaiki `clear_music_memory_caches()` agar memanggil `.clear_expired()` pada `_SEARCH_RESULT_CACHE`, `_STREAM_EXTRACT_CACHE`, `_TRACK_META_REGISTRY`, serta implementasikan fungsi pemangkasan file terlama di `_LOCAL_AUDIO_CACHE_DIR`.
  - Ubah `MusicPlayerControlView` agar menggunakan `timeout=1800` (30 menit).
  - Tambahkan pembersihan periodik entri kosong/kedaluwarsa pada `SlidingWindowRateLimiter._hits` (atau batasi kapasitas maksimum key).
  - Perbaiki pemanggilan `lyrics_service.get_lyrics`, `get_verified_radios()`, dan pembacaan `st.recent_tracks` di `client.py`.
- **Estimasi Dampak RAM & UX:** **Menghemat RAM secara nyata** dan memulihkan fitur mention yang sebelumnya error diam-diam.
- **Sumber Primer:** [OWASP API4:2023 Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/).

---

### A-11. [TINGGI] Logika AutoMod Mudah Di-bypass via Mention `@Athena` & Substring False Positive
- **Lokasi:** `/tmp/bot_src/athenaa/app/bot/client.py`, baris `2236–2253`; `/tmp/bot_src/athenaa/app/services/ai_assistant_service.py`, baris `1508–1532`.
- **Analisis Kode:**
  1. Pada `client.py:2248`, tertulis `if violated and not is_tagging_bot:`. Artinya, pesan yang jelas melanggar AutoMod (promosi judi online, link phishing/invite Discord luar, atau mass-mention) **tidak akan dihapus** jika pengirimnya menambahkan mention `@Athena` di dalam pesan!
  2. Pada `client.py:2236–2239`, pengecualian admin hanya mengecek `administrator` tanpa mengecek `manage_messages`, sehingga moderator resmi server bisa terkena hapus senyap.
  3. Pada `ai_assistant_service.py:1516`, pencocokan kata terlarang memakai `if bw and bw in low:` (substring polos tanpa *word boundary* dan tanpa normalisasi karakter zero-width).
- **Skenario Eksploitasi (Konseptual):**
  Spammer mengirim tautan `discord.gg/...` atau iklan situs terlarang disertai tag `@Athena` di ujung pesan; AutoMod sepenuhnya meloloskan pesan tersebut.
- **Rekomendasi Perbaikan:**
  - Hapus pengecualian `and not is_tagging_bot` pada `client.py:2248` agar AutoMod selalu berjalan lebih dulu sebelum pemrosesan mention AI.
  - Tambahkan `manage_messages` sebagai kriteria moderator yang dikecualikan dari AutoMod.
  - Normalisasi karakter tak terlihat (zero-width) dan gunakan regex *word boundary* (`\b`) untuk kata tunggal di `evaluate_automod_message()`.
- **Estimasi Dampak RAM & UX:** 0 MB RAM; menutup bypass moderasi tanpa mengganggu percakapan wajar.
- **Sumber Primer:** [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

---

### A-12. [SEDANG-TINGGI] Mutasi Global `/ai_model` Tanpa Cek Owner, Spam `/ram_clean`, & Task `sleeptimer` Tidak Pernah Dibatalkan
- **Lokasi:** `/tmp/bot_src/athenaa/app/bot/client.py`, baris `2224–2233`, `2568–2571`, `5153–5183`, `5377–5418`, `5442–5457`, `5486–5519`.
- **Analisis Kode:**
  1. `/ai_model` (`5496–5500`) mengubah `os.environ["AI_AUTOPLAY_MODEL"]` dan `settings.ai_autoplay_model` secara **global untuk seluruh server** tanpa memeriksa apakah pemanggil adalah Bot Owner.
  2. `!ram_clean` (`2224`), `/ram_clean` (`5443`), dan `@Athena bersihkan ram` (`2568`) dapat dipanggil siapa pun tanpa cooldown, menjalankan `gc.collect(2)` dan `malloc_trim(0)` secara sinkron di *main event loop* Discord.
  3. Pada `/sleeptimer` (`5156–5160`), memilih `menit=0` hanya mengirim pesan *"Sleep Timer Dibatalkan"* tanpa membatalkan `asyncio.Task` yang sudah dibuat sebelumnya di baris `5183`! Jika dipanggil berulang kali, beberapa timer lama akan tetap mengeksekusi `stop` dan memutus voice secara tak terduga.
- **Rekomendasi Perbaikan:**
  - Batasi `/ai_model` dan `/ram_clean` / `!ram_clean` khusus untuk Bot Owner (atau Admin Server dengan cooldown 60 detik untuk `/ram_clean`).
  - Simpan dictionary `self._sleep_timers[guild_id] = task` dan panggil `old_task.cancel()` saat timer baru dipasang atau saat `menit=0`.
  - Batasi jumlah `/remindme` aktif per user (mis. maks 5 pengingat aktif).
- **Estimasi Dampak RAM & UX:** Mencegah penumpukan background `asyncio.Task` dan jeda event loop; tidak mengganggu penggunaan normal.
- **Sumber Primer:** [OWASP API5:2023 Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/), [OWASP API4:2023 Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/).

---

## Kategori B — Ada Trade-off RAM / Performa / Kenyamanan UX (Wajib Didiskusikan dengan Pemilik Bot Sebelum Diterapkan)

### B-01. [KRITIS] Kontradiksi Logika Host Lock: Hardcode `is_admin=True` / `is_owner=True` & Spoofing `actor_id` di Jalur Musik
- **Lokasi:**
  - `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `2431–2435` (`/music/play`) & `2610–2613` (`/music/control`).
  - `/tmp/bot_src/athenaa/app/bot/client.py`, baris `2331–2558` (mention `@Athena`), `2929–2936` (`_member_context`), `3037` (`MusicPlayerControlView`), `3774–3801`, `4832–5061`.
  - `/tmp/bot_src/athenaa/app/security/validators.py`, baris `154–184` (`can_control_queue`).
- **Analisis Kode & Kontradiksi:**
  1. Arsitektur Athenaa memiliki **Host Lock System** lengkap (`validators.py:154–184` dan transfer host di `queue_service.py:794–838`). Namun pada praktiknya, sistem ini **100% lumpuh** karena `is_admin=True` / `is_owner=True` di-hardcode di REST API (`api.py:2434–2435, 2612–2613`), `_member_context()` (`client.py:2932`), tombol Embed (`client.py:3037`), dan handler mention `@Athena` (`client.py:2338, 2358, 2485, 2498, 2535, 2540`).
  2. Selain itu, perintah `/filter`, `/seek`, `/replay`, `/previous`, `/skipto`, `/move`, `/clear`, `/autoplay`, `/247`, serta mention `@Athena skip/stop/clear/leave/remove/filter` **tidak memeriksa apakah pengguna berada di Voice Channel yang sama** dengan bot! Anggota yang tidak sedang mendengarkan musik (di luar VC) dapat menghentikan, mengosongkan antrean, atau memindahkan filter audio kapan saja.
  3. **Celah Spoofing di Web API:** Pada `api.py:2432` dan `2611`, jika `sess is None`, server menerima `body.requester_id` / `body.actor_id` langsung dari payload JSON klien. Penyerang cukup mengintip `user_id` siapa pun yang sedang berada di Voice Channel (lewat `user_voice_map` di A-06), lalu mengirim `POST /api/guilds/{guild_id}/music/control` dengan `actor_id` milik orang tersebut untuk lolos pengecekan Voice Isolation dan membajak sesi musik server lain!
- **Trade-off UX yang Perlu Didiskusikan:**
  - **Bagian yang wajib segera dikunci:** Menghilangkan spoofing `actor_id` (wajibkan `sess` login pada `/music/play` dan `/music/control`) serta mewajibkan pengguna berada di Voice Channel yang sama untuk mengontrol pemutaran.
  - **Pilihan kebijakan Host Lock untuk didiskusikan:**
    - *Opsi 1 (Ramah Server Pertemanan):* Semua anggota yang berada di Voice Channel yang sama boleh mengontrol musik (tanpa Host Lock ketat), tetapi pengguna di luar VC ditolak.
    - *Opsi 2 (Host Lock Ketat / Configurable):* Aktifkan kembali `can_control_queue()` dengan status `is_admin` dan `dj_role_id` asli (hanya Session Host, DJ Role, dan Admin Server yang boleh `stop`/`skip`/`clear`), atau jadikan opsi *toggle* `host_lock_enabled` di `guild_settings`.
- **Sumber Primer:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [OWASP API1:2023 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

---

### B-02. [TINGGI] Prompt Injection (OWASP LLM01), Multi-Command Abuse, & Kelelahan Kuota Gemini API pada `@Athena`
- **Lokasi:** `/tmp/bot_src/athenaa/app/services/ai_assistant_service.py`, baris `286–292`, `817–905`, `1439–1468`; `/tmp/bot_src/athenaa/app/bot/client.py`, baris `2258–2286`.
- **Analisis Kode:**
  1. **Penggabungan System Prompt & User Input:** Di `ai_assistant_service.py:286`, `system_instruction` dan `prompt` (yang mengandung pesan user mentah, memori obrolan channel, serta judul lagu dari YouTube) digabungkan menjadi satu string `full_prompt` di `contents` alih-alih menggunakan field terpisah `systemInstruction` milik Gemini REST API.
  2. **Eksekusi Multi-Command Tanpa Batas Ketat:** `parse_gemini_action_plan_json()` (`832`) mengizinkan LLM menghasilkan hingga **12 aksi beruntun** dalam 1 pesan, termasuk aksi destruktif/sistem seperti `cmd_stop`, `cmd_leave`, `cmd_clear`, `cmd_247`, `cmd_ram_clean`, dan `cmd_sync_waskita`.
  3. **Tanpa Cooldown Per-User:** Tidak ada rate limit pada mention `@Athena`, sehingga 1 pengguna dapat mengirim pesan mention berulang kali untuk menghabiskan kuota seluruh API Key Gemini yang dikonfigurasi dan memicu request HTTP berulang ke Google News RSS & Wikipedia.
- **Skenario Eksploitasi (Konseptual):**
  Pengguna menyisipkan instruksi manipulasi prompt pada mention `@Athena` (atau melalui judul lagu/riwayat obrolan sebelumnya) agar *Intent Translator* mengeluarkan rangkaian aksi seperti `cmd_clear`, `cmd_stop`, `cmd_leave`, dan `cmd_ram_clean` sekaligus, atau melakukan spam mention untuk melumpuhkan kuota Gemini API bagi seluruh server.
- **Trade-off UX & Performa yang Perlu Didiskusikan:**
  - Memisahkan `systemInstruction` secara resmi di payload Gemini dan menghapus `cmd_ram_clean` / `cmd_sync_waskita` dari `ALLOWED_AI_ACTIONS` tidak mengganggu UX.
  - Namun, penambahan **cooldown mention per-user** (mis. 5–8 detik) dan pembatasan **maksimal 3 aksi per mention** (atau membatasi aksi destruktif `stop`/`clear`/`leave` hanya untuk user yang berada di VC) dapat sedikit mengubah gaya interaksi cepat pengguna sehingga perlu disepakati pemilik bot.
- **Sumber Primer:** [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

---

### B-03. [TINGGI] DoS / Queue Flooding, Rate Limit Global Terlalu Longgar, & Penggunaan Cache Disk/tmpfs Audio
- **Lokasi:** `/tmp/bot_src/athenaa/app/services/queue_service.py`, baris `207–321`; `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `120`, `2488–2523`, `2860–2984`; `/tmp/bot_src/athenaa/app/services/music_service.py`, baris `2644–2698`.
- **Analisis Kode:**
  1. **Antrean Tanpa Batas (`MAX_QUEUE_SIZE`):** `QueueService.add_track()` tidak membatasi panjang `state.queue`. Pengulangan impor playlist (50 lagu per klik) dapat menumpuk ribuan objek `QueueItemModel` di memori dan tabel `playlists`/`playlist_items` di SQLite.
  2. **Rate Limiter Terlalu Longgar:** `api.py:120` menetapkan `max_requests=1000` per 60 detik untuk semua endpoint termasuk endpoint berat yang memicu `yt-dlp`, scraping HTML YouTube/Spotify, dan penulisan file modul.
  3. **Cache Audio Lokal di `/tmp`:** `_try_cache_youtube_audio_file()` (`music_service.py:2666`) mengizinkan hingga 20 file audio di `/tmp/athenaa_audio_cache` (tanpa batas total MB). Pada kontainer Pterodactyl yang me-mount `/tmp` sebagai `tmpfs` (RAM disk), 20 file audio berdurasi 5–15 menit dapat menyedot **100–250 MB RAM** secara langsung.
- **Trade-off RAM / UX yang Perlu Didiskusikan:**
  - Menetapkan `MAX_QUEUE_SIZE` (mis. 100–200 lagu per guild), menurunkan batas file cache `/tmp` (mis. maks 5 file atau total <= 50 MB), dan menerapkan *tiered rate limiting* (mis. 20 req/menit untuk `/music/play`, `/resolve`, `/import-spotify`, `/modules/upload`, `/sync-moodle`) sangat efektif menjaga stabilitas RAM kontainer Pterodactyl, tetapi membatasi pengguna yang biasa mengimpor banyak playlist sekaligus.
- **Sumber Primer:** [OWASP API4:2023 Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/).

---

### B-04. [SEDANG] Tidak Adanya Pembatasan Peran pada Command Manajemen Tugas Akademik di Discord
- **Lokasi:** `/tmp/bot_src/athenaa/app/bot/client.py`, baris `3946–4149`.
- **Analisis Kode:**
  Seluruh slash command `/tugas_add`, `/tugas_done`, `/tugas_hapus`, `/sync_waskita`, dan `/sync_moodle` dapat dieksekusi oleh **anggota mana pun** di server Discord tanpa pemeriksaan peran (Admin/Moderator/Pembuat Tugas).
- **Skenario Eksploitasi (Konseptual):**
  Satu anggota iseng (atau akun baru) dapat menghapus seluruh daftar tugas kuliah server dengan `/tugas_hapus`, menandai semua tugas belum dikerjakan sebagai selesai lewat `/tugas_done` (menghentikan pengingat H-3d/H-6h/H-1h untuk seluruh kelas), atau menyuntikkan jadwal palsu melalui `/sync_waskita ical_url:<url_palsu>`.
- **Trade-off UX yang Perlu Didiskusikan:**
  - Di server kelas mahasiswa, kolaborasi bersama untuk menambah tugas (`/tugas_add`) sering diinginkan agar siapa saja bisa mencatat tugas baru.
  - **Rekomendasi untuk didiskusikan:** Izinkan semua member memakai `/tugas` & `/tugas_add`, tetapi batasi `/tugas_hapus`, `/tugas_done` (atau hanya pembuat tugas + Admin), dan parameter `ical_url` pada `/sync_waskita` khusus untuk Admin Server atau role khusus (mis. `PJ Matkul` / `Komting`).
- **Sumber Primer:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

---

### B-05. [SEDANG] Token Sesi Tanpa Masa Kedaluwarsa (TTL) & Penyimpanan di `localStorage`
- **Lokasi:** `/tmp/bot_src/athenaa/app/web/routes/api.py`, baris `1005–1225`, `1970–2006`; `/tmp/bot_src/athenaa/app/database.py`, baris `236–259`.
- **Analisis Kode:**
  1. Tabel `discord_user_sessions` dan `discord_sessions` tidak memiliki kolom `expires_at` dan `_get_session_from_token()` tidak pernah memeriksa umur token. Token tetap aktif selamanya selama belum tergeser oleh 5 sesi baru.
  2. Token sesi disimpan di `window.localStorage` (`athenaa_session_token`), sehingga apabila terjadi celah XSS di sisi frontend SPA, penyerang dapat langsung mencuri token sesi permanen tersebut.
- **Trade-off UX & Usaha Refactoring yang Perlu Didiskusikan:**
  - Menambahkan `expires_at` (mis. 7 hari, selaras dengan `max_age=604800` cookie) akan meminta pengguna login ulang seminggu sekali.
  - Memindahkan autentikasi sepenuhnya ke cookie `HttpOnly; Secure; SameSite=Lax` (menghapus `localStorage` dan `?session_token=`) meningkatkan ketahanan terhadap XSS secara drastis, tetapi membutuhkan pembaruan pada skrip frontend SPA (`athenaa-ui-v51.js`) dan autentikasi WebSocket.
- **Sumber Primer:** [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).

---

## Ringkasan Prioritas Implementasi

1. **Tahap 1 — Eksekusi Segera (Kategori A — Zero RAM Overhead, Zero UX Friction):**
   - Pasang *auth dependency* wajib pada `PATCH/GET /settings`, `/tasks*`, `/modules*`, `/playlists*`, `/favorites*`, dan `/afk*` (**A-01, A-02**).
   - Kunci `/api/admin/*` khusus Bot Owner dan evaluasi admin per-server di `/rpg/activity` (**A-03**).
   - Nonaktifkan atau kunci total `/music/stream` dan tolak `stream_url` mentah dari klien (**A-04**).
   - Tambahkan OAuth2 `state`, perbaiki `postMessage` origin, escape HTML callback, perketat host check & CORS (**A-05, A-08**).
   - Autentikasi `/ws` dan isolasi broadcast + `user_voice_map` per-guild (**A-06**).
   - Aktifkan `resolve_dns=True` + validasi redirect SSRF, hapus `--no-check-certificates`, perbaiki `decrypt_secret()` (**A-07**).
   - Perbaiki validasi file upload asli & cek ukuran sebelum `.read()` (**A-09**).
   - Perbaiki `clear_music_memory_caches()`, timeout `MusicPlayerControlView`, pruning rate limiter, bug mention, bypass AutoMod, `/ai_model`, dan `sleeptimer` (**A-10, A-11, A-12**).
2. **Tahap 2 — Diskusi Kebijakan dengan Pemilik Bot (Kategori B):**
   - Tentukan kebijakan Host Lock vs bebas kontrol di VC yang sama (**B-01**).
   - Tentukan cooldown mention AI & batas aksi multi-command (**B-02**).
   - Tentukan batas `MAX_QUEUE_SIZE` dan batas ukuran cache audio `/tmp` sesuai kuota RAM Pterodactyl (**B-03**).
   - Tentukan hak akses `/tugas_hapus`, `/tugas_done`, dan `/sync_waskita` (**B-04**) serta TTL sesi & migrasi cookie `HttpOnly` (**B-05**).
