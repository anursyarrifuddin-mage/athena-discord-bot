/**
 * Pure domain logic for Athenaa Music Queue, Host Lock, LRCLIB Synced Lyrics,
 * Moodle .ics Parsing, 3-Stage Academy Reminders, and RPG Leveling.
 */

export interface SyncedLyricLine {
  timeSec: number;
  text: string;
}

export interface HostLockContext {
  userId: string;
  userRoles: string[];
  isAdmin: boolean;
  isOwner: boolean;
  sessionHostId: string;
  djRoleId: string;
  action: string;
  targetItemRequesterId?: string;
}

export interface ParsedIcsEvent {
  uid: string;
  courseName: string;
  title: string;
  description: string;
  deadlineIso: string;
  sourceUrl: string;
}

/**
 * Official Athenaa RPG EXP progression formula:
 * max_exp = 100 + (level * 25)
 */
export function calculateMaxExp(level: number): number {
  const safeLevel = Math.max(1, Math.floor(level));
  return 100 + safeLevel * 25;
}

export function applyExpGain(
  currentLevel: number,
  currentExp: number,
  expGain: number
): { leveledUp: boolean; level: number; currentExp: number; maxExp: number } {
  let level = Math.max(1, Math.floor(currentLevel));
  let exp = Math.max(0, Math.floor(currentExp)) + Math.max(0, Math.floor(expGain));
  let leveledUp = false;
  let maxExp = calculateMaxExp(level);

  while (exp >= maxExp) {
    exp -= maxExp;
    level += 1;
    leveledUp = true;
    maxExp = calculateMaxExp(level);
  }

  return { leveledUp, level, currentExp: exp, maxExp };
}

/**
 * Host Lock System validation rules (Per-Server: Admin, DJ, Member):
 * - Server Administrator and DJ Role can control all queue actions.
 * - Active Session Host can control queue during their session.
 * - Toggling autoplay or mode_247 is allowed for active session participants.
 * - Regular members can remove items they requested themselves.
 */
export function canControlQueue(ctx: HostLockContext): { allowed: boolean; reason: string } {
  if (ctx.isAdmin || ctx.isOwner) {
    return { allowed: true, reason: 'Diizinkan (Admin Server).' };
  }
  if (ctx.djRoleId && ctx.userRoles.includes(ctx.djRoleId)) {
    return { allowed: true, reason: 'Diizinkan (Role DJ).' };
  }
  if (ctx.userRoles.includes('role-dj') || ctx.userRoles.includes('dj') || ctx.userRoles.includes('admin')) {
    return { allowed: true, reason: 'Diizinkan (Role DJ / Admin).' };
  }
  if (ctx.action === 'autoplay' || ctx.action === 'mode_247' || ctx.action === 'loop') {
    return { allowed: true, reason: 'Diizinkan (Kontrol Mode Pemutaran).' };
  }
  if (!ctx.sessionHostId || ctx.sessionHostId === ctx.userId) {
    return { allowed: true, reason: 'Diizinkan (Session Host).' };
  }
  if (
    ctx.action === 'remove_item' &&
    ctx.targetItemRequesterId &&
    ctx.targetItemRequesterId === ctx.userId
  ) {
    return { allowed: true, reason: 'Diizinkan (Menghapus lagu milik sendiri).' };
  }

  return {
    allowed: false,
    reason: `Host Lock aktif: Hanya Session Host, pemilik Role DJ, atau Admin Server yang dapat menjalankan aksi "${ctx.action}".`,
  };
}

/**
 * Parses LRC format syncedLyrics from LRCLIB into sorted timestamped lines.
 */
export function parseLrcLyrics(rawLrc: string): SyncedLyricLine[] {
  if (!rawLrc) return [];
  const lines: SyncedLyricLine[] = [];
  const regex = /^\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\](.*)$/;

  for (const rawLine of rawLrc.split(/\r?\n/)) {
    const match = rawLine.trim().match(regex);
    if (!match) continue;
    const mins = parseInt(match[1], 10);
    const secs = parseInt(match[2], 10);
    const fracStr = match[3] || '0';
    const frac = parseInt(fracStr, 10) / Math.pow(10, fracStr.length);
    const text = match[4].trim() || '♪';
    lines.push({
      timeSec: Number((mins * 60 + secs + frac).toFixed(2)),
      text,
    });
  }

  return lines.sort((a, b) => a.timeSec - b.timeSec);
}

/**
 * Finds the active lyric line index for the given playback position in seconds.
 */
export function getActiveLyricIndex(lines: SyncedLyricLine[], positionSec: number): number {
  if (!lines.length) return -1;
  let activeIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (positionSec >= lines[i].timeSec) {
      activeIdx = i;
    } else {
      break;
    }
  }
  return activeIdx;
}

/**
 * Evaluates which 3-stage reminder ('H-3d', 'H-6h', 'H-1h') applies to a task.
 */
export function evaluateReminderStage(
  deadlineIso: string,
  nowMs: number,
  isCompleted: boolean,
  daysBefore: number = 3
): string | null {
  if (isCompleted) return null;
  const deadlineMs = new Date(deadlineIso).getTime();
  if (Number.isNaN(deadlineMs) || deadlineMs <= nowMs) return null;

  const hoursLeft = (deadlineMs - nowMs) / (1000 * 60 * 60);
  if (hoursLeft <= 1) return 'H-1h';
  if (hoursLeft <= 6) return 'H-6h';
  if (hoursLeft <= daysBefore * 24) return `H-${daysBefore}d`;
  return null;
}

/**
 * Determines whether a Moodle/Waskita calendar event represents an actionable
 * submittable assignment/quiz or task with a due date, excluding attendance/presensi,
 * lecture material/module downloads (which students cannot submit to), and 'activity opens' announcements.
 */
export function isSubmittableOrDueTask(params: {
  summary: string;
  description?: string;
  url?: string;
  hasDueOrEndProp?: boolean;
}): boolean {
  const summaryClean = (params.summary || '').trim().toLowerCase();
  const descClean = (params.description || '').trim().toLowerCase();
  const urlClean = (params.url || '').trim().toLowerCase();
  const fullText = `${summaryClean} ${descClean}`.trim();

  if (!summaryClean) return false;

  // 1. Exclude lecturer materials, modules, slides, resource downloads, and reading pages
  // (In Moodle/Waskita, these are resources for students to read/download, not places to turn in / upload work)
  if (
    urlClean.includes('/mod/resource/') ||
    urlClean.includes('/mod/folder/') ||
    urlClean.includes('/mod/page/') ||
    urlClean.includes('/mod/url/') ||
    urlClean.includes('/mod/book/') ||
    urlClean.includes('/mod/label/')
  ) {
    return false;
  }

  // 2. Exclude events that only mark when an activity opens (not the turn-in due date)
  if (
    /\b(opens|is open|dibuka|mulai dibuka|tersedia mulai)\s*$/i.test(summaryClean) &&
    !/\b(due|closes|berakhir|deadline|tenggat|kumpul|submit|turn in)\b/i.test(fullText)
  ) {
    return false;
  }

  // 3. Exclude pure attendance / presensi / absensi logs without task indicators
  const isAttendanceOnly =
    (/\b(attendance|presensi|absensi|daftar hadir)\b/i.test(summaryClean) ||
      urlClean.includes('/mod/attendance/')) &&
    !/\b(tugas|assign|assignment|kumpul|submit|turn in|laporan|praktikum|laprak|kuis|quiz|ujian|uts|uas|proyek|project)\b/i.test(
      fullText
    );
  if (isAttendanceOnly) {
    return false;
  }

  // 4. Exclude pure module/lecture file announcements sent by lecturers (no turn-in / student upload action)
  const isPureModuleOrSlide =
    /\b(materi|slide|bahan ajar|bahan kuliah|silabus|handout|catatan kuliah|buku ajar|referensi|bacaan|rekaman perkuliahan|video materi)\b/i.test(
      summaryClean
    ) &&
    !/\b(tugas|assign|assignment|kumpul|pengumpulan|submit|turn in|upload|unggah|laporan|praktikum|laprak|kuis|quiz|ujian|uts|uas|project|proyek|tubes|tugas besar)\b/i.test(
      fullText
    );
  if (isPureModuleOrSlide) {
    return false;
  }

  // Filter out titles starting with "Modul ..." or "Pertemuan ..." that don't have task/turn-in keywords
  if (
    /^(modul|pertemuan|bab|ch\.|chapter|sesi|unit)\s+\d+[\s:.-]*$/i.test(summaryClean) ||
    (/^(modul|pertemuan|materi)\b/i.test(summaryClean) &&
      !/\b(tugas|kumpul|submit|turn in|laporan|laprak|praktikum|assign|due|deadline|tenggat|unggah|upload)\b/i.test(fullText))
  ) {
    return false;
  }

  // 5. Positive matching: ONLY accept if it is a submittable module URL or has explicit student turn-in keywords
  if (
    urlClean.includes('/mod/assign/') ||
    urlClean.includes('/mod/quiz/') ||
    urlClean.includes('/mod/workshop/') ||
    urlClean.includes('/mod/turnitintool')
  ) {
    return true;
  }

  // Explicit turn-in / submission keywords
  if (
    /\b(is due|due|closes|tenggat|deadline|tugas|assign|assignment|kumpul|pengumpulan|submit|submission|turn in|unggah tugas|upload tugas|upload file|laporan praktikum|laprak|laporan|praktikum|kuis|quiz|uts|uas|ujian|proyek|project|tubes|tugas besar|makalah|responsi|lembar kerja)\b/i.test(
      fullText
    )
  ) {
    return true;
  }

  // Do not count non-turn-in module items as tasks
  return false;
}

/**
 * Parses Moodle/Waskita .ics calendar text into structured academic tasks,
 * filtering strictly for submittable / due-date tasks.
 */
export function parseIcsEvents(icsText: string): ParsedIcsEvent[] {
  if (!icsText) return [];
  const unfolded = icsText.replace(/\r?\n[ \t]/g, '');
  const events: ParsedIcsEvent[] = [];
  let inEvent = false;
  let fields: Record<string, string> = {};

  for (const rawLine of unfolded.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === 'BEGIN:VEVENT') {
      inEvent = true;
      fields = {};
      continue;
    }
    if (line === 'END:VEVENT') {
      inEvent = false;
      const uid = (fields['UID'] || '').trim();
      const summary = (fields['SUMMARY'] || '').trim();
      const hasDueOrEndProp = Boolean(fields['DTEND'] || fields['DUE']);
      const dtRaw = fields['DTEND'] || fields['DUE'] || fields['DTSTART'] || '';
      const description = (fields['DESCRIPTION'] || '').replace(/\\n/g, '\n').trim();
      const sourceUrl = (fields['URL'] || '').trim();

      if (
        uid &&
        summary &&
        dtRaw &&
        isSubmittableOrDueTask({
          summary,
          description,
          url: sourceUrl,
          hasDueOrEndProp,
        })
      ) {
        const dtMatch = dtRaw.match(/(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?/);
        if (dtMatch) {
          const [, y, m, d, hh = '23', mm = '59', ss = '00', z] = dtMatch;
          const isoStr = z
            ? `${y}-${m}-${d}T${hh}:${mm}:${ss}.000Z`
            : `${y}-${m}-${d}T${hh}:${mm}:${ss}+07:00`;
          let courseName = (fields['CATEGORIES'] || '').trim();
          if (!courseName && summary.includes('[') && summary.includes(']')) {
            courseName = summary.slice(summary.indexOf('[') + 1, summary.indexOf(']')).trim();
          }
          if (!courseName) courseName = 'Waskita Akademik';

          const cleanedTitle = summary
            .replace(/\s+is due$/i, '')
            .replace(/\s+closes$/i, '')
            .trim();

          events.push({
            uid,
            courseName,
            title: cleanedTitle,
            description,
            deadlineIso: new Date(isoStr).toISOString(),
            sourceUrl,
          });
        }
      }
      continue;
    }
    if (inEvent && line.includes(':')) {
      const idx = line.indexOf(':');
      const keyPart = line.slice(0, idx).split(';')[0].toUpperCase();
      const valPart = line.slice(idx + 1);
      fields[keyPart] = valPart;
    }
  }

  return events;
}

/**
 * Validates module attachment filename, size (<= 15 MB), and extension allowlist (.pdf, .doc, .docx).
 */
export function validateAttachmentMeta(
  filename: string,
  sizeBytes: number,
  maxMb: number = 15
): { valid: boolean; reason: string } {
  if (!filename || filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
    return { valid: false, reason: 'Nama file tidak valid atau mengandung karakter path traversal.' };
  }
  const lower = filename.toLowerCase();
  const allowed = ['.pdf', '.doc', '.docx'];
  const hasAllowedExt = allowed.some((ext) => lower.endsWith(ext));
  if (!hasAllowedExt) {
    return { valid: false, reason: 'Ekstensi file ditolak. Hanya .pdf, .doc, dan .docx yang diizinkan.' };
  }
  if (sizeBytes <= 0) {
    return { valid: false, reason: 'File kosong tidak dapat diunggah.' };
  }
  if (sizeBytes > maxMb * 1024 * 1024) {
    return { valid: false, reason: `Ukuran file melebihi batas maksimum ${maxMb} MB.` };
  }
  return { valid: true, reason: 'OK' };
}

/**
 * Verifies whether the current Discord user session is authorized to view or download
 * the Python Bot source code (.zip) and Admin Server Hub. Restricted to Server Admin.
 */
export function canAccessAdminResources(ctx: {
  isAdmin?: boolean;
  isOwner?: boolean;
  sessionToken?: string | null;
}): { allowed: boolean; reason: string } {
  if (!ctx.sessionToken || !ctx.sessionToken.trim()) {
    return {
      allowed: false,
      reason: 'Sesi login Discord tidak valid. Silakan login terlebih dahulu.',
    };
  }
  if (!ctx.isAdmin && !ctx.isOwner) {
    return {
      allowed: false,
      reason: 'Akses Ditolak: Kode Bot Python dan Admin Hub khusus untuk Admin Server.',
    };
  }
  return { allowed: true, reason: 'Diizinkan (Admin Server).' };
}

export const canAccessOwnerResources = canAccessAdminResources;


/**
 * Enforces 1 active session per Discord user ID.
 * If the user already had a previous session token, revokes the old token and binds the new one.
 */
export function enforceSingleDiscordSession(
  activeByUserId: Map<string, string>,
  discordUserId: string,
  newSessionToken: string
): { previousTokenRevoked: string | null; activeToken: string } {
  const cleanUserId = discordUserId.trim();
  const previousToken = activeByUserId.get(cleanUserId) || null;
  activeByUserId.set(cleanUserId, newSessionToken);
  return {
    previousTokenRevoked:
      previousToken && previousToken !== newSessionToken ? previousToken : null,
    activeToken: newSessionToken,
  };
}

