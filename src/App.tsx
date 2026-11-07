/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Home,
  Disc3,
  ListOrdered,
  Library,
  GraduationCap,
  FileArchive,
  Trophy,
  Clock,
  Settings,
  Shield,
  Code2,
  Play,
  CheckCircle2,
  Circle,
  Download,
  Music,
  ShieldCheck,
  Mic2,
  Clock3,
  Radio,
  LogOut,
  LogIn,
  Lock,
  Menu,
  X,
  ListMusic,
} from 'lucide-react';
import {
  AcademicTask,
  ActiveActorProfile,
  AfkEntry,
  GuildMusicState,
  GuildSettings,
  LevelProfile,
  ReminderDelivery,
  TaskAttachment,
  TrackItem,
} from './types/athenaa';
import { SearchDropdownBar, formatDuration } from './components/SearchDropdownBar';
import { SpotifyBottomPlayer } from './components/SpotifyBottomPlayer';
import { MusicAndLyricsView } from './components/MusicAndLyricsView';
import { AcademyAndModulesView, MoodleEnvStatus } from './components/AcademyAndModulesView';
import { RpgAndSettingsView } from './components/RpgAndSettingsView';
import { audioEngine } from './utils/audioSynth';

type NavTab =
  | 'overview'
  | 'player'
  | 'queue'
  | 'academy'
  | 'modules'
  | 'rpg'
  | 'afk'
  | 'settings'
  | 'admin'
  | 'codebase';

const DEFAULT_ADMIN_PROFILE: ActiveActorProfile = {
  id: '844174494099701780',
  name: 'Aetheriaaa',
  role: 'admin',
  roleLabel: 'Admin Server',
  roles: ['role-admin', 'role-dj'],
  hasDjRole: true,
  isAdmin: true,
  isOwner: true,
};

const DEFAULT_MUSIC_STATE: GuildMusicState = {
  guild_id: '1428666546942902294',
  voice_channel_id: '1428666547701809167',
  voice_channel_name: 'NyolBar',
  host_user_id: '844174494099701780',
  host_username: 'Aetheriaaa',
  current_track: null,
  queue: [],
  is_playing: false,
  is_paused: false,
  position_sec: 0,
  volume: 80,
  loop_mode: 'off',
  autoplay: true,
  mode_247: true,
  active_radio_name: '',
  radios: [],
};

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('overview');
  const [sidebarFilter, setSidebarFilter] = useState<'all' | 'music' | 'academy' | 'system'>('all');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [guilds, setGuilds] = useState<GuildSettings[]>([]);
  const [selectedGuildId, setSelectedGuildId] = useState('1428666546942902294');
  const [activeActor, setActiveActor] = useState<ActiveActorProfile>(DEFAULT_ADMIN_PROFILE);
  const [sessionToken, setSessionToken] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    const urlTok = params.get('session_token');
    if (urlTok) {
      window.localStorage.setItem('athenaa_session_token', urlTok);
      return urlTok;
    }
    return window.localStorage.getItem('athenaa_session_token') || 'default-admin-session';
  });
  const [showLoginModal, setShowLoginModal] = useState(false);

  const [musicState, setMusicState] = useState<GuildMusicState>(DEFAULT_MUSIC_STATE);
  const [tasks, setTasks] = useState<AcademicTask[]>([]);
  const [attachments, setAttachments] = useState<TaskAttachment[]>([]);
  const [reminders, setReminders] = useState<ReminderDelivery[]>([]);
  const [moodleEnv, setMoodleEnv] = useState<MoodleEnvStatus | null>(null);
  const [leaderboard, setLeaderboard] = useState<LevelProfile[]>([]);
  const [afkList, setAfkList] = useState<AfkEntry[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [browserAudioMuted, setBrowserAudioMuted] = useState(false);
  const [bannerNotice, setBannerNotice] = useState<{ text: string; isError: boolean } | null>(null);

  const showNotice = useCallback((text: string, isError = false) => {
    setBannerNotice({ text, isError });
    window.setTimeout(() => {
      setBannerNotice((prev) => (prev?.text === text ? null : prev));
    }, 4500);
  }, []);

  const applyAuthenticatedUser = useCallback(
    (
      token: string,
      user: {
        id: string;
        name: string;
        role?: 'admin' | 'dj' | 'member';
        roleLabel: string;
        isOwner?: boolean;
        hasDjRole: boolean;
        isAdmin: boolean;
      }
    ) => {
      window.localStorage.setItem('athenaa_session_token', token);
      setSessionToken(token);
      const resolvedRole: 'admin' | 'dj' | 'member' =
        user.role || (user.isAdmin ? 'admin' : user.hasDjRole ? 'dj' : 'member');
      setActiveActor({
        id: user.id,
        name: user.name,
        role: resolvedRole,
        roleLabel:
          user.roleLabel ||
          (resolvedRole === 'admin'
            ? 'Admin Server'
            : resolvedRole === 'dj'
            ? 'Role DJ'
            : 'Member Server'),
        roles:
          resolvedRole === 'admin'
            ? ['role-admin', 'role-dj']
            : resolvedRole === 'dj'
            ? ['role-dj']
            : [],
        hasDjRole: Boolean(user.hasDjRole || resolvedRole === 'admin' || resolvedRole === 'dj'),
        isAdmin: Boolean(user.isAdmin || resolvedRole === 'admin'),
        isOwner: Boolean(user.isAdmin || resolvedRole === 'admin'),
      });
      setShowLoginModal(false);
      if (resolvedRole !== 'admin') {
        setActiveTab((prev) => (prev === 'admin' || prev === 'codebase' ? 'overview' : prev));
      }
    },
    []
  );

  const handleSwitchRole = useCallback(
    async (role: 'admin' | 'dj' | 'member') => {
      try {
        const resp = await fetch('/api/auth/login', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role }),
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.session_token && data.user) {
            applyAuthenticatedUser(data.session_token, data.user);
            showNotice(`Peran aktif diubah ke: ${data.user.roleLabel} (${data.user.name})`);
            return;
          }
        }
      } catch {
        // Fallback local switch if offline
      }
      const fallbackUser =
        role === 'admin'
          ? {
              id: '844174494099701780',
              name: 'Aetheriaaa',
              role: 'admin' as const,
              roleLabel: 'Admin Server',
              isAdmin: true,
              hasDjRole: true,
            }
          : role === 'dj'
          ? {
              id: '532574896605757452',
              name: 'Nacht',
              role: 'dj' as const,
              roleLabel: 'Role DJ',
              isAdmin: false,
              hasDjRole: true,
            }
          : {
              id: '698812445519002112',
              name: 'Kazuha',
              role: 'member' as const,
              roleLabel: 'Member Server',
              isAdmin: false,
              hasDjRole: false,
            };
      applyAuthenticatedUser(`local-${role}-session`, fallbackUser);
      showNotice(`Peran aktif diubah ke: ${fallbackUser.roleLabel}`);
    },
    [applyAuthenticatedUser, showNotice]
  );

  // Validate or bootstrap Discord session on load (defaults to Admin Server if not configured)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlTok = params.get('session_token');
    if (urlTok) {
      window.localStorage.setItem('athenaa_session_token', urlTok);
      window.history.replaceState({}, '', window.location.pathname);
    }

    const storedToken = urlTok || window.localStorage.getItem('athenaa_session_token') || '';
    const url = storedToken
      ? `/api/auth/session?session_token=${encodeURIComponent(storedToken)}`
      : '/api/auth/session?auto_bootstrap=1';

    fetch(url, {
      credentials: 'include',
      headers: storedToken ? { Authorization: `Bearer ${storedToken}` } : {},
    })
      .then(async (r) => {
        if (r.ok) {
          const data = await r.json();
          if (data.authenticated && data.session_token && data.user) {
            applyAuthenticatedUser(data.session_token, data.user);
            if (urlTok) {
              showNotice(`Otorisasi Discord OAuth2 berhasil: ${data.user.name} (${data.user.roleLabel}).`);
            }
          }
        }
      })
      .catch(() => {
        // Ignore transient offline error
      });
  }, [applyAuthenticatedUser, showNotice]);

  // Listen for official Discord OAuth2 completion via postMessage, BroadcastChannel, storage, and polling
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'OAUTH_AUTH_SUCCESS' && event.data.session_token && event.data.user) {
        applyAuthenticatedUser(event.data.session_token, event.data.user);
        showNotice(`Otorisasi Discord OAuth2 berhasil: ${event.data.user.name} (1 Sesi Aktif).`);
      }
    };
    window.addEventListener('message', handleMessage);

    let bc: BroadcastChannel | null = null;
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        bc = new BroadcastChannel('athenaa_oauth');
        bc.onmessage = (ev) => {
          if (ev.data?.type === 'OAUTH_AUTH_SUCCESS' && ev.data.session_token && ev.data.user) {
            applyAuthenticatedUser(ev.data.session_token, ev.data.user);
            showNotice(`Otorisasi Discord OAuth2 berhasil: ${ev.data.user.name} (1 Sesi Aktif).`);
          }
        };
      }
    } catch {
      // BroadcastChannel not supported
    }

    const handleStorage = (ev: StorageEvent) => {
      if (ev.key === 'athenaa_session_token' && ev.newValue) {
        const tok = ev.newValue;
        fetch(`/api/auth/session?session_token=${encodeURIComponent(tok)}`, {
          credentials: 'include',
          headers: { Authorization: `Bearer ${tok}` },
        })
          .then(async (r) => {
            if (r.ok) {
              const data = await r.json();
              if (data.authenticated && data.session_token && data.user) {
                applyAuthenticatedUser(data.session_token, data.user);
                showNotice(`Otorisasi Discord OAuth2 berhasil: ${data.user.name} (1 Sesi Aktif).`);
              }
            }
          })
          .catch(() => {});
      }
    };
    window.addEventListener('storage', handleStorage);

    return () => {
      window.removeEventListener('message', handleMessage);
      window.removeEventListener('storage', handleStorage);
      if (bc) bc.close();
    };
  }, [applyAuthenticatedUser, showNotice]);

  // While Login Modal is open, poll session/cookie/localStorage every 1.5s so popup completion never gets stuck
  useEffect(() => {
    if (!showLoginModal) return;
    const timer = window.setInterval(async () => {
      const tok = window.localStorage.getItem('athenaa_session_token') || '';
      const checkUrl = tok
        ? `/api/auth/session?session_token=${encodeURIComponent(tok)}`
        : '/api/auth/session';
      try {
        const resp = await fetch(checkUrl, {
          credentials: 'include',
          headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.authenticated && data.session_token && data.user) {
            applyAuthenticatedUser(data.session_token, data.user);
            showNotice(`Otorisasi Discord OAuth2 berhasil: ${data.user.name} (1 Sesi Aktif).`);
          }
        }
      } catch {
        // Ignore network poll error
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [showLoginModal, applyAuthenticatedUser, showNotice]);

  const handleDiscordOAuthAuthorize = async (usePopup: boolean) => {
    try {
      const resp = await fetch('/api/auth/discord/url');
      const data = await resp.json();
      if (!resp.ok || !data.url) {
        showNotice(
          data.error || 'DISCORD_CLIENT_ID belum dikonfigurasi pada environment server.',
          true
        );
        return;
      }
      if (usePopup) {
        const popup = window.open(data.url, 'discord_oauth_popup', 'width=560,height=720');
        if (!popup) {
          window.location.href = data.url;
        }
      } else {
        window.location.href = data.url;
      }
    } catch {
      showNotice('Gagal menghubungi server OAuth2 Discord.', true);
    }
  };

  const handleDiscordLogout = async () => {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {},
    }).catch(() => {});
    setShowLoginModal(true);
  };

  const fetchGuilds = useCallback(async () => {
    try {
      const resp = await fetch('/api/guilds');
      if (resp.ok) {
        const data = await resp.json();
        const list: GuildSettings[] = Array.isArray(data.guilds) ? data.guilds : [];
        setGuilds(list);
        if (list.length > 0) {
          setSelectedGuildId((prev) =>
            list.some((g) => g.guild_id === prev) ? prev : list[0].guild_id
          );
        }
      }
    } catch {
      // Ignore transient network failure
    }
  }, []);

  const fetchMusicState = useCallback(async (guildId: string) => {
    const resp = await fetch(`/api/guilds/${guildId}/music/state`);
    if (resp.ok) {
      const data = await resp.json();
      setMusicState(data);
    }
  }, []);

  const fetchTasks = useCallback(async (guildId: string) => {
    const resp = await fetch(`/api/guilds/${guildId}/tasks`);
    if (resp.ok) {
      const data = await resp.json();
      setTasks(data.tasks || []);
      setReminders(data.reminders || []);
      setAttachments(data.attachments || []);
      if (data.moodle_env) {
        setMoodleEnv(data.moodle_env);
      }
    }
  }, []);

  const fetchRpg = useCallback(async (guildId: string) => {
    const resp = await fetch(`/api/guilds/${guildId}/rpg`);
    if (resp.ok) {
      const data = await resp.json();
      setLeaderboard(data.leaderboard || []);
      setAfkList(data.afk_list || []);
    }
  }, []);

  useEffect(() => {
    fetchGuilds();
    const guildTimer = window.setInterval(() => {
      fetchGuilds();
    }, 10000);
    return () => window.clearInterval(guildTimer);
  }, [fetchGuilds]);

  useEffect(() => {
    fetchMusicState(selectedGuildId);
    fetchTasks(selectedGuildId);
    fetchRpg(selectedGuildId);
  }, [selectedGuildId, fetchMusicState, fetchTasks, fetchRpg]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let unmounted = false;

    const connectWs = () => {
      if (unmounted) return;
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${window.location.host}/ws`);

      ws.onopen = () => {
        if (!unmounted) setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (Array.isArray(msg.guilds) && msg.guilds.length > 0) {
            setGuilds(msg.guilds);
          }
          if (msg.type === 'POSITION_TICK' && msg.guild_id === selectedGuildId) {
            setMusicState((prev) => {
              if (prev.position_sec === msg.position_sec) return prev;
              return { ...prev, position_sec: msg.position_sec };
            });
          }
          if (msg.type === 'MUSIC_STATE_UPDATE' && msg.guild_id === selectedGuildId) {
            setMusicState((prev) => ({
              ...prev,
              ...msg.state,
              radios: prev.radios,
            }));
          }
        } catch {
          // Ignore malformed WS message
        }
      };

      ws.onclose = () => {
        if (!unmounted) {
          setWsConnected(false);
          reconnectTimer = window.setTimeout(connectWs, 2500);
        }
      };
    };

    connectWs();

    // Fallback state sync poll only when /ws is not actively open (e.g., if a reverse proxy blocks WebSocket)
    const syncPollTimer = window.setInterval(() => {
      if (!unmounted && (!ws || ws.readyState !== WebSocket.OPEN)) {
        fetchMusicState(selectedGuildId).catch(() => {});
      }
    }, 3000);

    return () => {
      unmounted = true;
      window.clearInterval(syncPollTimer);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, [selectedGuildId, fetchMusicState]);

  useEffect(() => {
    audioEngine.setVolume(musicState.volume);
    audioEngine.syncPlayback(
      musicState.is_playing && !musicState.is_paused,
      musicState.current_track?.stream_url || '',
      musicState.current_track?.title || '',
      musicState.current_track?.artist || '',
      musicState.current_track?.source_url || ''
    );
  }, [
    musicState.is_playing,
    musicState.is_paused,
    musicState.volume,
    musicState.current_track?.item_id,
    musicState.current_track?.stream_url,
    musicState.current_track?.title,
    musicState.current_track?.artist,
    musicState.current_track?.source_url,
    browserAudioMuted,
  ]);

  const handlePlayOrQueueTrack = useCallback(async (track: TrackItem, playNow: boolean) => {
    const isPlaylist =
      track.source_type === 'spotify_playlist' ||
      track.source_type === 'spotify_album' ||
      track.source_type === 'youtube_playlist' ||
      track.title.startsWith('🎶 [PLAYLIST]');

    if (playNow && !isPlaylist) {
      audioEngine.forceStop();
      setMusicState((prev) => ({
        ...prev,
        current_track: {
          ...track,
          item_id: track.item_id || `trk-opt-${Date.now()}`,
          requester_id: activeActor.id,
          requester_name: activeActor.name,
        },
        position_sec: 0,
        is_playing: true,
        is_paused: false,
      }));
    }
    const actorRole = activeActor.role || (activeActor.isAdmin ? 'admin' : activeActor.hasDjRole ? 'dj' : 'member');
    const resp = await fetch(`/api/guilds/${selectedGuildId}/music/play`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Role': actorRole,
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      },
      body: JSON.stringify({
        title: track.title,
        artist: track.artist,
        album: track.album,
        duration_sec: track.duration_sec,
        source_type: track.source_type,
        source_url: track.source_url,
        stream_url: track.stream_url,
        thumbnail_url: track.thumbnail_url,
        play_now: playNow,
        requester_id: activeActor.id,
        requester_name: activeActor.name,
        user_roles: activeActor.roles,
        is_admin: activeActor.isAdmin,
        is_owner: activeActor.isAdmin,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      await fetchMusicState(selectedGuildId);
      showNotice(data.error || 'Aksi ditolak oleh Host Lock System.', true);
      return;
    }
    if (data.state) {
      setMusicState((prev) => ({
        ...prev,
        ...data.state,
        radios: prev.radios,
      }));
    } else {
      fetchMusicState(selectedGuildId);
    }
    if (data.playlist_tracks_added) {
      showNotice(
        `Playlist (${data.playlist_tracks_added} lagu) langsung diputar & ditambahkan ke antrean!`
      );
    } else {
      showNotice(
        data.started_immediately
          ? `Sedang memutar: ${track.title} — ${track.artist}`
          : `Ditambahkan ke antrean (#${data.item?.position ?? ''}): ${track.title} — ${track.artist}`
      );
    }
  }, [activeActor, selectedGuildId, sessionToken, fetchMusicState, showNotice]);

  const handlePlayerControl = useCallback(async (action: string, value?: unknown, itemId?: string) => {
    // Immediate optimistic update (0ms UI latency) + immediate browser audio cut on stop/skip/pause
    if (action === 'stop' || action === 'skip' || action === 'pause') {
      audioEngine.forceStop();
    }
    setMusicState((prev) => {
      switch (action) {
        case 'pause':
          return prev.current_track ? { ...prev, is_paused: true, is_playing: false } : prev;
        case 'resume':
          return prev.current_track ? { ...prev, is_paused: false, is_playing: true } : prev;
        case 'stop':
          return {
            ...prev,
            current_track: null,
            queue: [],
            is_playing: false,
            is_paused: false,
            position_sec: 0,
            active_radio_name: '',
          };
        case 'skip': {
          const nextTrack = prev.queue[0] || null;
          if (!nextTrack && prev.autoplay) {
            return {
              ...prev,
              position_sec: 0,
              is_playing: true,
              is_paused: false,
            };
          }
          const remainingQueue = prev.queue.slice(1).map((it, idx) => ({ ...it, position: idx + 1 }));
          return {
            ...prev,
            current_track: nextTrack,
            queue: remainingQueue,
            position_sec: 0,
            is_playing: Boolean(nextTrack),
            is_paused: false,
          };
        }
        case 'clear':
          return { ...prev, queue: [] };
        case 'play_item': {
          const target = prev.queue.find((it) => it.item_id === itemId);
          if (!target) return prev;
          return {
            ...prev,
            current_track: target,
            queue: prev.queue
              .filter((it) => it.item_id !== itemId)
              .map((it, idx) => ({ ...it, position: idx + 1 })),
            position_sec: 0,
            is_playing: true,
            is_paused: false,
          };
        }
        case 'remove_item':
          return {
            ...prev,
            queue: prev.queue
              .filter((it) => it.item_id !== itemId)
              .map((it, idx) => ({ ...it, position: idx + 1 })),
          };
        case 'move_to_top': {
          const target = prev.queue.find((it) => it.item_id === itemId);
          if (!target) return prev;
          return {
            ...prev,
            queue: [target, ...prev.queue.filter((it) => it.item_id !== itemId)].map((it, idx) => ({
              ...it,
              position: idx + 1,
            })),
          };
        }
        case 'seek':
          return { ...prev, position_sec: Math.max(0, Number(value) || 0) };
        case 'volume':
          return { ...prev, volume: Math.max(1, Math.min(100, Math.round(Number(value) || 80))) };
        case 'loop':
          return value === 'off' || value === 'one' || value === 'queue'
            ? { ...prev, loop_mode: value }
            : prev;
        case 'autoplay':
          return {
            ...prev,
            autoplay: Boolean(value),
            is_playing: Boolean(value) && !prev.current_track ? true : prev.is_playing,
            is_paused: Boolean(value) && !prev.current_track ? false : prev.is_paused,
          };
        case 'mode_247':
          return { ...prev, mode_247: Boolean(value) };
        default:
          return prev;
      }
    });

    const actorRole = activeActor.role || (activeActor.isAdmin ? 'admin' : activeActor.hasDjRole ? 'dj' : 'member');
    const resp = await fetch(`/api/guilds/${selectedGuildId}/music/control`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Role': actorRole,
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      },
      body: JSON.stringify({
        action,
        value,
        item_id: itemId,
        actor_id: activeActor.id,
        actor_name: activeActor.name,
        user_roles: activeActor.roles,
        is_admin: activeActor.isAdmin,
        is_owner: activeActor.isAdmin,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      await fetchMusicState(selectedGuildId);
      showNotice(data.error || 'Aksi ditolak oleh Host Lock System.', true);
      return;
    }
    if (data.state) {
      setMusicState((prev) => ({
        ...prev,
        ...data.state,
        radios: prev.radios,
      }));
    }
    if (action === 'autoplay') {
      showNotice(
        Boolean(value)
          ? 'Autoplay Diaktifkan: rekomendasi lagu otomatis berjalan saat antrean habis.'
          : 'Autoplay Dinonaktifkan.'
      );
    } else if (action === 'mode_247') {
      showNotice(
        Boolean(value)
          ? 'Mode 24/7 Diaktifkan: bot tetap standby di voice channel.'
          : 'Mode 24/7 Dinonaktifkan.'
      );
    }
  }, [activeActor, selectedGuildId, sessionToken, fetchMusicState, showNotice]);

  const currentGuildSettings = guilds.find((g) => g.guild_id === selectedGuildId) || null;
  const pendingTasks = tasks.filter((t) => !t.is_completed);

  const navItems: Array<{
    id: NavTab;
    label: string;
    subtitle: string;
    group: 'music' | 'academy' | 'system';
    icon: React.ReactNode;
    adminOnly?: boolean;
  }> = [
    {
      id: 'overview',
      label: 'Ringkasan Server',
      subtitle: 'Beranda · Voice & Tugas',
      group: 'music',
      icon: <Home className="w-5 h-5" />,
    },
    {
      id: 'player',
      label: 'Pemutar & Lirik',
      subtitle: 'LRCLIB Sync · Radio Stream',
      group: 'music',
      icon: <Disc3 className="w-5 h-5" />,
    },
    {
      id: 'queue',
      label: 'Antrean & Host Lock',
      subtitle: `${musicState.queue.length} lagu dalam antrean`,
      group: 'music',
      icon: <ListOrdered className="w-5 h-5" />,
    },
    {
      id: 'academy',
      label: 'Tugas Akademik',
      subtitle: `${pendingTasks.length} tugas aktif · Waskita`,
      group: 'academy',
      icon: <GraduationCap className="w-5 h-5" />,
    },
    {
      id: 'modules',
      label: 'Modul & Lampiran',
      subtitle: `${attachments.length} file tervalidasi (.pdf)`,
      group: 'academy',
      icon: <FileArchive className="w-5 h-5" />,
    },
    {
      id: 'rpg',
      label: 'Leaderboard',
      subtitle: 'Top 15 EXP · Chat & Voice',
      group: 'system',
      icon: <Trophy className="w-5 h-5" />,
    },
    {
      id: 'afk',
      label: 'Status AFK',
      subtitle: `${afkList.length} anggota sedang AFK`,
      group: 'system',
      icon: <Clock className="w-5 h-5" />,
    },
    {
      id: 'settings',
      label: 'Pengaturan Server',
      subtitle: 'Channel · Role DJ · Zona Waktu',
      group: 'system',
      icon: <Settings className="w-5 h-5" />,
    },
    {
      id: 'admin',
      label: 'Admin Server Hub',
      subtitle: 'Metrik · Cadangan Data · Tests',
      group: 'system',
      icon: <Shield className="w-5 h-5" />,
      adminOnly: true,
    },
    {
      id: 'codebase',
      label: 'Kode Bot Python',
      subtitle: 'Source /athenaa & Paket .zip',
      group: 'system',
      icon: <Code2 className="w-5 h-5" />,
      adminOnly: true,
    },
  ];

  const isServerAdmin = Boolean(activeActor.isAdmin);
  const currentRole = activeActor.role || (activeActor.isAdmin ? 'admin' : activeActor.hasDjRole ? 'dj' : 'member');

  const visibleNavItems = navItems.filter((item) => {
    if (item.adminOnly && !isServerAdmin) return false;
    if (sidebarFilter !== 'all' && item.group !== sidebarFilter) return false;
    return true;
  });

  const currentTrack = musicState.current_track;
  const nextUpTrack = musicState.queue[0] || null;

  return (
    <div className="h-screen w-screen flex flex-col bg-[#000000] text-white overflow-hidden select-none">
      {/* Authentic Spotify Top Bar (Responsive Mobile + 3-Zone Desktop) */}
      <header className="px-3 md:px-4 py-2 md:py-0 md:h-16 flex flex-col gap-2 md:grid md:grid-cols-12 items-center md:gap-4 shrink-0 z-40 border-b border-white/5 md:border-b-0">
        {/* Top Row on Mobile / Left + Right Zones on Desktop */}
        <div className="w-full md:w-auto md:col-span-4 flex items-center justify-between md:justify-start gap-1.5 sm:gap-2.5 min-w-0">
          <div className="flex items-center gap-1.5 sm:gap-2.5 min-w-0 flex-1">
            <button
              type="button"
              aria-label="Buka menu navigasi mobile"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              className="md:hidden w-8 h-8 rounded-full bg-[#1F1F1F] hover:bg-[#2A2A2A] text-white flex items-center justify-center shrink-0"
            >
              {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>

            <img
              src="/logo.png"
              alt="Athenaa Logo"
              className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shrink-0 shadow border border-white/15"
            />
            <span className="hidden sm:inline text-sm md:text-base font-bold tracking-tight text-white font-display whitespace-nowrap shrink-0">
              Athenaa
            </span>

            <select
              aria-label="Pilih Server Discord"
              value={selectedGuildId}
              onFocus={() => fetchGuilds()}
              onMouseDown={() => fetchGuilds()}
              onChange={(e) => setSelectedGuildId(e.target.value)}
              className="bg-[#1F1F1F] hover:bg-[#2A2A2A] border border-white/10 rounded-full px-2.5 md:px-3 py-1 md:py-1.5 text-xs font-medium text-white truncate max-w-[140px] sm:max-w-[210px] focus:outline-none transition-colors"
            >
              {guilds.map((g) => (
                <option key={g.guild_id} value={g.guild_id}>
                  {g.guild_name}
                </option>
              ))}
            </select>

            <span className="hidden lg:inline text-[11px] font-mono text-[#DC95FF] whitespace-nowrap shrink-0">
              {wsConnected ? 'WS Live' : 'Syncing'}
            </span>
          </div>

          {/* Mobile Account & Role Pill (shown on right of top row on < md) */}
          <div className="flex md:hidden items-center gap-1.5 pl-1.5 pr-1.5 py-1 rounded-full bg-[#1F1F1F] border border-white/10 shrink-0">
            <select
              aria-label="Pilih Peran Server"
              value={currentRole}
              onChange={(e) => handleSwitchRole(e.target.value as 'admin' | 'dj' | 'member')}
              className="bg-[#282828] text-[#DC95FF] font-bold text-[10px] rounded-full px-2 py-0.5 focus:outline-none"
            >
              <option value="admin">Admin</option>
              <option value="dj">DJ</option>
              <option value="member">Member</option>
            </select>
            <span className="text-[11px] font-bold text-white truncate max-w-[68px]">
              {activeActor.name}
            </span>
          </div>
        </div>

        {/* Center Zone (Full width row on mobile, 4 cols on desktop): Home Button + Search Bar */}
        <div className="w-full md:w-auto md:col-span-4 flex items-center justify-center gap-2 min-w-0">
          <button
            type="button"
            aria-label="Kembali ke Ringkasan Server"
            onClick={() => setActiveTab('overview')}
            className={`hidden sm:flex w-10 h-10 md:w-11 md:h-11 rounded-full items-center justify-center shrink-0 transition-transform active:scale-95 ${
              activeTab === 'overview'
                ? 'bg-[#282828] text-white'
                : 'bg-[#1F1F1F] text-[#B3B3B3] hover:text-white hover:bg-[#2A2A2A]'
            }`}
            title="Ringkasan Server (Home)"
          >
            <Home className="w-5 h-5" />
          </button>

          <SearchDropdownBar
            onPlayNow={(track) => handlePlayOrQueueTrack(track, true)}
            onAddToQueue={(track) => handlePlayOrQueueTrack(track, false)}
          />
        </div>

        {/* Right Zone (Desktop 4 cols): Admin-Only Code/ZIP Actions + Role Switcher & Discord Account Pill */}
        <div className="hidden md:flex md:col-span-4 items-center justify-end gap-2 min-w-0">
          {isServerAdmin && (
            <>
              <button
                type="button"
                onClick={() => setActiveTab('codebase')}
                className="px-3 py-1.5 rounded-full bg-[#1F1F1F] hover:bg-[#2A2A2A] border border-white/10 text-xs font-bold text-white whitespace-nowrap flex items-center gap-1.5 transition-colors shrink-0"
                title="Khusus Admin Server: Inspeksi Kode Sumber Python"
              >
                <Code2 className="w-3.5 h-3.5 text-[#DC95FF]" />
                Kode Python
              </button>

              <a
                href={`/api/python-codebase/download-zip?session_token=${encodeURIComponent(sessionToken)}`}
                download="athenaa-discord-bot.zip"
                className="px-3.5 py-1.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs whitespace-nowrap flex items-center gap-1.5 transition-transform active:scale-95 shrink-0"
                title="Khusus Admin Server: Unduh Paket Bot Python (.zip) Siap Pterodactyl"
              >
                <Download className="w-3.5 h-3.5" />
                Unduh Bot (.zip)
              </a>
            </>
          )}

          {/* Per-Server Role Switcher + Discord Account Pill */}
          <div className="flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-full bg-[#1F1F1F] border border-white/10 min-w-0">
            <select
              aria-label="Pilih Peran Server (Admin / DJ / Member)"
              value={currentRole}
              onChange={(e) => handleSwitchRole(e.target.value as 'admin' | 'dj' | 'member')}
              className="bg-[#282828] hover:bg-[#333333] text-[#DC95FF] font-bold text-[11px] rounded-full px-2.5 py-1 border border-white/10 focus:outline-none cursor-pointer transition-colors shrink-0"
              title="Ganti Peran Per-Server: Admin Server, Role DJ, atau Member"
            >
              <option value="admin">Admin Server</option>
              <option value="dj">Role DJ</option>
              <option value="member">Member</option>
            </select>
            <div className="min-w-0 hidden xl:block px-1">
              <div className="text-xs font-bold text-white truncate max-w-[100px] leading-tight">
                {activeActor.name}
              </div>
              <div className="text-[10px] text-[#B3B3B3] truncate leading-tight">
                {activeActor.roleLabel}
              </div>
            </div>
            <button
              type="button"
              aria-label="Opsi Akun & Login Discord"
              onClick={handleDiscordLogout}
              className="p-1.5 rounded-full hover:bg-white/10 text-[#B3B3B3] hover:text-white transition-colors shrink-0"
              title="Otorisasi Akun Discord / Ganti Peran"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Mobile Horizontal Quick-Navigation Strip (< md) */}
        <div className="w-full flex md:hidden items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
          {navItems
            .filter((item) => !item.adminOnly || isServerAdmin)
            .map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setActiveTab(item.id);
                    setMobileMenuOpen(false);
                  }}
                  className={`px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap shrink-0 transition-colors ${
                    isActive
                      ? 'bg-[#DC95FF] text-black font-bold'
                      : 'bg-[#1F1F1F] text-[#B3B3B3] hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
        </div>
      </header>

      {/* Mobile Slide-Over Sidebar Drawer (< md) */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-xs"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside className="relative w-[280px] max-w-[82vw] bg-[#121212] h-full flex flex-col z-10 border-r border-white/10 shadow-2xl">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <img
                  src="/logo.png"
                  alt="Athenaa Logo"
                  className="w-7 h-7 rounded-full object-cover shrink-0 border border-white/15"
                />
                <span className="text-sm font-bold text-white">Menu Athenaa</span>
              </div>
              <button
                type="button"
                aria-label="Tutup menu mobile"
                onClick={() => setMobileMenuOpen(false)}
                className="p-1.5 rounded-full bg-[#232323] text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {navItems
                .filter((item) => !item.adminOnly || isServerAdmin)
                .map((item) => {
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        setActiveTab(item.id);
                        setMobileMenuOpen(false);
                      }}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left ${
                        isActive ? 'bg-[#232323] text-[#DC95FF]' : 'text-white hover:bg-white/5'
                      }`}
                    >
                      <div className="shrink-0">{item.icon}</div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold truncate">{item.label}</div>
                        <div className="text-[11px] text-[#B3B3B3] truncate">{item.subtitle}</div>
                      </div>
                    </button>
                  );
                })}
            </div>

            {isServerAdmin && (
              <div className="p-3 border-t border-white/10 space-y-2">
                <a
                  href={`/api/python-codebase/download-zip?session_token=${encodeURIComponent(sessionToken)}`}
                  download="athenaa-discord-bot.zip"
                  className="w-full py-2 px-3 rounded-full bg-[#DC95FF] text-black font-bold text-xs flex items-center justify-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  Unduh Paket Bot (.zip)
                </a>
              </div>
            )}
          </aside>
        </div>
      )}

      {/* Spotify 3-Island Workspace (Left Library + Center Stage + Right Now Playing View) */}
      <div className="flex-1 flex gap-2 px-2 min-h-0 overflow-hidden">
        {/* Left Island: Spotify "Your Library" Navigation (Hidden on < md, visible on md+) */}
        <aside className="hidden md:flex w-[260px] lg:w-[280px] bg-[#121212] rounded-lg flex-col overflow-hidden shrink-0">
          <div className="px-3.5 pt-3.5 pb-2.5 space-y-2.5 border-b border-white/5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[#B3B3B3] hover:text-white transition-colors">
                <Library className="w-5 h-5" />
                <span className="text-sm font-bold tracking-tight">Koleksi & Modul Bot</span>
              </div>
              <span className="text-[11px] font-mono text-[#B3B3B3]">v1.2</span>
            </div>

            {/* Spotify Library Filter Pills */}
            <div className="grid grid-cols-4 gap-1">
              {(
                [
                  ['all', 'Semua'],
                  ['music', 'Musik'],
                  ['academy', 'Akademik'],
                  ['system', 'Sistem'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSidebarFilter(key)}
                  className={`py-1 rounded-full text-[11px] font-semibold transition-colors text-center truncate ${
                    sidebarFilter === key
                      ? 'bg-white text-black'
                      : 'bg-[#232323] text-white hover:bg-[#2A2A2A]'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <nav
            aria-label="Menu Utama Dashboard"
            className="flex-1 overflow-y-auto px-2 py-1.5 space-y-0.5"
          >
            {visibleNavItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-left transition-colors group ${
                    isActive
                      ? 'bg-[#232323] text-white'
                      : 'text-[#B3B3B3] hover:bg-[#1A1A1A] hover:text-white'
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 transition-colors ${
                      isActive
                        ? 'bg-[#DC95FF]/15 text-[#DC95FF]'
                        : 'bg-[#1F1F1F] text-[#B3B3B3] group-hover:text-white'
                    }`}
                  >
                    {item.icon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div
                      className={`text-[13px] font-semibold truncate leading-tight ${
                        isActive ? 'text-[#DC95FF]' : 'text-white'
                      }`}
                    >
                      {item.label}
                    </div>
                    <div className="text-[11px] text-[#B3B3B3] truncate leading-tight mt-0.5">
                      {item.subtitle}
                    </div>
                  </div>
                </button>
              );
            })}
          </nav>

          {/* Compact Discord User Card at bottom of Left Island */}
          <div className="p-3 border-t border-white/5 bg-[#181818]/60 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-white truncate">{activeActor.name}</div>
              <div className="text-[11px] text-[#B3B3B3] truncate">{activeActor.roleLabel}</div>
            </div>
            <span className="w-2 h-2 rounded-full bg-[#DC95FF] shrink-0" />
          </div>
        </aside>

        {/* Center Island: Main Spotify Stage */}
        <main className="flex-1 bg-[#121212] rounded-lg overflow-y-auto min-w-0 relative">
          {/* Subtle Spotify Top Ambient Gradient */}
          <div className="bg-gradient-to-b from-[#2b1644]/65 via-[#121212]/90 to-[#121212] px-3.5 sm:px-6 pt-4 sm:pt-5 pb-6 space-y-6">
            {/* Notification Toast Banner */}
            {bannerNotice && (
              <div
                role="status"
                className={`px-4 py-2.5 rounded-lg text-xs font-semibold flex items-center justify-between ${
                  bannerNotice.isError
                    ? 'bg-rose-950/90 text-rose-200 border border-rose-800'
                    : 'bg-[#DC95FF] text-black'
                }`}
              >
                <span>{bannerNotice.text}</span>
                <button
                  type="button"
                  onClick={() => setBannerNotice(null)}
                  className="text-xs font-bold underline ml-4 shrink-0"
                >
                  Tutup
                </button>
              </div>
            )}

            {activeTab === 'overview' && (
              <div className="space-y-7">
                {/* Spotify Top Greeting + 2x3 Quick-Access Shortcuts Grid */}
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-4">
                    <h1 className="text-lg sm:text-xl xl:text-2xl font-bold text-white tracking-tight truncate">
                      Selamat Datang di {currentGuildSettings?.guild_name || 'Athenaa Server'}
                    </h1>
                    <span className="text-xs text-[#B3B3B3] whitespace-nowrap shrink-0">
                      Voice: <strong className="text-white">{musicState.voice_channel_name}</strong>
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3">
                    {/* Card 1: Active Music */}
                    <div
                      onClick={() => setActiveTab('player')}
                      className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-14 h-14 bg-[#DC95FF]/20 flex items-center justify-center shrink-0">
                          {currentTrack?.thumbnail_url ? (
                            <img
                              src={currentTrack.thumbnail_url}
                              alt={currentTrack.title}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <Disc3 className="w-6 h-6 text-[#DC95FF]" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate">
                            {currentTrack ? `${currentTrack.title} — ${currentTrack.artist}` : 'Pemutar Musik'}
                          </div>
                          <div className="text-[11px] text-[#B3B3B3] truncate">
                            Sedang Diputar · Lirik LRCLIB
                          </div>
                        </div>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-[#DC95FF] text-black flex items-center justify-center shadow-lg opacity-90 group-hover:scale-105 transition-transform shrink-0">
                        <Play className="w-4 h-4 fill-current ml-0.5" />
                      </div>
                    </div>

                    {/* Card 2: Queue & Audio Info */}
                    <div
                      onClick={() => setActiveTab('queue')}
                      className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-14 h-14 bg-purple-900/50 flex items-center justify-center shrink-0">
                          <ListMusic className="w-6 h-6 text-[#DC95FF]" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate">
                            Antrean Musik ({musicState.queue.length} Lagu)
                          </div>
                          <div className="text-[11px] text-[#B3B3B3] truncate">
                            {musicState.voice_channel_name || 'Voice Siap'} · Loop {musicState.loop_mode.toUpperCase()}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Card 3: Academic Tasks */}
                    <div
                      onClick={() => setActiveTab('academy')}
                      className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-14 h-14 bg-amber-900/40 flex items-center justify-center shrink-0">
                          <GraduationCap className="w-6 h-6 text-amber-400" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate">
                            {pendingTasks.length} Tugas Akademik Aktif
                          </div>
                          <div className="text-[11px] text-[#B3B3B3] truncate">
                            Sinkronisasi Kalender Waskita
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Card 4: Leaderboard (No RPG word) */}
                    <div
                      onClick={() => setActiveTab('rpg')}
                      className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-14 h-14 bg-purple-900/40 flex items-center justify-center shrink-0">
                          <Trophy className="w-6 h-6 text-purple-300" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate">
                            {leaderboard[0]
                              ? `#1 ${leaderboard[0].display_name} (Lv. ${leaderboard[0].level})`
                              : 'Leaderboard Server'}
                          </div>
                          <div className="text-[11px] text-[#B3B3B3] truncate">
                            Top 15 Server · Chat & Voice EXP
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Card 5: Radio Internet */}
                    <div
                      onClick={() => setActiveTab('player')}
                      className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-14 h-14 bg-sky-900/40 flex items-center justify-center shrink-0">
                          <Radio className="w-6 h-6 text-sky-300" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate">
                            Radio Prambors, Hard Rock & Lofi
                          </div>
                          <div className="text-[11px] text-[#B3B3B3] truncate">
                            Mode 24/7: {musicState.mode_247 ? 'Aktif' : 'Nonaktif'} · Autoplay: {musicState.autoplay ? 'ON' : 'OFF'}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Card 6: Admin Server & Python Bot OR Member Modules Card */}
                    {isServerAdmin ? (
                      <div
                        onClick={() => setActiveTab('codebase')}
                        className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-14 h-14 bg-fuchsia-900/40 flex items-center justify-center shrink-0">
                            <Code2 className="w-6 h-6 text-[#DC95FF]" />
                          </div>
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-white truncate">
                              Admin Server & Kode Python
                            </div>
                            <div className="text-[11px] text-[#B3B3B3] truncate">
                              Khusus Admin Server · Paket Deploy .zip
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div
                        onClick={() => setActiveTab('modules')}
                        className="h-14 bg-white/5 hover:bg-white/15 rounded-md overflow-hidden flex items-center justify-between pr-3 cursor-pointer transition-colors group"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-14 h-14 bg-purple-900/40 flex items-center justify-center shrink-0">
                            <FileArchive className="w-6 h-6 text-[#DC95FF]" />
                          </div>
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-white truncate">
                              Modul & Lampiran PDF ({attachments.length})
                            </div>
                            <div className="text-[11px] text-[#B3B3B3] truncate">
                              Unduh Materi & Modul Kuliah Tervalidasi
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Section 1: Authentic Spotify Tracklist Table (Active Track + Queue) */}
                <section className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                        01. Antrean & Lagu Aktif di Discord Voice
                      </h2>
                      <p className="text-xs text-[#B3B3B3]">
                        Klik lagu untuk memutar atau kelola urutan melalui Host Lock System.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setActiveTab('queue')}
                      className="text-xs font-bold text-[#B3B3B3] hover:text-white hover:underline shrink-0"
                    >
                      Semua Antrean
                    </button>
                  </div>

                  <div className="bg-[#181818]/90 border border-white/5 rounded-xl p-2">
                    {/* Precision Spotify Table Header (Responsive on Mobile) */}
                    <div className="grid grid-cols-[28px_minmax(0,1fr)_76px] sm:grid-cols-[32px_minmax(0,2.1fr)_minmax(0,1.2fr)_minmax(0,1.1fr)_96px] items-center gap-3 px-2.5 sm:px-3 py-2 border-b border-white/10 text-xs font-medium text-[#B3B3B3]">
                      <span>#</span>
                      <span>Judul & Penyanyi</span>
                      <span className="hidden sm:inline">Album / Sumber</span>
                      <span className="hidden sm:inline">Diminta Oleh</span>
                      <span className="flex justify-end">
                        <Clock3 className="w-3.5 h-3.5" />
                      </span>
                    </div>

                    <div className="divide-y divide-white/5 mt-1">
                      {currentTrack && (
                        <div
                          onClick={() => setActiveTab('player')}
                          className="grid grid-cols-[28px_minmax(0,1fr)_76px] sm:grid-cols-[32px_minmax(0,2.1fr)_minmax(0,1.2fr)_minmax(0,1.1fr)_96px] items-center gap-3 px-2.5 sm:px-3 py-2.5 rounded-lg bg-[#282828]/80 hover:bg-[#2A2A2A] cursor-pointer transition-colors"
                        >
                          <span className="text-xs font-bold text-[#DC95FF] font-mono">▶</span>
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded bg-[#181818] flex items-center justify-center shrink-0 overflow-hidden">
                              {currentTrack.thumbnail_url ? (
                                <img
                                  src={currentTrack.thumbnail_url}
                                  alt={currentTrack.title}
                                  className="w-full h-full object-cover"
                                />
                              ) : (
                                <Music className="w-4 h-4 text-[#DC95FF]" />
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="text-sm font-bold text-[#DC95FF] truncate">
                                {currentTrack.title}
                              </div>
                              <div className="text-xs text-white/80 truncate">
                                {currentTrack.artist} · Sedang Diputar
                              </div>
                            </div>
                          </div>
                          <span className="hidden sm:inline text-xs text-[#B3B3B3] truncate">
                            {currentTrack.album || 'Single'}
                          </span>
                          <span className="hidden sm:inline text-xs text-[#B3B3B3] truncate">
                            {currentTrack.requester_name}
                          </span>
                          <span className="font-mono tabular-nums text-xs text-[#DC95FF] text-right whitespace-nowrap">
                            {formatDuration(musicState.position_sec)} /{' '}
                            {formatDuration(currentTrack.duration_sec)}
                          </span>
                        </div>
                      )}

                      {musicState.queue.map((q, idx) => (
                        <div
                          key={q.item_id || idx}
                          onClick={() => handlePlayOrQueueTrack(q, true)}
                          className="grid grid-cols-[28px_minmax(0,1fr)_76px] sm:grid-cols-[32px_minmax(0,2.1fr)_minmax(0,1.2fr)_minmax(0,1.1fr)_96px] items-center gap-3 px-2.5 sm:px-3 py-2.5 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group"
                        >
                          <span className="font-mono tabular-nums text-xs text-[#B3B3B3] group-hover:text-white">
                            {idx + 1}
                          </span>
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded bg-[#282828] flex items-center justify-center shrink-0 overflow-hidden">
                              {q.thumbnail_url ? (
                                <img
                                  src={q.thumbnail_url}
                                  alt={q.title}
                                  className="w-full h-full object-cover"
                                />
                              ) : (
                                <Music className="w-4 h-4 text-[#DC95FF]" />
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-white truncate">
                                {q.title}
                              </div>
                              <div className="text-xs text-[#B3B3B3] truncate">{q.artist}</div>
                            </div>
                          </div>
                          <span className="hidden sm:inline text-xs text-[#B3B3B3] truncate">
                            {q.album || 'Single'}
                          </span>
                          <span className="hidden sm:inline text-xs text-[#B3B3B3] truncate">
                            {q.requester_name}
                          </span>
                          <div className="flex items-center justify-end gap-1.5">
                            <span className="font-mono tabular-nums text-xs text-[#B3B3B3] whitespace-nowrap mr-1">
                              {formatDuration(q.duration_sec)}
                            </span>
                            <button
                              type="button"
                              aria-label={`Putar ${q.title}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePlayerControl('play_item', undefined, q.item_id);
                              }}
                              className="px-2 py-1 rounded-full bg-gradient-to-r from-[#8C56D4] to-[#DC95FF] hover:from-[#DC95FF] hover:to-[#FFBEFB] text-black font-bold text-[11px] inline-flex items-center gap-1"
                              title="Play Sekarang"
                            >
                              <Play className="w-3 h-3 fill-current" />
                              Play
                            </button>
                            <button
                              type="button"
                              aria-label={`Hapus ${q.title} dari antrean`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePlayerControl('remove_item', undefined, q.item_id);
                              }}
                              className="px-2 py-1 rounded-full bg-[#282828] hover:bg-rose-900/70 text-[#B3B3B3] hover:text-rose-200 text-[11px] font-semibold"
                              title="Remove dari Antrean"
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>

                {/* Section 2: Pengingat Tugas Akademik (Spotify Episode List Style) */}
                <section className="space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                        02. Pengingat Tugas Akademik (Waskita)
                      </h2>
                      <p className="text-xs text-[#B3B3B3]">
                        Auto-sync tiap 1 jam (khusus tugas turn-in / ber-deadline) · Reminder Discord otomatis pukul 00:01 WIB.
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setActiveTab('modules')}
                        className="text-xs font-bold text-[#DC95FF] hover:underline"
                      >
                        Unduh Modul ({attachments.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTab('academy')}
                        className="px-3.5 py-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-xs font-bold text-white"
                      >
                        Kelola Tugas
                      </button>
                    </div>
                  </div>

                  <div className="bg-[#181818]/90 border border-white/5 rounded-xl divide-y divide-white/5 px-3 sm:px-4">
                    {tasks.slice(0, 4).map((t) => (
                      <div
                        key={t.task_id}
                        className="py-3.5 grid grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-3"
                      >
                        <button
                          type="button"
                          aria-label={
                            t.is_completed
                              ? `Buka kembali ${t.title}`
                              : `Tandai selesai ${t.title}`
                          }
                          onClick={async () => {
                            await fetch(`/api/tasks/${t.task_id}/toggle`, { method: 'POST' });
                            fetchTasks(selectedGuildId);
                          }}
                          className="text-[#B3B3B3] hover:text-[#DC95FF] transition-colors"
                        >
                          {t.is_completed ? (
                            <CheckCircle2 className="w-5 h-5 text-[#DC95FF]" />
                          ) : (
                            <Circle className="w-5 h-5" />
                          )}
                        </button>

                        <div className="min-w-0">
                          <div
                            className={`text-sm font-semibold truncate ${
                              t.is_completed ? 'line-through text-white/40' : 'text-white'
                            }`}
                          >
                            {t.title}
                          </div>
                          <div className="text-xs text-[#B3B3B3] truncate mt-0.5">
                            <span className="text-white/85 font-medium">{t.course_name}</span>
                            <span aria-hidden="true"> · </span>
                            <span>Sumber: {t.source_type === 'moodle_ics' ? 'Waskita' : t.source_type}</span>
                          </div>
                        </div>

                        <div className="text-right font-mono tabular-nums text-[11px] sm:text-xs text-[#B3B3B3] shrink-0">
                          {new Date(t.deadline_iso).toLocaleDateString('id-ID', {
                            day: '2-digit',
                            month: 'short',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {(activeTab === 'player' || activeTab === 'queue') && (
              <MusicAndLyricsView
                subTab={activeTab}
                guildId={selectedGuildId}
                sessionToken={sessionToken}
                musicState={musicState}
                activeActor={activeActor}
                onPlayTrack={handlePlayOrQueueTrack}
                onControl={handlePlayerControl}
                onRefreshMusicState={() => fetchMusicState(selectedGuildId)}
                onNotify={showNotice}
              />
            )}

            {(activeTab === 'academy' || activeTab === 'modules') && (
              <AcademyAndModulesView
                subTab={activeTab}
                guildId={selectedGuildId}
                tasks={tasks}
                attachments={attachments}
                reminders={reminders}
                moodleEnv={moodleEnv}
                onRefreshTasks={() => fetchTasks(selectedGuildId)}
                onNotify={showNotice}
              />
            )}

            {(activeTab === 'rpg' ||
              activeTab === 'afk' ||
              activeTab === 'settings' ||
              activeTab === 'admin' ||
              activeTab === 'codebase') && (
              <RpgAndSettingsView
                subTab={activeTab}
                guildId={selectedGuildId}
                sessionToken={sessionToken}
                isOwner={isServerAdmin}
                leaderboard={leaderboard}
                afkList={afkList}
                guildSettings={currentGuildSettings}
                onRefreshRpg={() => fetchRpg(selectedGuildId)}
                onRefreshSettings={fetchGuilds}
                onNotify={showNotice}
              />
            )}
          </div>
        </main>

        {/* Right Island: Authentic Spotify Desktop "Now Playing View" Sidebar */}
        <aside
          aria-label="Panel Sedang Diputar"
          className="hidden lg:flex w-[300px] xl:w-[320px] bg-[#121212] rounded-lg flex-col overflow-y-auto shrink-0 p-4 space-y-4"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-white truncate">
              {musicState.voice_channel_name}
            </span>
            <span className="text-[11px] font-mono text-[#DC95FF]">LIVE VOICE</span>
          </div>

          {/* Large Square Album Art Card */}
          <div className="aspect-square w-full rounded-lg bg-[#181818] overflow-hidden shadow-xl flex items-center justify-center">
            {currentTrack?.thumbnail_url ? (
              <img
                src={currentTrack.thumbnail_url}
                alt={currentTrack.title}
                referrerPolicy="no-referrer"
                className="w-full h-full object-cover"
              />
            ) : (
              <Music className="w-16 h-16 text-[#DC95FF]" />
            )}
          </div>

          {/* Track Title & Singer */}
          {currentTrack ? (
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-lg font-bold text-white leading-snug truncate">
                  {currentTrack.title}
                </h2>
                <p className="text-sm font-medium text-[#B3B3B3] truncate">
                  {currentTrack.artist}
                </p>
              </div>
            </div>
          ) : (
            <div className="text-xs text-[#B3B3B3]">Belum ada lagu yang sedang diputar.</div>
          )}

          {/* Audio & Queue Detail Card */}
          <div className="p-3.5 rounded-xl bg-[#1F1F1F] space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-white">Info Pemutaran & Audio</span>
              <button
                type="button"
                onClick={() => setActiveTab('queue')}
                className="text-[#DC95FF] font-semibold hover:underline"
              >
                Antrean ({musicState.queue.length})
              </button>
            </div>
            <div className="text-xs text-[#B3B3B3] space-y-1">
              <div>
                Diminta oleh: <strong className="text-white">{currentTrack?.requester_name || '—'}</strong>
              </div>
              <div>
                Sumber Audio:{' '}
                <strong className="text-white">
                  {currentTrack?.source_type === 'spotify_matched'
                    ? 'Spotify Matched'
                    : currentTrack?.source_type === 'radio'
                    ? 'Live Radio'
                    : 'YouTube Audio'}
                </strong>
              </div>
              <div>
                Mode: <strong className="text-white">Vol {musicState.volume}% · Loop {musicState.loop_mode.toUpperCase()}</strong>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-1.5 pt-1">
              <button
                type="button"
                aria-pressed={musicState.autoplay}
                onClick={() => handlePlayerControl('autoplay', !musicState.autoplay)}
                className={`py-1.5 px-2.5 rounded-full text-[11px] font-bold transition-colors border ${
                  musicState.autoplay
                    ? 'bg-[#DC95FF] text-black border-[#DC95FF]'
                    : 'bg-[#282828] text-[#B3B3B3] hover:text-white border-white/10'
                }`}
              >
                Autoplay {musicState.autoplay ? 'ON' : 'OFF'}
              </button>
              <button
                type="button"
                aria-pressed={musicState.mode_247}
                onClick={() => handlePlayerControl('mode_247', !musicState.mode_247)}
                className={`py-1.5 px-2.5 rounded-full text-[11px] font-bold transition-colors border ${
                  musicState.mode_247
                    ? 'bg-[#DC95FF] text-black border-[#DC95FF]'
                    : 'bg-[#282828] text-[#B3B3B3] hover:text-white border-white/10'
                }`}
              >
                24/7 {musicState.mode_247 ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

          {/* Live Lyrics Quick Card */}
          <div className="p-3.5 rounded-xl bg-gradient-to-br from-[#351a57] to-[#181818] space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-white flex items-center gap-1.5">
                <Mic2 className="w-3.5 h-3.5 text-[#DC95FF]" />
                Lirik Otomatis LRCLIB
              </span>
              <button
                type="button"
                onClick={() => setActiveTab('player')}
                className="px-2.5 py-1 rounded-full bg-black/40 hover:bg-black/60 text-[11px] font-bold text-white"
              >
                Buka Lirik
              </button>
            </div>
            <p className="text-xs text-white/80 leading-relaxed">
              Sinkronisasi lirik real-time sesuai detik lagu aktif tanpa memerlukan API key berbayar.
            </p>
          </div>

          {/* Next in Queue Card */}
          <div className="p-3.5 rounded-xl bg-[#1F1F1F] space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-white">Berikutnya di Antrean</span>
              <button
                type="button"
                onClick={() => setActiveTab('queue')}
                className="text-[#B3B3B3] hover:text-white font-semibold"
              >
                Buka Antrean
              </button>
            </div>
            {nextUpTrack ? (
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded bg-[#282828] flex items-center justify-center shrink-0 overflow-hidden">
                  {nextUpTrack.thumbnail_url ? (
                    <img
                      src={nextUpTrack.thumbnail_url}
                      alt={nextUpTrack.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <Music className="w-4 h-4 text-[#DC95FF]" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-bold text-white truncate">{nextUpTrack.title}</div>
                  <div className="text-[11px] text-[#B3B3B3] truncate">{nextUpTrack.artist}</div>
                </div>
                <span className="font-mono tabular-nums text-[11px] text-[#B3B3B3]">
                  {formatDuration(nextUpTrack.duration_sec)}
                </span>
              </div>
            ) : (
              <div className="text-xs text-[#B3B3B3]">
                Antrean kosong · Autoplay {musicState.autoplay ? 'Aktif' : 'Nonaktif'}
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Persistent Spotify Bottom Player Dock */}
      <SpotifyBottomPlayer
        musicState={musicState}
        browserAudioMuted={browserAudioMuted}
        onToggleBrowserAudio={() => {
          const nextMuted = !browserAudioMuted;
          setBrowserAudioMuted(nextMuted);
          audioEngine.setMuted(nextMuted);
          audioEngine.syncPlayback(
            musicState.is_playing && !musicState.is_paused,
            musicState.current_track?.stream_url || '',
            musicState.current_track?.title || 'Athenaa',
            musicState.current_track?.artist || '',
            musicState.current_track?.source_url || ''
          );
        }}
        onControl={handlePlayerControl}
      />

      {/* Per-Server Role Switcher & Discord OAuth2 Login Modal */}
      {showLoginModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Otorisasi Akun Discord & Pilih Peran Server"
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div className="w-full max-w-md bg-[#181818] border border-white/10 rounded-2xl p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <img
                  src="/logo.png"
                  alt="Athenaa Logo"
                  className="w-11 h-11 rounded-full object-cover shrink-0 shadow border border-white/15"
                />
                <div>
                  <h2 className="text-lg font-bold text-white tracking-tight">
                    Peran Server & Login Discord
                  </h2>
                  <p className="text-xs text-[#B3B3B3]">
                    Pilih peran server (Admin, DJ, Member) atau login via Discord OAuth2.
                  </p>
                </div>
              </div>
              <button
                type="button"
                aria-label="Tutup dialog login"
                onClick={() => setShowLoginModal(false)}
                className="p-1.5 rounded-full bg-[#282828] hover:bg-[#333333] text-[#B3B3B3] hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-[#232323] border border-white/10 space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-bold text-[#DC95FF]">
                <Shield className="w-3.5 h-3.5 shrink-0" />
                Pilih Peran Aktif di Server Ini (3-Tier Per-Server RBAC)
              </div>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => handleSwitchRole('admin')}
                  className={`py-2 px-2.5 rounded-xl text-xs font-bold border transition-colors ${
                    currentRole === 'admin'
                      ? 'bg-[#DC95FF] text-black border-[#DC95FF]'
                      : 'bg-[#181818] text-white border-white/10 hover:bg-[#2A2A2A]'
                  }`}
                >
                  Admin Server
                </button>
                <button
                  type="button"
                  onClick={() => handleSwitchRole('dj')}
                  className={`py-2 px-2.5 rounded-xl text-xs font-bold border transition-colors ${
                    currentRole === 'dj'
                      ? 'bg-[#DC95FF] text-black border-[#DC95FF]'
                      : 'bg-[#181818] text-white border-white/10 hover:bg-[#2A2A2A]'
                  }`}
                >
                  Role DJ
                </button>
                <button
                  type="button"
                  onClick={() => handleSwitchRole('member')}
                  className={`py-2 px-2.5 rounded-xl text-xs font-bold border transition-colors ${
                    currentRole === 'member'
                      ? 'bg-[#DC95FF] text-black border-[#DC95FF]'
                      : 'bg-[#181818] text-white border-white/10 hover:bg-[#2A2A2A]'
                  }`}
                >
                  Member
                </button>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-[#232323] border border-white/10 space-y-1.5">
              <div className="flex items-center gap-2 text-xs font-bold text-[#DC95FF]">
                <Lock className="w-3.5 h-3.5 shrink-0" />
                Verifikasi Discord OAuth2 Resmi
              </div>
              <p className="text-xs text-[#B3B3B3] leading-relaxed">
                Otorisasi akun Discord Anda untuk sinkronisasi otomatis hak akses Admin Server, Role DJ, atau Member pada server Discord terpilih.
              </p>
            </div>

            <div className="space-y-2.5">
              <button
                type="button"
                onClick={() => handleDiscordOAuthAuthorize(false)}
                className="w-full py-3 px-4 rounded-full bg-[#5865F2] hover:bg-[#4752C4] text-white font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-lg"
              >
                <LogIn className="w-4 h-4" />
                Login dengan Discord
              </button>

              <button
                type="button"
                onClick={() => handleDiscordOAuthAuthorize(true)}
                className="w-full py-2.5 px-4 rounded-full bg-[#282828] hover:bg-[#333333] border border-white/10 text-white font-semibold text-xs flex items-center justify-center gap-2 transition-colors"
              >
                <ShieldCheck className="w-4 h-4 text-[#DC95FF]" />
                Buka di Jendela Popup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
