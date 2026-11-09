/**
 * Hybrid Audio Engine for the Web Dashboard:
 * - Plays real HTML5 audio stream if stream_url is available or resolved via /api/music/stream (e.g., iTunes M4A preview or Radio stream)
 * - Falls back seamlessly to a warm polyphonic Web Audio synthesizer chord progression when playing catalog tracks
 *   if external stream is unavailable, ensuring audible playback and volume control at all times.
 */

class DashboardAudioEngine {
  private audioEl: HTMLAudioElement | null = null;
  private ctx: AudioContext | null = null;
  private intervalId: number | null = null;
  private currentUrl = '';
  private currentTrackKey = '';
  private volume = 0.8;
  private muted = false; // Unmuted by default so playback is immediately audible
  private resolvedStreamCache = new Map<string, string>();
  private pendingResolveKey = '';
  private lastSyncArgs: {
    isPlaying: boolean;
    streamUrl: string;
    trackTitle: string;
    trackArtist: string;
    sourceUrl: string;
  } | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      const unlockAudio = () => {
        if (this.ctx && this.ctx.state === 'suspended') {
          this.ctx.resume().catch(() => {});
        }
        if (this.lastSyncArgs && this.lastSyncArgs.isPlaying && !this.muted) {
          if (this.audioEl && this.audioEl.paused && this.currentUrl) {
            this.audioEl.play().catch(() => {});
          }
        }
      };
      window.addEventListener('pointerdown', unlockAudio, { passive: true });
      window.addEventListener('keydown', unlockAudio, { passive: true });
    }
  }

  public setVolume(volPercent: number) {
    this.volume = Math.max(0.01, Math.min(1, volPercent / 100));
    if (this.audioEl) {
      this.audioEl.volume = this.muted ? 0 : this.volume;
    }
  }

  public setMuted(muted: boolean) {
    this.muted = muted;
    if (this.audioEl) {
      this.audioEl.volume = muted ? 0 : this.volume;
    }
    if (muted) {
      this.forceStop();
    } else if (this.lastSyncArgs && this.lastSyncArgs.isPlaying) {
      const { isPlaying, streamUrl, trackTitle, trackArtist, sourceUrl } = this.lastSyncArgs;
      this.syncPlayback(isPlaying, streamUrl, trackTitle, trackArtist, sourceUrl);
    }
  }

  public isMuted(): boolean {
    return this.muted;
  }

  public forceStop() {
    this.stopSynth();
    if (this.audioEl) {
      try {
        this.audioEl.pause();
        this.audioEl.removeAttribute('src');
        this.audioEl.load();
      } catch {
        // Ignore media element reset errors
      }
    }
    this.currentUrl = '';
    this.currentTrackKey = '';
  }

  public syncPlayback(
    isPlaying: boolean,
    streamUrl: string,
    trackTitle: string,
    trackArtist: string = '',
    sourceUrl: string = ''
  ) {
    this.lastSyncArgs = { isPlaying, streamUrl, trackTitle, trackArtist, sourceUrl };

    if (this.muted || !isPlaying || !trackTitle) {
      this.forceStop();
      return;
    }

    const cacheKey = `${trackTitle.toLowerCase()}::${trackArtist.toLowerCase()}`;
    const effectiveStreamUrl = streamUrl || this.resolvedStreamCache.get(cacheKey) || '';

    const nextKey = `${trackTitle}::${trackArtist}::${effectiveStreamUrl}`;
    const trackChanged = this.currentTrackKey !== nextKey;
    if (trackChanged) {
      this.stopSynth();
      if (this.audioEl && this.currentUrl !== effectiveStreamUrl) {
        try {
          this.audioEl.pause();
          this.audioEl.currentTime = 0;
        } catch {
          // Ignore reset error
        }
      }
      this.currentTrackKey = nextKey;
    }

    const isDirectBrowserPlayable =
      Boolean(effectiveStreamUrl) &&
      effectiveStreamUrl.startsWith('http') &&
      !effectiveStreamUrl.includes('googlevideo.com');

    if (isDirectBrowserPlayable) {
      this.stopSynth();
      if (!this.audioEl) {
        this.audioEl = new Audio();
        this.audioEl.crossOrigin = 'anonymous';
        this.audioEl.loop = true;
      }
      if (this.currentUrl !== effectiveStreamUrl) {
        this.currentUrl = effectiveStreamUrl;
        this.audioEl.src = effectiveStreamUrl;
      }
      this.audioEl.volume = this.volume;
      if (this.audioEl.paused) {
        this.audioEl.play().catch(() => {
          this.startAmbientChordLoop(trackTitle);
        });
      }
      return;
    }

    // Resolve real playable audio preview stream asynchronously if not cached yet
    if (!this.resolvedStreamCache.has(cacheKey) && this.pendingResolveKey !== cacheKey) {
      this.pendingResolveKey = cacheKey;
      const params = new URLSearchParams({
        title: trackTitle,
        artist: trackArtist,
        source_url: sourceUrl,
      });
      fetch(`/api/music/stream?${params.toString()}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          const resolvedUrl = String(data?.stream_url || '').trim();
          this.resolvedStreamCache.set(cacheKey, resolvedUrl);
          if (
            resolvedUrl &&
            this.lastSyncArgs &&
            this.lastSyncArgs.isPlaying &&
            this.lastSyncArgs.trackTitle === trackTitle &&
            !this.muted
          ) {
            this.syncPlayback(true, resolvedUrl, trackTitle, trackArtist, sourceUrl);
          }
        })
        .catch(() => {
          this.resolvedStreamCache.set(cacheKey, '');
        })
        .finally(() => {
          if (this.pendingResolveKey === cacheKey) {
            this.pendingResolveKey = '';
          }
        });
    }

    if (this.audioEl) {
      try {
        this.audioEl.pause();
        this.audioEl.removeAttribute('src');
        this.audioEl.load();
      } catch {
        // Ignore
      }
      this.currentUrl = '';
    }
    this.startAmbientChordLoop(trackTitle);
  }

  private startAmbientChordLoop(seed: string) {
    if (this.intervalId !== null) return;
    try {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!this.ctx) {
        this.ctx = new AudioCtx();
      }
      if (this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {});
      }

      const chords = [
        [261.63, 329.63, 392.0], // C major
        [220.0, 261.63, 329.63], // A minor
        [174.61, 220.0, 261.63], // F major
        [196.0, 246.94, 293.66], // G major
      ];
      let step = seed.length % chords.length;

      const playPluck = () => {
        if (!this.ctx || this.muted) return;
        if (this.ctx.state === 'suspended') {
          this.ctx.resume().catch(() => {});
        }
        const now = this.ctx.currentTime;
        const notes = chords[step % chords.length];
        step += 1;

        notes.forEach((freq, idx) => {
          if (!this.ctx) return;
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = idx === 0 ? 'triangle' : 'sine';
          osc.frequency.setValueAtTime(freq, now);

          const peak = Math.max(0.008, this.volume * 0.05);
          gain.gain.setValueAtTime(0.0001, now);
          gain.gain.exponentialRampToValueAtTime(peak, now + 0.15);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.8);

          osc.connect(gain);
          gain.connect(this.ctx.destination);
          osc.start(now);
          osc.stop(now + 1.85);
        });
      };

      playPluck();
      this.intervalId = window.setInterval(playPluck, 2000);
    } catch {
      // Ignore Web Audio restriction if no user gesture yet
    }
  }

  private stopSynth() {
    if (this.intervalId !== null) {
      window.clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }
}

export const audioEngine = new DashboardAudioEngine();