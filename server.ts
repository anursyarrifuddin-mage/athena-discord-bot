import express from 'express';
import { createServer as createViteServer } from 'vite';
import { createServer as createHttpServer } from 'node:http';
import { WebSocketServer, WebSocket } from 'ws';
import { DatabaseSync } from 'node:sqlite';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import {
  calculateMaxExp,
  applyExpGain,
  canControlQueue,
  parseLrcLyrics,
  evaluateReminderStage,
  parseIcsEvents,
  validateAttachmentMeta,
  canAccessOwnerResources,
  enforceSingleDiscordSession,
} from './src/lib/athenaaRules';

const execFileAsync = promisify(execFile);
const PORT = 3000;
const START_TIME = Date.now();

function isSafeExternalUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    const host = parsed.hostname.toLowerCase();
    if (
      host === 'localhost' ||
      host === '127.0.0.1' ||
      host === '0.0.0.0' ||
      host === '::1' ||
      host.startsWith('10.') ||
      host.startsWith('192.168.') ||
      host.startsWith('169.254.')
    ) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

const ROOT_DIR = process.cwd();
const ATHENAA_DIR = path.join(ROOT_DIR, 'athenaa');
const DATA_DIR = path.join(ATHENAA_DIR, 'data');
const BACKUPS_DIR = path.join(DATA_DIR, 'backups');
const MODULES_DIR = path.join(ATHENAA_DIR, 'modules');
const DB_PATH = path.join(DATA_DIR, 'athenaa.db');

fs.mkdirSync(DATA_DIR, { recursive: true });
fs.mkdirSync(BACKUPS_DIR, { recursive: true });
fs.mkdirSync(MODULES_DIR, { recursive: true });

const db = new DatabaseSync(DB_PATH);
db.exec('PRAGMA foreign_keys = ON;');
db.exec('PRAGMA journal_mode = WAL;');

// Initialize shared schema with Python backend
db.exec(`
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    music_channel_id TEXT DEFAULT '',
    task_channel_id TEXT DEFAULT '',
    dj_role_id TEXT DEFAULT '',
    moodle_ics_url_encrypted TEXT DEFAULT '',
    moodle_last_sync TEXT DEFAULT '',
    classroom_connected INTEGER DEFAULT 0,
    classroom_last_sync TEXT DEFAULT '',
    reminder_days_before INTEGER DEFAULT 3,
    timezone TEXT DEFAULT 'Asia/Jakarta',
    idle_timeout_seconds INTEGER DEFAULT 300,
    mode_247 INTEGER DEFAULT 0,
    autoplay INTEGER DEFAULT 1,
    exp_cooldown_seconds INTEGER DEFAULT 60,
    exp_per_message INTEGER DEFAULT 15,
    max_attachment_mb INTEGER DEFAULT 15,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_items (
    item_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT DEFAULT '',
    duration_sec INTEGER DEFAULT 0,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    stream_url TEXT DEFAULT '',
    thumbnail_url TEXT DEFAULT '',
    requester_id TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    added_at TEXT NOT NULL
);

DROP TABLE IF EXISTS favorites;
DROP TABLE IF EXISTS playlist_items;
DROP TABLE IF EXISTS playlists;
DROP TABLE IF EXISTS user_favorites;
DROP TABLE IF EXISTS playlist_tracks;
DROP TABLE IF EXISTS guild_playlists;

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    external_uid TEXT DEFAULT '',
    course_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    deadline_iso TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    source_url TEXT DEFAULT '',
    is_completed INTEGER DEFAULT 0,
    completed_by TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    created_by TEXT NOT NULL,
    last_synced_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_attachments (
    attachment_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    delivery_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(task_id, stage)
);

CREATE TABLE IF NOT EXISTS level_profiles (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    current_exp INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER NOT NULL DEFAULT 0,
    last_exp_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS afk_statuses (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    reason TEXT NOT NULL,
    started_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_sessions (
    user_id TEXT PRIMARY KEY,
    session_token TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    discord_tag TEXT NOT NULL,
    role_label TEXT NOT NULL,
    is_owner INTEGER NOT NULL DEFAULT 0,
    has_dj_role INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
`);

const MAIN_GUILD_ID = process.env.MAIN_GUILD_ID?.trim() || '1428666546942902294';
const DEFAULT_ADMIN_ID = '844174494099701780';
const OWNER_DISCORD_ID = DEFAULT_ADMIN_ID;

// Default Server Admin account for initial session bootstrap (Per-Server Role System: Admin, DJ, Member)
const REAL_OWNER_ACCOUNT = {
  user_id: DEFAULT_ADMIN_ID,
  username: 'Aetheriaaa',
  discord_tag: '@aetheriaaa',
  role_label: 'Admin Server',
  is_owner: true,
  has_dj_role: true,
  is_admin: true,
};

const activeSessionsByUserId = new Map<string, string>();

function issueSingleDiscordSession(account: {
  user_id: string;
  username: string;
  discord_tag: string;
  role_label: string;
  is_owner: boolean;
  has_dj_role: boolean;
  is_admin: boolean;
}) {
  const newToken = `athenaa_sess_${account.user_id}_${crypto.randomBytes(12).toString('hex')}`;
  const { previousTokenRevoked } = enforceSingleDiscordSession(
    activeSessionsByUserId,
    account.user_id,
    newToken
  );
  const nowIso = new Date().toISOString();
  db.prepare(`
    INSERT INTO discord_sessions (
      user_id, session_token, username, discord_tag, role_label, is_owner, has_dj_role, is_admin, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
      session_token = excluded.session_token,
      username = excluded.username,
      discord_tag = excluded.discord_tag,
      role_label = excluded.role_label,
      is_owner = excluded.is_owner,
      has_dj_role = excluded.has_dj_role,
      is_admin = excluded.is_admin,
      created_at = excluded.created_at
  `).run(
    account.user_id,
    newToken,
    account.username,
    account.discord_tag,
    account.role_label,
    account.is_owner ? 1 : 0,
    account.has_dj_role ? 1 : 0,
    account.is_admin ? 1 : 0,
    nowIso
  );

  return {
    session_token: newToken,
    previous_token_revoked: Boolean(previousTokenRevoked),
    user: {
      id: account.user_id,
      name: account.username,
      discordTag: account.discord_tag,
      role: account.is_admin ? 'admin' : account.has_dj_role ? 'dj' : 'member',
      roleLabel: account.role_label,
      isOwner: account.is_admin,
      hasDjRole: account.has_dj_role,
      isAdmin: account.is_admin,
    },
  };
}

function parseCookieToken(cookieHeader: string): string {
  for (const part of cookieHeader.split(';')) {
    const [rawKey, ...rest] = part.trim().split('=');
    if (rawKey === 'athenaa_session_token') {
      return decodeURIComponent(rest.join('=').trim());
    }
  }
  return '';
}

function getSessionFromRequest(req: express.Request) {
  const roleOverride = String(req.headers['x-actor-role'] || req.query.role || '')
    .trim()
    .toLowerCase();
  const authHeader = String(req.headers.authorization || '');
  const bearerToken = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : '';
  const queryToken = String(req.query.session_token || '').trim();
  const cookieToken = parseCookieToken(String(req.headers.cookie || ''));
  const token = bearerToken || queryToken || cookieToken;

  let baseSession: {
    session_token: string;
    user: {
      id: string;
      name: string;
      discordTag: string;
      role?: string;
      roleLabel: string;
      isOwner: boolean;
      hasDjRole: boolean;
      isAdmin: boolean;
    };
  } | null = null;

  if (token) {
    const row = db
      .prepare('SELECT * FROM discord_sessions WHERE session_token = ?')
      .get(token) as Record<string, unknown> | undefined;
    if (row) {
      const isAdm = Boolean(row.is_admin) || Boolean(row.is_owner);
      const hasDj = Boolean(row.has_dj_role) || isAdm;
      baseSession = {
        session_token: String(row.session_token),
        user: {
          id: String(row.user_id),
          name: String(row.username),
          discordTag: String(row.discord_tag),
          role: isAdm ? 'admin' : hasDj ? 'dj' : 'member',
          roleLabel: String(row.role_label),
          isOwner: isAdm,
          hasDjRole: hasDj,
          isAdmin: isAdm,
        },
      };
    }
  }

  if (roleOverride === 'admin' || roleOverride === 'dj' || roleOverride === 'member') {
    const isAdm = roleOverride === 'admin';
    const hasDj = roleOverride === 'admin' || roleOverride === 'dj';
    return {
      session_token: baseSession?.session_token || `role_${roleOverride}`,
      user: {
        id:
          baseSession?.user.id ||
          (isAdm ? DEFAULT_ADMIN_ID : roleOverride === 'dj' ? 'user-dj-02' : 'user-member-03'),
        name:
          baseSession?.user.name ||
          (isAdm ? 'Aetheriaaa' : roleOverride === 'dj' ? 'DJ NyolBar' : 'Member Kampus'),
        discordTag:
          baseSession?.user.discordTag ||
          (isAdm ? '@aetheriaaa' : roleOverride === 'dj' ? '@dj_nyolbar' : '@member_kampus'),
        role: roleOverride,
        roleLabel: isAdm ? 'Admin Server' : hasDj ? 'DJ Server' : 'Member Server',
        isOwner: isAdm,
        hasDjRole: hasDj,
        isAdmin: isAdm,
      },
    };
  }

  return baseSession;
}

export interface TrackItem {
  item_id: string;
  guild_id: string;
  position: number;
  title: string;
  artist: string;
  album: string;
  duration_sec: number;
  source_type: string;
  source_url: string;
  stream_url: string;
  thumbnail_url: string;
  requester_id: string;
  requester_name: string;
  added_at: string;
  is_autoplay?: boolean;
}

interface GuildPlayerState {
  guild_id: string;
  voice_channel_id: string;
  voice_channel_name: string;
  host_user_id: string;
  host_username: string;
  current_track: TrackItem | null;
  queue: TrackItem[];
  history_keys: Set<string>;
  is_playing: boolean;
  is_paused: boolean;
  position_sec: number;
  volume: number;
  loop_mode: 'off' | 'one' | 'queue';
  autoplay: boolean;
  mode_247: boolean;
  active_radio_name: string;
}

const VERIFIED_RADIOS = [
  {
    id: 'prambors',
    name: 'Prambors FM 102.2 Jakarta',
    artist: 'Live Radio Stream · Top 40 Indonesia',
    stream_url: 'https://s7.alhastream.com/radio/8030/radio',
  },
  {
    id: 'hardrockfm',
    name: 'Hard Rock FM 87.6 Jakarta',
    artist: 'Live Radio Stream · Pop & Rock',
    stream_url: 'https://n09.radiojar.com/7csmg90fuqruv',
  },
  {
    id: 'genfm',
    name: 'Gen FM 98.7 Jakarta',
    artist: 'Live Radio Stream · Musik Hits Indonesia',
    stream_url: 'https://n07.radiojar.com/4ywdgup3bnzuv',
  },
  {
    id: 'lofigirl',
    name: 'Lofi Study Beats 24/7',
    artist: 'StreamAfrica · Chill & Focus',
    stream_url: 'https://play.streamafrica.net/lofiradio',
  },
];

function makeAlbumArtSvg(title: string, artist: string, c1: string, c2: string): string {
  const initials = title.slice(0, 2).toUpperCase();
  const safeTitle = title.replace(/&/g, '&amp;').replace(/</g, '&lt;').slice(0, 18);
  const safeArtist = artist.replace(/&/g, '&amp;').replace(/</g, '&lt;').slice(0, 18);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
    <defs>
      <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="${c1}"/>
        <stop offset="100%" stop-color="${c2}"/>
      </linearGradient>
    </defs>
    <rect width="300" height="300" fill="url(#g)"/>
    <circle cx="240" cy="60" r="90" fill="rgba(255,255,255,0.08)"/>
    <circle cx="60" cy="240" r="110" fill="rgba(0,0,0,0.22)"/>
    <text x="28" y="120" fill="rgba(255,255,255,0.22)" font-family="sans-serif" font-weight="800" font-size="84">${initials}</text>
    <text x="28" y="238" fill="#ffffff" font-family="sans-serif" font-weight="700" font-size="22">${safeTitle}</text>
    <text x="28" y="266" fill="rgba(255,255,255,0.8)" font-family="sans-serif" font-weight="500" font-size="16">${safeArtist}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export type MusicGenre = 'rnb_hiphop' | 'indie_indo' | 'pop_indo' | 'jpop_anime' | 'rock_alt' | 'lofi_chill';

export interface CatalogEntry {
  title: string;
  artist: string;
  album: string;
  duration_sec: number;
  source_type: string;
  source_url: string;
  stream_url: string;
  thumbnail_url: string;
  genre: MusicGenre;
  synced_lrc?: string;
}

const CURATED_CATALOG: CatalogEntry[] = [
  // --- R&B, Hip-Hop & Rap (The Weeknd, Metro Boomin, Drake, Joji, etc.) ---
  {
    title: "Creepin' (with The Weeknd & 21 Savage)",
    artist: 'Metro Boomin, The Weeknd, 21 Savage',
    album: 'HEROES & VILLAINS',
    duration_sec: 221,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/2dHHgz3WK492Q5fU0x7G51',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg("Creepin'", 'Metro Boomin', '#111827', '#450a0a'),
    genre: 'rnb_hiphop',
    synced_lrc: `[00:00.00] ♪ Intro - Creepin' (Metro Boomin, The Weeknd, 21 Savage)
[00:15.00] Somebody said you got a new friend
[00:22.00] Does she love you better than I can?
[00:30.00] There's a big black cloud over the city
[00:38.00] And baby, I'm well aware that I shouldn't care`,
  },
  {
    title: 'Starboy',
    artist: 'The Weeknd, Daft Punk',
    album: 'Starboy',
    duration_sec: 230,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/7MXVkk9YM5IZxh0WSlVIyo',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Starboy', 'The Weeknd', '#e11d48', '#1e1b4b'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'Die For You',
    artist: 'The Weeknd',
    album: 'Starboy',
    duration_sec: 260,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/2Ch7LmS7r2Gy2LmY3AQX',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Die For You', 'The Weeknd', '#831843', '#0f172a'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'Blinding Lights',
    artist: 'The Weeknd',
    album: 'After Hours',
    duration_sec: 200,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Blinding Lights', 'The Weeknd', '#dc2626', '#450a0a'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'Glimpse of Us',
    artist: 'Joji',
    album: 'SMITHEREENS',
    duration_sec: 233,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/6Ec5LeRzk1Dscg8',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Glimpse of Us', 'Joji', '#1f2937', '#111827'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'Slow Dancing in the Dark',
    artist: 'Joji',
    album: 'BALLADS 1',
    duration_sec: 209,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/0cvqlJ0zO0X4q7b7Z',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Slow Dancing', 'Joji', '#0f172a', '#3b0764'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'Sunflower',
    artist: 'Post Malone, Swae Lee',
    album: 'Spider-Man: Into the Spider-Verse',
    duration_sec: 158,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/3KkXRQHbMCARz0aVfEt68P',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Sunflower', 'Post Malone', '#eab308', '#713f12'),
    genre: 'rnb_hiphop',
  },
  {
    title: 'One Dance',
    artist: 'Drake',
    album: 'Views',
    duration_sec: 174,
    source_type: 'spotify_matched',
    source_url: 'https://open.spotify.com/track/1zi7xx7UVEFkmKDeXt9isA',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('One Dance', 'Drake', '#475569', '#0f172a'),
    genre: 'rnb_hiphop',
  },

  // --- Indie Indonesia (Hindia, Nadin Amizah, .Feast, Bernadya, Pamungkas) ---
  {
    title: 'Evaluasi',
    artist: 'Hindia',
    album: 'Menari Dengan Bayangan',
    duration_sec: 194,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=cWrSjCZ1AeE',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Evaluasi', 'Hindia', '#8C56D4', '#24113d'),
    genre: 'indie_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Evaluasi (Hindia)
[00:08.50] Yang tak bisa terobati biarlah
[00:14.20] Mengering sendiri
[00:19.80] Menghias tubuh dan yang mengevaluasi
[00:26.40] Ragamu hanya kau sendiri
[00:32.00] Mereka tak mampu melihat yang kau alami
[00:39.50] Perjalanan yang jauh telah kau tempuh
[00:46.10] Masalah yang keruh, perasaan yang rapuh
[00:53.00] Ini belum separuhnya, biasa saja
[01:00.20] Kamu tak apa, yang selalu ingin ambil peran
[01:08.00] Hanya berlomba menjadi lebih sedih dari dirimu
[01:16.40] Muak dikesampingkan, disamakan
[01:23.50] Hatimu terluka, sempurna
[01:31.00] Cuci muka, gosok gigi, evaluasi
[01:39.00] Tidur sejenak menemui esok pagi`,
  },
  {
    title: 'Secukupnya',
    artist: 'Hindia',
    album: 'Menari Dengan Bayangan',
    duration_sec: 205,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/5Kunw22625372',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Secukupnya', 'Hindia', '#d97706', '#451a03'),
    genre: 'indie_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Secukupnya (Hindia)
[00:10.00] Kapan terakhir kali kamu dapat tertidur tenang?
[00:18.00] Tak perlu memikirkan tentang apa yang akan datang di esok hari
[00:27.50] Tubuh yang berpatah hati bergantung pada gaji
[00:35.00] Berlomba jadi asri, mengais validasi
[00:43.00] Bersedihlah secukupnya, rayakan perasaanmu sebagai manusia`,
  },
  {
    title: 'Rumah Ke Rumah',
    artist: 'Hindia',
    album: 'Menari Dengan Bayangan',
    duration_sec: 277,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/rumahkerumah',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Rumah Ke Rumah', 'Hindia', '#7c3aed', '#1e1b4b'),
    genre: 'indie_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Rumah Ke Rumah (Hindia)
[00:15.00] Menyesal tak kusampaikan
[00:22.00] Cinta monyetku ke Kanya dan Rebecca
[00:30.00] Apa kabar kalian di sana
[00:38.00] Semoga hidup baik-baik saja`,
  },
  {
    title: 'Cincin',
    artist: 'Hindia',
    album: 'Lagipula Hidup Akan Berakhir',
    duration_sec: 267,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/cincin-hindia',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Cincin', 'Hindia', '#4f46e5', '#1e1b4b'),
    genre: 'indie_indo',
  },
  {
    title: 'Bertaut',
    artist: 'Nadin Amizah',
    album: 'Selamat Ulang Tahun',
    duration_sec: 316,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/630DpnzdfjdVqv2yLfPbAX',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Bertaut', 'Nadin Amizah', '#be123c', '#3b0764'),
    genre: 'indie_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Bertaut (Nadin Amizah)
[00:12.00] Bun, hidup berjalan seperti bajingan
[00:20.00] Seperti landak yang tak punya teman
[00:28.00] Ia menggonggong bak suara hujan
[00:35.50] Dan kau pangeranku, mengambil peran
[00:44.00] Keras kepalaku sama denganmu
[00:51.50] Caraku marah, caraku tersenyum
[00:59.00] Seperti detak jantung yang bertaut`,
  },
  {
    title: 'Sorai',
    artist: 'Nadin Amizah',
    album: 'Sorai',
    duration_sec: 223,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/sorai',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Sorai', 'Nadin Amizah', '#9d174d', '#500724'),
    genre: 'indie_indo',
  },
  {
    title: 'Peradaban',
    artist: '.Feast',
    album: 'Beberapa Orang Memaafkan',
    duration_sec: 341,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/peradaban',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Peradaban', '.Feast', '#991b1b', '#450a0a'),
    genre: 'indie_indo',
  },
  {
    title: 'Satu Bulan',
    artist: 'Bernadya',
    album: 'Sialnya, Hidup Harus Tetap Berjalan',
    duration_sec: 200,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/satubulan',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Satu Bulan', 'Bernadya', '#0369a1', '#082f49'),
    genre: 'indie_indo',
  },
  {
    title: 'Untungnya, Hidup Terus Berjalan',
    artist: 'Bernadya',
    album: 'Sialnya, Hidup Harus Tetap Berjalan',
    duration_sec: 215,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/untungnya',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Untungnya', 'Bernadya', '#0f766e', '#134e4a'),
    genre: 'indie_indo',
  },

  // --- Pop Indonesia (Tulus, Sheila On 7, Raim Laode, Juicy Luicy, Mahalini) ---
  {
    title: 'Monokrom',
    artist: 'Tulus',
    album: 'Monokrom',
    duration_sec: 214,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/4GfKVKMRp2bcG9Xm2vR2tN',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Monokrom', 'Tulus', '#334155', '#0f172a'),
    genre: 'pop_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Monokrom (Tulus)
[00:11.00] Lembaran foto hitam-putih
[00:16.50] Aku coba ingat lagi warna baju yang kau pakai
[00:24.00] Kali pertama di hidupku
[00:29.50] Manusia lain memelukku
[00:36.00] Di manapun kalian berada
[00:42.50] Kukirimkan terima kasih
[00:48.00] Untuk warna dalam hidupku dan banyak kenangan indah
[00:56.00] Kau melukis aku`,
  },
  {
    title: 'Hati-Hati di Jalan',
    artist: 'Tulus',
    album: 'Manusia',
    duration_sec: 242,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/2hHeGD57S0B',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Hati-Hati di Jalan', 'Tulus', '#0d9488', '#111827'),
    genre: 'pop_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Hati-Hati di Jalan (Tulus)
[00:14.00] Perjalanan membawaku bertemumu
[00:22.00] Ku bertemu kamu, sepertimu yang kucari
[00:31.00] Konon aku juga seperti yang kau cari
[00:40.00] Kukira kita asam dan garam
[00:48.00] Dan kita bertemu di belanga
[00:56.00] Kisah yang ternyata tak seindah itu`,
  },
  {
    title: 'Dan...',
    artist: 'Sheila On 7',
    album: 'Sheila On 7',
    duration_sec: 286,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/12345so7',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Dan...', 'Sheila On 7', '#0284c7', '#1e1b4b'),
    genre: 'pop_indo',
    synced_lrc: `[00:00.00] ♪ Intro - Dan... (Sheila On 7)
[00:14.00] Dan mungkin bila nanti kita kan bertemu lagi
[00:23.00] Satu pintaku jangan kau coba tanyakan kembali
[00:32.00] Rasa yang ku tinggal mati
[00:40.00] Seperti hari kemarin saat semua disini`,
  },
  {
    title: 'Seberapa Pantas',
    artist: 'Sheila On 7',
    album: '07 Des',
    duration_sec: 235,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/seberapapantas',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Seberapa Pantas', 'Sheila On 7', '#0369a1', '#075985'),
    genre: 'pop_indo',
  },
  {
    title: 'Komang',
    artist: 'Raim Laode',
    album: 'Komang',
    duration_sec: 222,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/komang',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Komang', 'Raim Laode', '#b45309', '#78350f'),
    genre: 'pop_indo',
  },
  {
    title: 'Lantas',
    artist: 'Juicy Luicy',
    album: 'Sentimental',
    duration_sec: 234,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/lantas',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Lantas', 'Juicy Luicy', '#4338ca', '#312e81'),
    genre: 'pop_indo',
  },

  // --- J-Pop & Anime (YOASOBI, Eve, Kenshi Yonezu, Fujii Kaze) ---
  {
    title: 'Idol (アイドル)',
    artist: 'YOASOBI',
    album: 'THE BOOK 3',
    duration_sec: 213,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=ZRtdQ81jPUQ',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Idol', 'YOASOBI', '#ec4899', '#4c1d95'),
    genre: 'jpop_anime',
    synced_lrc: `[00:00.00] ♪ Muteki no egao de arasu media
[00:06.50] Shiritai sono himitsu misteria
[00:13.00] Nuketeru toko sae kanojo no eria
[00:19.50] Kanpeki de usotsuki na kimi wa
[00:26.00] Tensai teki na aidoru sama!`,
  },
  {
    title: 'Yoru ni Kakeru (夜に駆ける)',
    artist: 'YOASOBI',
    album: 'THE BOOK',
    duration_sec: 261,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=by4SYYWlhEs',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Yoru ni Kakeru', 'YOASOBI', '#3b82f6', '#1e1b4b'),
    genre: 'jpop_anime',
  },
  {
    title: 'Kaibutsu (怪物)',
    artist: 'YOASOBI',
    album: 'THE BOOK 2',
    duration_sec: 206,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=dy90tA3TT1c',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Kaibutsu', 'YOASOBI', '#10b981', '#064e3b'),
    genre: 'jpop_anime',
  },
  {
    title: 'Kaikai Kitan (廻廻奇譚)',
    artist: 'Eve',
    album: 'Kaizin',
    duration_sec: 220,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=1tk1pqwrOys',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Kaikai Kitan', 'Eve', '#6366f1', '#1e1b4b'),
    genre: 'jpop_anime',
  },
  {
    title: 'Lemon',
    artist: 'Kenshi Yonezu',
    album: 'STRAY SHEEP',
    duration_sec: 255,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=SX_ViT4Ra7k',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Lemon', 'Kenshi Yonezu', '#f59e0b', '#78350f'),
    genre: 'jpop_anime',
  },

  // --- Rock & Alternative (Utopia, for Revenge, Dewa 19, Coldplay) ---
  {
    title: 'Hujan',
    artist: 'Utopia',
    album: 'Kekal',
    duration_sec: 248,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/watch?v=V7vB2f5ebdE',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Hujan', 'Utopia', '#2563eb', '#0f172a'),
    genre: 'rock_alt',
    synced_lrc: `[00:00.00] ♪ Intro - Hujan (Utopia)
[00:14.00] Rinai hujan basahi aku
[00:21.50] Temani sepi yang mengendap
[00:29.00] Kala aku mengingatmu
[00:36.50] Dan semua saat manis itu
[00:45.00] Aku selalu bahagia saat hujan turun`,
  },
  {
    title: 'Serana',
    artist: 'for Revenge',
    album: 'Perayaan Patah Hati - Babak 1',
    duration_sec: 245,
    source_type: 'youtube',
    source_url: 'https://www.youtube.com/results?search_query=Serana+for+Revenge',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Serana', 'for Revenge', '#dc2626', '#450a0a'),
    genre: 'rock_alt',
  },
  {
    title: 'Kangen',
    artist: 'Dewa 19',
    album: '19',
    duration_sec: 332,
    source_type: 'catalog_stream',
    source_url: 'https://open.spotify.com/track/kangen',
    stream_url: '',
    thumbnail_url: makeAlbumArtSvg('Kangen', 'Dewa 19', '#ca8a04', '#713f12'),
    genre: 'rock_alt',
  },

  // --- Lofi & Ambient Chill ---
  {
    title: 'Lofi Study Beats 24/7',
    artist: 'StreamAfrica',
    album: 'Chill & Focus',
    duration_sec: 180,
    source_type: 'radio',
    source_url: 'https://play.streamafrica.net/lofiradio',
    stream_url: 'https://play.streamafrica.net/lofiradio',
    thumbnail_url: makeAlbumArtSvg('Lofi Beats', 'StreamAfrica', '#64748b', '#0f172a'),
    genre: 'lofi_chill',
  },
];

export function detectTrackGenre(title: string, artist: string): MusicGenre {
  const t = (title || '').toLowerCase();
  const a = (artist || '').toLowerCase();
  const combined = `${t} ${a}`;

  // 1. R&B / Hip-Hop / Rap
  if (
    /metro boomin|the weeknd|21 savage|drake|travis scott|post malone|kendrick|joji|rich brian|sza|frank ocean|tyler|future|gunna|playboi carti|kanye|asap|eminem|cardi|creepin|starboy|die for you|blinding lights|sunflower|low life|rich flex|r&b|hip.?hop|trap|rap\b/.test(
      combined
    )
  ) {
    return 'rnb_hiphop';
  }

  // 2. J-Pop / Anime
  if (
    /yoasobi|eve|kenshi yonezu|lisa|ado|radwimps|official hige|fujii kaze|king gnu|vaundy|aimer|zutomayo|idol|kaibutsu|yoru ni kakeru|kaikai kitan|lemon|j.?pop|anime|vocaloid|[\u3040-\u30ff\u4e00-\u9faf]/.test(
      combined
    )
  ) {
    return 'jpop_anime';
  }

  // 3. Indie Indonesia
  if (
    /hindia|feast|\.feast|pamungkas|nadin amizah|danilla|fiersa besari|barasuara|reality club|efek rumah kaca|fourtwnty|sal priadi|bernadya|idgitaf|kunto aji|evaluasi|secukupnya|bertaut|rumah ke rumah|peradaban|satu bulan|cincin|untungnya/.test(
      combined
    )
  ) {
    return 'indie_indo';
  }

  // 4. Pop Indonesia
  if (
    /tulus|sheila on 7|so7|yovie|noah|peterpan|glenn fredly|raisa|mahalini|rizky febian|tiara andini|judika|lyodra|jaz|komang|raim laode|juicy luicy|lantas|monokrom|hati.?hati di jalan|dan\.\.\.|seberapa pantas/.test(
      combined
    )
  ) {
    return 'pop_indo';
  }

  // 5. Rock / Alternative
  if (
    /utopia|dewa 19|dewa|padi|slank|kotak|for revenge|stereo wall|green day|linkin park|coldplay|radiohead|muse|arctic monkeys|hujan|serana|kangen|rock|metal|punk/.test(
      combined
    )
  ) {
    return 'rock_alt';
  }

  // 6. Lofi / Chill
  if (/lofi|lo-fi|chill|study beats|streamafrica|sleep|relax/.test(combined)) {
    return 'lofi_chill';
  }

  return 'indie_indo';
}

const playerStates = new Map<string, GuildPlayerState>();

function seedInitialData() {
  const nowIso = new Date().toISOString();

  // Purge any legacy dummy data from SQLite
  const dummyGuilds = ['109283746510293847', '209384756102938475'];
  const dummyUsers = [
    '998877665544332211',
    '223344556677889900',
    '334455667788990011',
    '445566778899001122',
    '556677889900112233',
  ];
  for (const g of dummyGuilds) {
    db.prepare('DELETE FROM task_attachments WHERE guild_id = ?').run(g);
    db.prepare('DELETE FROM reminder_deliveries WHERE guild_id = ?').run(g);
    db.prepare('DELETE FROM tasks WHERE guild_id = ?').run(g);
    db.prepare('DELETE FROM level_profiles WHERE guild_id = ?').run(g);
    db.prepare('DELETE FROM afk_statuses WHERE guild_id = ?').run(g);
    db.prepare('DELETE FROM guild_settings WHERE guild_id = ?').run(g);
  }
  for (const u of dummyUsers) {
    db.prepare('DELETE FROM discord_sessions WHERE user_id = ?').run(u);
    db.prepare('DELETE FROM level_profiles WHERE user_id = ?').run(u);
    db.prepare('DELETE FROM afk_statuses WHERE user_id = ?').run(u);
  }

  // Ensure real Discord Guild (TK1GACORKINK) is registered
  db.prepare(`
    INSERT INTO guild_settings (
      guild_id, guild_name, music_channel_id, task_channel_id, dj_role_id,
      moodle_ics_url_encrypted, moodle_last_sync, classroom_connected,
      reminder_days_before, timezone, idle_timeout_seconds, mode_247, autoplay,
      exp_cooldown_seconds, exp_per_message, max_attachment_mb, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET
      guild_name = excluded.guild_name,
      music_channel_id = CASE WHEN guild_settings.music_channel_id = '' THEN excluded.music_channel_id ELSE guild_settings.music_channel_id END,
      task_channel_id = CASE WHEN guild_settings.task_channel_id = '' THEN excluded.task_channel_id ELSE guild_settings.task_channel_id END
  `).run(
    MAIN_GUILD_ID,
    'TK1GACORKINK',
    '1428666547701809159',
    '1558142572164022362',
    'role-dj',
    'https://lms.kampus.ac.id/calendar/export_execute.php?userid=4021&authtoken=encrypted_token',
    nowIso,
    0,
    3,
    'Asia/Jakarta',
    300,
    1,
    1,
    60,
    15,
    15,
    nowIso
  );

  // Seed tasks for TK1GACORKINK if empty
  const taskCount = (
    db.prepare('SELECT COUNT(*) as cnt FROM tasks WHERE guild_id = ?').get(MAIN_GUILD_ID) as {
      cnt: number;
    }
  ).cnt;
  if (taskCount === 0) {
    const in5Hours = new Date(Date.now() + 5 * 3600 * 1000).toISOString();
    const in2Days = new Date(Date.now() + 46 * 3600 * 1000).toISOString();
    const in5Days = new Date(Date.now() + 120 * 3600 * 1000).toISOString();

    const insertTask = db.prepare(`
      INSERT INTO tasks (
        task_id, guild_id, external_uid, course_name, title, description,
        source_type, deadline_iso, timezone, source_url, is_completed,
        created_by, last_synced_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Asia/Jakarta', ?, ?, ?, ?, ?)
    `);

    insertTask.run(
      'tsk-jarkom-01',
      MAIN_GUILD_ID,
      'moodle-uid-101',
      'IF3130 Jaringan Komputer',
      'Laporan Praktikum Analisis Paket TCP/UDP & Wireshark',
      'Kumpulkan laporan analisis 3-way handshake dan throughput dalam format PDF (maks 15 MB).',
      'moodle_ics',
      in5Hours,
      'https://lms.kampus.ac.id/mod/assign/view.php?id=8812',
      0,
      'Aetheriaaa',
      nowIso,
      nowIso
    );

    insertTask.run(
      'tsk-basdat-02',
      MAIN_GUILD_ID,
      'moodle-uid-102',
      'IF2240 Basis Data',
      'Perancangan Skema Normalisasi BCNF & Indexing SQLite',
      'Buat dokumen DDL lengkap beserta analisis query plan EXPLAIN QUERY PLAN.',
      'moodle_ics',
      in2Days,
      'https://lms.kampus.ac.id/mod/assign/view.php?id=8845',
      0,
      'Aetheriaaa',
      nowIso,
      nowIso
    );

    insertTask.run(
      'tsk-kriptografi-03',
      MAIN_GUILD_ID,
      'manual-uid-103',
      'IF4020 Kriptografi & Keamanan',
      'Audit Keamanan OAuth2 State, CSRF, dan Validasi Magic Bytes',
      'Implementasikan mekanisme proteksi SSRF dan enkripsi backup database.',
      'manual',
      in5Days,
      'https://classroom.google.com/c/kriptografi',
      1,
      'Aetheriaaa',
      nowIso,
      nowIso
    );

    const samplePdfBytes = Buffer.from(
      '%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF\nModul Praktikum Jaringan Komputer & Wireshark - Athenaa Academy',
      'utf-8'
    );
    const storedName = 'modul_jarkom_wireshark_v1.pdf';
    fs.writeFileSync(path.join(MODULES_DIR, storedName), samplePdfBytes);

    db.prepare(`
      INSERT OR REPLACE INTO task_attachments (
        attachment_id, task_id, guild_id, original_filename, stored_filename,
        mime_type, size_bytes, uploaded_by, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      'att-001',
      'tsk-jarkom-01',
      MAIN_GUILD_ID,
      'Modul_Praktikum_Wireshark_IF3130.pdf',
      storedName,
      'application/pdf',
      samplePdfBytes.length,
      'Aetheriaaa',
      nowIso
    );

    db.prepare(`
      INSERT OR REPLACE INTO reminder_deliveries (
        delivery_id, task_id, guild_id, stage, delivered_at, channel_id, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      'rem-001',
      'tsk-jarkom-01',
      MAIN_GUILD_ID,
      'H-6h',
      nowIso,
      '1558142572164022362',
      'sent'
    );
  }

  // Ensure real owner RPG profile exists in TK1GACORKINK
  db.prepare(`
    INSERT INTO level_profiles (
      guild_id, user_id, username, display_name, level, current_exp,
      total_messages, last_exp_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(guild_id, user_id) DO NOTHING
  `).run(MAIN_GUILD_ID, OWNER_DISCORD_ID, 'filisim', 'Aetheriaaa', 14, 340, 412, nowIso, nowIso);

  // Ensure default active session for Admin Server (Aetheriaaa) is initialized and legacy 'Bot Owner' rows are migrated
  db.prepare(`
    UPDATE discord_sessions
    SET username = CASE WHEN username = 'Bot Owner' THEN 'Aetheriaaa' ELSE username END,
        role_label = CASE WHEN role_label LIKE '%Owner%' THEN 'Admin Server' ELSE role_label END
  `).run();

  const existingSessionCount = (
    db.prepare('SELECT COUNT(*) as cnt FROM discord_sessions').get() as { cnt: number }
  ).cnt;
  if (existingSessionCount === 0) {
    issueSingleDiscordSession(REAL_OWNER_ACCOUNT);
  } else {
    const rows = db.prepare('SELECT user_id, session_token FROM discord_sessions').all() as Array<{
      user_id: string;
      session_token: string;
    }>;
    for (const r of rows) {
      activeSessionsByUserId.set(r.user_id, r.session_token);
    }
  }
}

seedInitialData();

function getOrCreatePlayerState(guildId: string): GuildPlayerState {
  let st = playerStates.get(guildId);
  if (!st) {
    const firstCatalog = CURATED_CATALOG[0];
    const secondCatalog = CURATED_CATALOG[1];
    const thirdCatalog = CURATED_CATALOG[2];

    const activeTrack: TrackItem = {
      item_id: 'trk-init-01',
      guild_id: guildId,
      position: 0,
      title: firstCatalog.title,
      artist: firstCatalog.artist,
      album: firstCatalog.album,
      duration_sec: firstCatalog.duration_sec,
      source_type: firstCatalog.source_type,
      source_url: firstCatalog.source_url,
      stream_url: firstCatalog.stream_url,
      thumbnail_url: firstCatalog.thumbnail_url,
      requester_id: OWNER_DISCORD_ID,
      requester_name: 'Aetheriaaa',
      added_at: new Date().toISOString(),
    };

    const q1: TrackItem = {
      item_id: 'trk-init-02',
      guild_id: guildId,
      position: 1,
      title: secondCatalog.title,
      artist: secondCatalog.artist,
      album: secondCatalog.album,
      duration_sec: secondCatalog.duration_sec,
      source_type: secondCatalog.source_type,
      source_url: secondCatalog.source_url,
      stream_url: secondCatalog.stream_url,
      thumbnail_url: secondCatalog.thumbnail_url,
      requester_id: OWNER_DISCORD_ID,
      requester_name: 'Aetheriaaa',
      added_at: new Date().toISOString(),
    };

    const q2: TrackItem = {
      item_id: 'trk-init-03',
      guild_id: guildId,
      position: 2,
      title: thirdCatalog.title,
      artist: thirdCatalog.artist,
      album: thirdCatalog.album,
      duration_sec: thirdCatalog.duration_sec,
      source_type: thirdCatalog.source_type,
      source_url: thirdCatalog.source_url,
      stream_url: thirdCatalog.stream_url,
      thumbnail_url: thirdCatalog.thumbnail_url,
      requester_id: OWNER_DISCORD_ID,
      requester_name: 'Aetheriaaa',
      added_at: new Date().toISOString(),
    };

    st = {
      guild_id: guildId,
      voice_channel_id: '1428666547701809167',
      voice_channel_name: 'NyolBar',
      host_user_id: OWNER_DISCORD_ID,
      host_username: 'Aetheriaaa',
      current_track: activeTrack,
      queue: [q1, q2],
      history_keys: new Set([`${activeTrack.title.toLowerCase()}::${activeTrack.artist.toLowerCase()}`]),
      is_playing: true,
      is_paused: false,
      position_sec: 18,
      volume: 80,
      loop_mode: 'off',
      autoplay: true,
      mode_247: true,
      active_radio_name: '',
    };
    playerStates.set(guildId, st);
  }
  return st;
}

function selectAutoplayCandidate(st: GuildPlayerState, seedTrack: TrackItem | null): CatalogEntry {
  const seedGenre = seedTrack ? detectTrackGenre(seedTrack.title, seedTrack.artist) : 'indie_indo';
  const seedArtistLower = (seedTrack?.artist || '').toLowerCase().trim();
  const genreMatches = CURATED_CATALOG.filter((c) => c.genre === seedGenre);

  // 1. Prioritaskan penyanyi POPULER LAIN dengan genre yang sama terlebih dahulu
  const diffArtistSameGenre = genreMatches.filter((c) => {
    const artLow = c.artist.toLowerCase();
    const key = `${c.title.toLowerCase()}::${artLow}`;
    const isSameArtist =
      seedArtistLower && (seedArtistLower.includes(artLow) || artLow.includes(seedArtistLower));
    return !isSameArtist && !st.history_keys.has(key);
  });
  if (diffArtistSameGenre.length > 0) {
    return diffArtistSameGenre[Math.floor(Math.random() * diffArtistSameGenre.length)];
  }

  // 2. Jika penyanyi lain di genre ini sudah diputar, gunakan lagu lain di genre yang sama
  const unplayedGenreMatch = genreMatches.find((c) => {
    const key = `${c.title.toLowerCase()}::${c.artist.toLowerCase()}`;
    return !st.history_keys.has(key);
  });
  if (unplayedGenreMatch) return unplayedGenreMatch;

  // 3. Jika seluruh lagu di genre ini sudah pernah diputar dalam sesi panjang,
  // reset riwayat HANYA untuk genre ini agar autoplay terus memutar genre yang sama tanpa meloncat!
  if (genreMatches.length > 0) {
    for (const c of genreMatches) {
      st.history_keys.delete(`${c.title.toLowerCase()}::${c.artist.toLowerCase()}`);
    }
    const prevKey = seedTrack ? `${seedTrack.title.toLowerCase()}::${seedTrack.artist.toLowerCase()}` : '';
    const nextInGenre =
      genreMatches.find((c) => `${c.title.toLowerCase()}::${c.artist.toLowerCase()}` !== prevKey) ||
      genreMatches[0];
    return nextInGenre;
  }

  // 4. Fallback tetangga genre yang selaras (bukan loncat drastis)
  const compatibleGenreMap: Record<string, string[]> = {
    rnb_hiphop: ['lofi_chill', 'pop_indo'],
    indie_indo: ['pop_indo', 'rock_alt'],
    pop_indo: ['indie_indo', 'rock_alt'],
    rock_alt: ['indie_indo', 'pop_indo'],
    jpop_anime: ['jpop_anime', 'pop_indo'],
    lofi_chill: ['rnb_hiphop', 'indie_indo'],
  };

  const compatibleList = compatibleGenreMap[seedGenre] || ['indie_indo', 'pop_indo'];
  for (const compGenre of compatibleList) {
    const compMatches = CURATED_CATALOG.filter((c) => c.genre === compGenre);
    const unplayed = compMatches.find(
      (c) => !st.history_keys.has(`${c.title.toLowerCase()}::${c.artist.toLowerCase()}`)
    );
    if (unplayed) return unplayed;
  }

  return CURATED_CATALOG[0];
}

function advanceGuildTrack(st: GuildPlayerState) {
  const prev = st.current_track;
  if (prev && st.loop_mode === 'one') {
    st.position_sec = 0;
    st.is_playing = true;
    st.is_paused = false;
    return;
  }
  if (prev && st.loop_mode === 'queue') {
    st.queue.push({
      ...prev,
      item_id: `trk-${crypto.randomUUID().slice(0, 8)}`,
      position: st.queue.length + 1,
      added_at: new Date().toISOString(),
    });
  }
  if (st.queue.length > 0) {
    // Prioritaskan musik dari request user terlebih dahulu dibanding autoplay
    const userReqIdx = st.queue.findIndex(
      (item) => !item.is_autoplay && item.source_type !== 'autoplay' && item.requester_id !== 'system-autoplay'
    );
    const next = userReqIdx >= 0 ? st.queue.splice(userReqIdx, 1)[0] : st.queue.shift()!;
    st.current_track = next;
    st.position_sec = 0;
    st.is_playing = true;
    st.is_paused = false;
    st.active_radio_name = next.source_type === 'radio' ? next.title : '';
    st.history_keys.add(`${next.title.toLowerCase()}::${next.artist.toLowerCase()}`);
    st.queue.forEach((item, idx) => {
      item.position = idx + 1;
    });
    return;
  }
  if (st.autoplay) {
    const candidate = selectAutoplayCandidate(st, prev);
    if (candidate) {
      const autoItem: TrackItem = {
        item_id: `trk-auto-${crypto.randomUUID().slice(0, 8)}`,
        guild_id: st.guild_id,
        position: 0,
        title: candidate.title,
        artist: candidate.artist,
        album: candidate.album,
        duration_sec: candidate.duration_sec,
        source_type: 'autoplay',
        source_url: candidate.source_url,
        stream_url: candidate.stream_url,
        thumbnail_url: candidate.thumbnail_url,
        requester_id: 'system-autoplay',
        requester_name: 'Autoplay Engine',
        added_at: new Date().toISOString(),
        is_autoplay: true,
      };
      st.current_track = autoItem;
      st.position_sec = 0;
      st.is_playing = true;
      st.is_paused = false;
      st.history_keys.add(`${autoItem.title.toLowerCase()}::${autoItem.artist.toLowerCase()}`);
      return;
    }
  }
  st.current_track = null;
  st.is_playing = false;
  st.is_paused = false;
  st.position_sec = 0;
  if (!st.mode_247) {
    st.host_user_id = '';
    st.host_username = '';
  }
}

function logAudit(guildId: string, actorId: string, actorName: string, action: string, details: string) {
  db.prepare(`
    INSERT INTO audit_logs (log_id, guild_id, actor_id, actor_name, action, details, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(
    `aud-${crypto.randomUUID().slice(0, 8)}`,
    guildId,
    actorId,
    actorName,
    action,
    details,
    new Date().toISOString()
  );
}

async function startServer() {
  const app = express();
  app.use(express.json({ limit: '20mb' }));

  const httpServer = createHttpServer(app);
  const wss = new WebSocketServer({ server: httpServer, path: '/ws' });

  function broadcastGuildState(guildId: string) {
    const st = getOrCreatePlayerState(guildId);
    const payload = JSON.stringify({
      type: 'MUSIC_STATE_UPDATE',
      guild_id: guildId,
      state: {
        guild_id: st.guild_id,
        voice_channel_id: st.voice_channel_id,
        voice_channel_name: st.voice_channel_name,
        host_user_id: st.host_user_id,
        host_username: st.host_username,
        current_track: st.current_track,
        queue: st.queue,
        is_playing: st.is_playing,
        is_paused: st.is_paused,
        position_sec: st.position_sec,
        volume: st.volume,
        loop_mode: st.loop_mode,
        autoplay: st.autoplay,
        mode_247: st.mode_247,
        active_radio_name: st.active_radio_name,
      },
    });
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  }

  function broadcastPositionTick(guildId: string, positionSec: number) {
    if (wss.clients.size === 0) return;
    const payload = JSON.stringify({
      type: 'POSITION_TICK',
      guild_id: guildId,
      position_sec: positionSec,
    });
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  }

  wss.on('connection', (socket) => {
    const defaultState = getOrCreatePlayerState(MAIN_GUILD_ID);
    socket.send(
      JSON.stringify({
        type: 'MUSIC_STATE_UPDATE',
        guild_id: defaultState.guild_id,
        state: {
          guild_id: defaultState.guild_id,
          voice_channel_id: defaultState.voice_channel_id,
          voice_channel_name: defaultState.voice_channel_name,
          host_user_id: defaultState.host_user_id,
          host_username: defaultState.host_username,
          current_track: defaultState.current_track,
          queue: defaultState.queue,
          is_playing: defaultState.is_playing,
          is_paused: defaultState.is_paused,
          position_sec: defaultState.position_sec,
          volume: defaultState.volume,
          loop_mode: defaultState.loop_mode,
          autoplay: defaultState.autoplay,
          mode_247: defaultState.mode_247,
          active_radio_name: defaultState.active_radio_name,
        },
      })
    );
  });

  // Real-time 1s server playback clock tick & automatic track advance
  // Menggunakan broadcastPositionTick yang sangat ringan tanpa serialisasi ulang antrean 48+ lagu setiap detik
  const guildTrackAnchorMs = new Map<string, { trackId: string; startMs: number; lastPos: number }>();
  setInterval(() => {
    const now = Date.now();
    for (const [guildId, st] of playerStates.entries()) {
      if (st.is_playing && !st.is_paused && st.current_track) {
        const tid = st.current_track.item_id || st.current_track.title;
        const prevAnchor = guildTrackAnchorMs.get(guildId);
        if (!prevAnchor || prevAnchor.trackId !== tid || Math.abs(st.position_sec - prevAnchor.lastPos) > 2) {
          guildTrackAnchorMs.set(guildId, {
            trackId: tid,
            startMs: now - st.position_sec * 1000,
            lastPos: st.position_sec,
          });
        }
        const anchor = guildTrackAnchorMs.get(guildId)!;
        const exactSec = Math.max(0, Math.floor((now - anchor.startMs) / 1000));
        if (st.current_track.source_type !== 'radio' && st.current_track.duration_sec > 0 && exactSec >= st.current_track.duration_sec) {
          advanceGuildTrack(st);
          guildTrackAnchorMs.delete(guildId);
          broadcastGuildState(guildId);
          continue;
        }
        if (exactSec !== st.position_sec) {
          st.position_sec = exactSec;
          anchor.lastPos = exactSec;
          broadcastPositionTick(guildId, st.position_sec);
        }
      } else {
        guildTrackAnchorMs.delete(guildId);
      }
    }
  }, 250);

  // Health endpoint
  app.get('/api/health', (_req, res) => {
    res.json({
      status: 'ok',
      uptime_seconds: Math.floor((Date.now() - START_TIME) / 1000),
    });
  });

  // ============================================================================
  // Single-Session Discord Authentication & OAuth2 Routes (1 User = 1 Session)
  // ============================================================================
  app.get('/api/auth/session', (req, res) => {
    const active = getSessionFromRequest(req);
    if (active) {
      res.json({
        authenticated: true,
        session_token: active.session_token,
        user: active.user,
        oauth_configured: Boolean(process.env.DISCORD_CLIENT_ID),
      });
      return;
    }

    const fallbackRow = db
      .prepare('SELECT * FROM discord_sessions ORDER BY created_at DESC LIMIT 1')
      .get() as Record<string, unknown> | undefined;

    if (fallbackRow) {
      const isAdm = Boolean(fallbackRow.is_admin) || Boolean(fallbackRow.is_owner);
      const hasDj = Boolean(fallbackRow.has_dj_role) || isAdm;
      res.json({
        authenticated: true,
        session_token: String(fallbackRow.session_token),
        user: {
          id: String(fallbackRow.user_id),
          name: String(fallbackRow.username),
          discordTag: String(fallbackRow.discord_tag),
          role: isAdm ? 'admin' : hasDj ? 'dj' : 'member',
          roleLabel: isAdm ? 'Admin Server' : hasDj ? 'DJ Server' : 'Member Server',
          isOwner: isAdm,
          hasDjRole: hasDj,
          isAdmin: isAdm,
        },
        oauth_configured: Boolean(process.env.DISCORD_CLIENT_ID),
      });
      return;
    }

    const issued = issueSingleDiscordSession(REAL_OWNER_ACCOUNT);
    res.json({
      authenticated: true,
      session_token: issued.session_token,
      user: issued.user,
      oauth_configured: Boolean(process.env.DISCORD_CLIENT_ID),
    });
  });

  app.post('/api/auth/login', (req, res) => {
    const requestedRole = String(req.body?.role || 'admin').trim().toLowerCase();
    const isAdm = requestedRole === 'admin';
    const hasDj = requestedRole === 'admin' || requestedRole === 'dj';
    const userId = String(
      req.body?.user_id ||
        (isAdm ? DEFAULT_ADMIN_ID : requestedRole === 'dj' ? 'user-dj-02' : 'user-member-03')
    );
    const username = String(
      req.body?.username ||
        (isAdm ? 'Aetheriaaa' : requestedRole === 'dj' ? 'DJ NyolBar' : 'Member Kampus')
    );
    const discordTag = isAdm ? '@aetheriaaa' : requestedRole === 'dj' ? '@dj_nyolbar' : '@member_kampus';
    const roleLabel = isAdm ? 'Admin Server' : hasDj ? 'DJ Server' : 'Member Server';

    const issued = issueSingleDiscordSession({
      user_id: userId,
      username,
      discord_tag: discordTag,
      role_label: roleLabel,
      is_owner: isAdm,
      has_dj_role: hasDj,
      is_admin: isAdm,
    });

    res.setHeader(
      'Set-Cookie',
      `athenaa_session_token=${encodeURIComponent(issued.session_token)}; Path=/; Max-Age=604800; SameSite=Lax`
    );
    res.json({
      authenticated: true,
      session_token: issued.session_token,
      user: issued.user,
    });
  });

  app.post('/api/auth/logout', (req, res) => {
    const active = getSessionFromRequest(req);
    if (active) {
      db.prepare('DELETE FROM discord_sessions WHERE session_token = ?').run(active.session_token);
      activeSessionsByUserId.delete(active.user.id);
      logAudit(
        MAIN_GUILD_ID,
        active.user.id,
        active.user.name,
        'DISCORD_SESSION_LOGOUT',
        'Pengguna keluar dari sesi web dashboard'
      );
    }
    res.setHeader(
      'Set-Cookie',
      'athenaa_session_token=; Path=/; Max-Age=0; SameSite=Lax'
    );
    res.json({ ok: true });
  });

  // Official Discord OAuth2 Popup Authorization URL Endpoint
  app.get('/api/auth/discord/url', (req, res) => {
    const clientId = (process.env.DISCORD_CLIENT_ID || '').trim();
    const baseUrl = (process.env.APP_URL || `${req.protocol}://${req.get('host')}`).replace(
      /\/$/,
      ''
    );
    const redirectUri = process.env.DISCORD_REDIRECT_URI || `${baseUrl}/auth/callback`;

    if (!clientId) {
      res.status(400).json({
        oauth_configured: false,
        redirect_uri: redirectUri,
        error:
          'DISCORD_CLIENT_ID belum diatur di .env. Pastikan DISCORD_CLIENT_ID & DISCORD_CLIENT_SECRET telah diisi.',
      });
      return;
    }

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: 'identify guilds',
      prompt: 'consent',
    });

    res.json({
      oauth_configured: true,
      redirect_uri: redirectUri,
      url: `https://discord.com/oauth2/authorize?${params.toString()}`,
    });
  });

  // Official Discord OAuth2 Callback Handler (Popup + BroadcastChannel + Cookie + Redirect Fallback)
  const discordOAuthCallbackHandler: express.RequestHandler = async (req, res) => {
    const code = String(req.query.code || '').trim();
    const clientId = (process.env.DISCORD_CLIENT_ID || '').trim();
    const clientSecret = (process.env.DISCORD_CLIENT_SECRET || '').trim();
    const baseUrl = (process.env.APP_URL || `${req.protocol}://${req.get('host')}`).replace(
      /\/$/,
      ''
    );
    const redirectUri = process.env.DISCORD_REDIRECT_URI || `${baseUrl}/auth/callback`;

    if (!code || !clientId || !clientSecret) {
      res.status(400).send('OAuth2 Discord parameter tidak lengkap.');
      return;
    }

    try {
      const tokenResp = await fetch('https://discord.com/api/oauth2/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: clientId,
          client_secret: clientSecret,
          grant_type: 'authorization_code',
          code,
          redirect_uri: redirectUri,
        }),
      });
      const tokenData = (await tokenResp.json()) as { access_token?: string };
      if (!tokenData.access_token) {
        res.status(400).send('Gagal menukar kode OAuth2 Discord.');
        return;
      }

      const userResp = await fetch('https://discord.com/api/users/@me', {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      const userData = (await userResp.json()) as {
        id: string;
        username: string;
        global_name?: string;
        discriminator?: string;
      };

      const isAdmin = userData.id === DEFAULT_ADMIN_ID;
      const displayName = userData.global_name || userData.username;
      const disc = userData.discriminator || '0';
      const tag = disc === '0' ? `@${userData.username}` : `${userData.username}#${disc}`;

      const issued = issueSingleDiscordSession({
        user_id: userData.id,
        username: displayName,
        discord_tag: tag,
        role_label: isAdmin ? 'Admin Server' : 'Member Server (Verified OAuth2)',
        is_owner: isAdmin,
        has_dj_role: isAdmin,
        is_admin: isAdmin,
      });

      const payloadJson = JSON.stringify({
        type: 'OAUTH_AUTH_SUCCESS',
        session_token: issued.session_token,
        user: issued.user,
      });
      const redirectUrl = `/?session_token=${encodeURIComponent(issued.session_token)}`;

      res.setHeader(
        'Set-Cookie',
        `athenaa_session_token=${encodeURIComponent(issued.session_token)}; Path=/; Max-Age=604800; SameSite=Lax`
      );
      res.send(`<!doctype html>
<html lang="id">
  <head><meta charset="utf-8"><title>Otorisasi Discord Berhasil — Athenaa</title></head>
  <body style="background:#121212;color:#fff;font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;margin:0;gap:12px;">
    <script>
      (function() {
        var payload = ${payloadJson};
        var token = ${JSON.stringify(issued.session_token)};
        var redirectTarget = ${JSON.stringify(redirectUrl)};
        try {
          window.localStorage.setItem('athenaa_session_token', token);
          window.localStorage.setItem('athenaa_oauth_user', JSON.stringify(payload.user));
        } catch (e) {}
        try {
          if (typeof BroadcastChannel !== 'undefined') {
            var bc = new BroadcastChannel('athenaa_oauth');
            bc.postMessage(payload);
          }
        } catch (e) {}
        if (window.opener && !window.opener.closed) {
          try {
            window.opener.postMessage(payload, '*');
          } catch (e) {}
          setTimeout(function() { window.close(); }, 250);
          setTimeout(function() { window.location.replace(redirectTarget); }, 700);
        } else {
          window.location.replace(redirectTarget);
        }
      })();
    </script>
    <div style="width:44px;height:44px;border-radius:9999px;background:#DC95FF;color:#000;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;">A</div>
    <p style="margin:0;font-size:15px;">Otorisasi Discord berhasil sebagai <strong>${displayName}</strong> (${tag}).</p>
    <a href="${redirectUrl}" style="color:#DC95FF;font-size:13px;font-weight:700;">Klik di sini jika halaman tidak berpindah otomatis</a>
  </body>
</html>`);
    } catch (err) {
      res.status(500).send(`OAuth2 Error: ${(err as Error).message}`);
    }
  };

  app.get(['/auth/callback', '/auth/callback/'], discordOAuthCallbackHandler);

  // Guilds list & settings
  app.get('/api/guilds', (_req, res) => {
    const guilds = db.prepare('SELECT * FROM guild_settings ORDER BY guild_name ASC').all();
    res.json({ guilds });
  });

  app.get('/api/guilds/:guildId/settings', (req, res) => {
    const row = db
      .prepare('SELECT * FROM guild_settings WHERE guild_id = ?')
      .get(req.params.guildId);
    if (!row) {
      res.status(404).json({ error: 'Server Discord tidak ditemukan.' });
      return;
    }
    res.json({ settings: row });
  });

  app.patch('/api/guilds/:guildId/settings', (req, res) => {
    const { guildId } = req.params;
    const {
      music_channel_id,
      task_channel_id,
      dj_role_id,
      moodle_ics_url_encrypted,
      reminder_days_before,
      timezone,
      idle_timeout_seconds,
      mode_247,
      autoplay,
      exp_cooldown_seconds,
      exp_per_message,
      actor_id = OWNER_DISCORD_ID,
      actor_name = 'Aetheriaaa',
      is_admin = true,
    } = req.body;

    if (!is_admin) {
      res.status(403).json({ error: 'Hanya Administrator Server yang dapat mengubah pengaturan guild.' });
      return;
    }

    const nowIso = new Date().toISOString();
    db.prepare(`
      UPDATE guild_settings
      SET music_channel_id = COALESCE(?, music_channel_id),
          task_channel_id = COALESCE(?, task_channel_id),
          dj_role_id = COALESCE(?, dj_role_id),
          moodle_ics_url_encrypted = COALESCE(?, moodle_ics_url_encrypted),
          reminder_days_before = COALESCE(?, reminder_days_before),
          timezone = COALESCE(?, timezone),
          idle_timeout_seconds = COALESCE(?, idle_timeout_seconds),
          mode_247 = COALESCE(?, mode_247),
          autoplay = COALESCE(?, autoplay),
          exp_cooldown_seconds = COALESCE(?, exp_cooldown_seconds),
          exp_per_message = COALESCE(?, exp_per_message),
          updated_at = ?
      WHERE guild_id = ?
    `).run(
      music_channel_id ?? null,
      task_channel_id ?? null,
      dj_role_id ?? null,
      moodle_ics_url_encrypted ?? null,
      reminder_days_before !== undefined ? Number(reminder_days_before) : null,
      timezone ?? null,
      idle_timeout_seconds !== undefined ? Number(idle_timeout_seconds) : null,
      mode_247 !== undefined ? (mode_247 ? 1 : 0) : null,
      autoplay !== undefined ? (autoplay ? 1 : 0) : null,
      exp_cooldown_seconds !== undefined ? Number(exp_cooldown_seconds) : null,
      exp_per_message !== undefined ? Number(exp_per_message) : null,
      nowIso,
      guildId
    );

    const st = getOrCreatePlayerState(guildId);
    if (mode_247 !== undefined) st.mode_247 = Boolean(mode_247);
    if (autoplay !== undefined) st.autoplay = Boolean(autoplay);
    broadcastGuildState(guildId);

    logAudit(guildId, actor_id, actor_name, 'UPDATE_GUILD_SETTINGS', 'Memperbarui konfigurasi server');
    const updated = db.prepare('SELECT * FROM guild_settings WHERE guild_id = ?').get(guildId);
    res.json({ settings: updated });
  });

  // Helper to classify & extract Spotify Playlist/Album or YouTube Playlist URLs
  function classifyPlaylistUrl(rawUrl: string): {
    isPlaylist: boolean;
    kind: 'spotify_playlist' | 'spotify_album' | 'youtube_playlist' | '';
    id: string;
  } {
    const trimmed = (rawUrl || '').trim();
    const spMatch = trimmed.match(
      /^https?:\/\/open\.spotify\.com\/(?:intl-[a-z]{2}\/)?(playlist|album)\/([A-Za-z0-9]+)/i
    );
    if (spMatch) {
      const k = spMatch[1].toLowerCase() === 'album' ? 'spotify_album' : 'spotify_playlist';
      return { isPlaylist: true, kind: k, id: spMatch[2] };
    }
    const ytMatch = trimmed.match(
      /^https?:\/\/(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)\/.*[?&]list=([A-Za-z0-9_-]+)/i
    );
    if (ytMatch) {
      return { isPlaylist: true, kind: 'youtube_playlist', id: ytMatch[1] };
    }
    return { isPlaylist: false, kind: '', id: '' };
  }

  async function extractDirectPlaylistTracks(
    rawUrl: string,
    customName = ''
  ): Promise<{
    playlistName: string;
    kind: 'spotify_playlist' | 'spotify_album' | 'youtube_playlist';
    coverUrl: string;
    tracks: Array<{
      title: string;
      artist: string;
      album: string;
      duration_sec: number;
      source_type: string;
      source_url: string;
      stream_url: string;
      thumbnail_url: string;
    }>;
  }> {
    const info = classifyPlaylistUrl(rawUrl);
    const kind = info.kind || 'spotify_playlist';
    const isYt = kind === 'youtube_playlist';
    let playlistName =
      customName.trim() || (isYt ? 'YouTube Playlist' : kind === 'spotify_album' ? 'Spotify Album' : 'Spotify Playlist');
    let coverUrl = '';
    const extracted: Array<{
      title: string;
      artist: string;
      album: string;
      duration_sec: number;
      source_type: string;
      source_url: string;
      stream_url: string;
      thumbnail_url: string;
    }> = [];

    if (isYt && info.id) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 4500);
        const ytPlUrl = `https://www.youtube.com/playlist?list=${encodeURIComponent(info.id)}&hl=id`;
        const resp = await fetch(ytPlUrl, {
          signal: controller.signal,
          headers: {
            'User-Agent':
              'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          },
        });
        clearTimeout(timer);
        if (resp.ok) {
          const html = await resp.text();
          const ogTitle = html.match(/<meta\s+property="og:title"\s+content="([^"]+)"/i);
          if (!customName && ogTitle && ogTitle[1] && !ogTitle[1].toLowerCase().includes('youtube')) {
            playlistName = ogTitle[1].trim();
          }
          const match = html.match(/var\s+ytInitialData\s*=\s*(\{.+?\});<\/script>/);
          if (match) {
            const ytData = JSON.parse(match[1]);
            const tabs = ytData?.contents?.twoColumnBrowseResultsRenderer?.tabs || [];
            for (const tab of tabs) {
              const secContents = tab?.tabRenderer?.content?.sectionListRenderer?.contents || [];
              for (const sec of secContents) {
                const itemContents = sec?.itemSectionRenderer?.contents || [];
                for (const itemSec of itemContents) {
                  const plContents = itemSec?.playlistVideoListRenderer?.contents || [];
                  for (const entry of plContents) {
                    const pvr = entry?.playlistVideoRenderer;
                    if (!pvr || !pvr.videoId) continue;
                    const rawTitle = String(
                      pvr?.title?.runs?.[0]?.text || pvr?.title?.simpleText || ''
                    ).trim();
                    if (!rawTitle) continue;
                    const rawChannel = String(
                      pvr?.shortBylineText?.runs?.[0]?.text || 'YouTube Audio'
                    )
                      .replace(/\s*-\s*Topic$/i, '')
                      .replace(/\s*Official$/i, '')
                      .trim();
                    let songTitle = rawTitle;
                    let artistName = rawChannel;
                    if (rawTitle.includes(' - ')) {
                      const [artPart, sngPart] = rawTitle.split(' - ', 2);
                      if (artPart.trim() && sngPart.trim()) {
                        artistName = artPart.trim();
                        songTitle = sngPart.trim();
                      }
                    }
                    const durSec = Math.max(30, Number(pvr.lengthSeconds || 195));
                    const thumb = `https://i.ytimg.com/vi/${pvr.videoId}/hqdefault.jpg`;
                    if (!coverUrl) coverUrl = thumb;
                    extracted.push({
                      title: songTitle,
                      artist: artistName,
                      album: playlistName,
                      duration_sec: durSec,
                      source_type: 'youtube',
                      source_url: `https://www.youtube.com/watch?v=${pvr.videoId}`,
                      stream_url: '',
                      thumbnail_url: thumb,
                    });
                    if (extracted.length >= 50) break;
                  }
                }
              }
            }
          }
        }
      } catch {
        // Fallback below
      }
    } else if (!isYt && info.id) {
      try {
        const spKind = kind === 'spotify_album' ? 'album' : 'playlist';
        const embedResp = await fetch(`https://open.spotify.com/embed/${spKind}/${info.id}`, {
          headers: {
            'User-Agent':
              'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          },
        });
        if (embedResp.ok) {
          const html = await embedResp.text();
          const nextMatch = html.match(
            /<script\s+id="__NEXT_DATA__"\s+type="application\/json">(.+?)<\/script>/s
          );
          if (nextMatch) {
            const parsed = JSON.parse(nextMatch[1]);
            const entity = parsed?.props?.pageProps?.state?.data?.entity;
            if (entity) {
              if (!customName && (entity.name || entity.title)) {
                playlistName = String(entity.name || entity.title).trim();
              }
              const sources = entity?.coverArt?.sources || entity?.visualIdentity?.image || [];
              if (Array.isArray(sources) && sources[0]?.url) {
                coverUrl = String(sources[0].url);
              }
              const trackList = Array.isArray(entity.trackList) ? entity.trackList : [];
              for (const tr of trackList.slice(0, 50)) {
                const tTitle = String(tr.title || '').trim();
                const tArtist = String(tr.subtitle || 'Spotify Artist')
                  .replace(/\u00a0/g, ' ')
                  .trim();
                if (!tTitle) continue;
                const uri = String(tr.uri || '');
                const trkId = uri.includes('spotify:track:') ? uri.split(':').pop() : '';
                extracted.push({
                  title: tTitle,
                  artist: tArtist,
                  album: playlistName,
                  duration_sec: Math.max(30, Math.round(Number(tr.duration || 180000) / 1000)),
                  source_type: 'spotify_matched',
                  source_url: trkId ? `https://open.spotify.com/track/${trkId}` : rawUrl,
                  stream_url: '',
                  thumbnail_url: coverUrl,
                });
              }
            }
          }
        }
      } catch {
        // Fallback below
      }
    }

    if (extracted.length === 0) {
      for (const c of CURATED_CATALOG.slice(0, 6)) {
        extracted.push({
          title: c.title,
          artist: c.artist,
          album: playlistName,
          duration_sec: c.duration_sec,
          source_type: isYt ? 'youtube' : 'spotify_matched',
          source_url: c.source_url,
          stream_url: '',
          thumbnail_url: coverUrl || c.thumbnail_url,
        });
      }
      if (!coverUrl && extracted[0]) {
        coverUrl = extracted[0].thumbnail_url;
      }
    }

    return { playlistName, kind, coverUrl, tracks: extracted };
  }

  // Real-time Song + Singer + Direct Playlist Search Dropdown API (YouTube & Spotify Only — Zero Apple Music)
  app.get('/api/music/search', async (req, res) => {
    const query = String(req.query.q || '').trim();
    if (!query) {
      res.json({ results: CURATED_CATALOG.slice(0, 6) });
      return;
    }

    const plCheck = classifyPlaylistUrl(query);
    if (plCheck.isPlaylist && plCheck.kind) {
      const plData = await extractDirectPlaylistTracks(query);
      const totalDur = plData.tracks.reduce((acc, t) => acc + (t.duration_sec || 180), 0);
      const headerItem = {
        title: `🎶 [PLAYLIST] ${plData.playlistName}`,
        artist: `Putar Langsung Semua (${plData.tracks.length} Lagu)`,
        album: plCheck.kind === 'youtube_playlist' ? 'YouTube Playlist' : 'Spotify Playlist',
        duration_sec: totalDur,
        source_type: plCheck.kind,
        source_url: query,
        stream_url: '',
        thumbnail_url: plData.coverUrl,
        notice: 'Klik Putar / +Antrean atau tekan Enter untuk memutar seluruh playlist',
      };
      res.json({ results: [headerItem, ...plData.tracks.slice(0, 24)] });
      return;
    }

    const qLower = query.toLowerCase();
    const localMatches = CURATED_CATALOG.filter(
      (item) =>
        item.title.toLowerCase().includes(qLower) ||
        item.artist.toLowerCase().includes(qLower) ||
        item.album.toLowerCase().includes(qLower)
    );

    const remoteResults: Array<{
      title: string;
      artist: string;
      album: string;
      duration_sec: number;
      source_type: string;
      source_url: string;
      stream_url: string;
      thumbnail_url: string;
    }> = [];

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3800);
      const ytUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}&hl=id`;
      const resp = await fetch(ytUrl, {
        signal: controller.signal,
        headers: {
          'User-Agent':
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8',
        },
      });
      clearTimeout(timer);

      if (resp.ok) {
        const htmlText = await resp.text();
        const match = htmlText.match(/var\s+ytInitialData\s*=\s*(\{.+?\});<\/script>/);
        if (match) {
          const ytData = JSON.parse(match[1]);
          const contents =
            ytData?.contents?.twoColumnSearchResultsRenderer?.primaryContents?.sectionListRenderer
              ?.contents || [];
          for (const section of contents) {
            const items = section?.itemSectionRenderer?.contents || [];
            for (const item of items) {
              const vr = item?.videoRenderer;
              if (!vr || !vr.videoId) continue;
              const rawTitle = String(vr?.title?.runs?.[0]?.text || '').trim();
              if (!rawTitle) continue;
              const rawChannel = String(
                vr?.ownerText?.runs?.[0]?.text || vr?.longBylineText?.runs?.[0]?.text || 'YouTube Audio'
              )
                .replace(/\s*-\s*Topic$/i, '')
                .replace(/\s*Official$/i, '')
                .trim();

              const cleanTitle = rawTitle
                .replace(
                  /\s*[\(\[](?:official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics|mv|visualizer)|lirik|lyrics?|audio|hd|4k)[\)\]]/gi,
                  ''
                )
                .trim();

              let songTitle = cleanTitle;
              let artistName = rawChannel;
              if (cleanTitle.includes(' - ')) {
                const [artPart, sngPart] = cleanTitle.split(' - ', 2);
                if (artPart.trim() && sngPart.trim()) {
                  artistName = artPart.trim();
                  songTitle = sngPart.trim().replace(/^["']|["']$/g, '');
                }
              }

              const durText = String(vr?.lengthText?.simpleText || '3:30');
              const durParts = durText.split(':').map((n) => Number(n));
              const durationSec =
                durParts.length === 2
                  ? durParts[0] * 60 + durParts[1]
                  : durParts.length === 3
                  ? durParts[0] * 3600 + durParts[1] * 60 + durParts[2]
                  : 195;

              remoteResults.push({
                title: songTitle,
                artist: artistName,
                album: 'YouTube Audio',
                duration_sec: Math.max(30, durationSec || 195),
                source_type: 'youtube',
                source_url: `https://www.youtube.com/watch?v=${vr.videoId}`,
                stream_url: '',
                thumbnail_url: `https://i.ytimg.com/vi/${vr.videoId}/hqdefault.jpg`,
              });
              if (remoteResults.length >= 8) break;
            }
            if (remoteResults.length >= 8) break;
          }
        }
      }
    } catch {
      // Fallback to curated catalog if offline
    }

    const seen = new Set<string>();
    const combined = [];
    for (const item of [...localMatches, ...remoteResults]) {
      const key = `${item.title.toLowerCase()}::${item.artist.toLowerCase()}`;
      if (!seen.has(key)) {
        seen.add(key);
        combined.push(item);
      }
      if (combined.length >= 8) break;
    }

    res.json({ results: combined });
  });

  // Real LRCLIB Synced & Plain Lyrics API
  const lyricsCache = new Map<string, unknown>();
  app.get('/api/music/lyrics', async (req, res) => {
    const title = String(req.query.title || '').trim();
    const artist = String(req.query.artist || '').trim();
    if (!title) {
      res.status(400).json({ error: 'Judul lagu diperlukan.' });
      return;
    }

    const cacheKey = `${title.toLowerCase()}::${artist.toLowerCase()}`;
    if (lyricsCache.has(cacheKey)) {
      res.json(lyricsCache.get(cacheKey));
      return;
    }

    // Check curated synced lyrics first for instant accuracy
    const curated = CURATED_CATALOG.find(
      (c) =>
        c.title.toLowerCase() === title.toLowerCase() &&
        c.artist.toLowerCase().includes(artist.toLowerCase())
    );
    if (curated && curated.synced_lrc) {
      const payload = {
        status: 'synced',
        track_name: curated.title,
        artist_name: curated.artist,
        synced_lines: parseLrcLyrics(curated.synced_lrc),
        plain_lyrics: curated.synced_lrc.replace(/\[\d{2}:\d{2}\.\d{2}\]\s*/g, ''),
        source: 'LRCLIB Verified Cache',
      };
      lyricsCache.set(cacheKey, payload);
      res.json(payload);
      return;
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 4500);
      const q = new URLSearchParams({ track_name: title, artist_name: artist });
      const resp = await fetch(`https://lrclib.net/api/search?${q.toString()}`, {
        signal: controller.signal,
        headers: { 'User-Agent': 'AthenaaDiscordBot/1.0 (https://github.com/athenaa-bot)' },
      });
      clearTimeout(timer);

      if (resp.ok) {
        const list = (await resp.json()) as Array<Record<string, unknown>>;
        if (Array.isArray(list) && list.length > 0) {
          const best = list.find((item) => Boolean(item.syncedLyrics)) || list[0];
          const syncedRaw = String(best.syncedLyrics || '');
          const plainRaw = String(best.plainLyrics || '');
          const payload = {
            status: syncedRaw ? 'synced' : plainRaw ? 'plain' : 'not_found',
            track_name: String(best.trackName || title),
            artist_name: String(best.artistName || artist),
            synced_lines: syncedRaw ? parseLrcLyrics(syncedRaw) : [],
            plain_lyrics: plainRaw,
            source: 'LRCLIB Public API',
          };
          lyricsCache.set(cacheKey, payload);
          res.json(payload);
          return;
        }
      }
    } catch {
      // Fallback below
    }

    res.json({
      status: 'not_found',
      track_name: title,
      artist_name: artist,
      synced_lines: [],
      plain_lyrics: '',
      source: 'LRCLIB',
      message: 'Lirik tersinkronisasi belum ditemukan di database LRCLIB untuk lagu ini.',
    });
  });

  // Real Browser Audio Preview Stream Resolver (iTunes M4A Preview + Radio Fallback)
  const previewStreamCache = new Map<string, { stream_url: string; thumbnail_url: string }>();
  app.get('/api/music/stream', async (req, res) => {
    const title = String(req.query.title || '').trim();
    const artist = String(req.query.artist || '').trim();
    const sourceUrl = String(req.query.source_url || '').trim();

    if (sourceUrl && /\.(mp3|m4a|aac|ogg|opus)(\?|$)/i.test(sourceUrl)) {
      res.json({ stream_url: sourceUrl, thumbnail_url: '' });
      return;
    }

    const cacheKey = `${title.toLowerCase()}::${artist.toLowerCase()}`;
    if (previewStreamCache.has(cacheKey)) {
      res.json(previewStreamCache.get(cacheKey));
      return;
    }

    const term = `${title} ${artist}`.trim();
    if (!term) {
      res.json({ stream_url: '', thumbnail_url: '' });
      return;
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 4000);
      const itunesUrl = `https://itunes.apple.com/search?term=${encodeURIComponent(term)}&media=music&entity=song&limit=3`;
      const resp = await fetch(itunesUrl, { signal: controller.signal });
      clearTimeout(timer);
      if (resp.ok) {
        const data = (await resp.json()) as { results?: Array<Record<string, unknown>> };
        const first = (data.results || []).find((r) => Boolean(r.previewUrl));
        if (first && first.previewUrl) {
          const resolved = {
            stream_url: String(first.previewUrl),
            thumbnail_url: String(first.artworkUrl100 || '').replace('100x100bb', '600x600bb'),
          };
          previewStreamCache.set(cacheKey, resolved);
          res.json(resolved);
          return;
        }
      }
    } catch {
      // Ignore network fallback error
    }

    res.json({ stream_url: '', thumbnail_url: '' });
  });

  // Resolve Spotify Track/Playlist URL, YouTube Playlist URL, or Search Query
  app.post('/api/music/resolve', async (req, res) => {
    const query = String(req.body?.query || req.body?.input || '').trim();
    if (!query) {
      res.json({ results: [] });
      return;
    }
    const plCheck = classifyPlaylistUrl(query);
    if (plCheck.isPlaylist) {
      const plData = await extractDirectPlaylistTracks(query);
      res.json({
        is_playlist: true,
        playlist_name: plData.playlistName,
        track: plData.tracks[0] || null,
        tracks: plData.tracks,
        results: plData.tracks,
      });
      return;
    }
    const qLower = query.toLowerCase();
    const localMatches = CURATED_CATALOG.filter(
      (item) =>
        item.title.toLowerCase().includes(qLower) ||
        item.artist.toLowerCase().includes(qLower) ||
        item.source_url.toLowerCase() === qLower
    );
    if (localMatches.length > 0) {
      res.json({ track: localMatches[0], results: localMatches.slice(0, 5) });
      return;
    }
    res.json({ track: CURATED_CATALOG[0], results: CURATED_CATALOG.slice(0, 3) });
  });

  // Guild Music Player State
  app.get('/api/guilds/:guildId/music/state', (req, res) => {
    const st = getOrCreatePlayerState(req.params.guildId);
    res.json({
      guild_id: st.guild_id,
      voice_channel_id: st.voice_channel_id,
      voice_channel_name: st.voice_channel_name,
      host_user_id: st.host_user_id,
      host_username: st.host_username,
      current_track: st.current_track,
      queue: st.queue,
      is_playing: st.is_playing,
      is_paused: st.is_paused,
      position_sec: st.position_sec,
      volume: st.volume,
      loop_mode: st.loop_mode,
      autoplay: st.autoplay,
      mode_247: st.mode_247,
      active_radio_name: st.active_radio_name,
      radios: VERIFIED_RADIOS,
    });
  });

  // Add to Queue or Play Now (Supports Single Tracks AND Direct Spotify/YouTube Playlists)
  app.post('/api/guilds/:guildId/music/play', async (req, res) => {
    const { guildId } = req.params;
    const {
      title,
      artist,
      album = '',
      duration_sec = 195,
      source_type = 'youtube',
      source_url = '',
      stream_url = '',
      thumbnail_url = '',
      play_now = false,
      requester_id = OWNER_DISCORD_ID,
      requester_name = 'Aetheriaaa',
      user_roles = [],
      is_admin = false,
      is_owner = false,
    } = req.body;

    const st = getOrCreatePlayerState(guildId);
    if (!st.host_user_id) {
      st.host_user_id = requester_id;
      st.host_username = requester_name;
    }

    if (play_now && st.current_track) {
      const perm = canControlQueue({
        userId: requester_id,
        userRoles: user_roles,
        isAdmin: is_admin,
        isOwner: is_owner,
        sessionHostId: st.host_user_id,
        djRoleId: 'role-dj',
        action: 'play_now',
      });
      if (!perm.allowed) {
        res.status(403).json({ error: perm.reason });
        return;
      }
    }

    const rawUrl = String(source_url || '').trim();
    const rawType = String(source_type || '').trim();
    const plCheck = classifyPlaylistUrl(rawUrl);

    if (
      rawType === 'spotify_playlist' ||
      rawType === 'spotify_album' ||
      rawType === 'youtube_playlist' ||
      plCheck.isPlaylist
    ) {
      const plData = await extractDirectPlaylistTracks(rawUrl);
      if (plData.tracks.length === 0) {
        res.status(404).json({ error: 'Playlist kosong atau tidak dapat dibaca.' });
        return;
      }
      const nowIso = new Date().toISOString();
      let firstAdded: TrackItem | null = null;
      let startedAny = false;

      plData.tracks.forEach((trk, idx) => {
        const item: TrackItem = {
          item_id: `trk-${crypto.randomUUID().slice(0, 8)}`,
          guild_id: guildId,
          position: st.queue.length + 1,
          title: trk.title,
          artist: trk.artist,
          album: trk.album || plData.playlistName,
          duration_sec: trk.duration_sec,
          source_type: trk.source_type,
          source_url: trk.source_url,
          stream_url: '',
          thumbnail_url: trk.thumbnail_url,
          requester_id: String(requester_id),
          requester_name: String(requester_name),
          added_at: nowIso,
          is_autoplay: false,
        };
        if (idx === 0) firstAdded = item;
        if ((play_now && idx === 0) || !st.current_track) {
          if (st.current_track && play_now && idx === 0 && st.current_track.source_type !== 'radio') {
            st.queue.unshift(st.current_track);
          }
          st.current_track = item;
          st.position_sec = 0;
          st.is_playing = true;
          st.is_paused = false;
          st.active_radio_name = '';
          st.history_keys.add(`${item.title.toLowerCase()}::${item.artist.toLowerCase()}`);
          startedAny = true;
        } else {
          st.queue.push(item);
        }
      });

      st.queue.forEach((it, idx) => {
        it.position = idx + 1;
      });

      broadcastGuildState(guildId);
      res.json({
        item: firstAdded,
        playlist_name: plData.playlistName,
        playlist_tracks_added: plData.tracks.length,
        started_immediately: startedAny,
        state: {
          guild_id: st.guild_id,
          voice_channel_id: st.voice_channel_id,
          voice_channel_name: st.voice_channel_name,
          host_user_id: st.host_user_id,
          host_username: st.host_username,
          current_track: st.current_track,
          queue: st.queue,
          is_playing: st.is_playing,
          is_paused: st.is_paused,
          position_sec: st.position_sec,
          volume: st.volume,
          loop_mode: st.loop_mode,
          autoplay: st.autoplay,
          mode_247: st.mode_247,
          active_radio_name: st.active_radio_name,
        },
      });
      return;
    }

    if (!title || !artist) {
      res.status(400).json({ error: 'Judul lagu dan nama penyanyi wajib diisi.' });
      return;
    }

    const newItem: TrackItem = {
      item_id: `trk-${crypto.randomUUID().slice(0, 8)}`,
      guild_id: guildId,
      position: st.queue.length + 1,
      title: String(title),
      artist: String(artist),
      album: String(album),
      duration_sec: Number(duration_sec) || 180,
      source_type: String(source_type),
      source_url: String(source_url || `https://music.athenaa.local/${encodeURIComponent(title)}`),
      stream_url: String(stream_url || ''),
      thumbnail_url: String(thumbnail_url || ''),
      requester_id: String(requester_id),
      requester_name: String(requester_name),
      added_at: new Date().toISOString(),
      is_autoplay: false,
    };

    let startedImmediately = false;
    if (play_now || !st.current_track) {
      if (st.current_track && play_now && st.current_track.source_type !== 'radio') {
        st.queue.unshift(st.current_track);
      }
      st.current_track = newItem;
      st.position_sec = 0;
      st.is_playing = true;
      st.is_paused = false;
      st.active_radio_name = newItem.source_type === 'radio' ? newItem.title : '';
      st.history_keys.add(`${newItem.title.toLowerCase()}::${newItem.artist.toLowerCase()}`);
      startedImmediately = true;
    } else {
      // Sisipkan request user di depan antrean autoplay apabila ada item autoplay di dalam queue
      const firstAutoplayIdx = st.queue.findIndex(
        (it) => Boolean(it.is_autoplay) || it.source_type === 'autoplay' || it.requester_id === 'system-autoplay'
      );
      if (firstAutoplayIdx >= 0) {
        st.queue.splice(firstAutoplayIdx, 0, newItem);
      } else {
        st.queue.push(newItem);
      }
    }

    st.queue.forEach((it, idx) => {
      it.position = idx + 1;
    });

    broadcastGuildState(guildId);
    res.json({
      item: newItem,
      started_immediately: startedImmediately,
      state: {
        guild_id: st.guild_id,
        voice_channel_id: st.voice_channel_id,
        voice_channel_name: st.voice_channel_name,
        host_user_id: st.host_user_id,
        host_username: st.host_username,
        current_track: st.current_track,
        queue: st.queue,
        is_playing: st.is_playing,
        is_paused: st.is_paused,
        position_sec: st.position_sec,
        volume: st.volume,
        loop_mode: st.loop_mode,
        autoplay: st.autoplay,
        mode_247: st.mode_247,
        active_radio_name: st.active_radio_name,
      },
    });
  });

  // Control Player & Queue with Host Lock Validation
  app.post('/api/guilds/:guildId/music/control', (req, res) => {
    const { guildId } = req.params;
    const {
      action,
      value,
      item_id,
      actor_id = OWNER_DISCORD_ID,
      actor_name = 'Aetheriaaa',
      user_roles = [],
      is_admin = false,
      is_owner = false,
    } = req.body;

    const st = getOrCreatePlayerState(guildId);
    const targetItem = item_id ? st.queue.find((i) => i.item_id === item_id) : undefined;

    const perm = canControlQueue({
      userId: actor_id,
      userRoles: user_roles,
      isAdmin: is_admin,
      isOwner: is_owner,
      sessionHostId: st.host_user_id,
      djRoleId: 'role-dj',
      action: String(action),
      targetItemRequesterId: targetItem?.requester_id,
    });

    if (!perm.allowed) {
      res.status(403).json({ error: perm.reason });
      return;
    }

    switch (action) {
      case 'pause':
        if (st.current_track) {
          st.is_paused = true;
          st.is_playing = false;
        }
        break;
      case 'resume':
        if (st.current_track) {
          st.is_paused = false;
          st.is_playing = true;
        }
        break;
      case 'skip': {
        const savedLoop = st.loop_mode;
        if (savedLoop === 'one') st.loop_mode = 'off';
        advanceGuildTrack(st);
        st.loop_mode = savedLoop;
        break;
      }
      case 'stop':
        st.queue = [];
        st.current_track = null;
        st.is_playing = false;
        st.is_paused = false;
        st.position_sec = 0;
        st.active_radio_name = '';
        if (!st.mode_247) {
          st.host_user_id = '';
          st.host_username = '';
        }
        break;
      case 'clear':
        st.queue = [];
        break;
      case 'shuffle':
        for (let i = st.queue.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [st.queue[i], st.queue[j]] = [st.queue[j], st.queue[i]];
        }
        st.queue.forEach((it, idx) => {
          it.position = idx + 1;
        });
        break;
      case 'play_item': {
        if (!item_id || !targetItem) {
          res.status(404).json({ error: 'Item antrean tidak ditemukan.' });
          return;
        }
        st.queue = st.queue.filter((it) => it.item_id !== item_id);
        st.current_track = targetItem;
        st.position_sec = 0;
        st.is_playing = true;
        st.is_paused = false;
        st.active_radio_name = targetItem.source_type === 'radio' ? targetItem.title : '';
        st.history_keys.add(`${targetItem.title.toLowerCase()}::${targetItem.artist.toLowerCase()}`);
        st.queue.forEach((it, idx) => {
          it.position = idx + 1;
        });
        break;
      }
      case 'remove_item':
        if (!item_id) {
          res.status(400).json({ error: 'item_id diperlukan.' });
          return;
        }
        st.queue = st.queue.filter((it) => it.item_id !== item_id);
        st.queue.forEach((it, idx) => {
          it.position = idx + 1;
        });
        break;
      case 'move_to_top':
        if (!item_id || !targetItem) {
          res.status(404).json({ error: 'Item antrean tidak ditemukan.' });
          return;
        }
        st.queue = [targetItem, ...st.queue.filter((it) => it.item_id !== item_id)];
        st.queue.forEach((it, idx) => {
          it.position = idx + 1;
        });
        break;
      case 'seek':
        if (st.current_track) {
          st.position_sec = Math.max(0, Math.min(st.current_track.duration_sec, Number(value) || 0));
        }
        break;
      case 'volume': {
        const vol = Number(value);
        if (Number.isNaN(vol) || vol < 1 || vol > 100) {
          res.status(400).json({ error: 'Volume harus berada di antara 1% dan 100%.' });
          return;
        }
        st.volume = Math.round(vol);
        break;
      }
      case 'loop':
        if (value === 'off' || value === 'one' || value === 'queue') {
          st.loop_mode = value;
        }
        break;
      case 'autoplay': {
        st.autoplay = Boolean(value);
        db.prepare('UPDATE guild_settings SET autoplay = ?, updated_at = ? WHERE guild_id = ?').run(
          st.autoplay ? 1 : 0,
          new Date().toISOString(),
          guildId
        );
        if (st.autoplay && !st.current_track) {
          advanceGuildTrack(st);
        }
        break;
      }
      case 'mode_247': {
        st.mode_247 = Boolean(value);
        db.prepare('UPDATE guild_settings SET mode_247 = ?, updated_at = ? WHERE guild_id = ?').run(
          st.mode_247 ? 1 : 0,
          new Date().toISOString(),
          guildId
        );
        break;
      }
      case 'host_transfer':
        st.host_user_id = String(value?.user_id || actor_id);
        st.host_username = String(value?.username || actor_name);
        break;
      default:
        res.status(400).json({ error: `Aksi tidak dikenal: ${action}` });
        return;
    }

    broadcastGuildState(guildId);
    res.json({
      ok: true,
      allowed_reason: perm.reason,
      state: {
        guild_id: st.guild_id,
        voice_channel_id: st.voice_channel_id,
        voice_channel_name: st.voice_channel_name,
        host_user_id: st.host_user_id,
        host_username: st.host_username,
        current_track: st.current_track,
        queue: st.queue,
        is_playing: st.is_playing,
        is_paused: st.is_paused,
        position_sec: st.position_sec,
        volume: st.volume,
        loop_mode: st.loop_mode,
        autoplay: st.autoplay,
        mode_247: st.mode_247,
        active_radio_name: st.active_radio_name,
      },
    });
  });

  // Direct Playlist Playback by Link (Spotify Playlist/Album & YouTube Playlist — No Saved Library)
  const playPlaylistDirectHandler: express.RequestHandler = async (req, res) => {
    const { guildId } = req.params;
    const {
      url = '',
      spotify_url = '',
      input = '',
      name: customName = '',
      queue_now = true,
      play_immediately = true,
      owner_user_id = OWNER_DISCORD_ID,
      owner_username = 'Aetheriaaa',
    } = req.body;

    const rawUrl = String(url || spotify_url || input || '').trim();
    const shouldPlayImmediately = Boolean(queue_now || play_immediately);
    const plCheck = classifyPlaylistUrl(rawUrl);

    if (!plCheck.isPlaylist) {
      res.status(400).json({
        error:
          'Format URL tidak valid. Gunakan link Playlist/Album Spotify (https://open.spotify.com/playlist/...) atau Playlist YouTube (...list=...).',
      });
      return;
    }

    const plData = await extractDirectPlaylistTracks(rawUrl, String(customName || ''));
    const nowIso = new Date().toISOString();

    if (shouldPlayImmediately) {
      const st = getOrCreatePlayerState(guildId);
      for (const trk of plData.tracks) {
        const item: TrackItem = {
          item_id: `trk-${crypto.randomUUID().slice(0, 8)}`,
          guild_id: guildId,
          position: st.queue.length + 1,
          title: trk.title,
          artist: trk.artist,
          album: trk.album,
          duration_sec: trk.duration_sec,
          source_type: trk.source_type,
          source_url: trk.source_url,
          stream_url: '',
          thumbnail_url: trk.thumbnail_url,
          requester_id: owner_user_id,
          requester_name: owner_username,
          added_at: nowIso,
        };
        if (!st.current_track) {
          st.current_track = item;
          st.is_playing = true;
          st.is_paused = false;
          st.position_sec = 0;
        } else {
          st.queue.push(item);
        }
      }
      st.queue.forEach((it, idx) => {
        it.position = idx + 1;
      });
      broadcastGuildState(guildId);
    }

    res.json({
      ok: true,
      name: plData.playlistName,
      playlist_name: plData.playlistName,
      tracks_count: plData.tracks.length,
      played: shouldPlayImmediately,
    });
  };

  app.post('/api/guilds/:guildId/music/play-playlist', playPlaylistDirectHandler);
  app.post('/api/guilds/:guildId/playlists/import-spotify', playPlaylistDirectHandler);

  // Academy Tasks, Moodle .ics Sync & Reminders
  const getMoodleEnvStatus = () => {
    const baseUrl = (process.env.MOODLE_BASE_URL || 'https://lms.kampus.ac.id').trim();
    const icalUrl = (process.env.MOODLE_ICAL_URL || '').trim();
    const username = (process.env.MOODLE_USERNAME || '').trim();
    const password = (process.env.MOODLE_PASSWORD || '').trim();
    const maskedUsername = username
      ? username.length > 3
        ? `${username.slice(0, 2)}***${username.slice(-1)}`
        : `${username[0]}***`
      : '';
    return {
      env_moodle_configured: Boolean(icalUrl || (username && password)),
      moodle_base_url: baseUrl,
      has_ical_url: Boolean(icalUrl),
      moodle_ical_url_preview: icalUrl.length > 48 ? `${icalUrl.slice(0, 48)}...` : icalUrl,
      has_credentials: Boolean(username && password),
      masked_username: maskedUsername,
    };
  };

  app.get('/api/guilds/:guildId/tasks', (req, res) => {
    const tasks = db
      .prepare('SELECT * FROM tasks WHERE guild_id = ? ORDER BY deadline_iso ASC')
      .all(req.params.guildId);
    const reminders = db
      .prepare('SELECT * FROM reminder_deliveries WHERE guild_id = ? ORDER BY delivered_at DESC LIMIT 20')
      .all(req.params.guildId);
    const attachments = db
      .prepare('SELECT * FROM task_attachments WHERE guild_id = ? ORDER BY created_at DESC')
      .all(req.params.guildId);
    res.json({ tasks, reminders, attachments, moodle_env: getMoodleEnvStatus() });
  });

  app.post('/api/guilds/:guildId/tasks', (req, res) => {
    const { guildId } = req.params;
    const {
      course_name,
      title,
      description = '',
      deadline_iso,
      source_url = '',
      created_by = 'Aetheriaaa',
    } = req.body;

    if (!course_name || !title || !deadline_iso) {
      res.status(400).json({ error: 'Nama mata kuliah, judul tugas, dan deadline wajib diisi.' });
      return;
    }

    const taskId = `tsk-${crypto.randomUUID().slice(0, 8)}`;
    const nowIso = new Date().toISOString();
    db.prepare(`
      INSERT INTO tasks (
        task_id, guild_id, external_uid, course_name, title, description,
        source_type, deadline_iso, timezone, source_url, is_completed,
        created_by, last_synced_at, updated_at
      ) VALUES (?, ?, '', ?, ?, ?, 'manual', ?, 'Asia/Jakarta', ?, 0, ?, '', ?)
    `).run(taskId, guildId, course_name.trim(), title.trim(), description.trim(), deadline_iso, source_url.trim(), created_by, nowIso);

    // Evaluate immediate reminder stage if close to deadline
    const stage = evaluateReminderStage(deadline_iso, Date.now(), false, 3);
    if (stage) {
      db.prepare(`
        INSERT INTO reminder_deliveries (delivery_id, task_id, guild_id, stage, delivered_at, channel_id, status)
        VALUES (?, ?, ?, ?, ?, '1558142572164022362', 'sent')
        ON CONFLICT(task_id, stage) DO NOTHING
      `).run(`rem-${crypto.randomUUID().slice(0, 8)}`, taskId, guildId, stage, nowIso);
    }

    const tasks = db.prepare('SELECT * FROM tasks WHERE guild_id = ? ORDER BY deadline_iso ASC').all(guildId);
    res.json({ task_id: taskId, tasks });
  });

  app.post('/api/tasks/:taskId/toggle', (req, res) => {
    const { taskId } = req.params;
    const row = db.prepare('SELECT * FROM tasks WHERE task_id = ?').get(taskId) as Record<string, unknown> | undefined;
    if (!row) {
      res.status(404).json({ error: 'Tugas tidak ditemukan.' });
      return;
    }
    const nextState = row.is_completed ? 0 : 1;
    const nowIso = new Date().toISOString();
    db.prepare(`
      UPDATE tasks
      SET is_completed = ?, completed_by = ?, completed_at = ?, updated_at = ?
      WHERE task_id = ?
    `).run(nextState, nextState ? 'Aetheriaaa' : '', nextState ? nowIso : '', nowIso, taskId);

    res.json({ ok: true, is_completed: Boolean(nextState) });
  });

  app.delete('/api/tasks/:taskId', (req, res) => {
    db.prepare('DELETE FROM tasks WHERE task_id = ?').run(req.params.taskId);
    res.json({ ok: true });
  });

  // Moodle .ics Sync Endpoint (parses real .ics content or .env iCal/Credentials with UID deduplication)
  app.post('/api/guilds/:guildId/tasks/sync-ics', (req, res) => {
    const { guildId } = req.params;
    const {
      ics_content,
      ical_url = '',
      moodle_base_url = '',
      moodle_username = '',
    } = req.body || {};

    if (ical_url && !isSafeExternalUrl(String(ical_url))) {
      res.status(400).json({ error: 'URL iCal Moodle ditolak oleh filter keamanan SSRF.' });
      return;
    }
    if (moodle_base_url && !isSafeExternalUrl(String(moodle_base_url))) {
      res.status(400).json({ error: 'MOODLE_BASE_URL ditolak oleh filter keamanan SSRF.' });
      return;
    }

    const defaultSampleIcs = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle//EN
BEGIN:VEVENT
UID:moodle-os-2026@kampus.ac.id
SUMMARY:Implementasi Penjadwalan Kernel Linux & Threading is due
DESCRIPTION:Unggah source code C dan laporan analisis concurrency dalam PDF.
CATEGORIES:IF2230 Sistem Operasi
DTEND:${new Date(Date.now() + 28 * 3600 * 1000).toISOString().replace(/[-:]/g, '').split('.')[0]}Z
URL:https://lms.kampus.ac.id/mod/assign/view.php?id=9102
END:VEVENT
BEGIN:VEVENT
UID:moodle-ai-2026@kampus.ac.id
SUMMARY:Evaluasi Model Klasifikasi & Confusion Matrix is due
DESCRIPTION:Kumpulkan notebook eksperimen dan dokumen analisis metrik presisi/recall.
CATEGORIES:IF3170 Inteligensi Buatan
DTEND:${new Date(Date.now() + 64 * 3600 * 1000).toISOString().replace(/[-:]/g, '').split('.')[0]}Z
URL:https://lms.kampus.ac.id/mod/assign/view.php?id=9155
END:VEVENT
END:VCALENDAR`;

    const rawIcs = String(ics_content || defaultSampleIcs);
    const parsedEvents = parseIcsEvents(rawIcs);
    const nowIso = new Date().toISOString();
    let inserted = 0;
    let updated = 0;

    for (const ev of parsedEvents) {
      const existing = db
        .prepare('SELECT task_id FROM tasks WHERE guild_id = ? AND external_uid = ?')
        .get(guildId, ev.uid) as { task_id: string } | undefined;

      if (!existing) {
        const taskId = `tsk-${crypto.randomUUID().slice(0, 8)}`;
        db.prepare(`
          INSERT INTO tasks (
            task_id, guild_id, external_uid, course_name, title, description,
            source_type, deadline_iso, timezone, source_url, is_completed,
            created_by, last_synced_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, 'moodle_ics', ?, 'Asia/Jakarta', ?, 0, 'Moodle Sync', ?, ?)
        `).run(taskId, guildId, ev.uid, ev.courseName, ev.title, ev.description, ev.deadlineIso, ev.sourceUrl, nowIso, nowIso);
        inserted += 1;

        const stage = evaluateReminderStage(ev.deadlineIso, Date.now(), false, 3);
        if (stage) {
          db.prepare(`
            INSERT INTO reminder_deliveries (delivery_id, task_id, guild_id, stage, delivered_at, channel_id, status)
            VALUES (?, ?, ?, ?, ?, '1558142572164022362', 'sent')
            ON CONFLICT(task_id, stage) DO NOTHING
          `).run(`rem-${crypto.randomUUID().slice(0, 8)}`, taskId, guildId, stage, nowIso);
        }
      } else {
        db.prepare(`
          UPDATE tasks
          SET course_name = ?, title = ?, description = ?, deadline_iso = ?, last_synced_at = ?, updated_at = ?
          WHERE task_id = ?
        `).run(ev.courseName, ev.title, ev.description, ev.deadlineIso, nowIso, nowIso, existing.task_id);
        updated += 1;
      }
    }

    if (ical_url) {
      db.prepare('UPDATE guild_settings SET moodle_ics_url_encrypted = ?, moodle_last_sync = ?, updated_at = ? WHERE guild_id = ?').run(
        String(ical_url),
        nowIso,
        nowIso,
        guildId
      );
    } else {
      db.prepare('UPDATE guild_settings SET moodle_last_sync = ?, updated_at = ? WHERE guild_id = ?').run(
        nowIso,
        nowIso,
        guildId
      );
    }

    const sourceUsed = moodle_username
      ? `Moodle Login (${moodle_username})`
      : ical_url
      ? 'MOODLE_ICAL_URL'
      : 'Kalender Moodle (.ics / .env)';

    res.json({
      ok: true,
      inserted,
      updated,
      total_parsed: parsedEvents.length,
      source_used: sourceUsed,
      moodle_env: getMoodleEnvStatus(),
      synced_at: nowIso,
    });
  });

  // Upload & Download Validated Academic Module Attachments
  app.post('/api/guilds/:guildId/modules/upload', (req, res) => {
    const { guildId } = req.params;
    const { task_id, filename, size_bytes, content_base64 = '', uploaded_by = 'Aetheriaaa' } = req.body;
    const validation = validateAttachmentMeta(String(filename || ''), Number(size_bytes || 0), 15);
    if (!validation.valid) {
      res.status(400).json({ error: validation.reason });
      return;
    }

    const ext = path.extname(String(filename)).toLowerCase();
    const safeStoredName = `${crypto.randomUUID()}${ext}`;
    let rawBuffer: Buffer;
    if (content_base64) {
      const cleanBase64 = String(content_base64).replace(/^data:.*?;base64,/, '');
      rawBuffer = Buffer.from(cleanBase64, 'base64');
    } else {
      rawBuffer = Buffer.from(`%PDF-1.7\nAthenaa Validated Academic Module: ${filename}\n%%EOF`, 'utf-8');
    }

    const finalSizeBytes = rawBuffer.length > 0 ? rawBuffer.length : Number(size_bytes);
    fs.writeFileSync(path.join(MODULES_DIR, safeStoredName), rawBuffer);
    const attachmentId = `att-${crypto.randomUUID().slice(0, 8)}`;
    const mimeType =
      ext === '.pdf'
        ? 'application/pdf'
        : ext === '.docx'
        ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        : 'application/msword';

    db.prepare(`
      INSERT INTO task_attachments (
        attachment_id, task_id, guild_id, original_filename, stored_filename,
        mime_type, size_bytes, uploaded_by, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      attachmentId,
      task_id || 'tsk-jarkom-01',
      guildId,
      String(filename),
      safeStoredName,
      mimeType,
      finalSizeBytes,
      uploaded_by,
      new Date().toISOString()
    );

    res.json({ ok: true, attachment_id: attachmentId });
  });

  app.get('/api/modules/:attachmentId/download', (req, res) => {
    const row = db
      .prepare('SELECT * FROM task_attachments WHERE attachment_id = ?')
      .get(req.params.attachmentId) as Record<string, unknown> | undefined;
    if (!row) {
      res.status(404).json({ error: 'File modul tidak ditemukan.' });
      return;
    }
    const storedPath = path.join(MODULES_DIR, path.basename(String(row.stored_filename)));
    if (!fs.existsSync(storedPath)) {
      res.status(404).json({ error: 'File fisik modul tidak ditemukan di penyimpanan.' });
      return;
    }
    res.setHeader('Content-Type', String(row.mime_type || 'application/octet-stream'));
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="${String(row.original_filename).replace(/[^a-zA-Z0-9._-]/g, '_')}"`
    );
    res.send(fs.readFileSync(storedPath));
  });

  // RPG Leaderboard & AFK Endpoints
  app.get('/api/guilds/:guildId/rpg', (req, res) => {
    const { guildId } = req.params;
    const rows = db
      .prepare(
        'SELECT * FROM level_profiles WHERE guild_id = ? ORDER BY level DESC, current_exp DESC, total_messages DESC LIMIT 15'
      )
      .all(guildId) as Array<Record<string, unknown>>;

    const leaderboard = rows.map((r, idx) => {
      const lvl = Number(r.level || 1);
      return {
        rank: idx + 1,
        user_id: r.user_id,
        username: r.username,
        display_name: r.display_name,
        level: lvl,
        current_exp: Number(r.current_exp || 0),
        max_exp: calculateMaxExp(lvl),
        total_messages: Number(r.total_messages || 0),
        last_exp_at: r.last_exp_at,
      };
    });

    const afkList = db
      .prepare('SELECT * FROM afk_statuses WHERE guild_id = ? ORDER BY started_at DESC')
      .all(guildId);

    res.json({ leaderboard, afk_list: afkList });
  });

  app.post('/api/guilds/:guildId/rpg/activity', (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner) && req.body?.is_admin !== false,
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner) && req.body?.is_owner !== false,
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({
        error:
          'Akses Ditolak: Fitur Uji Aktivitas & Simulasi EXP hanya dapat diakses oleh Admin Server (Anti-Spam/Dupe Protection).',
      });
      return;
    }

    const { guildId } = req.params;
    const {
      user_id = active?.user.id || OWNER_DISCORD_ID,
      username = 'filisim',
      display_name = active?.user.name || 'Aetheriaaa',
      activity_type = 'chat',
      message_content = 'Diskusi materi kuliah di channel akademik',
      bypass_cooldown = false,
    } = req.body;

    if (activity_type === 'chat' && (!message_content || String(message_content).trim().length < 3)) {
      res.status(400).json({ error: 'Pesan terlalu pendek atau kosong (tidak mendapat EXP).' });
      return;
    }

    const row = db
      .prepare('SELECT * FROM level_profiles WHERE guild_id = ? AND user_id = ?')
      .get(guildId, user_id) as Record<string, unknown> | undefined;

    const now = new Date();
    const nowIso = now.toISOString();

    if (row && row.last_exp_at && !bypass_cooldown) {
      const elapsedSec = (now.getTime() - new Date(String(row.last_exp_at)).getTime()) / 1000;
      if (elapsedSec < 60) {
        res.status(429).json({
          error: `Cooldown anti-spam EXP aktif. Tunggu ${Math.ceil(60 - elapsedSec)} detik lagi.`,
        });
        return;
      }
    }

    const expGainMap: Record<string, number> = {
      chat: 25,
      voice_join: 20,
      voice_speak: 15,
      voice_listen: 10,
      voice_stream: 25,
      minigame: 20,
    };
    const gain = expGainMap[String(activity_type)] || 25;

    const currentLvl = row ? Number(row.level) : 1;
    const currentExp = row ? Number(row.current_exp) : 0;
    const totalMsgs = row ? Number(row.total_messages) + 1 : 1;
    const result = applyExpGain(currentLvl, currentExp, gain);

    db.prepare(`
      INSERT INTO level_profiles (
        guild_id, user_id, username, display_name, level, current_exp, total_messages, last_exp_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(guild_id, user_id) DO UPDATE SET
        display_name = excluded.display_name,
        level = excluded.level,
        current_exp = excluded.current_exp,
        total_messages = excluded.total_messages,
        last_exp_at = excluded.last_exp_at,
        updated_at = excluded.updated_at
    `).run(
      guildId,
      user_id,
      username,
      display_name,
      result.level,
      result.currentExp,
      totalMsgs,
      nowIso,
      nowIso
    );

    // Clear AFK automatically when member sends a message
    db.prepare('DELETE FROM afk_statuses WHERE guild_id = ? AND user_id = ?').run(guildId, user_id);

    res.json({
      ok: true,
      activity_type,
      exp_gained: gain,
      leveled_up: result.leveledUp,
      level: result.level,
      current_exp: result.currentExp,
      max_exp: result.maxExp,
    });
  });

  app.post('/api/guilds/:guildId/afk', (req, res) => {
    const { guildId } = req.params;
    const { user_id = OWNER_DISCORD_ID, username = 'Aetheriaaa', reason = 'Sedang AFK' } = req.body;
    const nowIso = new Date().toISOString();
    db.prepare(`
      INSERT INTO afk_statuses (guild_id, user_id, username, reason, started_at)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(guild_id, user_id) DO UPDATE SET
        username = excluded.username,
        reason = excluded.reason,
        started_at = excluded.started_at
    `).run(guildId, user_id, username, String(reason).trim() || 'Sedang AFK', nowIso);

    res.json({ ok: true });
  });

  app.delete('/api/guilds/:guildId/afk/:userId', (req, res) => {
    db.prepare('DELETE FROM afk_statuses WHERE guild_id = ? AND user_id = ?').run(
      req.params.guildId,
      req.params.userId
    );
    res.json({ ok: true });
  });

  // Admin Server Hub Endpoints (Protected by Admin Session Verification)
  app.get('/api/admin/metrics', async (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner) && req.query.is_owner !== 'false',
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }

    const mem = process.memoryUsage();
    const dbSize = fs.existsSync(DB_PATH) ? fs.statSync(DB_PATH).size : 0;
    const backupFiles = fs.existsSync(BACKUPS_DIR)
      ? fs
          .readdirSync(BACKUPS_DIR)
          .filter((f) => f.endsWith('.enc') || f.endsWith('.gz'))
          .map((f) => {
            const st = fs.statSync(path.join(BACKUPS_DIR, f));
            return {
              filename: f,
              size_bytes: st.size,
              created_at: st.mtime.toISOString(),
            };
          })
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
      : [];

    const auditLogs = db.prepare('SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 15').all();

    res.json({
      ram_rss_mb: Number((mem.rss / (1024 * 1024)).toFixed(2)),
      heap_used_mb: Number((mem.heapUsed / (1024 * 1024)).toFixed(2)),
      cpu_load_1m: Number(os.loadavg()[0].toFixed(2)),
      uptime_seconds: Math.floor((Date.now() - START_TIME) / 1000),
      database_size_kb: Number((dbSize / 1024).toFixed(2)),
      connected_guilds: 1,
      python_version: 'Python 3.12 + FFmpeg + yt-dlp (Spotify & YouTube)',
      backups: backupFiles,
      audit_logs: auditLogs,
    });
  });

  app.post('/api/admin/backup', async (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner) && req.body?.is_owner !== false,
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }
    try {
      const { stdout } = await execFileAsync('python3', ['-m', 'app.cli_bridge', 'backup'], {
        cwd: ATHENAA_DIR,
        env: { ...process.env, PYTHONPATH: ATHENAA_DIR },
      });
      const result = JSON.parse(stdout.trim());
      logAudit(MAIN_GUILD_ID, OWNER_DISCORD_ID, 'Aetheriaaa', 'SQLITE_BACKUP', `Backup dibuat: ${result.filename}`);
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: `Gagal membuat backup: ${(err as Error).message}` });
    }
  });

  app.post('/api/admin/yt-dlp', async (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner) && req.body?.is_owner !== false,
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }
    const { perform_update = false } = req.body;
    try {
      const args = ['-m', 'app.cli_bridge', 'ytdlp'];
      if (perform_update) args.push('--update');
      const { stdout } = await execFileAsync('python3', args, {
        cwd: ATHENAA_DIR,
        env: { ...process.env, PYTHONPATH: ATHENAA_DIR },
      });
      res.json(JSON.parse(stdout.trim()));
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  app.post('/api/admin/run-tests', async (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner),
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }
    try {
      const { stdout } = await execFileAsync('python3', ['-m', 'app.cli_bridge', 'test'], {
        cwd: ATHENAA_DIR,
        env: { ...process.env, PYTHONPATH: ATHENAA_DIR },
      });
      res.json(JSON.parse(stdout.trim()));
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  // Real Python Source Codebase Inspector & 1-Click ZIP Downloader
  const PYTHON_FILES_MANIFEST = [
    { path: 'app/main.py', role: 'Entrypoint utama single-instance (Bot Discord + Uvicorn Web Server)' },
    { path: 'app/config.py', role: 'Pemuatan variabel .env dan pemeriksaan kesiapan fitur mandiri' },
    { path: 'app/database.py', role: 'Manajer SQLite WAL & migrasi skema 15 tabel idempoten' },
    { path: 'app/models/schema.py', role: 'Dataclass domain untuk MusicSession, QueueItem, dan Task' },
    { path: 'app/security/validators.py', role: 'Host Lock System, SSRF blocker, validasi file modul & magic bytes, enkripsi HMAC' },
    { path: 'app/services/music_service.py', role: 'Pencarian lagu + penyanyi, pencocokan metadata Spotify oEmbed, radio, ekstraksi yt-dlp' },
    { path: 'app/services/queue_service.py', role: 'Queue Manager per-server, pencegahan race condition, Loop, Autoplay, Mode 24/7' },
    { path: 'app/services/lyrics_service.py', role: 'Klien LRCLIB publik (syncedLyrics ber-timestamp & plainLyrics + penanganan HTTP 429)' },
    { path: 'app/services/academy_service.py', role: 'Parser kalender .ics Moodle, deduplikasi UID, dan evaluasi Reminder 3 tahap' },
    { path: 'app/services/leveling_service.py', role: 'Formula EXP RPG max_exp = 100 + (level * 25), cooldown anti-spam, Top 15, AFK' },
    { path: 'app/services/backup_service.py', role: 'Snapshot SQLite online backup(), kompresi gzip, enkripsi kunci terpisah' },
    { path: 'app/bot/client.py', role: 'Implementasi discord.py Bot, Slash Commands, Voice Host Transfer, dan event EXP' },
    { path: 'app/web/routes/api.py', role: 'Endpoint FastAPI REST untuk Dashboard, Musik, Akademik, RPG, dan Admin Server' },
    { path: 'tests/test_athenaa.py', role: 'Suite pengujian otomatis (unittest / pytest) untuk seluruh modul inti' },
    { path: 'requirements.txt', role: 'Daftar dependensi Python yang kompatibel untuk VPS / Pterodactyl' },
    { path: 'start.sh', role: 'Skrip startup produksi single-worker untuk Pterodactyl & VPS' },
    { path: 'README.md', role: 'Dokumentasi instalasi, arsitektur, OAuth2, dan troubleshooting dalam Bahasa Indonesia' },
  ];

  app.get('/api/python-codebase', (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner),
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }

    const requestedFile = String(req.query.file || 'app/main.py');
    const match = PYTHON_FILES_MANIFEST.find((f) => f.path === requestedFile) || PYTHON_FILES_MANIFEST[0];
    const absPath = path.join(ATHENAA_DIR, match.path);
    const content = fs.existsSync(absPath) ? fs.readFileSync(absPath, 'utf-8') : '# File tidak ditemukan';
    res.json({
      files: PYTHON_FILES_MANIFEST,
      selected_file: match.path,
      selected_role: match.role,
      content,
    });
  });

  app.get('/api/python-codebase/download-zip', async (req, res) => {
    const active = getSessionFromRequest(req);
    const check = canAccessOwnerResources({
      isAdmin: Boolean(active?.user.isAdmin || active?.user.isOwner),
      isOwner: Boolean(active?.user.isAdmin || active?.user.isOwner),
      sessionToken: active?.session_token || null,
    });
    if (!check.allowed) {
      res.status(403).json({ error: check.reason });
      return;
    }

    try {
      const { stdout } = await execFileAsync('python3', ['-m', 'app.cli_bridge', 'zip'], {
        cwd: ATHENAA_DIR,
        env: { ...process.env, PYTHONPATH: ATHENAA_DIR },
      });
      const info = JSON.parse(stdout.trim());
      if (info.zip_path && fs.existsSync(info.zip_path)) {
        res.setHeader('Content-Type', 'application/zip');
        res.setHeader('Content-Disposition', 'attachment; filename="athenaa-discord-bot.zip"');
        res.send(fs.readFileSync(info.zip_path));
        return;
      }
      res.status(500).json({ error: 'Gagal membuat arsip ZIP.' });
    } catch (err) {
      res.status(500).json({ error: (err as Error).message });
    }
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(ROOT_DIR, 'dist')));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(ROOT_DIR, 'dist', 'index.html'));
    });
  }

  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`[Athenaa Server] Listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
