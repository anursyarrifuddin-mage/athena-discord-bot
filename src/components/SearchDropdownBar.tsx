import React, { useState, useEffect, useRef } from 'react';
import { Search, Play, Plus, Music, X, Loader2, ListMusic } from 'lucide-react';
import { TrackItem } from '../types/athenaa';

interface SearchDropdownBarProps {
  onPlayNow: (track: TrackItem) => void;
  onAddToQueue: (track: TrackItem) => void;
}

export function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function isDirectPlaylistUrl(raw: string): boolean {
  const q = raw.trim().toLowerCase();
  return (
    q.includes('open.spotify.com/playlist/') ||
    q.includes('open.spotify.com/album/') ||
    ((q.includes('youtube.com/') || q.includes('youtu.be/')) && q.includes('list='))
  );
}

const SearchDropdownBarComponent: React.FC<SearchDropdownBarProps> = ({
  onPlayNow,
  onAddToQueue,
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<TrackItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const resp = await fetch(`/api/music/search?q=${encodeURIComponent(query.trim())}`);
        if (resp.ok && active) {
          const data = await resp.json();
          setResults(data.results || []);
        }
      } catch {
        // Ignore network error
      } finally {
        if (active) setIsLoading(false);
      }
    }, 160);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    const trimmed = query.trim();
    if (!trimmed) return;
    e.preventDefault();

    if (results.length > 0) {
      onPlayNow(results[0]);
      setIsOpen(false);
      setQuery('');
      return;
    }

    if (isDirectPlaylistUrl(trimmed)) {
      const isSpotify = trimmed.toLowerCase().includes('spotify.com');
      onPlayNow({
        title: isSpotify ? 'Spotify Playlist' : 'YouTube Playlist',
        artist: 'Putar Langsung Semua Lagu',
        album: isSpotify ? 'Spotify Playlist' : 'YouTube Playlist',
        duration_sec: 180,
        source_type: isSpotify ? 'spotify_playlist' : 'youtube_playlist',
        source_url: trimmed,
        stream_url: '',
        thumbnail_url: '',
      });
      setIsOpen(false);
      setQuery('');
    }
  };

  return (
    <div ref={containerRef} className="relative w-full max-w-[480px]">
      <div className="relative flex items-center h-11 rounded-full bg-[#1F1F1F] hover:bg-[#2A2A2A] border border-transparent focus-within:border-white/30 focus-within:bg-[#242424] transition-colors">
        <Search className="w-4 h-4 text-[#B3B3B3] absolute left-4 pointer-events-none" />
        <input
          type="text"
          role="searchbox"
          aria-label="Cari lagu, penyanyi, atau tempel tautan Playlist YouTube dan Spotify"
          placeholder="Cari lagu, penyanyi, atau tempel link Playlist YouTube / Spotify..."
          value={query}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          className="w-full h-full bg-transparent rounded-full pl-11 pr-10 text-sm text-white placeholder:text-[#B3B3B3] focus:outline-none"
        />
        {query && (
          <button
            type="button"
            aria-label="Bersihkan pencarian"
            onClick={() => {
              setQuery('');
              setIsOpen(true);
            }}
            className="absolute right-3 p-1 text-[#B3B3B3] hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {isOpen && (
        <div
          role="listbox"
          aria-label="Hasil pencarian lagu, penyanyi, dan playlist"
          className="absolute left-1/2 -translate-x-1/2 top-full mt-2 w-[540px] max-w-[92vw] bg-[#282828] border border-white/10 rounded-xl shadow-[0_16px_40px_rgba(0,0,0,0.8)] z-50 overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 text-xs font-medium text-[#B3B3B3]">
            <span className="truncate">
              {query.trim()
                ? isDirectPlaylistUrl(query)
                  ? 'Playlist Terdeteksi — Klik Putar Playlist atau tekan Enter'
                  : `Lagu & Penyanyi untuk "${query.trim()}"`
                : 'Rekomendasi Lagu & Penyanyi (Atau Tempel Link Playlist YouTube / Spotify)'}
            </span>
            {isLoading && (
              <span className="flex items-center gap-1.5 text-[#DC95FF] shrink-0 ml-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Mencari...
              </span>
            )}
          </div>

          {results.length === 0 && !isLoading ? (
            <div className="px-4 py-6 text-center text-sm text-[#B3B3B3]">
              Tidak ditemukan lagu untuk kata kunci tersebut. Coba ketik judul, penyanyi, atau tempel URL Playlist YouTube / Spotify.
            </div>
          ) : (
            <div className="max-h-[340px] overflow-y-auto p-1.5 space-y-0.5">
              {results.map((item, idx) => {
                const isPlaylistEntry =
                  item.source_type === 'spotify_playlist' ||
                  item.source_type === 'spotify_album' ||
                  item.source_type === 'youtube_playlist' ||
                  item.title.startsWith('🎶 [PLAYLIST]');
                return (
                  <div
                    key={`${item.title}-${item.artist}-${idx}`}
                    className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-2.5 py-2 rounded-lg transition-colors group ${
                      isPlaylistEntry
                        ? 'bg-[#351a57]/60 hover:bg-[#351a57]/90 border border-[#DC95FF]/30 mb-1'
                        : 'hover:bg-[#3E3E3E]/70'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded bg-[#181818] flex items-center justify-center shrink-0 overflow-hidden shadow">
                        {item.thumbnail_url ? (
                          <img
                            src={item.thumbnail_url}
                            alt={item.title}
                            referrerPolicy="no-referrer"
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.currentTarget as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        ) : isPlaylistEntry ? (
                          <ListMusic className="w-4 h-4 text-[#DC95FF]" />
                        ) : (
                          <Music className="w-4 h-4 text-[#DC95FF]" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-white truncate">
                          {item.title}
                        </div>
                        <div className="flex items-center gap-1.5 text-xs text-[#B3B3B3] truncate mt-0.5">
                          <span className="font-medium text-white/90">{item.artist}</span>
                          {item.album && (
                            <>
                              <span aria-hidden="true">·</span>
                              <span className="truncate">{item.album}</span>
                            </>
                          )}
                          <span aria-hidden="true">·</span>
                          <span className="font-mono tabular-nums text-[#B3B3B3]">
                            {formatDuration(item.duration_sec)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        aria-label={`Putar sekarang ${item.title} oleh ${item.artist}`}
                        onClick={() => {
                          onPlayNow(item);
                          setIsOpen(false);
                          if (isPlaylistEntry) setQuery('');
                        }}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs transition-transform active:scale-95 whitespace-nowrap cursor-pointer"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        {isPlaylistEntry ? 'Putar Playlist' : 'Putar'}
                      </button>
                      <button
                        type="button"
                        aria-label={`Tambah ke antrean ${item.title} oleh ${item.artist}`}
                        onClick={() => {
                          onAddToQueue(item);
                          setIsOpen(false);
                          if (isPlaylistEntry) setQuery('');
                        }}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-full bg-[#181818] hover:bg-black text-white text-xs font-medium transition-colors whitespace-nowrap cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        Antrean
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const SearchDropdownBar = React.memo(SearchDropdownBarComponent);
