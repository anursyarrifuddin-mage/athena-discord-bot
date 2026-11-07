import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  Pause,
  SkipForward,
  ArrowUp,
  Trash2,
  Shuffle,
  Radio,
  Mic2,
  ShieldAlert,
  Heart,
  FolderPlus,
  ListMusic,
  Music,
  Clock3,
} from 'lucide-react';
import {
  ActiveActorProfile,
  GuildMusicState,
  LyricsResponse,
  TrackItem,
} from '../types/athenaa';
import { formatDuration } from './SearchDropdownBar';
import { getActiveLyricIndex } from '../lib/athenaaRules';

interface MusicAndLyricsViewProps {
  subTab: 'player' | 'queue' | 'library';
  guildId: string;
  sessionToken?: string;
  musicState: GuildMusicState;
  activeActor: ActiveActorProfile;
  onPlayTrack: (track: TrackItem, playNow: boolean) => void;
  onControl: (action: string, value?: unknown, itemId?: string) => void;
  onAddFavorite: (track: TrackItem) => void;
  onRefreshMusicState?: () => void;
  onNotify: (msg: string, isError?: boolean) => void;
}

const MusicAndLyricsViewComponent: React.FC<MusicAndLyricsViewProps> = ({
  subTab,
  guildId,
  sessionToken = '',
  musicState,
  activeActor,
  onPlayTrack,
  onControl,
  onAddFavorite,
  onRefreshMusicState,
  onNotify,
}) => {
  const [lyrics, setLyrics] = useState<LyricsResponse | null>(null);
  const [lyricsLoading, setLyricsLoading] = useState(false);
  const [customRadioUrl, setCustomRadioUrl] = useState('');
  const [customRadioName, setCustomRadioName] = useState('');
  const [spotifyInputUrl, setSpotifyInputUrl] = useState('');

  const [favorites, setFavorites] = useState<Array<Record<string, unknown>>>([]);
  const [playlists, setPlaylists] = useState<Array<Record<string, unknown>>>([]);
  const [newPlaylistName, setNewPlaylistName] = useState('');
  const [newPlaylistDesc, setNewPlaylistDesc] = useState('');
  const [spotifyPlaylistUrl, setSpotifyPlaylistUrl] = useState('');
  const [spotifyPlaylistCustomName, setSpotifyPlaylistCustomName] = useState('');
  const [importingSpotify, setImportingSpotify] = useState(false);

  const currentTrack = musicState.current_track;

  useEffect(() => {
    if (!currentTrack) {
      setLyrics(null);
      return;
    }
    let active = true;
    setLyricsLoading(true);
    fetch(
      `/api/music/lyrics?title=${encodeURIComponent(currentTrack.title)}&artist=${encodeURIComponent(
        currentTrack.artist
      )}`
    )
      .then((r) => r.json())
      .then((data) => {
        if (active) setLyrics(data);
      })
      .catch(() => {
        if (active) setLyrics(null);
      })
      .finally(() => {
        if (active) setLyricsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [currentTrack?.title, currentTrack?.artist]);

  const loadLibrary = async () => {
    try {
      const resp = await fetch(`/api/guilds/${guildId}/library`);
      if (resp.ok) {
        const data = await resp.json();
        setFavorites(data.favorites || []);
        setPlaylists(data.playlists || []);
      }
    } catch {
      // Ignore
    }
  };

  useEffect(() => {
    if (subTab === 'library') {
      loadLibrary();
    }
  }, [subTab, guildId]);

  const lyricsContainerRef = useRef<HTMLDivElement | null>(null);
  const lyricLineRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const activeLyricIdx =
    lyrics && lyrics.status === 'synced'
      ? getActiveLyricIndex(lyrics.synced_lines, musicState.position_sec)
      : -1;

  // Auto-scroll lyrics container to center the active lyric line as timestamp progresses
  useEffect(() => {
    if (subTab !== 'player' || activeLyricIdx < 0) return;
    const container = lyricsContainerRef.current;
    const activeEl = lyricLineRefs.current[activeLyricIdx];
    if (!container || !activeEl) return;

    const targetTop =
      activeEl.offsetTop - container.clientHeight / 2 + activeEl.clientHeight / 2;
    container.scrollTo({
      top: Math.max(0, targetTop),
      behavior: 'smooth',
    });
  }, [activeLyricIdx, subTab, currentTrack?.item_id]);

  const handleResolveSpotifyOrUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    const raw = spotifyInputUrl.trim();
    if (!raw) return;

    // If user pasted a Spotify Playlist or Album link, import and queue all tracks
    if (
      raw.includes('open.spotify.com/playlist/') ||
      raw.includes('open.spotify.com/album/')
    ) {
      setImportingSpotify(true);
      try {
        const resp = await fetch(`/api/guilds/${guildId}/playlists/import-spotify`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
          },
          body: JSON.stringify({
            url: raw,
            owner_user_id: activeActor.id,
            owner_username: activeActor.name,
            queue_now: true,
          }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          onNotify(data.error || 'Gagal mengimpor Playlist Spotify.', true);
          return;
        }
        setSpotifyInputUrl('');
        loadLibrary();
        if (onRefreshMusicState) onRefreshMusicState();
        onNotify(
          `Playlist Spotify "${data.name}" (${data.tracks_count} lagu) berhasil diimpor & dimasukkan ke antrean YouTube/Spotify!`
        );
      } catch {
        onNotify('Gagal menghubungi server untuk impor Playlist Spotify.', true);
      } finally {
        setImportingSpotify(false);
      }
      return;
    }

    // Resolve single Spotify Track URL, YouTube URL, or search query
    try {
      const resolveResp = await fetch('/api/music/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: raw }),
      });
      if (resolveResp.ok) {
        const resolved = await resolveResp.json();
        const first = (resolved.results || [])[0];
        if (first) {
          onPlayTrack(
            {
              ...first,
              source_type: raw.includes('spotify.com') ? 'spotify_matched' : first.source_type || 'youtube',
              source_url: first.source_url || raw,
            },
            false
          );
          setSpotifyInputUrl('');
          onNotify(
            raw.includes('spotify.com')
              ? `Lagu Spotify dicocokkan ke stream YouTube: ${first.title} — ${first.artist}`
              : `Ditambahkan ke antrean (YouTube): ${first.title} — ${first.artist}`
          );
          return;
        }
      }
    } catch {
      // Fallback to /api/music/search below
    }

    const resp = await fetch(`/api/music/search?q=${encodeURIComponent(raw)}`);
    if (resp.ok) {
      const data = await resp.json();
      const first = (data.results || [])[0];
      if (first) {
        onPlayTrack(
          {
            ...first,
            source_type: raw.includes('spotify.com') ? 'spotify_matched' : first.source_type || 'youtube',
            source_url: first.source_url || raw,
          },
          false
        );
        setSpotifyInputUrl('');
        onNotify(
          raw.includes('spotify.com')
            ? `Metadata Spotify dicocokkan ke stream YouTube: ${first.title} — ${first.artist}`
            : `Ditambahkan ke antrean: ${first.title} — ${first.artist}`
        );
      } else {
        onNotify('Lagu tidak ditemukan di YouTube maupun Spotify.', true);
      }
    }
  };

  const handleImportSpotifyPlaylist = async (queueNow: boolean) => {
    const raw = spotifyPlaylistUrl.trim();
    if (!raw || !raw.includes('spotify.com/')) {
      onNotify(
        'Masukkan link Playlist atau Album Spotify yang valid (mis. https://open.spotify.com/playlist/...)',
        true
      );
      return;
    }
    setImportingSpotify(true);
    try {
      const resp = await fetch(`/api/guilds/${guildId}/playlists/import-spotify`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        },
        body: JSON.stringify({
          url: raw,
          name: spotifyPlaylistCustomName.trim(),
          owner_user_id: activeActor.id,
          owner_username: activeActor.name,
          queue_now: queueNow,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        onNotify(data.error || 'Gagal mengimpor Playlist Spotify.', true);
        return;
      }
      setSpotifyPlaylistUrl('');
      setSpotifyPlaylistCustomName('');
      await loadLibrary();
      if (queueNow && onRefreshMusicState) {
        onRefreshMusicState();
      }
      onNotify(
        queueNow
          ? `Playlist Spotify "${data.name}" (${data.tracks_count} lagu) berhasil disimpan & langsung diputar di Discord Voice!`
          : `Playlist Spotify "${data.name}" (${data.tracks_count} lagu) berhasil diimpor ke Koleksi Playlist Server!`
      );
    } catch {
      onNotify('Terjadi kesalahan jaringan saat mengimpor Playlist Spotify.', true);
    } finally {
      setImportingSpotify(false);
    }
  };

  const handlePlayCustomRadio = (e: React.FormEvent) => {
    e.preventDefault();
    const url = customRadioUrl.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      onNotify('URL stream radio harus diawali http:// atau https://', true);
      return;
    }
    if (url.includes('127.0.0.1') || url.includes('localhost') || url.includes('192.168.')) {
      onNotify('Proteksi SSRF: URL jaringan lokal/privat ditolak.', true);
      return;
    }
    onPlayTrack(
      {
        title: customRadioName.trim() || 'Stasiun Radio Kustom',
        artist: 'Live Internet Radio Stream',
        album: 'Live Broadcast',
        duration_sec: 0,
        source_type: 'radio',
        source_url: url,
        stream_url: url,
        thumbnail_url: '',
      },
      true
    );
    setCustomRadioUrl('');
    setCustomRadioName('');
  };

  const handleSaveQueueAsPlaylist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPlaylistName.trim()) {
      onNotify('Masukkan nama playlist terlebih dahulu.', true);
      return;
    }
    const resp = await fetch(`/api/guilds/${guildId}/playlists/save-queue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newPlaylistName.trim(),
        description: newPlaylistDesc.trim(),
        owner_user_id: activeActor.id,
        owner_username: activeActor.name,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      onNotify(data.error || 'Gagal menyimpan playlist', true);
      return;
    }
    setNewPlaylistName('');
    setNewPlaylistDesc('');
    onNotify('Antrean saat ini berhasil disimpan ke database sebagai Playlist!');
    loadLibrary();
  };

  if (subTab === 'player') {
    return (
      <div className="space-y-6">
        {/* Spotify Lyrics Stage + Track Banner */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-stretch">
          <div className="xl:col-span-5 bg-[#181818] border border-white/5 rounded-xl p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-[#B3B3B3] mb-4">
                <span>Sesi Voice · {musicState.voice_channel_name}</span>
                <span className="font-mono tabular-nums">Volume {musicState.volume}%</span>
              </div>

              {currentTrack ? (
                <div className="space-y-4">
                  <div className="flex items-start gap-4">
                    <div className="w-24 h-24 rounded-lg bg-[#282828] flex items-center justify-center shrink-0 overflow-hidden shadow-lg">
                      {currentTrack.thumbnail_url ? (
                        <img
                          src={currentTrack.thumbnail_url}
                          alt={currentTrack.title}
                          referrerPolicy="no-referrer"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.currentTarget as HTMLImageElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <Music className="w-10 h-10 text-[#DC95FF]" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-xl font-bold text-white leading-tight truncate">
                        {currentTrack.title}
                      </h2>
                      <p className="text-sm font-semibold text-[#DC95FF] mt-1 truncate">
                        {currentTrack.artist}
                      </p>
                      <div className="text-xs text-[#B3B3B3] mt-2 space-y-1">
                        <div>
                          Album: {currentTrack.album || 'Single'} ·{' '}
                          {currentTrack.source_type === 'spotify_matched'
                            ? 'Spotify Matched'
                            : currentTrack.source_type === 'radio'
                            ? 'Live Radio'
                            : 'YouTube Audio'}
                        </div>
                        <div>Diminta oleh: {currentTrack.requester_name}</div>
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          <span className="px-2 py-0.5 rounded bg-[#282828] text-[11px] text-white">
                            Loop: {musicState.loop_mode.toUpperCase()}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                              musicState.autoplay
                                ? 'bg-[#DC95FF]/20 text-[#DC95FF]'
                                : 'bg-[#282828] text-[#B3B3B3]'
                            }`}
                          >
                            Autoplay: {musicState.autoplay ? 'ON' : 'OFF'}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                              musicState.mode_247
                                ? 'bg-[#DC95FF]/20 text-[#DC95FF]'
                                : 'bg-[#282828] text-[#B3B3B3]'
                            }`}
                          >
                            24/7: {musicState.mode_247 ? 'ON' : 'OFF'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {currentTrack.source_type === 'spotify_matched' && (
                    <div className="p-3 rounded-lg bg-[#242424] text-xs text-[#B3B3B3]">
                      Metadata diambil dari tautan Spotify dan diputar melalui pencocokan sumber audio terbuka.
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() =>
                        onControl(
                          musicState.is_playing && !musicState.is_paused ? 'pause' : 'resume'
                        )
                      }
                      className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs transition-transform active:scale-95 cursor-pointer"
                    >
                      {musicState.is_playing && !musicState.is_paused ? (
                        <>
                          <Pause className="w-4 h-4 fill-current" />
                          Jeda Pemutaran
                        </>
                      ) : (
                        <>
                          <Play className="w-4 h-4 fill-current" />
                          Lanjutkan Pemutaran
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => onControl('skip')}
                      className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <SkipForward className="w-4 h-4" />
                      Skip Lagu
                    </button>

                    <button
                      type="button"
                      onClick={() => onControl('autoplay', !musicState.autoplay)}
                      className={`flex items-center gap-1.5 px-3.5 py-2.5 rounded-full text-xs font-bold transition-colors cursor-pointer ${
                        musicState.autoplay
                          ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/40'
                          : 'bg-[#282828] hover:bg-[#3E3E3E] text-[#B3B3B3] hover:text-white'
                      }`}
                    >
                      Autoplay {musicState.autoplay ? 'ON' : 'OFF'}
                    </button>

                    <button
                      type="button"
                      onClick={() => onControl('mode_247', !musicState.mode_247)}
                      className={`flex items-center gap-1.5 px-3.5 py-2.5 rounded-full text-xs font-bold transition-colors cursor-pointer ${
                        musicState.mode_247
                          ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/40'
                          : 'bg-[#282828] hover:bg-[#3E3E3E] text-[#B3B3B3] hover:text-white'
                      }`}
                    >
                      <Radio className="w-3.5 h-3.5" />
                      24/7 {musicState.mode_247 ? 'ON' : 'OFF'}
                    </button>

                    <button
                      type="button"
                      onClick={() => onAddFavorite(currentTrack)}
                      className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <Heart className="w-4 h-4 text-[#DC95FF]" />
                      Simpan Favorit
                    </button>
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center space-y-4">
                  <div className="text-sm text-[#B3B3B3]">
                    Belum ada lagu yang diputar. Gunakan kolom pencarian di atas atau aktifkan Autoplay di bawah.
                  </div>
                  <div className="flex flex-wrap items-center justify-center gap-2.5">
                    <button
                      type="button"
                      onClick={() => onControl('autoplay', true)}
                      className="px-4 py-2 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs cursor-pointer"
                    >
                      Mulai Autoplay Sekarang
                    </button>
                    <button
                      type="button"
                      onClick={() => onControl('mode_247', !musicState.mode_247)}
                      className={`px-4 py-2 rounded-full text-xs font-bold cursor-pointer ${
                        musicState.mode_247
                          ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/40'
                          : 'bg-[#282828] text-white'
                      }`}
                    >
                      Mode 24/7: {musicState.mode_247 ? 'ON' : 'OFF'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <form onSubmit={handleResolveSpotifyOrUrl} className="mt-6 pt-5 border-t border-white/10 space-y-2">
              <label className="block text-xs font-medium text-[#B3B3B3]">
                Impor Tautan Spotify (Track / Album / Playlist) atau YouTube URL
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="https://open.spotify.com/track/... atau judul lagu"
                  value={spotifyInputUrl}
                  onChange={(e) => setSpotifyInputUrl(e.target.value)}
                  className="flex-1 bg-[#242424] border border-white/10 rounded-full px-4 py-2 text-xs text-white placeholder:text-[#B3B3B3] focus:outline-none focus:border-white/40"
                />
                <button
                  type="submit"
                  className="px-4 py-2 rounded-full bg-white hover:bg-white/90 text-xs font-bold text-black whitespace-nowrap"
                >
                  Cocokkan & Antrekan
                </button>
              </div>
            </form>
          </div>

          {/* Authentic Spotify Synchronized Lyrics Stage (Auto-Scrolls to Active Timestamp) */}
          <div className="xl:col-span-7 bg-gradient-to-br from-[#351a57] via-[#1f1133] to-[#121212] border border-white/10 rounded-xl p-6 flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-4 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Mic2 className="w-4 h-4 text-[#DC95FF]" />
                <h3 className="text-base font-bold text-white">
                  Lirik Otomatis LRCLIB (Real-Time Auto-Sync)
                </h3>
              </div>
              <span className="text-xs font-mono tabular-nums text-[#DC95FF]">
                {lyrics?.status === 'synced'
                  ? `Auto-Scroll Aktif · ${formatDuration(musicState.position_sec)}`
                  : lyrics?.status === 'plain'
                  ? 'Teks biasa (Plain Lyrics)'
                  : 'Tanpa API Key · Public LRCLIB'}
              </span>
            </div>

            <div
              ref={lyricsContainerRef}
              className="flex-1 mt-4 max-h-72 overflow-y-auto pr-2 space-y-2 scroll-smooth relative"
            >
              {lyricsLoading ? (
                <div className="py-12 text-center text-sm text-white/70">
                  Mengambil lirik dari LRCLIB untuk {currentTrack?.title}...
                </div>
              ) : !currentTrack ? (
                <div className="py-12 text-center text-sm text-white/70">
                  Putar lagu terlebih dahulu untuk menampilkan lirik tersinkronisasi.
                </div>
              ) : lyrics?.status === 'synced' && lyrics.synced_lines.length > 0 ? (
                lyrics.synced_lines.map((line, idx) => {
                  const isCurrent = idx === activeLyricIdx;
                  return (
                    <div
                      key={`${line.timeSec}-${idx}`}
                      ref={(el) => {
                        lyricLineRefs.current[idx] = el;
                      }}
                      data-lyric-active={isCurrent ? 'true' : 'false'}
                      onClick={() => onControl('seek', Math.floor(line.timeSec))}
                      className={`grid grid-cols-[52px_1fr] items-baseline gap-3 px-3.5 py-2.5 rounded-lg cursor-pointer transition-all duration-300 ${
                        isCurrent
                          ? 'bg-black/45 text-white font-bold ring-1 ring-[#DC95FF]/40 shadow-md'
                          : 'text-white/55 hover:text-white hover:bg-black/20'
                      }`}
                    >
                      <span
                        className={`text-xs font-mono tabular-nums ${
                          isCurrent ? 'text-[#DC95FF] font-bold' : 'text-white/50'
                        }`}
                      >
                        {formatDuration(line.timeSec)}
                      </span>
                      <p className={isCurrent ? 'text-lg text-[#DC95FF] leading-snug' : 'text-sm'}>
                        {line.text}
                      </p>
                    </div>
                  );
                })
              ) : lyrics?.plain_lyrics ? (
                <pre className="text-sm text-white/85 whitespace-pre-wrap font-sans leading-relaxed">
                  {lyrics.plain_lyrics}
                </pre>
              ) : (
                <div className="py-12 text-center text-sm text-white/70">
                  {lyrics?.message || 'Lirik belum tersedia di LRCLIB untuk lagu ini. Pemutaran musik tetap berjalan normal.'}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Internet Radio Cards */}
        <div className="bg-[#181818] border border-white/5 rounded-xl p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Radio className="w-4 h-4 text-[#DC95FF]" />
                Stasiun Radio Internet & Live Stream
              </h3>
              <p className="text-xs text-[#B3B3B3] mt-0.5">
                Pilih stasiun radio terverifikasi atau masukkan URL stream khusus (dilindungi validasi anti-SSRF).
              </p>
            </div>
            <form onSubmit={handlePlayCustomRadio} className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                placeholder="Nama Radio"
                value={customRadioName}
                onChange={(e) => setCustomRadioName(e.target.value)}
                className="bg-[#242424] border border-white/10 rounded-full px-3.5 py-1.5 text-xs text-white w-36"
              />
              <input
                type="url"
                placeholder="https://stream.radio.../live"
                value={customRadioUrl}
                onChange={(e) => setCustomRadioUrl(e.target.value)}
                className="bg-[#242424] border border-white/10 rounded-full px-3.5 py-1.5 text-xs text-white w-60"
              />
              <button
                type="submit"
                className="px-4 py-1.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs whitespace-nowrap"
              >
                Putar Stream URL
              </button>
            </form>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
            {(musicState.radios || []).map((st) => {
              const isCurrentRadio =
                currentTrack?.source_type === 'radio' && currentTrack?.title === st.name;
              return (
                <div
                  key={st.id}
                  className="p-4 rounded-xl bg-[#242424] hover:bg-[#2A2A2A] transition-colors flex flex-col justify-between gap-4"
                >
                  <div>
                    <div className="text-sm font-bold text-white">{st.name}</div>
                    <div className="text-xs text-[#B3B3B3] mt-1">{st.artist}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      onPlayTrack(
                        {
                          title: st.name,
                          artist: st.artist,
                          album: 'Live Radio',
                          duration_sec: 0,
                          source_type: 'radio',
                          source_url: st.stream_url,
                          stream_url: st.stream_url,
                          thumbnail_url: '',
                        },
                        true
                      )
                    }
                    className={`w-full py-2 px-3 rounded-full text-xs font-bold flex items-center justify-center gap-1.5 transition-colors ${
                      isCurrentRadio
                        ? 'bg-[#DC95FF] text-black'
                        : 'bg-[#181818] hover:bg-black text-white'
                    }`}
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    {isCurrentRadio ? 'Sedang Mengudara' : 'Putar Stasiun'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  if (subTab === 'queue') {
    return (
      <div className="space-y-6">
        {/* Host Lock System Banner */}
        <div className="bg-[#181818] border border-white/5 rounded-xl p-5">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-[#DC95FF]" />
                Host Lock System & Izin Kontrol Antrean
              </h2>
              <p className="text-xs text-[#B3B3B3] mt-1">
                Session Host saat ini:{' '}
                <strong className="text-white">
                  {musicState.host_username || 'Tidak ada (Sesi Terbuka)'}
                </strong>
                . Pengguna biasa hanya dapat menghapus lagunya sendiri dan tidak dapat melewati/menghentikan lagu pengguna lain.
              </p>
            </div>

            <div className="flex items-center gap-2 px-3.5 py-2 rounded-full bg-[#242424] border border-white/10 shrink-0">
              <span className="w-2 h-2 rounded-full bg-[#DC95FF]" />
              <span className="text-xs text-[#B3B3B3]">Sesi Login:</span>
              <span className="text-xs font-bold text-white">{activeActor.name}</span>
              <span className="text-[11px] text-[#DC95FF]">({activeActor.roleLabel})</span>
            </div>
          </div>
        </div>

        {/* Spotify Precision Tracklist Queue */}
        <div className="bg-[#181818] border border-white/5 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="text-base font-bold text-white">
                Daftar Antrean Server ({musicState.queue.length} Lagu)
              </h3>
              <p className="text-xs text-[#B3B3B3] mt-0.5">
                Setiap item antrean memiliki UUID unik sehingga lagu yang sama dapat ditambahkan beberapa kali.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => onControl('autoplay', !musicState.autoplay)}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold transition-colors cursor-pointer ${
                  musicState.autoplay
                    ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/40'
                    : 'bg-[#282828] hover:bg-[#3E3E3E] text-[#B3B3B3] hover:text-white'
                }`}
              >
                Autoplay {musicState.autoplay ? 'ON' : 'OFF'}
              </button>
              <button
                type="button"
                onClick={() => onControl('mode_247', !musicState.mode_247)}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold transition-colors cursor-pointer ${
                  musicState.mode_247
                    ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/40'
                    : 'bg-[#282828] hover:bg-[#3E3E3E] text-[#B3B3B3] hover:text-white'
                }`}
              >
                <Radio className="w-3.5 h-3.5" />
                Mode 24/7 {musicState.mode_247 ? 'ON' : 'OFF'}
              </button>
              <button
                type="button"
                onClick={() => onControl('shuffle')}
                disabled={musicState.queue.length < 2}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] disabled:opacity-40 text-xs font-semibold text-white cursor-pointer"
              >
                <Shuffle className="w-3.5 h-3.5" />
                Acak Antrean
              </button>
              <button
                type="button"
                onClick={() => onControl('clear')}
                disabled={musicState.queue.length === 0}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-rose-950/60 hover:bg-rose-900/70 border border-rose-800/50 disabled:opacity-40 text-xs font-semibold text-rose-200 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Bersihkan Antrean
              </button>
            </div>
          </div>

          {musicState.queue.length === 0 ? (
            <div className="p-10 text-center text-sm text-[#B3B3B3]">
              Antrean kosong. Jika Autoplay aktif, bot akan otomatis memilih lagu berikutnya saat lagu saat ini selesai.
            </div>
          ) : (
            <div className="p-3">
              <div className="grid grid-cols-[36px_minmax(0,2fr)_minmax(0,1.1fr)_100px_68px_210px] items-center gap-3 px-3 py-2 border-b border-white/10 text-xs font-medium text-[#B3B3B3]">
                <span>#</span>
                <span>Judul & Penyanyi</span>
                <span>Diminta Oleh</span>
                <span>ID Unik</span>
                <span className="flex justify-end">
                  <Clock3 className="w-3.5 h-3.5" />
                </span>
                <span className="text-right">Kontrol</span>
              </div>

              <div className="divide-y divide-white/5 mt-1">
                {musicState.queue.map((item, idx) => (
                  <div
                    key={item.item_id || idx}
                    className="grid grid-cols-[36px_minmax(0,2fr)_minmax(0,1.1fr)_100px_68px_210px] items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 transition-colors"
                  >
                    <span className="font-mono tabular-nums text-xs text-[#B3B3B3]">
                      {idx + 1}
                    </span>
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded bg-[#282828] flex items-center justify-center shrink-0 overflow-hidden">
                        {item.thumbnail_url ? (
                          <img
                            src={item.thumbnail_url}
                            alt={item.title}
                            referrerPolicy="no-referrer"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Music className="w-4 h-4 text-[#DC95FF]" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold text-white text-sm truncate">
                          {item.title}
                        </div>
                        <div className="text-xs text-[#B3B3B3] truncate">
                          {item.artist} {item.album ? `· ${item.album}` : ''}
                        </div>
                      </div>
                    </div>
                    <span className="text-xs text-[#B3B3B3] truncate">{item.requester_name}</span>
                    <span className="font-mono text-xs text-white/45 truncate">{item.item_id}</span>
                    <span className="font-mono tabular-nums text-xs text-[#B3B3B3] text-right">
                      {formatDuration(item.duration_sec)}
                    </span>
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        aria-label={`Putar sekarang ${item.title}`}
                        onClick={() => onControl('play_item', undefined, item.item_id)}
                        className="px-2.5 py-1 rounded-full bg-gradient-to-r from-[#8C56D4] to-[#DC95FF] hover:from-[#DC95FF] hover:to-[#FFBEFB] text-black font-bold text-xs inline-flex items-center gap-1 transition-all"
                        title="Putar Sekarang"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        Play
                      </button>
                      <button
                        type="button"
                        aria-label={`Pindahkan ${item.title} ke urutan teratas`}
                        onClick={() => onControl('move_to_top', undefined, item.item_id)}
                        className="px-2 py-1 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-xs text-white inline-flex items-center gap-1"
                        title="Move to Top"
                      >
                        <ArrowUp className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Hapus ${item.title} dari antrean`}
                        onClick={() => onControl('remove_item', undefined, item.item_id)}
                        className="px-2.5 py-1 rounded-full bg-[#282828] hover:bg-rose-900/70 text-xs text-[#B3B3B3] hover:text-rose-200 inline-flex items-center gap-1"
                        title="Hapus dari Antrean"
                      >
                        <Trash2 className="w-3 h-3" />
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
      <div className="lg:col-span-6 bg-[#181818] border border-white/5 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Heart className="w-4 h-4 text-[#DC95FF]" />
              Lagu yang Disukai ({favorites.length})
            </h2>
            <p className="text-xs text-[#B3B3B3] mt-0.5">
              Daftar lagu favorit yang tersimpan pada akun Discord Anda.
            </p>
          </div>
        </div>

        {favorites.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#B3B3B3]">
            Belum ada lagu favorit. Klik ikon hati pada hasil pencarian atau pemutar musik.
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {favorites.map((fav) => (
              <div key={String(fav.favorite_id)} className="py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white truncate">
                    {String(fav.title)}
                  </div>
                  <div className="text-xs text-[#B3B3B3] truncate">
                    {String(fav.artist)} ·{' '}
                    <span className="font-mono tabular-nums">
                      {formatDuration(Number(fav.duration_sec || 180))}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() =>
                      onPlayTrack(
                        {
                          title: String(fav.title),
                          artist: String(fav.artist),
                          album: String(fav.album || ''),
                          duration_sec: Number(fav.duration_sec || 180),
                          source_type: String(
                            fav.source_type === 'itunes_preview' || !fav.source_type
                              ? 'youtube'
                              : fav.source_type
                          ),
                          source_url: String(fav.source_url || ''),
                          stream_url: '',
                          thumbnail_url: String(fav.thumbnail_url || ''),
                        },
                        false
                      )
                    }
                    className="px-3 py-1 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
                  >
                    + Antrean
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      await fetch(`/api/favorites/${fav.favorite_id}`, { method: 'DELETE' });
                      loadLibrary();
                    }}
                    className="p-1.5 rounded-full bg-[#282828] hover:bg-rose-900/60 text-[#B3B3B3] hover:text-rose-200"
                    aria-label={`Hapus favorit ${String(fav.title)}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="lg:col-span-6 bg-[#181818] border border-white/5 rounded-xl p-6 space-y-4">
        <div className="border-b border-white/10 pb-3">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <ListMusic className="w-4 h-4 text-[#DC95FF]" />
            Playlist Tersimpan Server ({playlists.length})
          </h2>
          <p className="text-xs text-[#B3B3B3] mt-0.5">
            Impor langsung menggunakan link Playlist Spotify atau simpan antrean aktif ke koleksi server.
          </p>
        </div>

        {/* Impor Playlist dari Link Spotify */}
        <div className="p-4 rounded-xl bg-gradient-to-br from-[#351a57]/60 to-[#242424] border border-[#DC95FF]/30 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-bold text-white flex items-center gap-1.5">
              <Music className="w-3.5 h-3.5 text-[#DC95FF]" />
              Impor Playlist dari Link Spotify (Spotify &rarr; YouTube Audio)
            </div>
            <span className="text-[10px] font-mono text-[#DC95FF] bg-black/30 px-2 py-0.5 rounded-full">
              Spotify + YouTube
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="url"
              placeholder="https://open.spotify.com/playlist/..."
              value={spotifyPlaylistUrl}
              onChange={(e) => setSpotifyPlaylistUrl(e.target.value)}
              className="bg-[#181818] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-[#B3B3B3] focus:outline-none focus:border-[#DC95FF]"
            />
            <input
              type="text"
              placeholder="Nama Playlist Kustom (opsional)"
              value={spotifyPlaylistCustomName}
              onChange={(e) => setSpotifyPlaylistCustomName(e.target.value)}
              className="bg-[#181818] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-[#B3B3B3] focus:outline-none focus:border-[#DC95FF]"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={importingSpotify}
              onClick={() => handleImportSpotifyPlaylist(false)}
              className="px-4 py-1.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] disabled:opacity-50 text-black font-bold text-xs transition-transform active:scale-95"
            >
              {importingSpotify ? 'Mengimpor dari Spotify...' : 'Impor ke Koleksi Playlist'}
            </button>
            <button
              type="button"
              disabled={importingSpotify}
              onClick={() => handleImportSpotifyPlaylist(true)}
              className="px-4 py-1.5 rounded-full bg-white hover:bg-white/90 disabled:opacity-50 text-black font-bold text-xs transition-transform active:scale-95"
            >
              Impor & Langsung Putar
            </button>
          </div>
        </div>

        <form onSubmit={handleSaveQueueAsPlaylist} className="p-4 rounded-xl bg-[#242424] space-y-3">
          <div className="text-xs font-bold text-white flex items-center gap-1.5">
            <FolderPlus className="w-3.5 h-3.5 text-[#DC95FF]" />
            Simpan Antrean Saat Ini Sebagai Playlist Baru
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="text"
              placeholder="Nama Playlist (mis. Lo-Fi Sesi UAS)"
              value={newPlaylistName}
              onChange={(e) => setNewPlaylistName(e.target.value)}
              className="bg-[#181818] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white"
            />
            <input
              type="text"
              placeholder="Deskripsi singkat"
              value={newPlaylistDesc}
              onChange={(e) => setNewPlaylistDesc(e.target.value)}
              className="bg-[#181818] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-1.5 rounded-full bg-[#282828] hover:bg-[#3E3E3E] text-white font-bold text-xs"
          >
            Simpan Antrean ke Playlist
          </button>
        </form>

        <div className="space-y-3">
          {playlists.map((pl) => {
            const items = (pl.items as Array<Record<string, unknown>>) || [];
            return (
              <div
                key={String(pl.playlist_id)}
                className="p-4 rounded-xl bg-[#242424] space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-bold text-white">{String(pl.name)}</div>
                    <div className="text-xs text-[#B3B3B3]">
                      Oleh {String(pl.owner_username)} · {items.length} lagu
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={async () => {
                        const resp = await fetch(
                          `/api/guilds/${guildId}/playlists/${pl.playlist_id}/play`,
                          { method: 'POST' }
                        );
                        if (resp.ok) {
                          onNotify(`Memuat playlist "${String(pl.name)}" ke antrean server.`);
                        }
                      }}
                      className="px-3.5 py-1 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs"
                    >
                      Putar Playlist
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        await fetch(`/api/guilds/${guildId}/playlists/${pl.playlist_id}`, {
                          method: 'DELETE',
                        });
                        loadLibrary();
                      }}
                      className="p-1.5 rounded-full bg-[#181818] hover:bg-rose-900/60 text-[#B3B3B3] hover:text-rose-200"
                      aria-label={`Hapus playlist ${String(pl.name)}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                {items.length > 0 && (
                  <div className="text-xs text-[#B3B3B3] pt-1 border-t border-white/10">
                    {items.map((it) => `${it.title} (${it.artist})`).join(' · ')}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const MusicAndLyricsView = React.memo(MusicAndLyricsViewComponent);
