/**
 * Hybrid Audio Engine for the Web Dashboard:
 * - Plays real HTML5 audio stream if stream_url is available and reachable (e.g., iTunes M4A preview or Radio stream)
 * - Falls back seamlessly to a warm polyphonic Web Audio synthesizer chord progression when playing catalog tracks
 *   or if browser autoplay/network blocks external audio, ensuring audible playback and volume control at all times.
 */

class DashboardAudioEngine {
  private audioEl: HTMLAudioElement | null = null;
  private ctx: AudioContext | null = null;
  private intervalId: number | null = null;
  private currentUrl = '';
  private currentTrackKey = '';
  private volume = 0.8;
  private muted = true; // Muted by default until user explicitly unmutes browser audio monitor

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

  public syncPlayback(isPlaying: boolean, streamUrl: string, trackTitle: string) {
    if (this.muted || !isPlaying || !trackTitle) {
      this.forceStop();
      return;
    }

    const nextKey = `${trackTitle}::${streamUrl}`;
    const trackChanged = this.currentTrackKey !== nextKey;
    if (trackChanged) {
      this.stopSynth();
      if (this.audioEl && this.currentUrl !== streamUrl) {
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
      Boolean(streamUrl) &&
      streamUrl.startsWith('http') &&
      !streamUrl.includes('googlevideo.com');

    if (isDirectBrowserPlayable) {
      this.stopSynth();
      if (!this.audioEl) {
        this.audioEl = new Audio();
      }
      if (this.currentUrl !== streamUrl) {
        this.currentUrl = streamUrl;
        this.audioEl.src = streamUrl;
      }
      this.audioEl.volume = this.volume;
      if (this.audioEl.paused) {
        this.audioEl.play().catch(() => {
          this.startAmbientChordLoop(trackTitle);
        });
      }
    } else {
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
  }

  private startAmbientChordLoop(seed: string) {
    if (this.intervalId !== null) return;
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!this.ctx) {
        this.ctx = new AudioCtx();
      }
      if (this.ctx.state === 'suspended') {
        this.ctx.resume();
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
        const now = this.ctx.currentTime;
        const notes = chords[step % chords.length];
        step += 1;

        notes.forEach((freq, idx) => {
          if (!this.ctx) return;
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = idx === 0 ? 'triangle' : 'sine';
          osc.frequency.setValueAtTime(freq, now);

          const peak = Math.max(0.005, this.volume * 0.04);
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
