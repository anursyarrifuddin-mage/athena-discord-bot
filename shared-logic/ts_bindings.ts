// TypeScript bindings for Athenaa Shared Logic (WASM)
// Generated from shared-logic Rust crate

export interface SyncedLyricLine {
  time_sec: number;
  text: string;
}

export interface HostLockContext {
  user_id: string;
  user_roles: string[];
  is_admin: boolean;
  is_owner: boolean;
  session_host_id: string;
  dj_role_id: string;
  action: string;
  target_item_requester_id?: string;
}

export interface ParsedIcsEvent {
  uid: string;
  course_name: string;
  title: string;
  description: string;
  deadline_iso: string;
  source_url: string;
}

export interface ExpResult {
  leveled_up: boolean;
  level: number;
  current_exp: number;
  max_exp: number;
}

export interface HostLockResult {
  allowed: boolean;
  reason: string;
}

export interface ReminderStageResult {
  stage: string | null;
}

export interface ValidationResult {
  valid: boolean;
  reason: string;
}

export interface SingleSessionResult {
  previous_token_revoked: string | null;
  active_token: string;
}

export interface OwnerAccessResult {
  allowed: boolean;
  reason: string;
}

export interface SharedLogicModule {
  // EXP Formula
  calculate_max_exp(level: number): number;
  apply_exp_gain(current_level: number, current_exp: number, exp_gain: number): ExpResult;
  
  // Host Lock
  can_control_queue(ctx: HostLockContext): HostLockResult;
  
  // Lyrics
  parse_lrc_lyrics(raw_lrc: string): SyncedLyricLine[];
  get_active_lyric_index(lines: SyncedLyricLine[], position_sec: number): number;
  
  // Reminders
  evaluate_reminder_stage(deadline_iso: string, now_ms: number, is_completed: boolean, days_before: number): ReminderStageResult;
  
  // Moodle .ics
  is_submittable_or_due_task(summary: string, description: string, url: string, has_due_prop: boolean, event_type: string): boolean;
  parse_ics_events(ics_text: string): ParsedIcsEvent[];
  
  // Attachments
  validate_attachment_meta(filename: string, size_bytes: number, max_mb: number): ValidationResult;
  
  // Session
  enforce_single_discord_session(active_by_user_id: Record<string, string>, discord_user_id: string, new_session_token: string): SingleSessionResult;
  
  // Owner access
  can_access_owner_resources(is_owner: boolean, session_token: string | null): OwnerAccessResult;
  
  // Song identity
  normalize_title_only(title: string): string;
  normalize_artist_only(artist: string): string;
  normalize_song_identity(title: string, artist: string): string;
  is_same_base_song(title_1: string, title_2: string): boolean;
  
  // Init
  init(): void;
}

let _module: SharedLogicModule | null = null;
let _initPromise: Promise<void> | null = null;

/**
 * Initialize the shared logic module (loads WASM)
 */
export async function initSharedLogic(wasmUrl?: string): Promise<SharedLogicModule> {
  if (_module) return _module;
  if (_initPromise) {
    await _initPromise;
    return _module!;
  }

  _initPromise = (async () => {
    // Dynamic import of wasm-bindgen generated module
    const { default: init, ...exports } = await import(
      wasmUrl || new URL('./pkg/athenaa_shared.js', import.meta.url).href
    );
    
    await init();
    
    _module = {
      calculate_max_exp: exports.calculate_max_exp,
      apply_exp_gain: exports.apply_exp_gain,
      can_control_queue: exports.can_control_queue,
      parse_lrc_lyrics: exports.parse_lrc_lyrics,
      get_active_lyric_index: exports.get_active_lyric_index,
      evaluate_reminder_stage: exports.evaluate_reminder_stage,
      is_submittable_or_due_task: exports.is_submittable_or_due_task,
      parse_ics_events: exports.parse_ics_events,
      validate_attachment_meta: exports.validate_attachment_meta,
      enforce_single_discord_session: exports.enforce_single_discord_session,
      can_access_owner_resources: exports.can_access_owner_resources,
      normalize_title_only: exports.normalize_title_only,
      normalize_artist_only: exports.normalize_artist_only,
      normalize_song_identity: exports.normalize_song_identity,
      is_same_base_song: exports.is_same_base_song,
      init: exports.init,
    };
  })();

  await _initPromise;
  return _module!;
}

/**
 * Get the initialized module (must call initSharedLogic first)
 */
export function getSharedLogic(): SharedLogicModule {
  if (!_module) {
    throw new Error('SharedLogic not initialized. Call initSharedLogic() first.');
  }
  return _module;
}

/**
 * Convenience functions (matching existing TS API in athenaaRules.ts)
 */
export async function calculateMaxExp(level: number): Promise<number> {
  const mod = await initSharedLogic();
  return mod.calculate_max_exp(level);
}

export async function applyExpGain(currentLevel: number, currentExp: number, expGain: number): Promise<ExpResult> {
  const mod = await initSharedLogic();
  return mod.apply_exp_gain(currentLevel, currentExp, expGain);
}

export async function canControlQueue(ctx: HostLockContext): Promise<HostLockResult> {
  const mod = await initSharedLogic();
  return mod.can_control_queue(ctx);
}

export async function parseLrcLyrics(rawLrc: string): Promise<SyncedLyricLine[]> {
  const mod = await initSharedLogic();
  return mod.parse_lrc_lyrics(rawLrc);
}

export async function getActiveLyricIndex(lines: SyncedLyricLine[], positionSec: number): Promise<number> {
  const mod = await initSharedLogic();
  return mod.get_active_lyric_index(lines, positionSec);
}

export async function evaluateReminderStage(
  deadlineIso: string, 
  nowMs: number, 
  isCompleted: boolean, 
  daysBefore: number = 3
): Promise<ReminderStageResult> {
  const mod = await initSharedLogic();
  return mod.evaluate_reminder_stage(deadlineIso, nowMs, isCompleted, daysBefore);
}

export async function isSubmittableOrDueTask(
  summary: string,
  description: string,
  url: string,
  hasDueProp: boolean,
  eventType: string
): Promise<boolean> {
  const mod = await initSharedLogic();
  return mod.is_submittable_or_due_task(summary, description, url, hasDueProp, eventType);
}

export async function parseIcsEvents(icsText: string): Promise<ParsedIcsEvent[]> {
  const mod = await initSharedLogic();
  return mod.parse_ics_events(icsText);
}

export async function validateAttachmentMeta(
  filename: string, 
  sizeBytes: number, 
  maxMb: number = 15
): Promise<ValidationResult> {
  const mod = await initSharedLogic();
  return mod.validate_attachment_meta(filename, sizeBytes, maxMb);
}

export async function enforceSingleDiscordSession(
  activeByUserId: Record<string, string>,
  discordUserId: string,
  newSessionToken: string
): Promise<SingleSessionResult> {
  const mod = await initSharedLogic();
  return mod.enforce_single_discord_session(activeByUserId, discordUserId, newSessionToken);
}

export async function canAccessOwnerResources(
  isOwner: boolean, 
  sessionToken: string | null
): Promise<OwnerAccessResult> {
  const mod = await initSharedLogic();
  return mod.can_access_owner_resources(isOwner, sessionToken);
}

export async function normalizeTitleOnly(title: string): Promise<string> {
  const mod = await initSharedLogic();
  return mod.normalize_title_only(title);
}

export async function normalizeArtistOnly(artist: string): Promise<string> {
  const mod = await initSharedLogic();
  return mod.normalize_artist_only(artist);
}

export async function normalizeSongIdentity(title: string, artist: string): Promise<string> {
  const mod = await initSharedLogic();
  return mod.normalize_song_identity(title, artist);
}

export async function isSameBaseSong(title1: string, title2: string): Promise<boolean> {
  const mod = await initSharedLogic();
  return mod.is_same_base_song(title1, title2);
}