---
name: athena-no-audio-fix
description: "Root cause and fixes for Athena Discord bot \"no audio output\" issue on Pterodactyl"
metadata:
  node_type: memory
  type: project
  originSessionId: 31033948-9b35-4cba-8948-4e75ae87a21b
  modified: 2026-11-09T17:09:15.579Z
---

## Athena Discord Bot - No Audio Output Issue (Pterodactyl/Python 3.12)

**Status:** FIXES APPLIED - Awaiting deployment verification
**Date:** 2026-11-10
**Environment:** Pterodactyl panel, Python 3.12.16, discord.py 2.4+, davey for voice encryption

---

### Problem Summary
Bot connects to Discord voice channel successfully, shows as "playing" (vc.is_playing()=True), but **no audio output** on Discord. Web player is control-only; audio output is Discord voice channel only.

---

### Root Cause Identified

**Primary Issue: Malformed ffmpeg `-headers` option with CRLF breaking shlex.split()**

Location: `athenaa/app/bot/client.py` lines ~1696-1702

**Broken code:**
```python
cookie_header = f"Cookie: {cookie_val}\r\n"  # Literal CRLF characters
before_opts += f'-headers {_ffmpeg_escape(cookie_header)} '
```

**Why it fails:** 
- discord.py uses `shlex.split()` to parse `before_options` 
- CRLF (`\r\n`) inside quoted argument breaks shlex parsing
- ffmpeg receives malformed arguments → cookies not sent to YouTube
- HLS segment requests to googlevideo.com return HTTP 403 (unauthorized)
- FFmpeg gets 0-byte segments → silence, but vc.is_playing()=True

**Fix applied:** Use correct `-cookies` option instead:
```python
before_opts += f'-cookies {_ffmpeg_escape(cookie_val)} '
# Format: "name1=value1; name2=value2; ..."
```

---

### All Fixes Applied (2026-11-09 to 2026-11-10)

| File | Change | Purpose |
|------|--------|---------|
| `athenaa/app/bot/client.py` | Fixed `-headers` → `-cookies` for HLS cookie auth | **Primary fix** - enables YouTube HLS segment auth |
| `athenaa/app/bot/client.py` | Enhanced `_ensure_bot_unmuted_in_vc()` with logging | Auto-unmute + log if bot is self_muted/server_muted |
| `athenaa/app/bot/client.py` | Added pre-playback debug logging | Logs VC state, bot voice state, stream type, ffmpeg args |
| `athenaa/app/bot/client.py` | Added playback verification (await + vc.is_playing() check) | Confirms audio actually started, logs failure if not |
| `requirements.txt` (root) | Added `davey>=0.1.0; python_version >= "3.10"` | Voice encryption dependency for Python 3.12+ |
| `athenaa/requirements.txt` | Already had davey | Confirmed |
| `constants.yaml` (both) | HLS format priority: `bestaudio[protocol^=m3u8]/...` | Prefers stable HLS manifests over direct URLs |

---

### Debug Logging Added (Will Appear After Redeploy)

Look for these log entries to diagnose:

```
INFO  Starting playback for guild XXX: track=..., stream_type=HLS/m3u8, url_prefix=https://...
DEBUG Full ffmpeg before_options: -user_agent "Mozilla/..." -cookies "VISITOR_INFO1_LIVE=...; ..." -reconnect 1...
INFO  VoiceClient state for guild XXX: connected=True, channel=General, ws_state=<WebSocket...>
INFO  Bot voice state: self_mute=False, mute=False, self_deaf=True, deaf=False, channel=General
INFO  Playback confirmed: vc.is_playing()=True for guild XXX
```

If playback fails:
```
ERROR Playback FAILED: vc.is_playing()=False immediately after play() for guild XXX
```

If bot was muted:
```
WARNING Bot muted detected in guild XXX: self_mute=True, server_mute=False, unmuting...
```

---

### Architecture Notes

**Audio Pipeline:**
1. `music_service.py:extract_playable_stream_ytdlp()` → extracts stream URL + cookies + user_agent via yt-dlp (tv_embedded player client)
2. `client.py:start_or_sync_voice_playback()` → builds ffmpeg `before_options` with cookies
3. `discord.FFmpegPCMAudio()` / `FFmpegOpusAudio()` → plays via discord.py voice client
4. `PCMVolumeTransformer` → applies volume (default 80%)

**Key Constants:**
- `DISCORD_OPTIMAL_YTDLP_FORMAT` (music_service.py:2292) - HLS-first format string
- `YTDLP_EXTRACTOR_ARGS` (music_service.py:2302) - `youtube:player_client=tv_embedded;skip=translated_subs`
- `DEFAULT_STREAM_USER_AGENT` (music_service.py:2283) - Chrome 124 UA string

---

### Remaining Verification Needed

After deploying to Pterodactyl and testing:

1. ✅ Check logs for "Playback confirmed: vc.is_playing()=True"
2. ✅ Verify audio audible in Discord voice channel
3. ✅ Confirm no "Bot muted detected" warnings (or that they auto-resolve)
4. ✅ Test multiple tracks, seek, pause/resume, queue

---

### If Issue Persists After Deployment

**Check these in order:**

1. **Logs show "Playback FAILED"** → ffmpeg can't read stream (check network/cookies)
2. **Logs show "Bot muted detected" repeatedly** → Discord permissions issue (bot lacks "Mute Members" or "Deafen Members" perms)
3. **vc.is_playing()=True but no audio** → Opus library issue or Discord voice connection issue
   - Check "Library Opus untuk Discord Voice berhasil dimuat dari: libopus.so.0" in startup logs
   - Verify davey package installed: `pip show davey`
4. **HLS cookies empty in logs** → yt-dlp not extracting cookies (check extractor_args)

---

### Related Files for Deep Debugging

- `athenaa/app/bot/client.py` - Main playback logic (lines 1670-1850)
- `athenaa/app/services/music_service.py` - Stream extraction (lines 2383-2525)
- `athenaa/app/config/config_data/constants.yaml` - Format config (line 29)
- `athenaa/app/config_data/constants.yaml` - Duplicate config (line 29)

---

### Previous Working Code Reference

The user mentioned "old code works but new code doesn't". Key differences to investigate if needed:
- Old code may have used direct googlevideo.com URLs (shorter-lived signatures)
- Old code may not have used HLS/m3u8 streams
- Old code may have used different yt-dlp player client (android/web vs tv_embedded)
- Old code may have handled cookies differently

Current implementation uses **tv_embedded + HLS + cookies** which is the modern, stable approach - but requires correct ffmpeg cookie passing (the bug fixed above).