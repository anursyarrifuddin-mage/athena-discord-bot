# Riset Desain UI/UX Modern & Blueprint Redesign Web Interface Athenaa (`bot.athenaa.my.id`)

Dokumen ini merangkum hasil riset desain antarmuka modern berbasis sumber primer (Apple Human Interface Guidelines, Linear UI, W3C WCAG 2.1/2.2, Radix UI Colors, Tailwind CSS, Spotify Encore, Raycast, MDN Web Docs, dan web.dev) serta audit langsung terhadap arsitektur SPA React yang sedang berjalan di `app/web/static/index.html` dan `app/web/routes/api.py` (`UI_CUSTOMIZATION_INJECTION`).

Seluruh rekomendasi mempertahankan identitas palet 4-gradasi **Royal Amethyst & Velvet Lavender** pilihan pengguna:
- **Deep Royal Plum:** `#4C2365`
- **Muted Amethyst:** `#7F5D99`
- **Soft Lavender:** `#9E7EB5`
- **Pastel Lilac Mist:** `#C4A4DA`

---

## 0. Audit Kondisi UI & Arsitektur Teknis Saat Ini

Hasil inspeksi langsung pada `/tmp/bot_src/athenaa/app/web/static/index.html`, `/tmp/bot_src/athenaa/app/web/routes/api.py` (baris 129–691 dan 3424–3432), serta bundle `/tmp/bot_src/athenaa/app/web/static/assets/athenaa-ui-v51.js` menunjukkan arsitektur berikut:

1. **Mekanisme Rendering & Injeksi Non-Destruktif**:
   - `index.html` menjalankan SPA React terkompilasi (`athenaa-ui-v51.js?v=20261118v63`) + Tailwind CSS (`index-DxVQMrIP.css?v=20261118v63`) dengan tiga keluarga font Google Fonts yang sudah sangat tepat: `Outfit` (500–700), `Plus Jakarta Sans` (400–700), dan `JetBrains Mono` (400–600).
   - FastAPI menyuntikkan blok `UI_CUSTOMIZATION_INJECTION` tepat sebelum `</body>` pada setiap request halaman utama (`api.py` baris 3429). Artinya, seluruh redesign visual dapat diimplementasikan **100% kompatibel** tanpa merusak bundle React maupun state WebSocket.
2. **Fitur Real-Time yang Wajib Dipertahankan Utuh**:
   - Koneksi **WebSocket** sinkronisasi progres pemutar & status server.
   - **Ringkasan Server**, **Pemutar & Lirik** (termasuk form impor Spotify/YouTube URL & sinkronisasi LRCLIB), **Studio DSP & Ambience** (`#athenaa-studio-dsp-rack` yang terpasang di dalam kartu Pemutar & Lirik, tepat di atas form impor, serta otomatis dilepas di tab lain), **Antrean Musik**, **Tugas Akademik**, **Leaderboard**, **AFK**, dan **Pengaturan Server** (`#athenaa-koya-carl-suite` untuk AutoMod/Sensor Kata, Anti-Link, Anti-Spam, Welcome/Goodbye, Auto-Role, dan AI Chatbot dengan isolasi peran Admin vs. Member per guild).
3. **Temuan Celah Visual & Performa yang Perlu Diperbaiki**:
   - **Kebocoran Permukaan Abu-Abu Mentah**: Bundle React masih menggunakan beberapa kelas latar belakang netral (`bg-[#1A1A1A]`, `bg-[#202020]`, `bg-[#232323]`, `bg-[#252525]`, `bg-[#2A2A2A]`, `bg-[#333333]`, `bg-[#3E3E3E]`) yang belum semuanya tercakup di `UI_CUSTOMIZATION_INJECTION` (saat ini baru meng-override `#121212`, `#181818`, `#1F1F1F`, `#242424`, dan `#282828`). Akibatnya, sebagian kartu sekunder atau tombol masih tampil abu-abu datar.
   - **Overhead `MutationObserver` Tanpa Throttling**: Di `api.py` baris 683–688, `MutationObserver` memantau seluruh `document.documentElement` (`subtree: true`) dan langsung memanggil `applyAthenaaUiCleanup()` (yang menjalankan beberapa `document.querySelectorAll`) pada setiap perubahan DOM—termasuk pembaruan WebSocket progres lagu tiap detik. Ini perlu di-debounce/dijadwalkan lewat `requestAnimationFrame` dan dipersempit ke `#root`.
   - **Properti Transisi Tidak Efisien**: Kelas `.studio-dsp-btn` (baris 273) masih memakai `transition: all 140ms ease;` alih-alih properti spesifik (`transform`, `opacity`, `background-color`, `border-color`), yang bertentangan dengan praktik animasi compositor berkinerja tinggi ([web.dev Compositor Properties](https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count)).
   - **Navigasi Mobile Inline**: `#athenaa-mobile-bottom-nav` (baris 289–295) masih memakai style inline hardcoded dan belum menampilkan indikator tab aktif yang jelas.

---

## 1. Eksplorasi 3 Arah Konsep Visual Modern & Elegan

Seluruh arah konsep dirancang khusus untuk konteks **Dark-Only Audio & Server Console**. Sesuai [Apple Human Interface Guidelines — Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode), antarmuka media imersif memang ideal menggunakan tampilan gelap permanen agar *chrome* UI mundur ke belakang dan fokus pengguna tertuju pada konten audio, lirik, dan kendali real-time.

### Konsep A: *Velvet Glass Studio* (Inspirasi: Apple Music Web & Linear UI) — **Rekomendasi Utama**
- **Nuansa Visual**: Permukaan gelap plum-obsidian (`#0C0612` hingga `#1B0F29`) yang dipadukan dengan lapisan elevasi *base vs. elevated* ala [Apple HIG Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode) serta kontrol translusen tipis (*tinted frosted glass*) hanya pada elemen navigasi melayang (top bar, bottom player/mobile bar, dan dropdown), dengan batas hairline 1px berwarna Lavender tipis (`rgba(158, 126, 181, 0.22)`) dan kilau top-edge 1px (`inset 0 1px 0 rgba(196, 164, 218, 0.14)`). Pendekatan ini mengambil pelajaran dari evolusi [Apple Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/liquid-glass) dan [Linear UI Redesign](https://linear.app/now/how-we-redesigned-the-linear-ui) yang membatasi saturasi warna *chrome* agar tetap tenang, tak lekang waktu, dan berfokus pada keterbacaan tinggi.
- **Kelebihan**:
  - Paling selaras dengan karakter 4-gradasi *Royal Amethyst & Velvet Lavender*—terasa mewah, hangat, dan musikal tanpa norak.
  - Hierarki kedalaman antar lapisan (Canvas -> Sidebar/Main -> Card -> Elevated Control) sangat mudah dipindai mata dalam penggunaan jangka panjang.
  - Kompatibilitas 100% dengan DOM SPA saat ini cukup melalui CSS token & selector terarah.
- **Kekurangan**: Jika `backdrop-filter` dipakai berlebihan di terlalu banyak kartu sekaligus, beban GPU pada laptop lama/mobile bisa meningkat.
- **Dampak Performa Browser**: **Rendah–Sangat Ringan** *jika* `backdrop-filter: blur(12px)` dibatasi hanya pada 2–3 lapisan *chrome* tetap (header, player footer, modal/dropdown), sementara kartu konten di dalam `<main>` menggunakan latar solid-translusen (`rgba(27, 15, 41, 0.92)`) tanpa blur live.

### Konsep B: *Obsidian Amethyst Minimalist* (Inspirasi: Raycast & Tidal)
- **Nuansa Visual**: Estetika ultra-presisi, tajam, dan nyaris monokromatik dengan kanvas gelap pekat (`#0B0610`), permukaan kartu datar tanpa gradasi mencolok (`#140C1D`), dan aksen `#C4A4DA` / `#9E7EB5` yang sangat hemat (hanya muncul pada elemen aktif, tombol CTA utama, dan fokus keyboard). Terinspirasi dari filosofi [Raycast](https://www.raycast.com/blog/a-technical-deep-dive-into-the-new-raycast) yang mengutamakan responsivitas instan dan rasa antarmuka *native* ("making things behave right"), serta kepadatan informasi rapi ala Tidal Desktop.
- **Kelebihan**:
  - Kontras teks tertinggi di kelasnya (mendekati AAA di seluruh panel).
  - Nol efek blur berat (*zero backdrop-filter* pada konten), sangat cepat di perangkat berspesifikasi rendah dan konsumsi RAM/GPU paling minimal.
  - Sangat cocok untuk tab padat data seperti *Pengaturan Server*, *AutoMod*, *Tugas Akademik*, dan *Leaderboard*.
- **Kekurangan**: Bisa terasa terlalu "dingin" atau klinis seperti *developer tool* untuk pengalaman mendengarkan musik & lirik jika tidak diberi sentuhan atmosfer tipis di area *Now Playing*.
- **Dampak Performa Browser**: **Sangat Ringan (Terbaik)** — 100% memanfaatkan warna solid, border 1px, dan transisi compositor `transform`/`opacity`.

### Konsep C: *Bento Audio Atelier* (Inspirasi: Spotify Encore Modular Cards & Bento Grid)
- **Nuansa Visual**: Mengorganisasi konsol ke dalam modul-modul kartu *bento* berkotak rapi dengan radius konsisten (`16px` untuk kartu induk, `10px` untuk sub-modul), pemisahan visual tegas antar fungsi (Kartu Pemutar, Rak Studio DSP, Panel Lirik, Modul AutoMod 2x2), serta hierarki tipografi display yang ekspresif. Mengadopsi prinsip komposisi modular dari [Spotify Engineering — Encore Design System](https://engineering.atspotify.com/2023/05/multiple-layers-of-abstraction-in-design-systems) yang menyediakan *default* terstruktur namun tetap fleksibel lewat pola *slot*.
- **Kelebihan**:
  - Struktur informasi paling jelas untuk pengguna baru; setiap fitur (DSP, Ambience, AutoMod, Welcome/Goodbye) punya "rumah" visual yang tegas.
  - Sangat ramah untuk tata letak responsif 1-kolom di mobile dan 2-kolom di desktop.
- **Kekurangan**: Di layar sempit (1280px atau mobile), terlalu banyak kartu bersarang (*nested cards*) dapat memakan ruang vertikal dan membuat tampilan terasa terkotak-kotak bila padding tidak dikalibrasi ketat.
- **Dampak Performa Browser**: **Ringan** — mengandalkan CSS Grid/Flexbox dan `contain: layout paint` ([MDN CSS Containment](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/contain)) pada setiap kartu bento agar pembaruan satu modul (mis. progres lagu) tidak memicu *repaint* modul lain.

### Matriks Perbandingan & Keputusan Rekomendasi

| Dimensi Evaluasi | Konsep A: *Velvet Glass Studio* | Konsep B: *Obsidian Amethyst Minimalist* | Konsep C: *Bento Audio Atelier* |
| :--- | :--- | :--- | :--- |
| **Kesan Estetika** | Elegan, atmosferik, studio audio modern | Tajam, presisi, ultra-clean | Terstruktur, modular, mudah dipindai |
| **Keselarasan 4-Gradasi Ungu** | Sangat Tinggi (memanfaatkan seluruh 4 pita) | Tinggi (dominan gelap + aksen Lilac) | Tinggi (pita warna membedakan peran modul) |
| **Beban GPU/RAM Browser** | Rendah (blur dibatasi di 2–3 surface) | Paling Rendah (tanpa blur) | Rendah (isolasi repaint via `contain`) |
| **Kompatibilitas SPA React** | 100% via `UI_CUSTOMIZATION_INJECTION` | 100% via `UI_CUSTOMIZATION_INJECTION` | 95% via injeksi (optimal di tab Settings & DSP) |

**Keputusan Rekomendasi**: Terapkan **Hibrida Konsep A (*Velvet Glass Studio*) + Disiplin Modular Konsep C (*Bento*) untuk Pengaturan & DSP**. Artinya, gunakan atmosfer *Velvet Glass* yang ringan pada *chrome* utama dan kartu *Pemutar & Lirik*, sambil menerapkan ketajaman kontras ala *Obsidian Minimalist* dan struktur grid *Bento* pada *Studio DSP & Ambience* serta *Pengaturan Server*.

---

## 2. Arsitektur Design Tokens 3-Layer & Verifikasi Kontras WCAG 2.1

Arsitektur token di bawah ini mengikuti prinsip spesifikasi [W3C Design Tokens Format Module 2025.10](https://www.w3.org/community/reports/design-tokens/CG-FINAL-format-20251028/), sistem skala fungsional 12-langkah dari [Radix UI Colors — Understanding the Scale](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale), serta variabel tema CSS modern pada [Tailwind CSS Theme Variables](https://tailwindcss.com/docs/theme). Seperti ditegaskan pula dalam [Linear UI Redesign](https://linear.app/now/how-we-redesigned-the-linear-ui), membatasi jumlah variabel inti dan menurunkannya secara sistematis ke lapisan elevasi menjamin konsistensi kontras di seluruh antarmuka.

### 2.1 Layer 1 -> Layer 2 -> Layer 3 (Siap Pakai di `:root`)

```css
:root {
  /* =========================================================
     LAYER 1: PRIMITIVE TOKENS (Nilai Mentah & Palet 4-Gradasi)
     ========================================================= */
  /* 4-Gradasi Identitas Pengguna (Jangan diubah) */
  --prim-plum-700: #4C2365;       /* Deep Royal Plum */
  --prim-amethyst-500: #7F5D99;   /* Muted Amethyst */
  --prim-lavender-400: #9E7EB5;   /* Soft Lavender */
  --prim-lilac-300: #C4A4DA;      /* Pastel Lilac Mist */

  /* Skala Gelap Turunan Plum (Radix Step 1–5 equivalent untuk Dark Mode) */
  --prim-void-950: #0C0612;       /* Step 1: App canvas base */
  --prim-void-900: #130A1C;       /* Step 2: Panel & sidebar */
  --prim-void-850: #1B0F29;       /* Step 3: Card surface */
  --prim-void-800: #241437;       /* Step 4: Elevated / hover surface */
  --prim-void-750: #2F1A47;       /* Step 5: Active / selected surface */

  /* Skala Teks & Ink (Radix Step 11–12 equivalent) */
  --prim-ink-100: #F7F2FC;        /* Step 12: High-contrast primary text */
  --prim-ink-200: #C9B8DB;        /* Step 11: Secondary / muted text */
  --prim-ink-950: #14081E;        /* Dark ink untuk tombol aksen terang */

  /* Status Semantik (Terharmonisasi untuk Dark Mode) */
  --prim-mint-300: #6EE7B7;       /* Online / WebSocket connected */
  --prim-amber-300: #FCD34D;      /* AFK / Warning */
  --prim-rose-300: #FDA4AF;       /* Danger / AutoMod alert */

  /* =========================================================
     LAYER 2: SEMANTIC TOKENS (Peran Fungsional & Elevasi)
     ========================================================= */
  --bg-canvas: var(--prim-void-950);
  --bg-chrome: rgba(19, 10, 28, 0.86);
  --bg-panel: var(--prim-void-900);
  --bg-surface: var(--prim-void-850);
  --bg-surface-elevated: var(--prim-void-800);
  --bg-surface-active: var(--prim-void-750);
  --bg-accent-deep: var(--prim-plum-700);
  --bg-accent-mid: var(--prim-amethyst-500);

  --text-primary: var(--prim-ink-100);
  --text-secondary: var(--prim-ink-200);
  --text-accent: var(--prim-lilac-300);
  --text-accent-subtle: var(--prim-lavender-400);
  --text-on-accent: var(--prim-ink-950);

  /* Border Scale (Radix Step 6–8 equivalent) */
  --border-subtle: rgba(158, 126, 181, 0.18);      /* Non-interaktif */
  --border-interactive: rgba(158, 126, 181, 0.34); /* Input, tombol, kartu */
  --border-strong: rgba(196, 164, 218, 0.52);      /* Hover / aktif */
  --ring-focus: var(--prim-lilac-300);             /* Focus-visible ring */

  /* Status */
  --status-online: var(--prim-mint-300);
  --status-warning: var(--prim-amber-300);
  --status-danger: var(--prim-rose-300);

  /* Typography & Radii */
  --font-display: 'Outfit', system-ui, sans-serif;
  --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
  --radius-card: 16px;
  --radius-control: 10px;
  --radius-pill: 9999px;

  /* =========================================================
     LAYER 3: COMPONENT TOKENS (Spesifik Komponen Athenaa)
     ========================================================= */
  --btn-cta-bg: linear-gradient(135deg, var(--prim-lilac-300) 0%, var(--prim-lavender-400) 100%);
  --btn-cta-text: var(--text-on-accent);
  --btn-cta-shadow: 0 4px 14px rgba(76, 35, 101, 0.45);

  --dsp-rack-bg: linear-gradient(160deg, rgba(76, 35, 101, 0.34) 0%, rgba(27, 15, 41, 0.94) 100%);
  --dsp-pill-bg: rgba(76, 35, 101, 0.32);
  --dsp-pill-hover-bg: rgba(127, 93, 153, 0.44);
  --dsp-pill-active-bg: var(--btn-cta-bg);
  --dsp-pill-active-text: var(--text-on-accent);

  --input-bg: rgba(19, 10, 28, 0.92);
  --input-border: var(--border-interactive);
  --input-focus-border: var(--prim-lilac-300);
  --input-focus-ring: 0 0 0 2px rgba(196, 164, 218, 0.28);

  --mobile-nav-bg: rgba(19, 10, 28, 0.94);
  --mobile-nav-item-bg: var(--bg-surface);
  --mobile-nav-item-active-bg: var(--bg-accent-deep);
}
```

### 2.2 Verifikasi Matematis Rasio Kontras WCAG 2.1 (AA & AAA)

Seluruh rasio di bawah ini dihitung menggunakan rumus *relative luminance* resmi [W3C WCAG 2.2/2.1 SC 1.4.3 Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) (syarat teks normal **>= 4.5:1**, teks besar **>= 3.0:1**, AAA **>= 7.0:1**) dan [W3C WCAG 2.1 SC 1.4.11 Non-text Contrast](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html) (komponen UI & indikator fokus **>= 3.0:1**):

| Penggunaan Pasangan Warna | Foreground | Background | Rasio Kontras | Status WCAG 2.1 | Catatan Penggunaan |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Teks Primer di Canvas | `#F7F2FC` | `#0C0612` | **18.15 : 1** | **AAA** | Judul utama & isi teks |
| Teks Primer di Panel/Sidebar | `#F7F2FC` | `#130A1C` | **17.52 : 1** | **AAA** | Item navigasi aktif |
| Teks Primer di Kartu | `#F7F2FC` | `#1B0F29` | **16.62 : 1** | **AAA** | Judul lagu, lirik aktif, label form |
| Teks Primer di Elevated | `#F7F2FC` | `#241437` | **15.49 : 1** | **AAA** | Dropdown, modal, popover |
| Teks Primer di Deep Royal Plum | `#F7F2FC` | `#4C2365` | **10.98 : 1** | **AAA** | Badge, tab aktif, banner header |
| Teks Sekunder di Kartu | `#C9B8DB` | `#1B0F29` | **9.91 : 1** | **AAA** | Nama artis, deskripsi sub-form |
| **Pastel Lilac Mist** di Kartu | `#C4A4DA` | `#1B0F29` | **8.43 : 1** | **AAA** | Heading aksen, status DSP, tautan |
| **Pastel Lilac Mist** di Deep Plum | `#C4A4DA` | `#4C2365` | **5.57 : 1** | **AA Normal** | Pill status di atas `#4C2365` |
| **Soft Lavender** di Kartu | `#9E7EB5` | `#1B0F29` | **5.32 : 1** | **AA Normal** | Label sekunder & metadata |
| **Soft Lavender** di Elevated | `#9E7EB5` | `#241437` | **4.96 : 1** | **AA Normal** | Batas aman teks kecil di surface hover |
| **Muted Amethyst** di Kartu | `#7F5D99` | `#1B0F29` | **3.42 : 1** | **Hanya UI/Non-Text** | **Dilarang untuk teks normal!** Pakai untuk border/slider/ikon besar (>=3:1) |
| Teks Gelap di CTA **Lilac Mist** | `#14081E` | `#C4A4DA` | **8.93 : 1** | **AAA** | Tombol CTA utama (Play, Simpan) |
| Teks Gelap di CTA **Soft Lavender** | `#14081E` | `#9E7EB5` | **5.64 : 1** | **AA Normal** | Ujung gradasi CTA & state hover |
| Teks Terang di **Muted Amethyst** | `#F7F2FC` | `#7F5D99` | **4.85 : 1** | **AA Normal** | Tombol sekunder / tag solid |
| Focus Ring vs Kartu | `#C4A4DA` | `#1B0F29` | **8.43 : 1** | **Lulus 1.4.11** | Outline fokus keyboard (`:focus-visible`) |
| Status Online / AFK / AutoMod | `#6EE7B7` / `#FCD34D` / `#FDA4AF` | `#1B0F29` | **12.01 / 12.70 / 9.68 : 1** | **AAA** | Indikator WebSocket, AFK, & Moderasi |

> **Aturan Keras Aksesibilitas Palet**: Sesuai temuan kalkulasi di atas dan panduan [Apple HIG Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode) yang menganjurkan kontras >= 4.5:1 (dan mengejar 7:1 untuk teks kecil), **`#7F5D99` (Muted Amethyst) tidak boleh dipakai sebagai warna teks isi/label kecil di atas latar gelap**. Gunakan `#7F5D99` secara eksklusif sebagai *surface* (dengan teks `#F7F2FC`), *border* interaktif, *track* slider audio, atau aksen grafis non-teks.

---

## 3. Blueprint Perbaikan Tata Letak, Tipografi & Performa

### 3.1 Hierarki Visual & Sistem Spasi (8px Grid / 4px Micro-Grid)
- **Tutup Kebocoran Warna SPA**: Petakan seluruh kelas abu-abu lama di React bundle (`bg-[#1A1A1A]`, `bg-[#202020]`, `bg-[#232323]`, `bg-[#252525]`, `bg-[#2A2A2A]`, `bg-[#333333]`, `bg-[#3E3E3E]`) ke token elevasi `--bg-surface`, `--bg-surface-elevated`, dan `--bg-surface-active` sehingga tidak ada lagi blok abu-abu mentah di tab *Antrean*, *Leaderboard*, *Tugas Akademik*, atau *AFK*.
- **Elevasi Berbasis Luminansi (Bukan Drop Shadow Berat)**: Ikuti aturan *base vs. elevated* dari [Apple HIG Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode) dan [Radix Colors Composing a Palette](https://www.radix-ui.com/colors/docs/palette-composition/composing-a-palette)—tiap lapisan yang lebih dekat ke pengguna naik sedikit lebih terang (`#0C0612` -> `#130A1C` -> `#1B0F29` -> `#241437`) dipisahkan oleh border 1px `--border-subtle` dan *inner top highlight* 1px (`inset 0 1px 0 rgba(196, 164, 218, 0.10)`).
- **Skala Spasi Konsisten**: Padding kartu utama `20px` (`p-5`), sub-kartu `16px` (`p-4`), jarak antar blok vertikal `16px–20px` (`gap-4` / `gap-5`), jarak antar pill DSP `6px–8px` (`gap-1.5` / `gap-2`).

### 3.2 Typography Pairing (Mengoptimalkan Font yang Sudah Dimuat di `index.html`)
`index.html` sudah memuat tiga font yang sangat ideal—tanpa menambah *network request* font baru:
- **Display & Judul Halaman / Judul Lagu (`Outfit`, 600–700)**: Beri `letter-spacing: -0.02em` pada `h1`/`h2` dan judul trek aktif agar terasa modern dan ekspresif, sejalan dengan pemakaian font display khusus untuk heading pada [Linear UI Redesign](https://linear.app/now/how-we-redesigned-the-linear-ui).
- **Antarmuka, Navigasi, Lirik & Form (`Plus Jakarta Sans`, 400–600)**: Ukuran minimum teks isi `13px–14px` (`0.8125rem–0.875rem`), `line-height: 1.55` untuk keterbacaan lirik dan deskripsi pengaturan.
- **Telemetri, Timestamp Audio, ID Channel/Role, & Status DSP (`JetBrains Mono`, 500)**: Wajib tambahkan `font-variant-numeric: tabular-nums;` pada durasi lagu (`01:24 / 03:45`), angka EXP *Leaderboard*, dan ping WebSocket agar teks tidak bergetar (*jitter*) setiap detik saat angka berubah.

### 3.3 Glassmorphism Halus Tanpa Lag & Optimasi Performa Browser
Merujuk pada dokumentasi [MDN `backdrop-filter`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter), [Tailwind CSS Backdrop Blur](https://tailwindcss.com/docs/backdrop-filter-blur), [web.dev Compositor-Only Properties](https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count), dan [web.dev `prefers-reduced-motion`](https://web.dev/articles/prefers-reduced-motion):

1. **Kuota Ketat `backdrop-filter`**:
   - Terapkan `backdrop-filter: blur(12px) saturate(135%);` **hanya** pada maksimal 3 permukaan melayang (*chrome*): `<header>`, `<footer>` / mini-player, dan `#athenaa-mobile-bottom-nav` (serta modal/dropdown saat terbuka).
   - **Jangan** memasang `backdrop-filter` pada kartu di dalam area scroll `<main>`, daftar antrean, atau baris leaderboard. Gunakan latar semi-solid (`rgba(27, 15, 41, 0.92)`) agar GPU tidak melakukan *readback* berulang saat scroll.
2. **Aksesibilitas Transparansi & Gerakan**:
   - Hormati preferensi OS melalui `@media (prefers-reduced-transparency: reduce)` ([MDN `prefers-reduced-transparency`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-transparency)) dengan mematikan `backdrop-filter: none` dan menaikkan opasitas latar ke `0.98`.
   - Hormati `@media (prefers-reduced-motion: reduce)` ([web.dev](https://web.dev/articles/prefers-reduced-motion)) dengan menonaktifkan transisi/animasi dekoratif.
3. **Isolasi Repaint & Optimasi Animasi**:
   - Terapkan `contain: layout style paint;` ([MDN `contain`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/contain)) pada `#athenaa-studio-dsp-rack` dan `#athenaa-koya-carl-suite` agar interaksi klik di dalamnya tidak memicu perhitungan layout seluruh halaman.
   - Ganti `transition: all 140ms ease` pada `.studio-dsp-btn` menjadi properti spesifik (`transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease, transform 140ms ease;`) dan hindari animasi `box-shadow` terus-menerus.
4. **Optimasi `MutationObserver` di `UI_CUSTOMIZATION_INJECTION`**:
   - Ubah target observer dari `document.documentElement` menjadi `document.getElementById('root') || document.body`.
   - Bungkus `applyAthenaaUiCleanup()` dalam penjadwalan `requestAnimationFrame` + debounce ringan (mis. 80ms) sehingga pembaruan WebSocket per detik tidak memicu *DOM scan* berulang-ulang tanpa henti.

### 3.4 Blueprint Per Komponen Utama

1. **Kartu Pemutar & Lirik (*Hero Console*)**:
   - **Atmosfer Artwork Halus**: Gunakan gradien radial statis ringan berbasis `#4C2365` (`rgba(76, 35, 101, 0.36)`) di sudut kiri atas kartu *Now Playing*—cukup untuk menciptakan nuansa panggung ala Apple Music tanpa *canvas blur* real-time yang boros GPU.
   - **Hierarki Kendali Audio**: Tombol Play/Pause memakai `--btn-cta-bg` (`#C4A4DA -> #9E7EB5`) dengan ikon `#14081E` (kontras `8.93:1`), sedangkan tombol sekunder (Prev/Next/Shuffle/Repeat) memakai surface `--bg-surface-elevated` dengan ikon `#F7F2FC`.
   - **Panel Lirik (LRCLIB)**: Baris lirik aktif menggunakan `#F7F2FC` dengan bobot `600` dan indikator vertikal kiri `3px` berwarna `#C4A4DA`; baris lirik non-aktif menggunakan `#C9B8DB` pada opasitas `0.68` agar tetap nyaman dibaca tanpa mengganggu fokus baris aktif.
2. **Penempatan & Desain Studio DSP & Ambience (`#athenaa-studio-dsp-rack`)**:
   - **Penempatan Tetap Kompatibel**: Tetap di-mount di dalam kartu *Pemutar & Lirik* tepat di atas form `Impor Tautan Spotify`, dan otomatis dilepas pada tab lain (mempertahankan perilaku v6.3 yang sudah terbukti aman).
   - **Peningkatan Visual**: Ubah menjadi sub-panel *Velvet Inset* dengan header tipis berisi indikator status mono (`DSP: NORMAL` / `Ambience: RAIN`) berlatar `#4C2365` + border `#9E7EB5/40`, diikuti 2 baris kontrol terstruktur (Baris 1: **Filter Audio DSP** 8 preset; Baris 2: **Ambience** 5 tema) dan tombol aksi cepat (`Putar Ulang`, `Bersihkan Antrean`) dengan gaya *ghost pill* agar tidak menyaingi tombol aktif. Tambahkan status `data-active="true"` juga untuk tombol Ambience yang sedang dipilih (saat ini baru diterapkan pada tombol DSP Filter).
3. **Form Pengaturan Server & AutoMod (`#athenaa-koya-carl-suite`)**:
   - **Struktur Bento 2x2 Responsif**: Pertahankan grid `grid-cols-1 md:grid-cols-2 gap-4` untuk 4 modul (01. Asisten AI & Notifikasi, 02. AutoMod & Sensor Kata, 03. Welcome & Auto-Role, 04. Goodbye & Mod-Log).
   - **Peningkatan Keterbacaan & Aksesibilitas**: Sesuai [Spotify Encore x Accessibility](https://engineering.atspotify.com/2023/03/encore-x-accessibility-a-balancing-act) dan [WCAG 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html), berikan label `for="..."` yang terhubung eksplisit dengan `id` input, ganti checkbox standar dengan *custom toggle/checkbox* berukuran minimal `18px x 18px` beraksen `#C4A4DA`, pisahkan tombol aksi utama **"Simpan Pengaturan Administrasi & Sensor Kata"** menjadi *sticky action bar* di bawah grid 2x2 (bukan terjepit di dalam kartu nomor 04) agar lebih jelas bahwa satu tombol menyimpan keempat modul sekaligus, dan tampilkan toast konfirmasi inline dengan ikon status `#6EE7B7`.
4. **Tab Antrean, Tugas Akademik, Leaderboard, AFK & Navigasi Mobile**:
   - **Antrean & Leaderboard**: Gunakan *zebra-subtle hover* (`--bg-surface-elevated`) dan `tabular-nums` untuk nomor urut, durasi, serta skor EXP; sorot peringkat 1–3 dengan badge `#4C2365` berborder `#C4A4DA`.
   - **Tugas Akademik & AFK**: Gunakan badge status semantik (`#FCD34D` untuk tenggat dekat/AFK, `#FDA4AF` untuk lewat tenggat, `#6EE7B7` untuk selesai) di atas latar `#1B0F29`.
   - **Navigasi Mobile (`#athenaa-mobile-bottom-nav`)**: Pindahkan seluruh style inline ke CSS class berbasis token (`--mobile-nav-bg`, `backdrop-filter: blur(12px)`), tambahkan `padding-bottom: env(safe-area-inset-bottom)` untuk layar ber-notch, dan tandai tab aktif dengan latar `#4C2365` + border `#C4A4DA` agar status navigasi langsung terbaca.

---

## 4. Referensi Sumber Primer Terverifikasi

1. **Apple Developer — Human Interface Guidelines: Dark Mode**: [https://developer.apple.com/design/human-interface-guidelines/dark-mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode)
2. **Apple Developer — Human Interface Guidelines: Materials**: [https://developer.apple.com/design/human-interface-guidelines/materials](https://developer.apple.com/design/human-interface-guidelines/materials)
3. **Apple Developer — Liquid Glass Technology Overview**: [https://developer.apple.com/documentation/technologyoverviews/liquid-glass](https://developer.apple.com/documentation/technologyoverviews/liquid-glass)
4. **Linear — How we redesigned the Linear UI (Part II)**: [https://linear.app/now/how-we-redesigned-the-linear-ui](https://linear.app/now/how-we-redesigned-the-linear-ui)
5. **W3C WAI — Understanding Success Criterion 1.4.3: Contrast (Minimum) (WCAG 2.1/2.2)**: [https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
6. **W3C WAI — Understanding Success Criterion 1.4.11: Non-text Contrast (WCAG 2.1)**: [https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)
7. **W3C Design Tokens Community Group — Design Tokens Format Module 2025.10**: [https://www.w3.org/community/reports/design-tokens/CG-FINAL-format-20251028/](https://www.w3.org/community/reports/design-tokens/CG-FINAL-format-20251028/)
8. **Radix UI Colors — Understanding the Scale (12-Step Functional Color System)**: [https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale)
9. **Radix UI Colors — Composing a Color Palette**: [https://www.radix-ui.com/colors/docs/palette-composition/composing-a-palette](https://www.radix-ui.com/colors/docs/palette-composition/composing-a-palette)
10. **Tailwind CSS — Theme Variables Documentation**: [https://tailwindcss.com/docs/theme](https://tailwindcss.com/docs/theme)
11. **Tailwind CSS — `backdrop-filter: blur()` Documentation**: [https://tailwindcss.com/docs/backdrop-filter-blur](https://tailwindcss.com/docs/backdrop-filter-blur)
12. **Spotify Engineering — Multiple Layers of Abstraction in Design Systems (Encore)**: [https://engineering.atspotify.com/2023/05/multiple-layers-of-abstraction-in-design-systems](https://engineering.atspotify.com/2023/05/multiple-layers-of-abstraction-in-design-systems)
13. **Spotify Engineering — Encore x Accessibility: A Balancing Act**: [https://engineering.atspotify.com/2023/03/encore-x-accessibility-a-balancing-act](https://engineering.atspotify.com/2023/03/encore-x-accessibility-a-balancing-act)
14. **Raycast Blog — A Technical Deep Dive Into the New Raycast**: [https://www.raycast.com/blog/a-technical-deep-dive-into-the-new-raycast](https://www.raycast.com/blog/a-technical-deep-dive-into-the-new-raycast)
15. **MDN Web Docs — `backdrop-filter` CSS Property**: [https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)
16. **MDN Web Docs — `contain` CSS Property (CSS Containment)**: [https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/contain](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/contain)
17. **MDN Web Docs — `prefers-reduced-transparency` CSS Media Feature**: [https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-transparency](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-transparency)
18. **web.dev — Stick to Compositor-Only Properties and Manage Layer Count**: [https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count](https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count)
19. **web.dev — `prefers-reduced-motion`: Sometimes Less Movement Is More**: [https://web.dev/articles/prefers-reduced-motion](https://web.dev/articles/prefers-reduced-motion)
