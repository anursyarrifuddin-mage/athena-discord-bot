export interface SlashCommandInfo {
  name: string;
  params: string;
  category: 'Musik' | 'Akademik' | 'Mahasiswa' | 'Leaderboard & AFK' | 'Minigames';
  description: string;
}

export const SLASH_COMMANDS_LIST: SlashCommandInfo[] = [
  { name: '/play', params: 'query', category: 'Musik', description: 'Putar lagu dari judul/penyanyi, URL YouTube, Spotify Track/Playlist, atau stream Radio' },
  { name: '/search', params: 'query', category: 'Musik', description: 'Cari lagu dan tampilkan kartu embed interaktif beserta nama penyanyi' },
  { name: '/queue', params: '[page]', category: 'Musik', description: 'Tampilkan daftar antrean lagu aktif dengan progress bar modern' },
  { name: '/remove', params: 'posisi', category: 'Musik', description: 'Hapus lagu tertentu dari daftar antrean berdasarkan nomor urut (Host Lock / Lagu Sendiri)' },
  { name: '/nowplaying', params: '', category: 'Musik', description: 'Tampilkan kartu embed lagu yang sedang diputar dan Session Host' },
  { name: '/skip', params: '', category: 'Musik', description: 'Lewati lagu saat ini (memerlukan izin Session Host / DJ / Admin)' },
  { name: '/stop', params: '', category: 'Musik', description: 'Hentikan pemutaran dan bersihkan antrean (Host Lock)' },
  { name: '/pause', params: '', category: 'Musik', description: 'Jeda pemutaran lagu aktif (Host Lock)' },
  { name: '/resume', params: '', category: 'Musik', description: 'Lanjutkan pemutaran lagu yang dijeda (Host Lock)' },
  { name: '/shuffle', params: '', category: 'Musik', description: 'Acak urutan antrean musik (Host Lock)' },
  { name: '/volume', params: 'persen (1-100)', category: 'Musik', description: 'Atur volume suara bot antara 1% hingga 100% (Host Lock)' },
  { name: '/loop', params: 'mode (off|one|queue)', category: 'Musik', description: 'Atur mode pengulangan lagu atau antrean' },
  { name: '/autoplay', params: 'aktif (true|false)', category: 'Musik', description: 'Aktifkan/nonaktifkan pencarian lagu lanjutan otomatis saat antrean habis' },
  { name: '/247', params: 'aktif (true|false)', category: 'Musik', description: 'Pertahankan koneksi bot di voice channel selama 24/7' },
  { name: '/lyrics', params: '[judul]', category: 'Musik', description: 'Tampilkan lirik tersinkronisasi atau teks dari LRCLIB dalam kartu embed' },
  { name: '/leave', params: '', category: 'Musik', description: 'Putuskan koneksi voice channel dan reset Session Host' },
  { name: '/task_list', params: '', category: 'Akademik', description: 'Lihat daftar tugas mendatang pada server ini dalam format embed modern' },
  { name: '/task_add', params: 'mata_kuliah judul deadline_iso', category: 'Akademik', description: 'Tambahkan tugas akademik baru secara manual' },
  { name: '/task_done', params: 'task_id', category: 'Akademik', description: 'Tandai tugas selesai dan hentikan reminder berikutnya' },
  { name: '/sync_waskita', params: '[ical_url]', category: 'Akademik', description: 'Sinkronkan ulang kalender Waskita (.ics & Kredensial Login .env)' },
  { name: '/pomodoro', params: '[fokus_menit] [istirahat_menit] [topik]', category: 'Mahasiswa', description: 'Mulai timer fokus belajar Pomodoro di Discord (+30 EXP)' },
  { name: '/ipk', params: 'sks_nilai', category: 'Mahasiswa', description: 'Hitung simulasi IP/IPK semester dari format SKS:Nilai (mis. 3:A, 4:AB, 3:B+)' },
  { name: '/kelompok', params: 'jumlah_kelompok [daftar_nama]', category: 'Mahasiswa', description: 'Acak pembagian kelompok tugas dari daftar nama atau anggota Voice Channel' },
  { name: '/level', params: '[member]', category: 'Leaderboard & AFK', description: 'Lihat kartu profil Level, progres EXP, dan sumber EXP (Chat & Voice)' },
  { name: '/leaderboard', params: '', category: 'Leaderboard & AFK', description: 'Tampilkan Top 15 Leaderboard Server (Chat, Join Voice, Speak, Listening, Streaming)' },
  { name: '/afk', params: '[alasan]', category: 'Leaderboard & AFK', description: 'Pasang status AFK dengan alasan opsional' },
  { name: '/kuis', params: '', category: 'Minigames', description: 'Mainkan kuis interaktif pilihan ganda dengan tombol A/B/C/D (+25 EXP)' },
  { name: '/mathbattle', params: '', category: 'Minigames', description: 'Tantangan hitung cepat matematika dengan tombol interaktif (+20 EXP)' },
  { name: '/suit', params: 'pilihan (batu|gunting|kertas)', category: 'Minigames', description: 'Mainkan suit Batu-Gunting-Kertas melawan Athenaa (+15 EXP)' },
  { name: '/8ball', params: 'pertanyaan', category: 'Minigames', description: 'Tanyakan pertanyaan ke Kerang Ajaib Athenaa' },
  { name: '/dadu', params: '[sisi]', category: 'Minigames', description: 'Lempar dadu keberuntungan (d6, d20, d100)' },
];
