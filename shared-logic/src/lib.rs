//! Athenaa Shared Logic - Core domain logic shared between Python and TypeScript
//! Compiled to WASM for use in both environments

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;
use wasm_bindgen::prelude::*;

// ============================================================================
// Types
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncedLyricLine {
    pub time_sec: f64,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HostLockContext {
    pub user_id: String,
    pub user_roles: Vec<String>,
    pub is_admin: bool,
    pub is_owner: bool,
    pub session_host_id: String,
    pub dj_role_id: String,
    pub action: String,
    pub target_item_requester_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedIcsEvent {
    pub uid: String,
    pub course_name: String,
    pub title: String,
    pub description: String,
    pub deadline_iso: String,
    pub source_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpResult {
    pub leveled_up: bool,
    pub level: u32,
    pub current_exp: u64,
    pub max_exp: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HostLockResult {
    pub allowed: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReminderStageResult {
    pub stage: Option<String>,  // "H-3d", "H-6h", "H-1h", or null
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub valid: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SingleSessionResult {
    pub previous_token_revoked: Option<String>,
    pub active_token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OwnerAccessResult {
    pub allowed: bool,
    pub reason: String,
}

// ============================================================================
// Errors
// ============================================================================

#[derive(Error, Debug, Serialize, Deserialize)]
pub enum SharedError {
    #[error("Invalid input: {0}")]
    InvalidInput(String),
    #[error("Parse error: {0}")]
    ParseError(String),
    #[error("Validation failed: {0}")]
    ValidationError(String),
    #[error("Internal error: {0}")]
    Internal(String),
}

impl From<SharedError> for JsValue {
    fn from(err: SharedError) -> JsValue {
        JsValue::from_str(&err.to_string())
    }
}

// ============================================================================
// RPG EXP Formula
// ============================================================================

/// Official Athenaa RPG EXP progression formula:
/// max_exp = 100 + (level * 25)
#[wasm_bindgen]
pub fn calculate_max_exp(level: u32) -> u64 {
    let safe_level = level.max(1);
    100 + (safe_level as u64 * 25)
}

/// Apply EXP gain and calculate level-ups
#[wasm_bindgen]
pub fn apply_exp_gain(current_level: u32, current_exp: u64, exp_gain: u64) -> ExpResult {
    let mut level = current_level.max(1);
    let mut exp = current_exp.saturating_add(exp_gain);
    let mut leveled_up = false;
    let mut max_exp = calculate_max_exp(level);

    while exp >= max_exp {
        exp -= max_exp;
        level += 1;
        leveled_up = true;
        max_exp = calculate_max_exp(level);
    }

    ExpResult {
        leveled_up,
        level,
        current_exp: exp,
        max_exp,
    }
}

// ============================================================================
// Host Lock System
// ============================================================================

/// Host Lock System validation rules:
/// - Bot Owner, Server Administrator, and DJ Role can control all queue actions.
/// - Active Session Host can control queue during their session.
/// - Regular members can only remove items they requested themselves.
#[wasm_bindgen]
pub fn can_control_queue(ctx: HostLockContext) -> HostLockResult {
    if ctx.is_owner || ctx.is_admin {
        return HostLockResult {
            allowed: true,
            reason: "Diizinkan (Administrator / Owner).".to_string(),
        };
    }
    if !ctx.dj_role_id.is_empty() && ctx.user_roles.contains(&ctx.dj_role_id) {
        return HostLockResult {
            allowed: true,
            reason: "Diizinkan (Role DJ).".to_string(),
        };
    }
    if ctx.session_host_id.is_empty() || ctx.session_host_id == ctx.user_id {
        return HostLockResult {
            allowed: true,
            reason: "Diizinkan (Session Host).".to_string(),
        };
    }
    if ctx.action == "remove_item"
        && ctx.target_item_requester_id.is_some()
        && ctx.target_item_requester_id.unwrap() == ctx.user_id
    {
        return HostLockResult {
            allowed: true,
            reason: "Diizinkan (Menghapus lagu milik sendiri).".to_string(),
        };
    }

    HostLockResult {
        allowed: false,
        reason: format!(
            "Host Lock aktif: Hanya Session Host (<@{}>), Role DJ, atau Administrator yang dapat menjalankan aksi \"{}\".",
            ctx.session_host_id, ctx.action
        ),
    }
}

// ============================================================================
// LRCLIB Synced Lyrics Parser
// ============================================================================

/// Parses LRC format syncedLyrics from LRCLIB into sorted timestamped lines.
#[wasm_bindgen]
pub fn parse_lrc_lyrics(raw_lrc: String) -> Vec<SyncedLyricLine> {
    if raw_lrc.trim().is_empty() {
        return vec![];
    }

    let mut lines = Vec::new();
    // Regex: [mm:ss.xx]text or [mm:ss]text
    let regex = regex::Regex::new(r"^\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\](.*)$").unwrap();

    for raw_line in raw_lrc.lines() {
        let line = raw_line.trim();
        if let Some(captures) = regex.captures(line) {
            let mins: u64 = captures[1].parse().unwrap_or(0);
            let secs: u64 = captures[2].parse().unwrap_or(0);
            let frac_str = captures.get(3).map(|m| m.as_str()).unwrap_or("0");
            let frac: f64 = frac_str.parse::<u64>().unwrap_or(0) as f64 / 10_f64.powi(frac_str.len() as i32);
            let text = captures[4].trim().to_string();
            
            lines.push(SyncedLyricLine {
                time_sec: (mins * 60 + secs) as f64 + frac,
                text: if text.is_empty() { "♪".to_string() } else { text },
            });
        }
    }

    lines.sort_by(|a, b| a.time_sec.partial_cmp(&b.time_sec).unwrap());
    lines
}

/// Finds the active lyric line index for the given playback position in seconds.
#[wasm_bindgen]
pub fn get_active_lyric_index(lines: Vec<SyncedLyricLine>, position_sec: f64) -> i32 {
    if lines.is_empty() {
        return -1;
    }
    let mut active_idx = -1;
    for (i, line) in lines.iter().enumerate() {
        if position_sec >= line.time_sec {
            active_idx = i as i32;
        } else {
            break;
        }
    }
    active_idx
}

// ============================================================================
// 3-Stage Reminder Evaluation
// ============================================================================

/// Evaluates which 3-stage reminder ('H-3d', 'H-6h', 'H-1h') applies to a task.
#[wasm_bindgen]
pub fn evaluate_reminder_stage(
    deadline_iso: String,
    now_ms: u64,
    is_completed: bool,
    days_before: u32,
) -> ReminderStageResult {
    if is_completed {
        return ReminderStageResult { stage: None };
    }

    let deadline_ms = chrono::DateTime::parse_from_rfc3339(&deadline_iso)
        .map(|dt| dt.timestamp_millis() as u64)
        .unwrap_or(0);

    if deadline_ms == 0 || deadline_ms <= now_ms {
        return ReminderStageResult { stage: None };
    }

    let hours_left = (deadline_ms as f64 - now_ms as f64) / (1000.0 * 60.0 * 60.0);
    
    let stage = if hours_left <= 1.0 {
        Some("H-1h".to_string())
    } else if hours_left <= 6.0 {
        Some("H-6h".to_string())
    } else if hours_left <= (days_before as f64 * 24.0) {
        Some(format!("H-{}d", days_before))
    } else {
        None
    };

    ReminderStageResult { stage }
}

// ============================================================================
// Moodle .ics Task Filter (Submittable Tasks Only)
// ============================================================================

#[wasm_bindgen]
pub fn is_submittable_or_due_task(
    summary: String,
    description: String,
    url: String,
    has_due_prop: bool,
    event_type: String,
) -> bool {
    let s = summary.trim().to_lowercase();
    let d = description.trim().to_lowercase();
    let u = url.trim().to_lowercase();
    let ev_type = event_type.trim().to_lowercase();
    let full_text = format!("{} {}", s, d).trim().to_string();

    if s.is_empty() {
        return false;
    }

    // 1. Exclude lecturer materials, modules, slides, resource downloads, reading pages
    if u.contains("/mod/resource/")
        || u.contains("/mod/folder/")
        || u.contains("/mod/page/")
        || u.contains("/mod/url/")
        || u.contains("/mod/book/")
        || u.contains("/mod/label/")
    {
        return false;
    }

    // 2. Exclude events that only mark when an activity opens (not the turn-in due date)
    let opens_keywords = ["opens", "is open", "dibuka", "mulai dibuka", "tersedia mulai"];
    let due_keywords = ["due", "closes", "berakhir", "deadline", "tenggat", "kumpul", "submit", "turn in"];
    
    let is_opens_only = opens_keywords.iter().any(|kw| s.ends_with(kw) || s.contains(kw))
        && !due_keywords.iter().any(|kw| full_text.contains(kw));
    
    if is_opens_only || ev_type == "open" || ev_type == "opens" {
        return false;
    }

    // 3. Exclude pure attendance / presensi / absensi logs without task indicators
    let is_attendance_only = (s.contains("attendance")
        || s.contains("presensi")
        || s.contains("absensi")
        || s.contains("daftar hadir")
        || u.contains("/mod/attendance/"))
        && !full_text.contains("tugas")
        && !full_text.contains("assign")
        && !full_text.contains("kumpul")
        && !full_text.contains("submit")
        && !full_text.contains("turn in")
        && !full_text.contains("laporan")
        && !full_text.contains("praktikum")
        && !full_text.contains("laprak")
        && !full_text.contains("kuis")
        && !full_text.contains("quiz")
        && !full_text.contains("ujian")
        && !full_text.contains("uts")
        && !full_text.contains("uas")
        && !full_text.contains("proyek")
        && !full_text.contains("project");
    
    if is_attendance_only {
        return false;
    }

    // 4. Exclude pure module/lecture file announcements (no turn-in action)
    let is_pure_module = (s.contains("materi")
        || s.contains("slide")
        || s.contains("bahan ajar")
        || s.contains("bahan kuliah")
        || s.contains("silabus")
        || s.contains("handout")
        || s.contains("catatan kuliah")
        || s.contains("buku ajar")
        || s.contains("referensi")
        || s.contains("bacaan")
        || s.contains("rekaman perkuliahan")
        || s.contains("video materi"))
        && !full_text.contains("tugas")
        && !full_text.contains("assign")
        && !full_text.contains("assignment")
        && !full_text.contains("kumpul")
        && !full_text.contains("pengumpulan")
        && !full_text.contains("submit")
        && !full_text.contains("turn in")
        && !full_text.contains("upload")
        && !full_text.contains("unggah")
        && !full_text.contains("laporan")
        && !full_text.contains("praktikum")
        && !full_text.contains("laprak")
        && !full_text.contains("kuis")
        && !full_text.contains("quiz")
        && !full_text.contains("ujian")
        && !full_text.contains("uts")
        && !full_text.contains("uas")
        && !full_text.contains("project")
        && !full_text.contains("proyek")
        && !full_text.contains("tubes")
        && !full_text.contains("tugas besar");
    
    if is_pure_module {
        return false;
    }

    // Filter out titles starting with "Modul N", "Pertemuan N" that don't have task keywords
    let modul_pattern = regex::Regex::new(r"^(modul|pertemuan|bab|ch\.|chapter|sesi|unit)\s+\d+[\s:.-]*$").unwrap();
    let modul_prefix_pattern = regex::Regex::new(r"^(modul|pertemuan|materi)\b").unwrap();
    let task_keywords = regex::Regex::new(r"\b(tugas|kumpul|submit|turn in|laporan|laprak|praktikum|assign|due|deadline|tenggat|unggah|upload)\b").unwrap();

    if modul_pattern.is_match(&s) 
        || (modul_prefix_pattern.is_match(&s) && !task_keywords.is_match(&full_text)) {
        return false;
    }

    // 5. Positive matching: ONLY accept if submittable module URL or explicit turn-in keywords
    if u.contains("/mod/assign/")
        || u.contains("/mod/quiz/")
        || u.contains("/mod/workshop/")
        || u.contains("/mod/turnitintool")
        || u.contains("/mod/turnitintooltwo/")
    {
        return true;
    }

    // Explicit turn-in / submission keywords
    let explicit_keywords = [
        "is due", "due", "closes", "tenggat", "deadline", "tugas", "assign",
        "assignment", "kumpul", "pengumpulan", "submit", "submission", "turn in",
        "unggah tugas", "upload tugas", "upload file", "laporan praktikum",
        "laprak", "laporan", "praktikum", "kuis", "quiz", "uts", "uas", "ujian",
        "proyek", "project", "tubes", "tugas besar", "makalah", "responsi", "lembar kerja",
    ];
    
    if explicit_keywords.iter().any(|kw| full_text.contains(kw)) {
        return true;
    }

    false
}

/// Parse Moodle/Waskita .ics calendar text into structured academic tasks
#[wasm_bindgen]
pub fn parse_ics_events(ics_text: String) -> Vec<ParsedIcsEvent> {
    if ics_text.trim().is_empty() {
        return vec![];
    }

    let unfolded = ics_text.replace("\r\n ", "").replace("\n ", "");
    let mut events = Vec::new();
    let mut in_event = false;
    let mut fields: HashMap<String, String> = HashMap::new();

    for raw_line in unfolded.lines() {
        let line = raw_line.trim();
        
        if line == "BEGIN:VEVENT" {
            in_event = true;
            fields.clear();
            continue;
        }
        
        if line == "END:VEVENT" {
            in_event = false;
            
            let uid = fields.get("UID").map(|s| s.trim()).unwrap_or("").to_string();
            let summary = fields.get("SUMMARY").map(|s| s.trim()).unwrap_or("").to_string();
            let has_due = fields.contains_key("DTEND") || fields.contains_key("DUE");
            let dt_raw = fields.get("DTEND")
                .or_else(|| fields.get("DUE"))
                .or_else(|| fields.get("DTSTART"))
                .map(|s| s.trim())
                .unwrap_or("");
            let description = fields.get("DESCRIPTION")
                .map(|s| s.replace("\\\\n", "\n").trim().to_string())
                .unwrap_or_default();
            let source_url = fields.get("URL").map(|s| s.trim()).unwrap_or("").to_string();

            if !uid.is_empty() && !summary.is_empty() && !dt_raw.is_empty() {
                if is_submittable_or_due_task(
                    summary.clone(),
                    description.clone(),
                    source_url.clone(),
                    has_due,
                    String::new(),
                ) {
                    // Parse datetime: YYYYMMDDTHHMMSSZ or YYYYMMDD
                    let datetime_regex = regex::Regex::new(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?").unwrap();
                    if let Some(caps) = datetime_regex.captures(dt_raw) {
                        let y = &caps[1];
                        let m = &caps[2];
                        let d = &caps[3];
                        let hh = caps.get(4).map(|m| m.as_str()).unwrap_or("23");
                        let mm = caps.get(5).map(|m| m.as_str()).unwrap_or("59");
                        let ss = caps.get(6).map(|m| m.as_str()).unwrap_or("00");
                        let z = caps.get(7).map(|m| m.as_str()).unwrap_or("");
                        
                        let iso_str = if z == "Z" {
                            format!("{}-{}-{}T{}:{}:{}.000Z", y, m, d, hh, mm, ss)
                        } else {
                            format!("{}-{}-{}T{}:{}:{}+07:00", y, m, d, hh, mm, ss)
                        };

                        let mut course_name = fields.get("CATEGORIES")
                            .map(|s| s.trim().to_string())
                            .unwrap_or_default();
                        
                        if course_name.is_empty() && summary.contains('[') && summary.contains(']') {
                            let start = summary.find('[').unwrap() + 1;
                            let end = summary.find(']').unwrap();
                            course_name = summary[start..end].trim().to_string();
                        }
                        if course_name.is_empty() {
                            course_name = "Waskita Akademik".to_string();
                        }

                        let cleaned_title = summary
                            .replace(" is due", "")
                            .replace(" closes", "")
                            .replace(" berakhir", "")
                            .replace(" jatuh tempo", "")
                            .trim()
                            .to_string();

                        events.push(ParsedIcsEvent {
                            uid,
                            course_name,
                            title: cleaned_title,
                            description,
                            deadline_iso: iso_str,
                            source_url,
                        });
                    }
                }
            }
            continue;
        }

        if in_event && line.contains(':') {
            let idx = line.find(':').unwrap();
            let key_part = line[..idx].split(';').next().unwrap().to_uppercase();
            let val_part = line[idx + 1..].to_string();
            fields.insert(key_part, val_part);
        }
    }

    events
}

// ============================================================================
// Module Attachment Validation
// ============================================================================

#[wasm_bindgen]
pub fn validate_attachment_meta(filename: String, size_bytes: u64, max_mb: u32) -> ValidationResult {
    if filename.is_empty() || filename.contains('\0') {
        return ValidationResult {
            valid: false,
            reason: "Nama file tidak valid.".to_string(),
        };
    }

    if filename.contains("..") || filename.contains('/') || filename.contains('\\') {
        return ValidationResult {
            valid: false,
            reason: "Terdeteksi percobaan path traversal pada nama file.".to_string(),
        };
    }

    let lower = filename.to_lowercase();
    let allowed = [".pdf", ".doc", ".docx"];
    let has_allowed_ext = allowed.iter().any(|ext| lower.ends_with(ext));
    
    if !has_allowed_ext {
        return ValidationResult {
            valid: false,
            reason: "Ekstensi file ditolak. Hanya .pdf, .doc, dan .docx yang diizinkan.".to_string(),
        };
    }

    if size_bytes == 0 {
        return ValidationResult {
            valid: false,
            reason: "File kosong tidak dapat diunggah.".to_string(),
        };
    }

    let max_bytes = (max_mb as u64) * 1024 * 1024;
    if size_bytes > max_bytes {
        return ValidationResult {
            valid: false,
            reason: format!("Ukuran file melebihi batas maksimum {} MB.", max_mb),
        };
    }

    ValidationResult {
        valid: true,
        reason: "OK".to_string(),
    }
}

// ============================================================================
// Single Session Enforcement (1 session per Discord user)
// ============================================================================

#[wasm_bindgen]
pub fn enforce_single_discord_session(
    active_by_user_id: HashMap<String, String>,
    discord_user_id: String,
    new_session_token: String,
) -> SingleSessionResult {
    let clean_user_id = discord_user_id.trim();
    let previous_token = active_by_user_id.get(&clean_user_id).cloned();
    
    let mut new_map = active_by_user_id;
    new_map.insert(clean_user_id, new_session_token.clone());
    
    SingleSessionResult {
        previous_token_revoked: if let Some(prev) = previous_token {
            if prev != new_session_token { Some(prev) } else { None }
        } else { None },
        active_token: new_session_token,
    }
}

// ============================================================================
// Owner Resource Access Control
// ============================================================================

#[wasm_bindgen]
pub fn can_access_owner_resources(is_owner: bool, session_token: Option<String>) -> OwnerAccessResult {
    if session_token.is_none() || session_token.as_ref().unwrap().trim().is_empty() {
        return OwnerAccessResult {
            allowed: false,
            reason: "Sesi login Discord tidak valid. Silakan login terlebih dahulu.".to_string(),
        };
    }
    
    if !is_owner {
        return OwnerAccessResult {
            allowed: false,
            reason: "Akses Ditolak: Kode Bot Python dan unduhan .zip khusus untuk Bot Owner.".to_string(),
        };
    }
    
    OwnerAccessResult {
        allowed: true,
        reason: "Diizinkan (Bot Owner).".to_string(),
    }
}

// ============================================================================
// Song Identity Normalization (for deduplication)
// ============================================================================

#[wasm_bindgen]
pub fn normalize_title_only(title: String) -> String {
    let clean_t = clean_youtube_title(title, "").0;
    let no_brackets = regex::Regex::new(r"\s*[\(\[\{].*?[\)\]\}]").unwrap().replace_all(&clean_t, " ");
    let core = VERSION_MODIFIERS_RE.replace_all(&no_brackets, " ");
    let core = regex::Regex::new(r"\b(the|a|an)\b").unwrap().replace_all(&core, " ");
    let res = regex::Regex::new(r"[^\w]+").unwrap().replace_all(&core.to_lowercase(), "").replace("_", "");
    if res.len() >= 3 {
        return res.to_string();
    }
    let fallback = regex::Regex::new(r"[^\w]+").unwrap().replace_all(&clean_t.to_lowercase(), "").replace("_", "");
    if fallback.is_empty() { clean_t.to_lowercase() } else { fallback }
}

#[wasm_bindgen]
pub fn normalize_artist_only(artist: String) -> String {
    let primary = regex::Regex::new(r"[,&/]|(?:\bfeat\.?\b)|(?:\bft\.?\b)|(?:\bwith\b)").unwrap().split(&artist).next().unwrap_or("");
    let clean_a = clean_youtube_title("", primary).1;
    let core_a = VERSION_MODIFIERS_RE.replace_all(&clean_a, " ");
    regex::Regex::new(r"[^\w]+").unwrap().replace_all(&core_a.to_lowercase(), "").replace("_", "")
}

#[wasm_bindgen]
pub fn normalize_song_identity(title: String, artist: String) -> String {
    format!("{}::{}", normalize_title_only(title), normalize_artist_only(artist))
}

#[wasm_bindgen]
pub fn is_same_base_song(title_1: String, title_2: String) -> bool {
    let n1 = normalize_title_only(title_1);
    let n2 = normalize_title_only(title_2);
    if n1.is_empty() || n2.is_empty() {
        return false;
    }
    if n1 == n2 {
        return true;
    }
    if n1.len() >= 5 && n2.len() >= 5 && (n1.contains(&n2) || n2.contains(&n1)) {
        return true;
    }
    false
}

// ============================================================================
// Helpers
// ============================================================================

const VERSION_MODIFIERS_RE: &str = r"\b(remix|remixed|slowed|slow|reverb|sped\s*up|speed\s*up|nightcore|daycore|dj|bass\s*boosted|bassboost|jedag\s*jedug|jj|tiktok|douyin|viral|trend|trending|version|ver|ori|original|edit|bootleg|flip|mashup|mix|extended|radio\s*edit|acoustic|akustik|live|cover|koplo|dangdut|instrumental|karaoke|official|audio|video|music|lyrics?l?|lirik|lagu|terbaru|ost|soundtrack|theme|song|prod|feat|ft|with|by|x)\b";

lazy_static::lazy_static! {
    static ref VERSION_MODIFIERS_REGEX: regex::Regex = regex::Regex::new(VERSION_MODIFIERS_RE).unwrap();
    static ref YOUTUBE_JUNK_BRACKET_REGEX: regex::Regex = regex::Regex::new(r"\s*(?:[\(\[\{][^\)\]\}]*?(?:official|lyric|lirik|video|audio|mv|visualizer|live|performance|hd|hq|4k|remastered|terbaru|lagu|clip|ost|soundtrack|karaoke|sub\s*indo|eng\s*sub)[^\)\]\}]*?[\)\]\}]|\|.*$|//.*$)").unwrap();
    static ref YOUTUBE_TRAILING_TAG_REGEX: regex::Regex = regex::Regex::new(r"\s*[-–—:]?\s*\b(?:official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics|mv|visualizer)|lyric\s*video|video\s*lirik|full\s*lirik|with\s*lyrics|audio\s*only)\s*$").unwrap();
}

fn clean_youtube_title_and_artist(raw_title: String, channel_name: String) -> (String, String) {
    let mut cleaned_title = html_escape::decode_html(&raw_title).trim().to_string();
    let mut cleaned_channel = html_escape::decode_html(&channel_name).trim().to_string();
    
    cleaned_channel = regex::Regex::new(r"\s*-\s*Topic$").unwrap().replace(&cleaned_channel, "").to_string();
    cleaned_channel = regex::Regex::new(r"\s*(?:Official(?:\s*Channel|\s*Music)?|VEVO|Music|Records|Entertainment|Indonesia|ID)\s*$").unwrap().replace(&cleaned_channel, "").trim().to_string();

    for _ in 0..3 {
        cleaned_title = YOUTUBE_JUNK_BRACKET_REGEX.replace(&cleaned_title, "").trim_matches(|c| " -–—|:·.".contains(c)).to_string();
        cleaned_title = YOUTUBE_TRAILING_TAG_REGEX.replace(&cleaned_title, "").trim_matches(|c| " -–—|:·.".contains(c)).to_string();
    }

    let mut artist_out = cleaned_channel.clone();
    let mut song_out = cleaned_title.clone();

    for sep in [" - ", " – ", " — "] {
        if sep.contains(&cleaned_title) {
            let parts: Vec<&str> = cleaned_title.splitn(2, sep).collect();
            if parts.len() == 2 {
                let left = parts[0].trim().trim_matches('"').trim_matches('\'');
                let right = parts[1].trim().trim_matches('"').trim_matches('\'');
                if !left.is_empty() && !right.is_empty() {
                    if YOUTUBE_TRAILING_TAG_REGEX.is_match(right) {
                        song_out = left.to_string();
                    } else {
                        artist_out = left.to_string();
                        song_out = right.to_string();
                    }
                    break;
                }
            }
        }
    }

    for _ in 0..2 {
        song_out = YOUTUBE_JUNK_BRACKET_REGEX.replace(&song_out, "").trim_matches(|c| " -–—|:·.\"'" .contains(c)).to_string();
        song_out = YOUTUBE_TRAILING_TAG_REGEX.replace(&song_out, "").trim_matches(|c| " -–—|:·.\"'" .contains(c)).to_string();
        artist_out = YOUTUBE_JUNK_BRACKET_REGEX.replace(&artist_out, "").trim_matches(|c| " -–—|:·.\"'" .contains(c)).to_string();
    }

    song_out = regex::Regex::new(r"\.{2,}$").unwrap().replace(&song_out, "").trim().to_string();
    song_out = normalize_casing(&song_out).unwrap_or_else(|| "Unknown Track".to_string());
    artist_out = normalize_casing(&artist_out).unwrap_or_else(|| "Spotify Artist".to_string());
    
    (song_out, artist_out)
}

fn normalize_casing(text: &str) -> Option<String> {
    let s = text.trim();
    if s.is_empty() {
        return None;
    }
    let letters: Vec<char> = s.chars().filter(|c| c.is_alphabetic() && c.is_ascii()).collect();
    if letters.len() >= 4 && letters.iter().all(|c| c.is_uppercase()) {
        let upper = s.to_uppercase();
        if ["SZA", "RAN", "SO7", "BCL", "GAC", "BTS", "NIKI", "TXT", "OST"].contains(&upper.as_str()) {
            return Some(upper);
        }
        return Some(s.chars().enumerate().map(|(i, c)| if i == 0 { c.to_uppercase().to_string() } else { c.to_lowercase().to_string() }).collect());
    }
    Some(s.to_string())
}

#[wasm_bindgen]
pub fn init() {
    console_error_panic_hook::set_once();
}