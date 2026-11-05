import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateMaxExp,
  applyExpGain,
  canControlQueue,
  parseLrcLyrics,
  getActiveLyricIndex,
  evaluateReminderStage,
  parseIcsEvents,
  validateAttachmentMeta,
  canAccessOwnerResources,
  enforceSingleDiscordSession,
} from './athenaaRules';

test('RPG leveling formula calculates max_exp = 100 + (level * 25) and handles level up', () => {
  assert.equal(calculateMaxExp(1), 125);
  assert.equal(calculateMaxExp(4), 200);

  const res = applyExpGain(1, 115, 20);
  assert.equal(res.leveledUp, true);
  assert.equal(res.level, 2);
  assert.equal(res.currentExp, 10);
  assert.equal(res.maxExp, 150);
});

test('Host Lock system enforces session host, DJ override, and own-item removal', () => {
  const blockedSkip = canControlQueue({
    userId: 'user-regular',
    userRoles: [],
    isAdmin: false,
    isOwner: false,
    sessionHostId: 'user-host',
    djRoleId: 'role-dj',
    action: 'skip',
  });
  assert.equal(blockedSkip.allowed, false);

  const allowedOwnRemove = canControlQueue({
    userId: 'user-regular',
    userRoles: [],
    isAdmin: false,
    isOwner: false,
    sessionHostId: 'user-host',
    djRoleId: 'role-dj',
    action: 'remove_item',
    targetItemRequesterId: 'user-regular',
  });
  assert.equal(allowedOwnRemove.allowed, true);

  const allowedDj = canControlQueue({
    userId: 'user-dj',
    userRoles: ['role-dj'],
    isAdmin: false,
    isOwner: false,
    sessionHostId: 'user-host',
    djRoleId: 'role-dj',
    action: 'shuffle',
  });
  assert.equal(allowedDj.allowed, true);
});

test('LRCLIB synced lyrics parser and active timestamp finder work accurately', () => {
  const sample = '[00:05.00] Baris pembuka\n[00:12.50] Baris kedua lagu\n[00:20.00] Reff utama';
  const parsed = parseLrcLyrics(sample);
  assert.equal(parsed.length, 3);
  assert.equal(parsed[1].timeSec, 12.5);
  assert.equal(getActiveLyricIndex(parsed, 3), -1);
  assert.equal(getActiveLyricIndex(parsed, 14), 1);
  assert.equal(getActiveLyricIndex(parsed, 25), 2);
});

test('Moodle .ics parser filters only submittable/due-date tasks and 3-stage reminder evaluator works', () => {
  const ics = [
    'BEGIN:VCALENDAR',
    'BEGIN:VEVENT',
    'UID:evt-99@moodle.kampus.id',
    'SUMMARY:Tugas Besar Basis Data is due',
    'CATEGORIES:IF2240 Basis Data',
    'DTEND:20261120T160000Z',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'UID:evt-open@moodle.kampus.id',
    'SUMMARY:Kuis 1 Jaringan Komputer opens',
    'CATEGORIES:IF3130 Jaringan Komputer',
    'DTSTART:20261118T010000Z',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'UID:evt-att@moodle.kampus.id',
    'SUMMARY:Attendance Pertemuan 9 (Presensi)',
    'CATEGORIES:IF3130 Jaringan Komputer',
    'DTEND:20261119T030000Z',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'UID:evt-module-resource@moodle.kampus.id',
    'SUMMARY:Modul Pertemuan 5 - Jaringan Komputer 1',
    'DESCRIPTION:File modul materi PDF dikirim oleh dosen.',
    'CATEGORIES:IF3130 Jaringan Komputer',
    'URL:https://lms.kampus.ac.id/mod/resource/view.php?id=8831',
    'DTEND:20261119T030000Z',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'UID:evt-slide@moodle.kampus.id',
    'SUMMARY:Slide Kuliah Bab 4 Threading',
    'DESCRIPTION:Bahan ajar perkuliahan untuk dipelajari.',
    'CATEGORIES:IF2230 Sistem Operasi',
    'DTEND:20261119T030000Z',
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\n');

  const events = parseIcsEvents(ics);
  assert.equal(events.length, 1);
  assert.equal(events[0].uid, 'evt-99@moodle.kampus.id');
  assert.equal(events[0].title, 'Tugas Besar Basis Data');
  assert.equal(events[0].courseName, 'IF2240 Basis Data');

  const deadlineMs = new Date(events[0].deadlineIso).getTime();
  assert.equal(
    evaluateReminderStage(events[0].deadlineIso, deadlineMs - 4 * 3600 * 1000, false, 3),
    'H-6h'
  );
  assert.equal(
    evaluateReminderStage(events[0].deadlineIso, deadlineMs - 30 * 60 * 1000, false, 3),
    'H-1h'
  );
  assert.equal(
    evaluateReminderStage(events[0].deadlineIso, deadlineMs - 30 * 60 * 1000, true, 3),
    null
  );
});

test('Module attachment security validator blocks path traversal, bad extensions, and >15MB', () => {
  assert.equal(validateAttachmentMeta('Modul_Aljabar.pdf', 1024 * 500, 15).valid, true);
  assert.equal(validateAttachmentMeta('../secret.pdf', 1024, 15).valid, false);
  assert.equal(validateAttachmentMeta('payload.exe', 1024, 15).valid, false);
  assert.equal(validateAttachmentMeta('oversized.docx', 16 * 1024 * 1024, 15).valid, false);
});

test('Owner-only Python codebase & ZIP access and 1-user-1-session lock work accurately', () => {
  assert.equal(
    canAccessOwnerResources({ isOwner: false, sessionToken: 'sess_member_123' }).allowed,
    false
  );
  assert.equal(
    canAccessOwnerResources({ isOwner: true, sessionToken: '' }).allowed,
    false
  );
  assert.equal(
    canAccessOwnerResources({ isOwner: true, sessionToken: 'sess_owner_999' }).allowed,
    true
  );

  const sessions = new Map<string, string>();
  const first = enforceSingleDiscordSession(sessions, '998877665544332211', 'tok_1');
  assert.equal(first.previousTokenRevoked, null);
  assert.equal(first.activeToken, 'tok_1');

  const second = enforceSingleDiscordSession(sessions, '998877665544332211', 'tok_2');
  assert.equal(second.previousTokenRevoked, 'tok_1');
  assert.equal(second.activeToken, 'tok_2');
  assert.equal(sessions.get('998877665544332211'), 'tok_2');
});

