/**
 * Remote Control Audio State Tracker for Web Dashboard:
 * Web Dashboard berfungsi murni sebagai Remote Control untuk Bot Discord.
 * Seluruh output suara diputar langsung oleh Bot Discord di Voice Channel (bukan di browser).
 */

class DashboardAudioEngine {
  private volume = 0.8;
  private muted = true;

  public setVolume(volPercent: number) {
    this.volume = Math.max(0.01, Math.min(1, volPercent / 100));
  }

  public setMuted(muted: boolean) {
    this.muted = muted;
  }

  public isMuted(): boolean {
    return this.muted;
  }

  public forceStop() {
    // No browser audio output; audio plays in Discord Bot Voice Channel
  }

  public syncPlayback(_isPlaying: boolean, _streamUrl: string, _trackTitle: string) {
    // Web Dashboard acts strictly as Remote Control for the Discord Bot
  }
}

export const audioEngine = new DashboardAudioEngine();
