import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Square,
  Shuffle,
  Repeat,
  Repeat1,
  Volume2,
  VolumeX,
  Radio,
  ShieldCheck,
  Music,
} from 'lucide-react';
import { GuildMusicState } from '../types/athenaa';
import { formatDuration } from './SearchDropdownBar';

interface SpotifyBottomPlayerProps {
  musicState: GuildMusicState;
<<<<<<< HEAD
=======
  browserAudioMuted: boolean;
  onToggleBrowserAudio: () => void;
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
  onControl: (action: string, value?: unknown, itemId?: string) => void;
}

const SpotifyBottomPlayerComponent: React.FC<SpotifyBottomPlayerProps> = ({
  musicState,
<<<<<<< HEAD
=======
  browserAudioMuted,
  onToggleBrowserAudio,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
  onControl,
}) => {
  const track = musicState.current_track;
  const duration = track?.duration_sec || 1;
  const serverPos = Math.min(musicState.position_sec, duration);

  const [isSeeking, setIsSeeking] = useState(false);
  const [dragPos, setDragPos] = useState(serverPos);

  const [isChangingVol, setIsChangingVol] = useState(false);
  const [localVol, setLocalVol] = useState(musicState.volume);
  const volumeDebounceRef = useRef<number | null>(null);

  // Sync seek pos from server when not dragging
  useEffect(() => {
    if (!isSeeking) {
      setDragPos(serverPos);
    }
  }, [serverPos, isSeeking]);

  // Sync volume from server when not interacting
  useEffect(() => {
    if (!isChangingVol) {
      setLocalVol(musicState.volume);
    }
  }, [musicState.volume, isChangingVol]);

  const nextLoopMode =
    musicState.loop_mode === 'off'
      ? 'queue'
      : musicState.loop_mode === 'queue'
      ? 'one'
      : 'off';

<<<<<<< HEAD
  const effectiveVol = isChangingVol ? localVol : musicState.volume;

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
  return (
    <footer
      aria-label="Pemutar Musik Real-Time"
      className="bg-[#000000] border-t border-white/5 md:border-t-0 px-3 py-2 md:py-0 md:px-4 md:h-[88px] flex flex-col md:grid md:grid-cols-12 items-center gap-2 md:gap-4 shrink-0 z-30 select-none"
    >
      {/* Top Row on Mobile / Zone 1 (Left, 3-4 cols) on Desktop: Active Track Art, Title & Singer */}
      <div className="w-full md:w-auto md:col-span-3 lg:col-span-3 flex items-center justify-between md:justify-start gap-3 min-w-0">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-11 h-11 md:w-14 md:h-14 rounded-md bg-[#181818] flex items-center justify-center shrink-0 overflow-hidden shadow-md">
            {track?.thumbnail_url ? (
              <img
                src={track.thumbnail_url}
                alt={track.title}
                referrerPolicy="no-referrer"
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
            ) : (
              <Music className="w-5 h-5 md:w-6 md:h-6 text-[#DC95FF]" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            {track ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs md:text-sm font-semibold text-white truncate hover:underline cursor-pointer">
                    {track.title}
                  </span>
                </div>
                <div className="text-[11px] md:text-xs text-[#B3B3B3] truncate mt-0.5">
                  <span className="text-white/85 font-medium">{track.artist}</span>
                  <span aria-hidden="true"> · </span>
                  <span>{track.requester_name}</span>
                </div>
                <div className="hidden sm:flex items-center gap-1 text-[11px] text-[#DC95FF] mt-0.5 truncate">
                  <ShieldCheck className="w-3 h-3 shrink-0" />
                  <span className="truncate">
                    {track.source_type === 'spotify_matched'
                      ? 'Spotify Matched'
                      : track.source_type === 'radio'
                      ? 'Live Radio'
                      : 'YouTube Audio'}{' '}
                    · {musicState.voice_channel_name}
                  </span>
                </div>
              </>
            ) : (
              <div>
                <div className="text-xs md:text-sm font-semibold text-white">Tidak ada lagu aktif</div>
                <div className="text-[11px] md:text-xs text-[#B3B3B3] truncate">
                  Cari lagu di atas untuk memulai sesi voice Discord
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Mobile Quick Transport Controls (visible on < md) */}
        <div className="flex md:hidden items-center gap-1.5 shrink-0">
          <button
            type="button"
            aria-label="Toggle Autoplay Mobile"
            onClick={() => onControl('autoplay', !musicState.autoplay)}
            className={`px-2 py-1 rounded-full text-[10px] font-bold transition-colors whitespace-nowrap ${
              musicState.autoplay
                ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/50'
                : 'bg-[#1F1F1F] text-[#B3B3B3]'
            }`}
          >
            AUTO {musicState.autoplay ? 'ON' : 'OFF'}
          </button>

          <button
            type="button"
            aria-label="Toggle Mode 24/7 Mobile"
            onClick={() => onControl('mode_247', !musicState.mode_247)}
            className={`px-2 py-1 rounded-full text-[10px] font-bold transition-colors whitespace-nowrap ${
              musicState.mode_247
                ? 'bg-[#DC95FF]/20 text-[#DC95FF] border border-[#DC95FF]/50'
                : 'bg-[#1F1F1F] text-[#B3B3B3]'
            }`}
          >
            24/7 {musicState.mode_247 ? 'ON' : 'OFF'}
          </button>

          <button
            type="button"
            aria-label={musicState.is_playing && !musicState.is_paused ? 'Jeda lagu' : 'Lanjutkan lagu'}
            onClick={() => {
              if (!track) {
                onControl('autoplay', true);
                return;
              }
              onControl(musicState.is_playing && !musicState.is_paused ? 'pause' : 'resume');
            }}
            className="w-8 h-8 rounded-full bg-white text-black flex items-center justify-center shadow"
          >
            {musicState.is_playing && !musicState.is_paused ? (
              <Pause className="w-4 h-4 fill-current" />
            ) : (
              <Play className="w-4 h-4 fill-current ml-0.5" />
            )}
          </button>

          <button
            type="button"
            aria-label="Lewati lagu"
            onClick={() => onControl('skip')}
            className="text-[#B3B3B3] hover:text-white p-1"
          >
            <SkipForward className="w-4 h-4 fill-current" />
          </button>
<<<<<<< HEAD
=======

          <button
            type="button"
            aria-label={browserAudioMuted ? 'Aktifkan suara monitor browser' : 'Bisukan suara monitor browser'}
            onClick={onToggleBrowserAudio}
            className={`p-1.5 rounded-full ${
              !browserAudioMuted ? 'text-[#DC95FF]' : 'text-[#B3B3B3]'
            }`}
          >
            {browserAudioMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        </div>
      </div>

      {/* Zone 2 (Center, 6 cols): Wide Mathematically Centered Transport Controls & Seek Bar */}
      <div className="w-full md:w-full md:col-span-6 lg:col-span-6 flex flex-col items-center justify-center max-w-[640px] mx-auto gap-2 px-1 sm:px-3">
        <div className="hidden md:flex items-center justify-center gap-6">
          <button
            type="button"
            aria-label="Acak antrean"
            onClick={() => onControl('shuffle')}
            className="text-[#B3B3B3] hover:text-white transition-colors p-1"
            title="Acak Antrean (Shuffle)"
          >
            <Shuffle className="w-4 h-4" />
          </button>

          <button
            type="button"
            aria-label="Ulangi dari awal lagu"
            onClick={() => onControl('seek', 0)}
            disabled={!track}
            className="text-[#B3B3B3] hover:text-white disabled:opacity-40 transition-colors p-1"
            title="Ulangi Lagu dari 00:00"
          >
            <SkipBack className="w-4 h-4 fill-current" />
          </button>

          <button
            type="button"
            aria-label={musicState.is_playing && !musicState.is_paused ? 'Jeda lagu' : 'Lanjutkan lagu'}
            onClick={() => {
              if (!track) {
                onControl('autoplay', true);
                return;
              }
              onControl(musicState.is_playing && !musicState.is_paused ? 'pause' : 'resume');
            }}
            className="w-9 h-9 rounded-full bg-white hover:scale-105 active:scale-95 text-black flex items-center justify-center transition-transform shadow cursor-pointer"
          >
            {musicState.is_playing && !musicState.is_paused ? (
              <Pause className="w-4 h-4 fill-current" />
            ) : (
              <Play className="w-4 h-4 fill-current ml-0.5" />
            )}
          </button>

          <button
            type="button"
            aria-label="Lewati lagu"
            onClick={() => onControl('skip')}
            disabled={!track}
            className="text-[#B3B3B3] hover:text-white disabled:opacity-40 transition-colors p-1"
            title="Lewati Lagu (Skip)"
          >
            <SkipForward className="w-4 h-4 fill-current" />
          </button>

          <button
            type="button"
            aria-label="Hentikan pemutaran"
            onClick={() => onControl('stop')}
            disabled={!track && musicState.queue.length === 0}
            className="text-[#B3B3B3] hover:text-rose-400 disabled:opacity-40 transition-colors p-1"
            title="Hentikan & Bersihkan Sesi (Stop)"
          >
            <Square className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            aria-label={`Ubah mode loop, saat ini ${musicState.loop_mode}`}
            onClick={() => onControl('loop', nextLoopMode)}
            className={`p-1 transition-colors flex items-center gap-1 text-xs font-medium ${
              musicState.loop_mode !== 'off'
                ? 'text-[#DC95FF]'
                : 'text-[#B3B3B3] hover:text-white'
            }`}
            title={`Loop: ${musicState.loop_mode.toUpperCase()}`}
          >
            {musicState.loop_mode === 'one' ? (
              <Repeat1 className="w-4 h-4" />
            ) : (
              <Repeat className="w-4 h-4" />
            )}
          </button>
        </div>

        <div className="w-full max-w-[580px] flex items-center gap-3">
          <span className="text-[11px] md:text-xs font-mono tabular-nums text-[#B3B3B3] w-10 md:w-11 text-right shrink-0">
            {formatDuration(isSeeking ? dragPos : serverPos)}
          </span>
          <input
            type="range"
            aria-label="Posisi pemutaran lagu"
            min={0}
            max={duration}
            value={isSeeking ? dragPos : serverPos}
            disabled={!track || track.source_type === 'radio'}
            onPointerDown={() => setIsSeeking(true)}
            onTouchStart={() => setIsSeeking(true)}
            onChange={(e) => {
              const val = Number(e.target.value);
              setDragPos(val);
            }}
            onPointerUp={(e) => {
              setIsSeeking(false);
              onControl('seek', Number((e.target as HTMLInputElement).value));
            }}
            onTouchEnd={() => {
              setIsSeeking(false);
              onControl('seek', dragPos);
            }}
            onKeyUp={(e) => {
              if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                onControl('seek', dragPos);
              }
            }}
            className="flex-1 w-full min-w-[200px] sm:min-w-[320px] md:min-w-[380px] h-1.5 bg-[#4D4D4D] hover:bg-[#5E5E5E] rounded-full appearance-none cursor-pointer accent-[#DC95FF] transition-colors"
          />
          <span className="text-[11px] md:text-xs font-mono tabular-nums text-[#B3B3B3] w-10 md:w-11 shrink-0">
            {track?.source_type === 'radio' ? 'LIVE' : formatDuration(track?.duration_sec || 0)}
          </span>
        </div>
      </div>

<<<<<<< HEAD
      {/* Zone 3 (Right, 3 cols on Desktop): Autoplay, 24/7 Mode & Bot Discord Volume Slider */}
=======
      {/* Zone 3 (Right, 3 cols on Desktop): Autoplay, 24/7 Mode & Volume Slider */}
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
      <div className="hidden md:flex md:col-span-3 lg:col-span-3 items-center justify-end gap-2">
        <button
          type="button"
          aria-label="Toggle Autoplay"
          onClick={() => onControl('autoplay', !musicState.autoplay)}
          className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors whitespace-nowrap ${
            musicState.autoplay
              ? 'bg-[#DC95FF]/15 text-[#DC95FF] border border-[#DC95FF]/40'
              : 'bg-[#1F1F1F] text-[#B3B3B3] hover:text-white'
          }`}
        >
          Autoplay {musicState.autoplay ? 'ON' : 'OFF'}
        </button>

        <button
          type="button"
          aria-label="Toggle Mode 24/7 Voice"
          onClick={() => onControl('mode_247', !musicState.mode_247)}
          className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors whitespace-nowrap flex items-center gap-1 ${
            musicState.mode_247
              ? 'bg-[#DC95FF]/15 text-[#DC95FF] border border-[#DC95FF]/40'
              : 'bg-[#1F1F1F] text-[#B3B3B3] hover:text-white'
          }`}
        >
          <Radio className="w-3 h-3" />
          24/7 {musicState.mode_247 ? 'ON' : 'OFF'}
        </button>

        <div className="flex items-center gap-2 pl-2">
          <button
            type="button"
<<<<<<< HEAD
            aria-label={effectiveVol <= 1 ? 'Kembalikan volume bot Discord ke 80%' : 'Kecilkan volume bot Discord ke 1%'}
            onClick={() => {
              const targetVol = effectiveVol <= 1 ? 80 : 1;
              setLocalVol(targetVol);
              onControl('volume', targetVol);
            }}
            className="p-1.5 rounded-full text-[#DC95FF] hover:text-white transition-colors"
            title="Volume Bot Discord Voice"
          >
            {effectiveVol <= 1 ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
=======
            aria-label={browserAudioMuted ? 'Aktifkan suara monitor browser' : 'Bisukan suara monitor browser'}
            onClick={onToggleBrowserAudio}
            className={`p-1.5 rounded-full transition-colors ${
              !browserAudioMuted
                ? 'text-[#DC95FF]'
                : 'text-[#B3B3B3] hover:text-white'
            }`}
            title={browserAudioMuted ? 'Klik untuk mendengar audio di browser' : 'Audio monitor browser aktif'}
          >
            {browserAudioMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
          </button>
          <input
            type="range"
            aria-label="Volume suara bot 1 sampai 100 persen"
            min={1}
            max={100}
<<<<<<< HEAD
            value={effectiveVol}
=======
            value={isChangingVol ? localVol : musicState.volume}
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            onPointerDown={() => setIsChangingVol(true)}
            onTouchStart={() => setIsChangingVol(true)}
            onChange={(e) => {
              const val = Number(e.target.value);
              setLocalVol(val);
              if (volumeDebounceRef.current) {
                window.clearTimeout(volumeDebounceRef.current);
              }
              volumeDebounceRef.current = window.setTimeout(() => {
                onControl('volume', val);
              }, 120);
            }}
            onPointerUp={(e) => {
              setIsChangingVol(false);
              if (volumeDebounceRef.current) {
                window.clearTimeout(volumeDebounceRef.current);
              }
              onControl('volume', Number((e.target as HTMLInputElement).value));
            }}
            onTouchEnd={() => {
              setIsChangingVol(false);
              if (volumeDebounceRef.current) {
                window.clearTimeout(volumeDebounceRef.current);
              }
              onControl('volume', localVol);
            }}
            className="w-20 lg:w-24 h-1 bg-[#4D4D4D] rounded-lg appearance-none cursor-pointer accent-[#DC95FF]"
          />
          <span className="text-[11px] font-mono tabular-nums text-[#B3B3B3] w-8 text-right">
<<<<<<< HEAD
            {effectiveVol}%
=======
            {isChangingVol ? localVol : musicState.volume}%
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
          </span>
        </div>
      </div>
    </footer>
  );
};

export const SpotifyBottomPlayer = React.memo(SpotifyBottomPlayerComponent);
<<<<<<< HEAD

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
