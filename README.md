# Athenaa — Discord Music, Academic Reminder, AI Assistant & Web Dashboard Bot

**Athenaa** adalah bot Discord multifungsi yang mengintegrasikan pemutar musik berkualitas tinggi berbasis **YouTube Music**, asisten obrolan cerdas **AI Interaktif (`@Athena`)**, sistem pengingat tugas kuliah otomatis (**Waskita / Moodle**), fitur komunitas & moderasi server (**AutoMod, Leveling EXP, AFK**), serta panel kendali jarak jauh berbasis web ([Athenaa Web Dashboard](https://www.google.com/search?q=https://bot.athenaa.my.id)) yang tersinkronisasi secara *real-time*.

Bot ini dirancang dengan optimasi penggunaan memori (*Low-Memory Optimizer*) agar pemutaran audio di Voice Channel tetap jernih, stabil, dan responsif sepanjang waktu tanpa membebani RAM server.

## Cara Instalasi & Menjalankan Bot

Pastikan perangkat atau server sudah terpasang **Python 3.11+**, **FFmpeg**, dan **Node.js** (opsional jika ingin membangun ulang tampilan web).

### 1. Clone Repositori & Masuk ke Folder Proyek
```bash
git clone https://github.com/username/athenaa.git
cd athenaa
```

### 2. Instal Dependensi Python
```bash
pip install -r requirements.txt
```

### 3. Build Tampilan Web Dashboard (Opsional)
Aset tampilan Web Player sudah tersedia secara bawaan. Namun jika kamu mengubah tampilan frontend, jalankan perintah berikut terlebih dahulu:
```bash
npm install
npm run build
```

### 4. Konfigurasi File `.env`
rename file `.env.example` menjadi `.env` lalu isi dengan code yang kamu punya ya. Meow!
```bash
ren .env.example .env
```

### 5. Jalankan Bot & Web Server
```bash
python -m app.main
```
Atau jika menggunakan Linux / Panel Hosting, kamu juga bisa langsung menjalankan skrip:
```bash
bash start.sh
```

Setelah berjalan, buka Web Dashboard di browser lokal melalui `http://localhost:8000` (atau `http://localhost:10031` sesuai nilai `WEB_PORT` pada file `.env`). Jika kamu menjalankan mode pengembangan frontend dengan `npm run dev`, tampilan Vite akan berjalan di `http://localhost:3000`.

## Manfaat & Fungsi Utama

1. **Hiburan Musik Tanpa Hambatan di Voice Channel**: Memudahkan anggota komunitas memutar lagu dari YouTube Music, tautan YouTube/Spotify, maupun stasiun radio langsung melalui perintah `/play`, menu pilihan `/search`, perintah obrolan `@Athena`, atau melalui tampilan Web Player.

2. **Asisten AI Tongkrongan yang Luwes & Informatif**: Menjawab pertanyaan umum, merangkum berita terkini dari pencarian internet secara singkat dan jelas, serta mengeksekusi seluruh perintah bot hanya dengan memanggil `@Athena` di chat tanpa harus mengetik *slash command*.

3. **Pengingat Tugas Kuliah Otomatis per Server**: Membantu mahasiswa dan komunitas kelas memantau tenggat waktu pengumpulan tugas dari kalender akademik Waskita/Moodle dengan pengingat otomatis setiap pukul **00:01 WIB** serta peringatan bertahap (H-3, H-1, dan H-0).

4. **Manajemen Multi-Server yang Terisolasi & Aman**: Setiap server Discord memiliki pengaturan independen di Web Dashboard, dan setiap pengguna hanya dapat melihat serta mengendalikan server Discord tempat mereka dan bot sama-sama bergabung.

5. **Moderasi Server Senyap & Gamifikasi Komunitas**: Menjaga kebersihan obrolan dengan penghapusan kata terlarang secara otomatis tanpa *spam* pesan peringatan, sekaligus meramaikan server lewat sistem Leveling EXP, *Leaderboard*, status AFK, dan *mini-games*.

## Fitur Unggulan Athenaa

### 1. Pemutar Musik YouTube Music & Efek Audio Real-Time

* **Pencarian Prioritas Judul Lagu (*Title-First Search*)**: Mengutamakan kecocokan judul lagu terlebih dahulu baru nama penyanyi, sehingga lagu lebih mudah ditemukan meskipun pengguna hanya mengingat judulnya atau terdapat sedikit salah ketik (*typo*).

* **Resolusi Tautan Presisi**: Mendukung pemutaran langsung dari tautan video YouTube maupun lagu Spotify dengan pencocokan audio resmi (*Official Audio / Topic*).

* **Pemberitahuan Lagu Otomatis di Chat**: Memberikan informasi lagu yang sedang diputar dan lagu berikutnya di channel teks setiap kali lagu baru dimulai atau berpindah dari antrean.

* **Pilihan Hasil Pencarian Interaktif (`/search`)**: Menampilkan 10 hasil pencarian lagu lengkap dengan menu pilihan (*dropdown*) di bawah pesan, sehingga pengguna cukup mengklik judul lagu untuk langsung memutar atau memasukkannya ke antrean tanpa perlu mengetik `/play` ulang.

* **8 Preset Filter Audio & 5 Suasana Ambience**: Mengubah karakter suara secara langsung (*Normal, Bassboost, Nightcore, Vaporwave, 8D Audio, Lo-Fi, Karaoke, Treble*) atau memutar suara latar (*Hujan, Kafe, Lo-Fi Study, Night Coding, Piano*) untuk menemani belajar dan bekerja.

* **Lirik Lagu Tersinkronisasi**: Menampilkan lirik lagu yang sedang diputar baik melalui Discord maupun secara berjalan (*live synced lyrics*) di Web Dashboard.

### 2. AI Chatbot Interaktif (`@Athena`) & Perintah Bahasa Alami

* **Aktif Khusus Saat Di-tag (`@Athena`)**: Bot hanya merespons apabila di-mention secara eksplisit oleh pengguna, sehingga tidak mengganggu percakapan biasa di dalam channel.

* **Gaya Bahasa Santai, Luwes, & Hemat Kuota**: Merespons sapaan maupun candaan tongkrongan secara luwes layaknya teman mengobrol, tidak kaku, dan tidak memaksakan tawaran memutar musik saat pengguna sedang bertanya hal umum. Untuk pertanyaan berat atau panjang, bot memberikan jawaban inti yang padat dan informatif dari hasil pencarian terkini.

* **Eksekusi Semua Perintah Lewat Chat Biasa**: Pengguna dapat menyuruh bot memutar lagu, melewati lagu, menghentikan musik, mengatur volume, mengaktifkan *autoplay*, mengecek antrean, hingga melihat daftar tugas hanya dengan kalimat sehari-hari.

* **Otomatis Putar atau Masuk Antrean (*Auto-Queue*)**: Saat diminta memutar lagu lewat tag `@Athena`, bot langsung memutar lagu tersebut setelah jeda singkat jika Voice Channel sedang kosong, atau otomatis menambahkannya ke urutan antrean (*queue*) jika sedang ada lagu yang berputar.

* **Memori Konteks per Channel**: Menyimpan riwayat percakapan singkat dan permintaan lagu terakhir secara terpisah di setiap channel. Jika pengguna mengeluhkan lagu sebelumnya belum terputar, bot langsung mengenali judul lagu terakhir yang diminta di channel tersebut dan memutarnya.

* **AI Smart Trending Autoplay**: Ketika mode Autoplay diaktifkan (secara bawaan nonaktif agar tidak memutar lagu sendiri tanpa izin), AI otomatis memilihkan lagu *trending* yang memiliki nuansa serupa saat antrean habis tanpa mengulang lagu yang baru saja diputar.

### 3. Web Dashboard & Remote Control (`bot.athenaa.my.id`)

* **Sinkronisasi Dua Arah Instan**: Seluruh perubahan status lagu, antrean, volume, mode *loop*, *autoplay*, dan lirik tersinkronisasi seketika antara Voice Channel Discord dan Web Player.

* **Filter Server Bersama (*Mutual Server Filtering*)**: Daftar pemilihan server di Web Dashboard disaring secara ketat per akun Discord yang login—hanya menampilkan server di mana pengguna tersebut dan bot Athenaa sama-sama menjadi anggota.

* **Isolasi Kendali Voice Antar-Server**: Pengguna hanya dapat mengendalikan pemutaran musik pada server tempat mereka sedang bergabung di Voice Channel, mencegah gangguan silang antar-server.

* **Pengaturan Multi-Guild Mandiri**: Setiap server memiliki halaman konfigurasi sendiri di Web Dashboard untuk mengatur ID Channel Musik, ID Channel Pengingat Tugas, Tautan Kalender Waskita (`.ics`), Zona Waktu, Interval Pengingat, Cooldown EXP, pesan *Welcome/Goodbye*, serta daftar kata terlarang tanpa terkunci pada pengaturan bawaan server utama.

### 4. Pengingat Tugas Akademik & Waskita Otomatis

* **Sinkronisasi Kalender Akademik (`.ics`)**: Mengambil jadwal tugas kuliah yang memiliki kewajiban pengumpulan (*submittable assignments*) secara otomatis setiap 1 jam dan menghapus tugas yang sudah melewati tenggat waktu.

* **Notifikasi Harian 00:01 WIB & Pengingat Bertahap**: Mengirimkan ringkasan tugas aktif ke channel pengingat masing-masing server setiap pukul 00:01 WIB serta pengingat khusus pada H-3, H-1, dan hari H tenggat pengumpulan.

* **Penyimpanan Modul & Materi Kuliah**: Mendukung pengunggahan dan pengunduhan dokumen materi kuliah (`.pdf`, `.doc`, `.docx`) yang terhubung dengan daftar tugas per server.

### 5. Moderasi Senyap (AutoMod) & Komunitas

* **Sensor Kata Terlarang & Anti-Spam Senyap**: Menghapus pesan yang memuat kata terlarang atau tautan terlarang secara instan dan senyap tanpa mengirimkan pesan peringatan yang memenuhi layar obrolan.

* **Sistem Leveling EXP & Leaderboard**: Menghitung perolehan EXP anggota dari aktivitas mengobrol di teks maupun bergabung di Voice Channel lengkap dengan pengaturan jeda waktu (*cooldown*) per server.

* **Manajemen Status AFK Otomatis**: Menandai pengguna yang sedang AFK beserta alasannya, memberi tahu anggota lain yang me-mention pengguna tersebut, dan mencabut status AFK secara otomatis ketika pengguna kembali aktif mengirim pesan.

## Contoh Interaksi Chat AI (`@Athena`) Tanpa Slash Command

Selain menggunakan *slash command* (`/`), pengguna dapat memanggil `@Athena` dengan kalimat sehari-hari:

| Contoh Pesan Pengguna di Discord | Aksi yang Dilakukan Bot Athenaa |
| ----- | ----- |
| `halo @Athena` | Membalas sapaan dengan gaya bahasa santai dan ramah tanpa memakan kuota AI. |
| `woi @Athena tolong puterin musik dari Lady Gaga yang judulnya Poker Face` | Mencari lagu *Poker Face — Lady Gaga* dengan prioritas judul, membalas singkat (`"Oke boskyuu, nih ku puterin musik dari Lady Gaga berjudul Poker Face yaa~"`), lalu memutarnya di Voice Channel (atau memasukkannya ke antrean jika sedang ada lagu aktif). |
| `mana @Athena, kok gak ke play musik nya` | Membaca memori channel untuk mengambil judul lagu terakhir yang diminta sebelumnya, lalu langsung memutarnya tanpa salah membaca kata `"nya"` sebagai judul lagu. |
| `@Athena skip lagu ini dong` | Melewati lagu yang sedang diputar ke lagu berikutnya di antrean. |
| `@Athena tolong aktifkan mode autoplay` | Mengaktifkan fitur *AI Smart Trending Autoplay* untuk sesi Voice Channel di server tersebut. |
| `@Athena buka queue` | Menampilkan daftar antrean lagu server saat ini beserta tombol kontrol interaktif. |
| `@Athena atur volume 90` | Mengubah volume pemutaran musik di Voice Channel menjadi 90%. |
| `@Athena filter bassboost` | Menerapkan efek audio *Bassboost* secara langsung pada lagu yang sedang diputar. |
| `@Athena cek tugas kuliah` | Menampilkan daftar tugas akademik yang masih aktif beserta sisa waktu tenggat pengumpulannya. |
| `@Athena apakah benar berita X hari ini?` | Mencari informasi terbaru dari berita daring dan memberikan jawaban ringkas, padat, serta informatif. |
| `@Athena reset memory` | Menghapus riwayat memori obrolan AI khusus pada channel tempat perintah tersebut dikirim. |

## Daftar Lengkap Perintah (*Slash Commands*)

### 1. Perintah Musik, Antrean & Efek Audio

| Perintah | Pilihan / Parameter | Penjelasan Fungsi |
| ----- | ----- | ----- |
| `/play` | `query` ( diketik pengguna ) | Memutar lagu dari judul/penyanyi YouTube Music, tautan YouTube/Spotify, atau menambahkannya ke antrean. Kolom pencarian sengaja dikosongkan di awal hingga pengguna mengetikkan judul lagu. |
| `/search` | `query` ( kata kunci lagu ) | Menampilkan 10 hasil pencarian lagu teratas lengkap dengan menu dropdown interaktif di bawah pesan agar pengguna bisa langsung mengklik lagu yang ingin diputar. |
| `/pause` | *(Tidak ada)* | Menjeda sementara lagu yang sedang diputar di Voice Channel. |
| `/resume` | *(Tidak ada)* | Melanjutkan pemutaran lagu yang sedang dijeda. |
| `/skip` | *(Tidak ada)* | Melewati lagu saat ini dan langsung memutar lagu berikutnya di antrean. |
| `/stop` | *(Tidak ada)* | Menghentikan pemutaran musik dan mengosongkan antrean aktif di server tersebut. |
| `/leave` | *(Tidak ada)* | Menghentikan musik dan mengeluarkan bot dari Voice Channel. |
| `/queue` | *(Tidak ada)* | Menampilkan daftar antrean lagu aktif lengkap dengan tombol kontrol interaktif. |
| `/nowplaying` | *(Tidak ada)* | Menampilkan detail lagu yang sedang diputar, progres durasi, pengaju lagu, dan tombol kontrol. |
| `/loop` | Pilihan: `Off`, `Satu Lagu (One)`, `Seluruh Antrean (Queue)` | Mengatur mode pengulangan lagu melalui menu pilihan langsung. |
| `/autoplay` | Pilihan: `Aktifkan (ON)`, `Matikan (OFF)` | Mengaktifkan atau mematikan fitur *AI Smart Trending Autoplay* saat antrean habis. |
| `/247` | Pilihan: `Aktifkan (ON)`, `Matikan (OFF)` | Mengatur agar bot tetap berada di Voice Channel selama 24/7 meskipun tidak ada lagu yang diputar. |
| `/volume` | `level` (`1` – `100`) | Mengatur tingkat keras suara pemutaran musik di Voice Channel dan Web Player. |
| `/seek` | `detik` ( posisi waktu ) | Melompat ke detik atau menit tertentu pada lagu yang sedang diputar. |
| `/replay` | *(Tidak ada)* | Memutar ulang lagu yang sedang berjalan kembali dari detik `00:00`. |
| `/previous` | *(Tidak ada)* | Memutar kembali lagu sebelumnya yang baru saja selesai diputar dari riwayat server. |
| `/shuffle` | *(Tidak ada)* | Mengacak urutan lagu yang ada di dalam daftar antrean saat ini. |
| `/clear` | *(Tidak ada)* | Menghapus seluruh lagu di daftar antrean tanpa menghentikan lagu yang sedang diputar. |
| `/remove` | `posisi` ( nomor urut ) | Menghapus satu lagu tertentu dari daftar antrean berdasarkan nomor urutnya. |
| `/move` | `dari`, `ke` ( nomor urut ) | Memindahkan posisi urutan lagu di dalam antrean ke nomor urut yang diinginkan. |
| `/skipto` | `posisi` ( nomor urut ) | Melompat langsung ke lagu pada nomor urut tertentu di antrean dan melewati lagu di antaranya. |
| `/grab` | *(Tidak ada)* | Mengirimkan detail dan tautan lagu yang sedang diputar langsung ke *Direct Message* (DM) pengguna. |
| `/history` | *(Tidak ada)* | Menampilkan daftar riwayat lagu yang baru saja diputar di server tersebut. |
| `/lyrics` | `judul` *(opsional)* | Mencari dan menampilkan lirik lagu yang sedang diputar atau berdasarkan judul lagu yang diketik. |
| `/filter` | Pilihan: `Normal`, `Bassboost`, `Nightcore`, `Vaporwave`, `8D Audio`, `Lo-Fi`, `Karaoke`, `Treble` | Menerapkan efek pemrosesan sinyal audio (*DSP filter*) secara langsung melalui menu pilihan tanpa perlu mengetik manual. |
| `/ambience` | Pilihan: `Hujan (Rain)`, `Suasana Kafe`, `Lo-Fi Study Beats`, `Night Coding`, `Piano Tenang` | Memutar audio suasana latar untuk belajar, santai, atau *coding* sesuai tautan yang dapat disesuaikan di konfigurasi server. |
| `/sleeptimer` | `menit` (`0` untuk batal) | Mengatur penghitung waktu mundur otomatis untuk menghentikan musik dan keluar dari Voice Channel setelah sejumlah menit. |
| `/radio` | Pilihan stasiun radio | Memutar siaran langsung stasiun radio Indonesia maupun internasional (*Prambors FM, Hard Rock FM, Lo-Fi 24/7, Jazz*). |

### 2. Perintah Akademik & Pengingat Tugas (Waskita / Moodle)

| Perintah | Pilihan / Parameter | Penjelasan Fungsi |
| ----- | ----- | ----- |
| `/tugas` | *(Tidak ada)* | Menampilkan daftar tugas kuliah aktif beserta mata kuliah, batas waktu pengumpulan, dan indikator urgensi. |
| `/tambah_tugas` | `matkul`, `judul`, `deadline` | Menambahkan jadwal tugas akademik baru secara manual ke daftar pengingat server. |
| `/selesai_tugas` | `task_id` | Menandai tugas akademik tertentu sebagai selesai agar tidak lagi memicu pengingat. |
| `/sync_waskita` | *(Tidak ada)* | Memicu sinkronisasi kalender akademik Waskita/Moodle (`.ics`) secara langsung dan menyaring tugas yang memerlukan pengumpulan. |
| `/modul` | *(Tidak ada)* | Menampilkan daftar berkas modul atau materi kuliah yang tersimpan di server beserta tautan unduhannya di Web Dashboard. |

### 3. Perintah Komunitas, Leveling RPG & Hiburan

| Perintah | Pilihan / Parameter | Penjelasan Fungsi |
| ----- | ----- | ----- |
| `/level` | `member` *(opsional)* | Menampilkan kartu profil RPG pengguna yang berisi Level saat ini, total EXP, dan progres menuju level berikutnya. |
| `/leaderboard` | *(Tidak ada)* | Menampilkan papan peringkat 10 anggota teratas dengan Level dan EXP tertinggi di server tersebut. |
| `/afk` | `alasan` *(opsional)* | Mengaktifkan status AFK sehingga bot otomatis memberi tahu siapa pun yang me-mention pengguna tersebut hingga kembali aktif. |
| `/poll` | `pertanyaan`, `opsi_1` .. `opsi_5` | Membuat pemungutan suara (*polling*) interaktif lengkap dengan reaksi angka otomatis di channel. |
| `/remindme` | `menit`, `pesan` | Mengatur pengingat pribadi yang akan dikirimkan kembali oleh bot setelah waktu yang ditentukan berakhir. |
| `/dadu` | `sisi` *(default: 6)* | Melempar dadu acak dengan jumlah sisi yang dapat ditentukan. |
| `/8ball` | `pertanyaan` | Menanyakan pertanyaan ke bola ajaib *Magic 8-Ball* untuk mendapatkan jawaban hiburan acak. |
| `/suit` | Pilihan: `Batu 🪨`, `Gunting ✂️`, `Kertas 📄` | Bermain suit (*Batu-Gunting-Kertas*) melawan bot melalui menu pilihan interaktif. |
| `/kuis` | *(Tidak ada)* | Memulai kuis pengetahuan umum dan teknologi interaktif dengan tombol pilihan ganda A/B/C/D berhadiah EXP. |
| `/mathbattle` | *(Tidak ada)* | Memulai tantangan berhitung cepat di channel untuk mengadu kecepatan menjawab antar-anggota server. |
| `/fakta` | *(Tidak ada)* | Menampilkan fakta unik seputar dunia sains, teknologi, dan musik. |
| `/motivasi` | *(Tidak ada)* | Menampilkan kutipan motivasi singkat untuk menyemangati aktivitas belajar atau pengerjaan proyek. |

### 4. Perintah Sistem, Memori & Bantuan

| Perintah | Pilihan / Parameter | Penjelasan Fungsi |
| ----- | ----- | ----- |
| `/help` | Pilihan Kategori: `Semua`, `Musik & Audio`, `Filter & Efek`, `Akademik & Waskita`, `RPG & Komunitas`, `Mini-Games`, `Sistem & Admin` | Menampilkan pusat bantuan interaktif yang dilengkapi menu dropdown kategori untuk menelusuri seluruh fitur dan perintah bot. |
| `/stats` | *(Tidak ada)* | Menampilkan statistik performa bot meliputi latensi (*ping*), waktu aktif (*uptime*), jumlah server, serta pemakaian RAM saat ini. |
| `/ram_clean` | *(Tidak ada)* | Menjalankan pembersihan memori (*Garbage Collection & Heap Trim*) secara langsung agar penggunaan RAM tetap rendah dan suara musik tetap stabil. |


Disclaimer saya membuat bot musik ini dikarenakan gabut, dengan Gemin 4 Argon yang saya punyai saya mencoba membuat Discord Bot Musik+Academy & Integrasi Web Player sebagai control Bot melalui UI. meow!
