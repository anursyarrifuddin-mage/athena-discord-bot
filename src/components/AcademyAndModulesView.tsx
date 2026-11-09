import React, { useState, useRef } from 'react';
import {
  CheckCircle2,
  Circle,
  Calendar,
  RefreshCw,
  Plus,
  Trash2,
  Download,
  Upload,
  Bell,
  FileText,
  ExternalLink,
  KeyRound,
  Link2,
  FileUp,
  X,
  AlertCircle,
} from 'lucide-react';
import { AcademicTask, ReminderDelivery, TaskAttachment } from '../types/athenaa';
import { evaluateReminderStage } from '../lib/athenaaRules';

export interface MoodleEnvStatus {
  env_moodle_configured?: boolean;
  moodle_base_url?: string;
  has_ical_url?: boolean;
  moodle_ical_url_preview?: string;
  has_credentials?: boolean;
  masked_username?: string;
}

interface AcademyAndModulesViewProps {
  subTab: 'academy' | 'modules';
  guildId: string;
  sessionToken?: string;
  isAdmin?: boolean;
  tasks: AcademicTask[];
  attachments: TaskAttachment[];
  reminders: ReminderDelivery[];
  moodleEnv?: MoodleEnvStatus | null;
  onRefreshTasks: () => void;
  onNotify: (msg: string, isError?: boolean) => void;
}

const AcademyAndModulesViewComponent: React.FC<AcademyAndModulesViewProps> = ({
  subTab,
  guildId,
  sessionToken,
  isAdmin = false,
  tasks,
  attachments,
  reminders,
  moodleEnv,
  onRefreshTasks,
  onNotify,
}) => {
  const [courseFilter, setCourseFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'completed' | 'overdue'>('all');

  const [courseName, setCourseName] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDesc, setTaskDesc] = useState('');
  const [deadlineDate, setDeadlineDate] = useState('2026-11-05T23:59');
  const [sourceUrl, setSourceUrl] = useState('');
  const [icsSyncing, setIcsSyncing] = useState(false);

  // Waskita .env / iCal & Login Credentials State
  const [showMoodleConfig, setShowMoodleConfig] = useState(false);
  const [moodleIcalUrl, setMoodleIcalUrl] = useState('');
  const [moodleBaseUrl, setMoodleBaseUrl] = useState('');
  const [moodleUsername, setMoodleUsername] = useState('');
  const [moodlePassword, setMoodlePassword] = useState('');

  const [selectedTaskId, setSelectedTaskId] = useState(tasks[0]?.task_id || '');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileBase64, setFileBase64] = useState<string>('');
  const [uploadFilename, setUploadFilename] = useState('');
  const [uploadSizeKb, setUploadSizeKb] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const courses = Array.from(new Set(tasks.map((t) => t.course_name)));
  const nowMs = Date.now();

  const processLocalFile = (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.pdf', '.doc', '.docx'].includes(ext)) {
      onNotify('Ekstensi file ditolak! Hanya file .pdf, .doc, dan .docx yang diizinkan.', true);
      return;
    }
    const maxBytes = 15 * 1024 * 1024;
    if (file.size > maxBytes) {
      onNotify(`Ukuran file (${(file.size / (1024 * 1024)).toFixed(1)} MB) melebihi batas maksimum 15 MB.`, true);
      return;
    }
    if (file.size <= 0) {
      onNotify('File lokal yang dipilih kosong (0 Bytes).', true);
      return;
    }

    setSelectedFile(file);
    setUploadFilename(file.name);
    setUploadSizeKb(Math.round(file.size / 1024) || 1);

    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      setFileBase64(result);
    };
    reader.onerror = () => {
      onNotify('Gagal membaca file dari penyimpanan lokal.', true);
    };
    reader.readAsDataURL(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processLocalFile(e.target.files[0]);
    }
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processLocalFile(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleClearSelectedFile = () => {
    setSelectedFile(null);
    setFileBase64('');
    setUploadFilename('');
    setUploadSizeKb(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const filteredTasks = tasks.filter((t) => {
    if (courseFilter !== 'all' && t.course_name !== courseFilter) return false;
    const isOverdue = !t.is_completed && new Date(t.deadline_iso).getTime() < nowMs;
    if (statusFilter === 'pending') return !t.is_completed;
    if (statusFilter === 'completed') return Boolean(t.is_completed);
    if (statusFilter === 'overdue') return isOverdue;
    return true;
  });

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!courseName.trim() || !taskTitle.trim()) {
      onNotify('Nama mata kuliah dan judul tugas wajib diisi.', true);
      return;
    }
    const isoDeadline = new Date(deadlineDate).toISOString();
    const resp = await fetch(`/api/guilds/${guildId}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        course_name: courseName.trim(),
        title: taskTitle.trim(),
        description: taskDesc.trim(),
        deadline_iso: isoDeadline,
        source_url: sourceUrl.trim(),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      onNotify(data.error || 'Gagal menambahkan tugas.', true);
      return;
    }
    setCourseName('');
    setTaskTitle('');
    setTaskDesc('');
    setSourceUrl('');
    onNotify('Tugas akademik baru berhasil disimpan.');
    onRefreshTasks();
  };

  const handleSyncMoodleIcs = async () => {
    setIcsSyncing(true);
    try {
      const resp = await fetch(`/api/guilds/${guildId}/tasks/sync-ics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ical_url: moodleIcalUrl.trim(),
          moodle_base_url: moodleBaseUrl.trim(),
          moodle_username: moodleUsername.trim(),
          moodle_password: moodlePassword,
        }),
      });
      const data = await resp.json();
      if (resp.ok) {
        const cleanSource = String(data.source_used || 'Kalender .ics / .env').replace(/Moodle/gi, 'Waskita');
        onNotify(
          `Sinkronisasi Waskita (${cleanSource}) selesai: ${data.inserted} tugas baru, ${data.updated} diperbarui.`
        );
        onRefreshTasks();
      } else {
        onNotify(data.error || 'Gagal menyinkronkan kalender Waskita', true);
      }
    } finally {
      setIcsSyncing(false);
    }
  };

  const handleToggleComplete = async (taskId: string) => {
    const resp = await fetch(`/api/tasks/${taskId}/toggle`, { method: 'POST' });
    if (resp.ok) {
      onRefreshTasks();
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    const resp = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    if (resp.ok) {
      onNotify('Tugas berhasil dihapus.');
      onRefreshTasks();
    }
  };

  const handleDeleteModule = async (attachmentId: string, filename: string) => {
    if (!isAdmin) {
      onNotify('Akses Ditolak: Hanya Admin Server yang dapat menghapus lampiran modul.', true);
      return;
    }
    try {
      const resp = await fetch(`/api/guilds/${guildId}/modules/${attachmentId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'X-Guild-Id': guildId,
          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        },
      });
      if (resp.ok) {
        onNotify(`Modul / lampiran "${filename}" berhasil dihapus.`);
        onRefreshTasks();
      } else {
        const data = await resp.json().catch(() => ({}));
        onNotify(data.error || data.detail || 'Gagal menghapus modul.', true);
      }
    } catch {
      onNotify('Terjadi kesalahan jaringan saat menghapus modul.', true);
    }
  };

  const handleUploadModule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile && !uploadFilename.trim()) {
      onNotify('Silakan pilih file modul dari perangkat lokal Anda terlebih dahulu.', true);
      return;
    }

    setIsUploading(true);
    try {
      const targetFilename = (uploadFilename.trim() || selectedFile?.name || 'Modul_Materi_Kuliah.pdf');
      const targetBytes = selectedFile ? selectedFile.size : Number(uploadSizeKb) * 1024;

      const resp = await fetch(`/api/guilds/${guildId}/modules/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: selectedTaskId || tasks[0]?.task_id || 'tsk-jarkom-01',
          filename: targetFilename,
          size_bytes: targetBytes,
          content_base64: fileBase64,
          uploaded_by: 'Aetheriaaa',
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        onNotify(data.error || 'Validasi lampiran modul gagal.', true);
        return;
      }
      handleClearSelectedFile();
      onNotify(`File lokal "${targetFilename}" berhasil diunggah dan disimpan ke direktori aman.`);
      onRefreshTasks();
    } catch {
      onNotify('Terjadi kesalahan jaringan saat mengunggah file lokal.', true);
    } finally {
      setIsUploading(false);
    }
  };

  if (subTab === 'modules') {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-5 bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 space-y-4">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Upload className="w-4 h-4 text-[#DC95FF]" />
                Unggah Langsung File Modul dari Local
              </h2>
              <p className="text-xs text-[#B3B3B3] mt-1">
                Pilih atau seret file dari komputer Anda · Maksimum 15 MB · Format didukung:{' '}
                <code className="font-mono text-[#DC95FF]">.pdf</code>,{' '}
                <code className="font-mono text-[#DC95FF]">.doc</code>,{' '}
                <code className="font-mono text-[#DC95FF]">.docx</code> · Penyimpanan aman berbasis UUID.
              </p>
            </div>

            <form onSubmit={handleUploadModule} className="space-y-4 pt-2">
              <div>
                <label className="block text-xs font-medium text-[#B3B3B3] mb-1">
                  Pilih Tugas Terkait
                </label>
                <select
                  aria-label="Pilih tugas untuk lampiran modul"
                  value={selectedTaskId}
                  onChange={(e) => setSelectedTaskId(e.target.value)}
                  className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#DC95FF]"
                >
                  {tasks.map((t) => (
                    <option key={t.task_id} value={t.task_id}>
                      {t.course_name} — {t.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Area Drag-and-Drop & File Picker dari Local Storage */}
              <div>
                <label className="block text-xs font-medium text-[#B3B3B3] mb-1.5">
                  File Dokumen Modul Lokal (.pdf, .doc, .docx)
                </label>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={handleFileChange}
                  className="hidden"
                />

                {!selectedFile ? (
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all duration-200 flex flex-col items-center justify-center gap-2.5 ${
                      isDragging
                        ? 'border-[#DC95FF] bg-[#DC95FF]/10 scale-[1.01]'
                        : 'border-white/15 bg-[#202020] hover:border-[#DC95FF]/50 hover:bg-[#252525]'
                    }`}
                  >
                    <div className="w-11 h-11 rounded-full bg-[#2a2a2a] flex items-center justify-center text-[#DC95FF]">
                      <FileUp className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white">
                        Klik untuk Pilih File dari Local atau Tarik ke Sini
                      </div>
                      <div className="text-[11px] text-[#B3B3B3] mt-0.5">
                        Mendukung PDF, Word DOC, & DOCX hingga 15 MB
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        fileInputRef.current?.click();
                      }}
                      className="mt-1 px-3.5 py-1.5 rounded-full bg-[#2e2e2e] hover:bg-[#3e3e3e] border border-white/10 text-xs font-semibold text-white flex items-center gap-1.5"
                    >
                      <Upload className="w-3.5 h-3.5 text-[#DC95FF]" />
                      Telusuri File di Komputer
                    </button>
                  </div>
                ) : (
                  <div className="p-3.5 rounded-xl bg-[#242424] border border-[#DC95FF]/40 flex items-center justify-between gap-3 shadow-md">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-[#DC95FF]/15 flex items-center justify-center text-[#DC95FF] shrink-0">
                        <FileText className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white truncate max-w-[210px] sm:max-w-[280px]">
                          {selectedFile.name}
                        </div>
                        <div className="text-[11px] text-[#B3B3B3] flex items-center gap-1.5 mt-0.5">
                          <span className="font-mono tabular-nums text-[#DC95FF]">
                            {(selectedFile.size / 1024).toFixed(1)} KB
                          </span>
                          <span>·</span>
                          <span className="uppercase text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white">
                            {selectedFile.name.split('.').pop()}
                          </span>
                          <span>·</span>
                          <span className="text-[#DC95FF] font-medium">Siap Diunggah</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium text-[#B3B3B3] hover:text-white hover:bg-white/5 transition-colors"
                        title="Ganti file lokal"
                      >
                        Ganti
                      </button>
                      <button
                        type="button"
                        onClick={handleClearSelectedFile}
                        className="p-1 rounded-full text-[#B3B3B3] hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                        title="Hapus pilihan file"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {selectedFile && (
                <div>
                  <label className="block text-xs font-medium text-[#B3B3B3] mb-1">
                    Ubah Nama File Simpanan (Opsional)
                  </label>
                  <input
                    type="text"
                    value={uploadFilename}
                    onChange={(e) => setUploadFilename(e.target.value)}
                    className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/35 focus:outline-none focus:border-[#DC95FF]"
                  />
                </div>
              )}

              <button
                type="submit"
                disabled={isUploading || (!selectedFile && !uploadFilename)}
                className="w-full py-2.5 px-4 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] disabled:opacity-40 disabled:cursor-not-allowed text-black font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow"
              >
                {isUploading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Mengunggah File ke Direktori Aman...
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    Validasi & Simpan Modul Lokal ke Direktori Aman
                  </>
                )}
              </button>
            </form>
          </div>

          <div className="lg:col-span-7 bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 space-y-4">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-[#DC95FF]" />
                Daftar Modul & Lampiran Tersedia ({attachments.length})
              </h2>
              <p className="text-xs text-[#B3B3B3] mt-1">
                Anggota terautentikasi dapat mengunduh modul. Penghapusan lampiran modul dikhususkan untuk <strong className="text-white">Admin Server</strong>.
              </p>
            </div>

            {attachments.length === 0 ? (
              <div className="py-10 text-center text-sm text-[#B3B3B3]">
                Belum ada lampiran modul pada server ini.
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {attachments.map((att) => (
                  <div
                    key={att.attachment_id}
                    className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-white truncate">
                        {att.original_filename}
                      </div>
                      <div className="text-xs text-[#B3B3B3] mt-0.5">
                        UUID Internal: <code className="font-mono">{att.stored_filename}</code> ·{' '}
                        <span className="font-mono tabular-nums">
                          {Math.round(att.size_bytes / 1024) || 1} KB
                        </span>{' '}
                        · Diunggah oleh {att.uploaded_by}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
                      <a
                        href={`/api/modules/${att.attachment_id}/download`}
                        download={att.original_filename}
                        className="px-3.5 py-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-xs font-semibold text-white flex items-center justify-center gap-1.5 transition-colors"
                      >
                        <Download className="w-3.5 h-3.5 text-[#DC95FF]" />
                        Unduh
                      </a>
                      {isAdmin && (
                        <button
                          type="button"
                          aria-label={`Hapus modul ${att.original_filename}`}
                          onClick={() => handleDeleteModule(att.attachment_id, att.original_filename)}
                          className="px-3.5 py-1.5 rounded-full bg-[#282828] hover:bg-rose-900/60 text-xs font-semibold text-[#B3B3B3] hover:text-rose-200 flex items-center justify-center gap-1.5 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-rose-400" />
                          Hapus
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="bg-[#181818] border border-white/5 rounded-xl p-4 sm:p-5 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#DC95FF]" />
              Sistem Tugas Akademik & Sinkronisasi Otomatis Waskita (Tiap 1 Jam)
            </h2>
            <div className="text-xs text-[#B3B3B3]">
              Auto-Sync Waskita: <strong className="text-white">Setiap 1 Jam (Filter Khusus Tugas Turn-In & Ber-Deadline)</strong> ·
              Jadwal Reminder Discord: <strong className="text-[#DC95FF]">Setiap Hari Pukul 00:01 WIB</strong> ·
              Status Waskita:{' '}
              {moodleEnv?.env_moodle_configured ? (
                <strong className="text-[#DC95FF]">
                  Aktif ({moodleEnv.has_credentials ? `Login ${moodleEnv.masked_username}` : 'Kalender iCal Terhubung'})
                </strong>
              ) : (
                <strong className="text-amber-400">
                  Siap Diatur via iCal atau Akun Waskita
                </strong>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setShowMoodleConfig((prev) => !prev)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white font-semibold text-xs transition-colors whitespace-nowrap"
            >
              <KeyRound className="w-3.5 h-3.5 text-[#DC95FF]" />
              {showMoodleConfig ? 'Tutup Konfigurasi Waskita' : 'Atur iCal & Login Waskita'}
            </button>

            <button
              type="button"
              onClick={handleSyncMoodleIcs}
              disabled={icsSyncing}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs transition-colors whitespace-nowrap"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${icsSyncing ? 'animate-spin' : ''}`} />
              {icsSyncing ? 'Menyinkronkan Waskita...' : 'Sinkronkan Kalender Waskita'}
            </button>
          </div>
        </div>

        {/* Panel Konfigurasi Waskita Calendar iCal & Username/Password */}
        {showMoodleConfig && (
          <div className="p-4 rounded-xl bg-[#232323] border border-white/10 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="text-xs font-bold text-white flex items-center gap-2">
                <Link2 className="w-4 h-4 text-[#DC95FF]" />
                Konfigurasi Kalender iCal & Akun Login Waskita
              </div>
              <span className="text-[11px] text-[#B3B3B3]">
                Otomatis disinkronkan tiap <strong className="text-white">1 jam</strong> (hanya tugas turn-in / memiliki due date) & perintah <code className="font-mono text-[#DC95FF]">/sync_waskita</code>
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-[11px] text-[#B3B3B3] mb-1">
                  URL Kalender iCal Waskita
                </label>
                <input
                  type="url"
                  placeholder={moodleEnv?.moodle_ical_url_preview || 'Contoh: https://waskita.kampus.ac.id/calendar/export_execute.php?...'}
                  value={moodleIcalUrl}
                  onChange={(e) => setMoodleIcalUrl(e.target.value)}
                  className="w-full bg-[#181818] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder:text-white/35"
                />
              </div>

              <div>
                <label className="block text-[11px] text-[#B3B3B3] mb-1">
                  URL Portal Waskita
                </label>
                <input
                  type="url"
                  placeholder={moodleEnv?.moodle_base_url || 'Contoh: https://waskita.kampus.ac.id'}
                  value={moodleBaseUrl}
                  onChange={(e) => setMoodleBaseUrl(e.target.value)}
                  className="w-full bg-[#181818] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder:text-white/35"
                />
              </div>

              <div>
                <label className="block text-[11px] text-[#B3B3B3] mb-1">
                  Username / NIM Waskita
                </label>
                <input
                  type="text"
                  placeholder={moodleEnv?.masked_username || 'Contoh: NIM / Username Waskita'}
                  value={moodleUsername}
                  onChange={(e) => setMoodleUsername(e.target.value)}
                  className="w-full bg-[#181818] border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/35"
                />
              </div>

              <div>
                <label className="block text-[11px] text-[#B3B3B3] mb-1">
                  Password Waskita
                </label>
                <input
                  type="password"
                  placeholder={moodleEnv?.has_credentials ? '•••••••• (Tersimpan di .env)' : 'Contoh: Password Waskita'}
                  value={moodlePassword}
                  onChange={(e) => setMoodlePassword(e.target.value)}
                  className="w-full bg-[#181818] border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/35"
                />
              </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 text-[11px] text-[#B3B3B3]">
              <span>
                Tip: Anda juga dapat mengisi URL iCal dan akun Waskita secara permanen melalui konfigurasi{' '}
                <code className="font-mono text-[#DC95FF]">.env</code> pada server.
              </span>
              <button
                type="button"
                onClick={handleSyncMoodleIcs}
                disabled={icsSyncing}
                className="px-4 py-1.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs shrink-0 self-start sm:self-auto"
              >
                Uji & Sinkronkan Sekarang
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-8 bg-[#181818] border border-white/5 rounded-xl p-4 sm:p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-white/10">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
              {(
                [
                  ['all', 'Semua Tugas'],
                  ['pending', 'Belum Selesai'],
                  ['completed', 'Selesai'],
                  ['overdue', 'Terlambat'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setStatusFilter(key)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors whitespace-nowrap ${
                    statusFilter === key
                      ? 'bg-white text-black'
                      : 'bg-[#282828] text-[#B3B3B3] hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <select
              aria-label="Filter mata kuliah"
              value={courseFilter}
              onChange={(e) => setCourseFilter(e.target.value)}
              className="bg-[#242424] border border-white/10 rounded-full px-3.5 py-1.5 text-xs text-white"
            >
              <option value="all">Semua Mata Kuliah ({courses.length})</option>
              {courses.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {filteredTasks.length === 0 ? (
            <div className="py-10 text-center text-sm text-[#B3B3B3]">
              Tidak ada tugas akademik yang sesuai dengan filter saat ini.
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {filteredTasks.map((task) => {
                const deadlineMs = new Date(task.deadline_iso).getTime();
                const hoursRemaining = Math.round((deadlineMs - nowMs) / (1000 * 3600));
                const stage = evaluateReminderStage(
                  task.deadline_iso,
                  nowMs,
                  Boolean(task.is_completed),
                  3
                );

                return (
                  <div
                    key={task.task_id}
                    className="py-3.5 grid grid-cols-[24px_minmax(0,1fr)_auto] items-start gap-3"
                  >
                    <button
                      type="button"
                      aria-label={
                        task.is_completed
                          ? `Buka kembali tugas ${task.title}`
                          : `Tandai selesai tugas ${task.title}`
                      }
                      onClick={() => handleToggleComplete(task.task_id)}
                      className="mt-0.5 text-[#B3B3B3] hover:text-[#DC95FF] transition-colors"
                    >
                      {task.is_completed ? (
                        <CheckCircle2 className="w-5 h-5 text-[#DC95FF]" />
                      ) : (
                        <Circle className="w-5 h-5" />
                      )}
                    </button>

                    <div className="min-w-0 space-y-1">
                      <div
                        className={`text-sm font-semibold ${
                          task.is_completed ? 'line-through text-white/40' : 'text-white'
                        }`}
                      >
                        {task.title}
                      </div>
                      <div className="text-xs text-[#B3B3B3] flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                        <span className="text-white/85 font-medium">{task.course_name}</span>
                        <span aria-hidden="true">·</span>
                        <span>{task.source_type === 'moodle_ics' ? 'Waskita' : task.source_type}</span>
                        <span aria-hidden="true">·</span>
                        <span className="font-mono tabular-nums">
                          {new Date(task.deadline_iso).toLocaleString('id-ID', {
                            dateStyle: 'medium',
                            timeStyle: 'short',
                          })}
                        </span>
                        {!task.is_completed && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span
                              className={`font-mono tabular-nums font-semibold ${
                                hoursRemaining <= 6 ? 'text-amber-400' : 'text-[#DC95FF]'
                              }`}
                            >
                              {hoursRemaining > 0
                                ? `Sisa ${hoursRemaining} jam`
                                : 'Melewati batas waktu'}
                            </span>
                          </>
                        )}
                        {stage && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span className="text-amber-300 font-medium">
                              Reminder {stage}
                            </span>
                          </>
                        )}
                      </div>
                      {task.description && (
                        <p className="text-xs text-[#B3B3B3] pt-0.5">{task.description}</p>
                      )}
                      {attachments.some((a) => a.task_id === task.task_id) && (
                        <div className="flex flex-wrap items-center gap-2 pt-1.5">
                          {attachments
                            .filter((a) => a.task_id === task.task_id)
                            .map((att) => (
                              <div
                                key={att.attachment_id}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#242424] border border-white/10 text-[11px] text-white"
                              >
                                <FileText className="w-3 h-3 text-[#DC95FF] shrink-0" />
                                <a
                                  href={`/api/modules/${att.attachment_id}/download`}
                                  download={att.original_filename}
                                  className="hover:text-[#DC95FF] truncate max-w-[180px] font-medium"
                                  title={`Unduh ${att.original_filename}`}
                                >
                                  {att.original_filename}
                                </a>
                                {isAdmin && (
                                  <button
                                    type="button"
                                    aria-label={`Hapus lampiran ${att.original_filename}`}
                                    onClick={() => handleDeleteModule(att.attachment_id, att.original_filename)}
                                    className="ml-0.5 p-0.5 rounded hover:bg-rose-500/20 text-[#B3B3B3] hover:text-rose-300 transition-colors"
                                    title={`Hapus lampiran ${att.original_filename}`}
                                  >
                                    <Trash2 className="w-3 h-3 text-rose-400" />
                                  </button>
                                )}
                              </div>
                            ))}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {task.source_url && (
                        <a
                          href={task.source_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Buka tautan tugas ${task.title}`}
                          className="p-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-[#B3B3B3] hover:text-white"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      <button
                        type="button"
                        aria-label={`Hapus tugas ${task.title}`}
                        onClick={() => handleDeleteTask(task.task_id)}
                        className="p-1.5 rounded-full bg-[#282828] hover:bg-rose-900/60 text-[#B3B3B3] hover:text-rose-200"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="lg:col-span-4 space-y-5">
          <form
            onSubmit={handleAddTask}
            className="bg-[#181818] border border-white/5 rounded-xl p-5 space-y-3"
          >
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Plus className="w-4 h-4 text-[#DC95FF]" />
              Tambah Tugas Akademik Baru
            </h3>

            <div>
              <label className="block text-xs text-[#B3B3B3] mb-1">Nama Mata Kuliah</label>
              <input
                type="text"
                placeholder="mis. IF3130 Jaringan Komputer"
                value={courseName}
                onChange={(e) => setCourseName(e.target.value)}
                className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white"
              />
            </div>

            <div>
              <label className="block text-xs text-[#B3B3B3] mb-1">Judul Tugas</label>
              <input
                type="text"
                placeholder="mis. Tugas Besar Routing OSPF"
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white"
              />
            </div>

            <div>
              <label className="block text-xs text-[#B3B3B3] mb-1">
                Tanggal & Waktu Deadline (WIB)
              </label>
              <input
                type="datetime-local"
                value={deadlineDate}
                onChange={(e) => setDeadlineDate(e.target.value)}
                className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono"
              />
            </div>

            <div>
              <label className="block text-xs text-[#B3B3B3] mb-1">Deskripsi Tugas</label>
              <textarea
                rows={2}
                placeholder="Instruksi pengumpulan atau catatan kelompok..."
                value={taskDesc}
                onChange={(e) => setTaskDesc(e.target.value)}
                className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white"
              />
            </div>

            <button
              type="submit"
              className="w-full py-2.5 px-4 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs transition-colors"
            >
              Simpan Tugas Baru
            </button>
          </form>

          <div className="bg-[#181818] border border-white/5 rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Bell className="w-4 h-4 text-[#DC95FF]" />
              Rekam Jejak Reminder Terkirim (Anti-Duplikat)
            </h3>
            <p className="text-xs text-[#B3B3B3]">
              Tercatat otomatis oleh sistem agar pengingat yang sama tidak dikirim berulang kali saat bot dimulai ulang.
            </p>
            <div className="divide-y divide-white/5 text-xs">
              {reminders.map((rem) => (
                <div key={rem.delivery_id} className="py-2 flex items-center justify-between">
                  <div>
                    <span className="font-mono text-white/80">{rem.task_id}</span> · Tahap{' '}
                    <strong className="text-[#DC95FF]">{rem.stage}</strong>
                  </div>
                  <span className="font-mono tabular-nums text-[#B3B3B3]">
                    {new Date(rem.delivered_at).toLocaleTimeString('id-ID', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const AcademyAndModulesView = React.memo(AcademyAndModulesViewComponent);