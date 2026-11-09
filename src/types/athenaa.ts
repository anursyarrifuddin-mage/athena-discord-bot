export interface TrackItem {
  item_id?: string;
  guild_id?: string;
  position?: number;
  title: string;
  artist: string;
  album: string;
  duration_sec: number;
  source_type: string;
  source_url: string;
  stream_url: string;
  thumbnail_url: string;
  requester_id?: string;
  requester_name?: string;
  added_at?: string;
}

export interface RadioStation {
  id: string;
  name: string;
  artist: string;
  stream_url: string;
}

export interface GuildMusicState {
  guild_id: string;
  voice_channel_id: string;
  voice_channel_name: string;
  host_user_id: string;
  host_username: string;
  current_track: TrackItem | null;
  queue: TrackItem[];
  is_playing: boolean;
  is_paused: boolean;
  position_sec: number;
  volume: number;
  loop_mode: 'off' | 'one' | 'queue';
  autoplay: boolean;
  mode_247: boolean;
  active_radio_name: string;
  radios?: RadioStation[];
}

export interface SyncedLyricLine {
  timeSec: number;
  text: string;
}

export interface LyricsResponse {
  status: 'synced' | 'plain' | 'not_found' | 'rate_limited' | 'error';
  track_name: string;
  artist_name: string;
  synced_lines: SyncedLyricLine[];
  plain_lyrics: string;
  source?: string;
  message?: string;
}

export interface AcademicTask {
  task_id: string;
  guild_id: string;
  external_uid: string;
  course_name: string;
  title: string;
  description: string;
  source_type: 'manual' | 'moodle_ics' | 'google_classroom';
  deadline_iso: string;
  timezone: string;
  source_url: string;
  is_completed: number;
  completed_by: string;
  completed_at: string;
  created_by: string;
  last_synced_at: string;
  updated_at: string;
}

export interface TaskAttachment {
  attachment_id: string;
  task_id: string;
  guild_id: string;
  original_filename: string;
  stored_filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: string;
  created_at: string;
}

export interface ReminderDelivery {
  delivery_id: string;
  task_id: string;
  guild_id: string;
  stage: string;
  delivered_at: string;
  channel_id: string;
  status: string;
}

export interface LevelProfile {
  rank: number;
  user_id: string;
  username: string;
  display_name: string;
  level: number;
  current_exp: number;
  max_exp: number;
  total_messages: number;
  last_exp_at: string;
}

export interface AfkEntry {
  guild_id: string;
  user_id: string;
  username: string;
  reason: string;
  started_at: string;
}

export interface GuildSettings {
  guild_id: string;
  guild_name: string;
  music_channel_id: string;
  task_channel_id: string;
  dj_role_id: string;
  moodle_ics_url_encrypted: string;
  moodle_last_sync: string;
  classroom_connected: number;
  classroom_last_sync: string;
  reminder_days_before: number;
  timezone: string;
  idle_timeout_seconds: number;
  mode_247: number;
  autoplay: number;
  exp_cooldown_seconds: number;
  exp_per_message: number;
  max_attachment_mb: number;
  updated_at: string;
}

export type ServerRoleType = 'admin' | 'dj' | 'member';

export interface ActiveActorProfile {
  id: string;
  name: string;
  discordTag?: string;
  avatarUrl?: string;
  role?: ServerRoleType;
  roleLabel: string;
  roles: string[];
  hasDjRole?: boolean;
  isAdmin: boolean;
  isOwner: boolean;
  guildRoles?: Record<string, ServerRoleType>;
}



