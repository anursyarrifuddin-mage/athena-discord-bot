/**
 * Web Browser Audio Disabled by Design:
 * Athenaa Web Player acts strictly as a remote control dashboard for the Discord Voice Bot.
 * All audio playback happens exclusively inside the Discord Voice Channel via the Discord Bot.
 */

class DashboardAudioEngine {
  public setVolume(_volPercent: number) {}
  public setMuted(_muted: boolean) {}
  public isMuted(): boolean {
    return true;
  }
  public forceStop() {}
  public syncPlayback(
    _isPlaying: boolean,
    _streamUrl: string,
    _trackTitle: string,
    _trackArtist: string = '',
    _sourceUrl: string = ''
  ) {}
}

export const audioEngine = new DashboardAudioEngine();
