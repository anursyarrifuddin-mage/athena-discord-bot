import React, { useState, useEffect } from 'react';
import {
  Trophy,
  MessageSquarePlus,
  Clock,
  Settings,
  Shield,
  Database,
  RefreshCw,
  Download,
  Code2,
  CheckCircle2,
  Terminal,
  Mic,
  Headphones,
  MonitorUp,
  LogIn,
  Lock,
  Sparkles,
} from 'lucide-react';
import { AfkEntry, GuildSettings, LevelProfile } from '../types/athenaa';
import { SLASH_COMMANDS_LIST } from '../utils/slashCommandsData';

interface RpgAndSettingsViewProps {
  subTab: 'rpg' | 'afk' | 'settings' | 'admin' | 'codebase';
  guildId: string;
  sessionToken: string;
  isOwner: boolean;
  leaderboard: LevelProfile[];
  afkList: AfkEntry[];
  guildSettings: GuildSettings | null;
  onRefreshRpg: () => void;
  onRefreshSettings: () => void;
  onNotify: (msg: string, isError?: boolean) => void;
}

const RpgAndSettingsViewComponent: React.FC<RpgAndSettingsViewProps> = ({
  subTab,
  guildId,
  sessionToken,
  isOwner,
  leaderboard,
  afkList,
  guildSettings,
  onRefreshRpg,
  onRefreshSettings,
  onNotify,
}) => {
  const [simMessage, setSimMessage] = useState('');
  const [simActivityType, setSimActivityType] = useState<
    'chat' | 'voice_join' | 'voice_speak' | 'voice_listen' | 'voice_stream'
  >('chat');
  const [afkReason, setAfkReason] = useState('');

  const [musicCh, setMusicCh] = useState(guildSettings?.music_channel_id || '');
  const [taskCh, setTaskCh] = useState(guildSettings?.task_channel_id || '');
  const [djRole, setDjRole] = useState(guildSettings?.dj_role_id || '');
  const [moodleUrl, setMoodleUrl] = useState(guildSettings?.moodle_ics_url_encrypted || '');
  const [remDays, setRemDays] = useState(guildSettings?.reminder_days_before || 3);
  const [tz, setTz] = useState(guildSettings?.timezone || 'Asia/Jakarta');
  const [expCooldown, setExpCooldown] = useState(guildSettings?.exp_cooldown_seconds || 60);

  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [ytdlpStatus, setYtdlpStatus] = useState<Record<string, unknown> | null>(null);
  const [adminBusy, setAdminBusy] = useState(false);

  const [pyFiles, setPyFiles] = useState<Array<{ path: string; role: string }>>([]);
  const [selectedPyFile, setSelectedPyFile] = useState('app/main.py');
  const [pyRole, setPyRole] = useState('');
  const [pyContent, setPyContent] = useState('');

  useEffect(() => {
    if (guildSettings) {
      setMusicCh(guildSettings.music_channel_id);
      setTaskCh(guildSettings.task_channel_id);
      setDjRole(guildSettings.dj_role_id);
      setMoodleUrl(guildSettings.moodle_ics_url_encrypted);
      setRemDays(guildSettings.reminder_days_before);
      setTz(guildSettings.timezone);
      setExpCooldown(guildSettings.exp_cooldown_seconds);
    }
  }, [guildSettings]);

  const loadAdminMetrics = async () => {
    if (!isOwner) return;
    const resp = await fetch(`/api/admin/metrics?is_owner=${isOwner ? 'true' : 'false'}`, {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (resp.ok) {
      setMetrics(await resp.json());
    }
  };

  const loadPythonFile = async (filePath: string) => {
    if (!isOwner) return;
    const resp = await fetch(`/api/python-codebase?file=${encodeURIComponent(filePath)}`, {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (resp.ok) {
      const data = await resp.json();
      setPyFiles(data.files || []);
      setSelectedPyFile(data.selected_file);
      setPyRole(data.selected_role);
      setPyContent(data.content);
    }
  };

  useEffect(() => {
    if (subTab === 'admin' && isOwner) {
      loadAdminMetrics();
    } else if (subTab === 'codebase' && isOwner) {
      loadPythonFile(selectedPyFile);
    }
  }, [subTab, isOwner, sessionToken]);

  if (subTab === 'rpg') {
    const expSources = [
      {
        key: 'chat',
        label: 'Chat Server',
        gain: '+15~25 EXP',
        desc: 'Kirim pesan aktif di channel teks server Discord (anti-spam cooldown 60d)',
        icon: <MessageSquarePlus className="w-3.5 h-3.5 text-[#DC95FF]" />,
      },
      {
        key: 'voice_join',
        label: 'Join Voice',
        gain: '+20 EXP',
        desc: 'Bergabung ke Voice Channel server bersama anggota lain',
        icon: <LogIn className="w-3.5 h-3.5 text-sky-400" />,
      },
      {
        key: 'voice_speak',
        label: 'Speak / Unmute',
        gain: '+15 EXP/m',
        desc: 'Berbicara (unmuted) saat diskusi atau nongkrong di Voice Channel',
        icon: <Mic className="w-3.5 h-3.5 text-[#DC95FF]" />,
      },
      {
        key: 'voice_listen',
        label: 'Listening',
        gain: '+10 EXP/m',
        desc: 'Mendengarkan musik/diskusi di Voice Channel tanpa deafen',
        icon: <Headphones className="w-3.5 h-3.5 text-amber-400" />,
      },
      {
        key: 'voice_stream',
        label: 'Streaming / Cam',
        gain: '+25 EXP/m',
        desc: 'Share screen materi kuliah, live coding, atau menyalakan kamera di Voice',
        icon: <MonitorUp className="w-3.5 h-3.5 text-purple-400" />,
      },
    ] as const;

    return (
      <div className="space-y-5">
        {/* Sumber Perolehan EXP Banner */}
        <div className="bg-[#181818] border border-white/5 rounded-xl p-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#DC95FF]" />
              <span className="text-xs font-bold text-white">
                Sumber Perolehan EXP Server (Otomatis & Real-Time dari Discord)
              </span>
            </div>
            <span className="text-[11px] text-[#B3B3B3]">
              Termasuk bonus dari command <code className="font-mono text-[#DC95FF]">/kuis</code>,{' '}
              <code className="font-mono text-[#DC95FF]">/mathbattle</code>,{' '}
              <code className="font-mono text-[#DC95FF]">/suit</code>, &{' '}
              <code className="font-mono text-[#DC95FF]">/pomodoro</code>
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-2.5 pt-3">
            {expSources.map((src) => (
              <div
                key={src.key}
                className="p-3 rounded-lg bg-[#232323] border border-white/5 flex flex-col justify-between gap-1.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-1">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    {src.icon}
                    {src.label}
                  </span>
                  <span className="text-[10px] font-mono font-bold text-[#DC95FF] bg-[#DC95FF]/10 px-1.5 py-0.5 rounded whitespace-nowrap">
                    {src.gain}
                  </span>
                </div>
                <p className="text-[11px] text-[#B3B3B3] leading-snug">{src.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-8 bg-[#181818] border border-white/5 rounded-xl overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <Trophy className="w-4 h-4 text-[#DC95FF]" />
                  Leaderboard Server (Top 15)
                </h2>
                <p className="text-xs text-[#B3B3B3] mt-0.5">
                  Formula progresif: <code className="font-mono text-white">max_exp = 100 + (level * 25)</code> · Cooldown anti-farming aktif.
                </p>
              </div>
            </div>

            <div className="p-2 sm:p-3 overflow-x-auto">
              <div className="min-w-[460px]">
                <div className="grid grid-cols-[40px_minmax(0,1.5fr)_68px_minmax(0,1.4fr)_90px] items-center gap-3 px-3 py-2 border-b border-white/10 text-xs font-medium text-[#B3B3B3]">
                  <span>#</span>
                  <span>Anggota Server</span>
                  <span className="text-right">Level</span>
                  <span>Progres EXP</span>
                  <span className="text-right">Aktivitas</span>
                </div>

                <div className="divide-y divide-white/5 mt-1">
                  {leaderboard.map((prof) => {
                    const pct = Math.min(100, Math.round((prof.current_exp / prof.max_exp) * 100));
                    return (
                      <div
                        key={prof.user_id}
                        className="grid grid-cols-[40px_minmax(0,1.5fr)_68px_minmax(0,1.4fr)_90px] items-center gap-3 px-3 py-3 rounded-lg hover:bg-white/5 transition-colors"
                      >
                        <span className="font-mono tabular-nums font-bold text-xs text-[#B3B3B3]">
                          #{prof.rank}
                        </span>
                        <div className="min-w-0">
                          <div className="font-semibold text-white text-sm truncate">
                            {prof.display_name}
                          </div>
                          <div className="text-xs text-[#B3B3B3] truncate">@{prof.username}</div>
                        </div>
                        <span className="font-mono tabular-nums font-bold text-[#DC95FF] text-sm text-right">
                          Lv. {prof.level}
                        </span>
                        <div>
                          <div className="flex items-center justify-between text-xs font-mono tabular-nums text-[#B3B3B3] mb-1">
                            <span>
                              {prof.current_exp} / {prof.max_exp} EXP
                            </span>
                            <span>{pct}%</span>
                          </div>
                          <div className="w-full h-1.5 bg-[#282828] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-[#DC95FF]"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                        <span className="font-mono tabular-nums text-xs text-white/80 text-right">
                          {prof.total_messages}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 space-y-5">
            {isOwner ? (
              <div className="bg-[#181818] border border-white/5 rounded-xl p-5 space-y-3.5">
                <div className="space-y-1.5">
                  <span className="inline-block px-2 py-0.5 rounded-full bg-[#DC95FF]/15 text-[#DC95FF] text-[10px] font-bold">
                    KHUSUS BOT OWNER
                  </span>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Shield className="w-4 h-4 text-[#DC95FF] shrink-0" />
                    Uji Aktivitas & Anti-Spam EXP
                  </h3>
                </div>
                <p className="text-xs text-[#B3B3B3]">
                  Panel pengujian EXP ini dikunci khusus <strong className="text-white">Bot Owner</strong> agar anggota biasa tidak dapat melakukan spam/dupe EXP dari web panel.
                </p>

                <div>
                  <label className="block text-[11px] text-[#B3B3B3] mb-1">
                    Pilih Jenis Aktivitas Discord
                  </label>
                  <select
                    aria-label="Jenis aktivitas EXP"
                    value={simActivityType}
                    onChange={(e) =>
                      setSimActivityType(
                        e.target.value as
                          | 'chat'
                          | 'voice_join'
                          | 'voice_speak'
                          | 'voice_listen'
                          | 'voice_stream'
                      )
                    }
                    className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white"
                  >
                    <option value="chat">Chat di Server (+25 EXP)</option>
                    <option value="voice_join">Join Voice Channel (+20 EXP)</option>
                    <option value="voice_speak">Speak / Unmute di Voice (+15 EXP)</option>
                    <option value="voice_listen">Listening di Voice (+10 EXP)</option>
                    <option value="voice_stream">Streaming / Cam di Voice (+25 EXP)</option>
                  </select>
                </div>

                {simActivityType === 'chat' && (
                  <input
                    type="text"
                    placeholder="Contoh: Mengerjakan latihan soal Algoritma & Struktur Data"
                    value={simMessage}
                    onChange={(e) => setSimMessage(e.target.value)}
                    className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/35"
                  />
                )}

                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={async () => {
                      const resp = await fetch(`/api/guilds/${guildId}/rpg/activity`, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                          'Content-Type': 'application/json',
                          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
                        },
                        body: JSON.stringify({
                          activity_type: simActivityType,
                          message_content:
                            simMessage.trim() || 'Mengerjakan latihan soal Algoritma & Struktur Data',
                          bypass_cooldown: false,
                        }),
                      });
                      const data = await resp.json();
                      if (!resp.ok) {
                        onNotify(data.error || 'Aksi ditolak.', true);
                        return;
                      }
                      onNotify(
                        data.leveled_up
                          ? `Level Up! Naik ke Level ${data.level} (${data.current_exp}/${data.max_exp} EXP)`
                          : `EXP (${simActivityType}) bertambah! Level ${data.level} (${data.current_exp}/${data.max_exp} EXP)`
                      );
                      onRefreshRpg();
                    }}
                    className="w-full py-2.5 px-3 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
                  >
                    Uji Aktivitas (Patuhi Cooldown Anti-Spam)
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      const resp = await fetch(`/api/guilds/${guildId}/rpg/activity`, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                          'Content-Type': 'application/json',
                          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
                        },
                        body: JSON.stringify({
                          activity_type: simActivityType,
                          message_content:
                            simMessage.trim() || 'Mengerjakan latihan soal Algoritma & Struktur Data',
                          bypass_cooldown: true,
                        }),
                      });
                      const data = await resp.json();
                      if (resp.ok) {
                        onNotify(
                          `Simulasi Owner berhasil (Level ${data.level}: ${data.current_exp}/${data.max_exp} EXP).`
                        );
                        onRefreshRpg();
                      } else {
                        onNotify(data.error || 'Akses ditolak.', true);
                      }
                    }}
                    className="w-full py-2 px-3 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white font-semibold text-xs"
                  >
                    Tambah EXP Instan (Bypass Cooldown — Owner)
                  </button>
                </div>
              </div>
            ) : (
              <div className="bg-[#181818] border border-white/5 rounded-xl p-5 space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-[#DC95FF]">
                  <Lock className="w-4 h-4 shrink-0" />
                  Proteksi Anti-Spam & Anti-Dupe EXP Aktif
                </div>
                <p className="text-xs text-[#B3B3B3] leading-relaxed">
                  Penambahan EXP dihitung secara otomatis dari aktivitas asli Anda di server Discord:
                </p>
                <ul className="text-xs text-white/85 space-y-1.5 pl-4 list-disc">
                  <li>Chat diskusi di channel server Discord</li>
                  <li>Join Voice Channel & mendengarkan musik/diskusi</li>
                  <li>Berbicara (Speak/Unmuted) di Voice Channel</li>
                  <li>Share Screen / Streaming atau menyalakan kamera</li>
                  <li>Bermain minigames (<code className="font-mono text-[#DC95FF]">/kuis</code>, <code className="font-mono text-[#DC95FF]">/mathbattle</code>, <code className="font-mono text-[#DC95FF]">/suit</code>)</li>
                </ul>
                <p className="text-[11px] text-[#B3B3B3] pt-1 border-t border-white/5">
                  Fitur simulasi EXP manual pada dashboard dikunci khusus untuk Bot Owner.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (subTab === 'afk') {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-5 bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#DC95FF]" />
            Pasang Status AFK
          </h2>
          <p className="text-xs text-[#B3B3B3]">
            Saat anggota di-mention di Discord, bot otomatis membalas dengan kartu Embed berisi alasan dan waktu mulai AFK. Status AFK otomatis dicabut saat anggota kembali berkirim pesan.
          </p>
          <input
            type="text"
            placeholder="Contoh: Sedang kuliah tatap muka di gedung lab"
            value={afkReason}
            onChange={(e) => setAfkReason(e.target.value)}
            className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/35"
          />
          <button
            type="button"
            onClick={async () => {
              const reasonToSave = afkReason.trim() || 'Sedang AFK';
              const resp = await fetch(`/api/guilds/${guildId}/afk`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: reasonToSave }),
              });
              if (resp.ok) {
                setAfkReason('');
                onNotify('Status AFK berhasil diaktifkan.');
                onRefreshRpg();
              }
            }}
            className="w-full py-2.5 px-4 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
          >
            Aktifkan Status AFK Sekarang
          </button>
        </div>

        <div className="lg:col-span-7 bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 space-y-4">
          <h2 className="text-base font-bold text-white">
            Daftar Anggota Server yang Sedang AFK ({afkList.length})
          </h2>
          {afkList.length === 0 ? (
            <div className="py-8 text-center text-sm text-[#B3B3B3]">
              Tidak ada anggota yang sedang berstatus AFK saat ini.
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {afkList.map((entry) => (
                <div key={entry.user_id} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-white truncate">{entry.username}</div>
                    <div className="text-xs text-[#B3B3B3]">
                      Alasan: <span className="text-white">{entry.reason}</span> · Sejak{' '}
                      <span className="font-mono tabular-nums">
                        {new Date(entry.started_at).toLocaleTimeString('id-ID')}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await fetch(`/api/guilds/${guildId}/afk/${entry.user_id}`, {
                        method: 'DELETE',
                      });
                      onNotify(`Status AFK ${entry.username} telah dicabut.`);
                      onRefreshRpg();
                    }}
                    className="px-3.5 py-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-xs font-semibold text-white shrink-0"
                  >
                    Cabut AFK
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (subTab === 'settings') {
    return (
      <div className="bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 max-w-3xl space-y-5">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Settings className="w-4 h-4 text-[#DC95FF]" />
            Pengaturan Multi-Guild Server ({guildSettings?.guild_name || guildId})
          </h2>
          <p className="text-xs text-[#B3B3B3] mt-1">
            Setiap server Discord memiliki konfigurasi terpisah untuk channel musik, channel pengingat tugas, dan role DJ.
          </p>
        </div>

        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const resp = await fetch(`/api/guilds/${guildId}/settings`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                music_channel_id: musicCh,
                task_channel_id: taskCh,
                dj_role_id: djRole,
                moodle_ics_url_encrypted: moodleUrl,
                reminder_days_before: Number(remDays),
                timezone: tz,
                exp_cooldown_seconds: Number(expCooldown),
              }),
            });
            if (resp.ok) {
              onNotify('Pengaturan server berhasil disimpan.');
              onRefreshSettings();
            }
          }}
          className="grid grid-cols-1 sm:grid-cols-2 gap-4"
        >
          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">ID Music Channel Discord</label>
            <input
              type="text"
              value={musicCh}
              onChange={(e) => setMusicCh(e.target.value)}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">
              ID Task Reminder Channel Discord (00:01 WIB · <code className="font-mono">TASK_REMINDER_CHANNEL_ID</code>)
            </label>
            <input
              type="text"
              placeholder="Contoh: 1558142572164022362 (atau atur di .env)"
              value={taskCh}
              onChange={(e) => setTaskCh(e.target.value)}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder:text-white/35"
            />
          </div>

          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">ID Role DJ Server</label>
            <input
              type="text"
              value={djRole}
              onChange={(e) => setDjRole(e.target.value)}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">Zona Waktu Server</label>
            <input
              type="text"
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white"
            />
          </div>

          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">
              Interval Reminder Tahap 1 (H-x Hari)
            </label>
            <input
              type="number"
              min={1}
              max={14}
              value={remDays}
              onChange={(e) => setRemDays(Number(e.target.value))}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono"
            />
          </div>

          <div>
            <label className="block text-xs text-[#B3B3B3] mb-1">
              Cooldown EXP Leaderboard per Anggota (Detik)
            </label>
            <input
              type="number"
              min={10}
              max={600}
              value={expCooldown}
              onChange={(e) => setExpCooldown(Number(e.target.value))}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs text-[#B3B3B3] mb-1">
              Tautan Kalender Waskita (.ics) — Dapat Diatur via <code className="font-mono">MOODLE_ICAL_URL</code> di <code className="font-mono">.env</code>
            </label>
            <input
              type="text"
              placeholder="Contoh: https://waskita.kampus.ac.id/calendar/export_execute.php?..."
              value={moodleUrl}
              onChange={(e) => setMoodleUrl(e.target.value)}
              className="w-full bg-[#242424] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder:text-white/35"
            />
          </div>

          <div className="sm:col-span-2 pt-2">
            <button
              type="submit"
              className="px-6 py-2.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
            >
              Simpan Pengaturan Server
            </button>
          </div>
        </form>
      </div>
    );
  }

  if (subTab === 'admin') {
    const backups = (metrics?.backups as Array<Record<string, unknown>>) || [];
    return (
      <div className="space-y-5">
        <div className="bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-white/10">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Shield className="w-4 h-4 text-[#DC95FF]" />
                Super-Admin Hub (Khusus OWNER_DISCORD_ID)
              </h2>
              <p className="text-xs text-[#B3B3B3] mt-0.5">
                Metrik diukur langsung dari proses aplikasi saat ini beserta fitur cadangan data terenkripsi.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={adminBusy}
                onClick={async () => {
                  setAdminBusy(true);
                  try {
                    const resp = await fetch('/api/admin/backup', {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${sessionToken}`,
                      },
                      body: JSON.stringify({ is_owner: true }),
                    });
                    const data = await resp.json();
                    if (resp.ok) {
                      onNotify(`Cadangan data terenkripsi berhasil dibuat: ${data.filename}`);
                      loadAdminMetrics();
                    } else {
                      onNotify(data.error || 'Backup gagal', true);
                    }
                  } finally {
                    setAdminBusy(false);
                  }
                }}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
              >
                <Database className="w-3.5 h-3.5" />
                Buat Cadangan Data Sekarang
              </button>

              <button
                type="button"
                disabled={adminBusy}
                onClick={async () => {
                  setAdminBusy(true);
                  try {
                    const resp = await fetch('/api/admin/yt-dlp', {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${sessionToken}`,
                      },
                      body: JSON.stringify({ is_owner: true, perform_update: false }),
                    });
                    const data = await resp.json();
                    setYtdlpStatus(data);
                    onNotify(String(data.message || 'Pemeriksaan yt-dlp selesai.'));
                  } finally {
                    setAdminBusy(false);
                  }
                }}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white font-semibold text-xs"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Cek Worker yt-dlp
              </button>

              <button
                type="button"
                disabled={adminBusy}
                onClick={async () => {
                  setAdminBusy(true);
                  try {
                    const resp = await fetch('/api/admin/run-tests', {
                      method: 'POST',
                      headers: { Authorization: `Bearer ${sessionToken}` },
                    });
                    const data = await resp.json();
                    setTestResult(data);
                    onNotify(`Suite unittest Python selesai: ${data.ran} tes dijalankan.`);
                  } finally {
                    setAdminBusy(false);
                  }
                }}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white font-semibold text-xs"
              >
                <Terminal className="w-3.5 h-3.5 text-[#DC95FF]" />
                Jalankan Automated Tests Python
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
            <div className="p-4 rounded-xl bg-[#242424]">
              <div className="text-xs text-[#B3B3B3]">RAM Proses Kontainer (RSS)</div>
              <div className="text-xl font-bold font-mono tabular-nums text-white mt-1">
                {String(metrics?.ram_rss_mb ?? '—')} MB
              </div>
            </div>
            <div className="p-4 rounded-xl bg-[#242424]">
              <div className="text-xs text-[#B3B3B3]">CPU Load Average (1m)</div>
              <div className="text-xl font-bold font-mono tabular-nums text-white mt-1">
                {String(metrics?.cpu_load_1m ?? '—')}
              </div>
            </div>
            <div className="p-4 rounded-xl bg-[#242424]">
              <div className="text-xs text-[#B3B3B3]">Ukuran Penyimpanan Data</div>
              <div className="text-xl font-bold font-mono tabular-nums text-[#DC95FF] mt-1">
                {String(metrics?.database_size_kb ?? '—')} KB
              </div>
            </div>
            <div className="p-4 rounded-xl bg-[#242424]">
              <div className="text-xs text-[#B3B3B3]">Runtime & Audio Stack</div>
              <div className="text-sm font-bold text-white mt-1.5">
                {String(metrics?.python_version ?? 'Python 3.12 + FFmpeg')}
              </div>
            </div>
          </div>

          {ytdlpStatus && (
            <div className="mt-4 p-3.5 rounded-xl bg-[#242424] text-xs text-white">
              <strong>Status Ekstraktor Audio:</strong> Versi={String(ytdlpStatus.current_version)} ·{' '}
              {String(ytdlpStatus.message)}
            </div>
          )}

          {testResult && (
            <div className="mt-4 p-4 rounded-xl bg-[#242424] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#DC95FF] flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  Hasil Eksekusi Pengujian Sistem ({String(testResult.ran)} Tes Lulus)
                </span>
              </div>
              <pre className="text-xs font-mono text-white/85 overflow-x-auto whitespace-pre-wrap">
                {String(testResult.output)}
              </pre>
            </div>
          )}

          <div className="mt-6">
            <h3 className="text-sm font-bold text-white mb-2">
              Daftar Arsip Cadangan Data Terenkripsi ({backups.length})
            </h3>
            {backups.length === 0 ? (
              <p className="text-xs text-[#B3B3B3]">
                Belum ada file cadangan. Klik tombol "Buat Cadangan Data Sekarang" di atas.
              </p>
            ) : (
              <div className="divide-y divide-white/5 text-xs">
                {backups.map((b) => (
                  <div key={String(b.filename)} className="py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <span className="font-mono text-white truncate">{String(b.filename)}</span>
                    <span className="font-mono tabular-nums text-[#B3B3B3]">
                      {String(b.size_bytes)} bytes · {new Date(String(b.created_at)).toLocaleString('id-ID')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="bg-[#181818] border border-rose-800/40 rounded-xl p-8 text-center space-y-2">
        <Shield className="w-8 h-8 text-rose-400 mx-auto" />
        <h2 className="text-base font-bold text-white">Akses Ditolak — Khusus Bot Owner</h2>
        <p className="text-xs text-[#B3B3B3] max-w-md mx-auto">
          Kode sumber Bot Python (<code className="font-mono">/athenaa</code>), unduhan paket{' '}
          <code className="font-mono">.zip</code>, dan Super-Admin Hub hanya dapat diakses oleh sesi login Bot Owner.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="bg-[#181818] border border-white/5 rounded-xl p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Code2 className="w-4 h-4 text-[#DC95FF]" />
            Kode Sumber Lengkap Bot Python (<code className="font-mono">/athenaa</code>) & Paket Deploy Pterodactyl
          </h2>
          <p className="text-xs text-[#B3B3B3] mt-1">
            Seluruh modul Bot Discord, API Web Player, Lirik Otomatis, dan Kalender Akademik Waskita telah terintegrasi dan siap dijalankan pada VPS atau Pterodactyl.
          </p>
        </div>

        <a
          href={`/api/python-codebase/download-zip?session_token=${encodeURIComponent(sessionToken)}`}
          download="athenaa-discord-bot.zip"
          className="px-4 py-2 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs flex items-center justify-center gap-2 shrink-0 whitespace-nowrap"
        >
          <Download className="w-4 h-4" />
          Unduh Paket Bot Python (.zip)
        </a>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-4 bg-[#181818] border border-white/5 rounded-xl p-4 space-y-1">
          <div className="text-xs font-bold text-white px-2 pb-2 border-b border-white/10">
            Struktur Modul Proyek <code className="font-mono">athenaa/</code>
          </div>
          {pyFiles.map((f) => (
            <button
              key={f.path}
              type="button"
              onClick={() => loadPythonFile(f.path)}
              className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                selectedPyFile === f.path
                  ? 'bg-[#282828] text-[#DC95FF] font-semibold'
                  : 'text-[#B3B3B3] hover:bg-white/5 hover:text-white'
              }`}
            >
              <div className="font-mono">{f.path}</div>
              <div className="text-[11px] text-[#B3B3B3] truncate mt-0.5">{f.role}</div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-8 bg-[#181818] border border-white/5 rounded-xl overflow-hidden flex flex-col">
          <div className="px-5 py-3.5 border-b border-white/10 bg-[#242424] flex items-center justify-between">
            <div>
              <span className="font-mono text-xs font-bold text-[#DC95FF]">
                athenaa/{selectedPyFile}
              </span>
              <p className="text-xs text-[#B3B3B3] mt-0.5">{pyRole}</p>
            </div>
          </div>
          <pre className="p-4 sm:p-5 text-xs font-mono text-white/90 overflow-x-auto max-h-[540px] leading-relaxed">
            {pyContent}
          </pre>
        </div>
      </div>

      <div className="bg-[#181818] border border-white/5 rounded-xl p-5 sm:p-6 space-y-4">
        <h3 className="text-base font-bold text-white">
          Daftar Lengkap Discord Slash Commands & Addon Mahasiswa/Minigames (<code className="font-mono">app/bot/client.py</code>)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {SLASH_COMMANDS_LIST.map((cmd) => (
            <div
              key={cmd.name}
              className="p-3.5 rounded-xl bg-[#242424] space-y-1"
            >
              <div className="flex items-center justify-between gap-2">
                <code className="font-mono text-xs font-bold text-[#DC95FF]">
                  {cmd.name} {cmd.params}
                </code>
                <span className="text-[11px] text-[#B3B3B3] shrink-0">{cmd.category}</span>
              </div>
              <p className="text-xs text-white/80">{cmd.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export const RpgAndSettingsView = React.memo(RpgAndSettingsViewComponent);
