export type Severity = 'CRITICAL' | 'WARNING' | 'INFO';

export interface Production {
  production_id: string;
  name: string;
  director?: string;
  status?: string;
  description?: string;
  /** 'registered' when a person filled a form in, 'auto' when an ingest
   *  guessed the id from a filename. Worth showing: a typo in a filename
   *  should be recognisable rather than looking deliberate. */
  origin?: 'registered' | 'auto';
  created_at?: string;
  updated_at?: string;
  shoot_days: string[];
  total_events: number;
  total_takes: number;
  last_activity?: string | null;
}

export interface ProductionVocabulary {
  statuses: string[];
}

export interface SourceDocumentSummary {
  doc_id: string;
  production_id: string;
  shoot_day: string;
  filename: string;
  doc_type: string;
  department: string;
  checksum?: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface SourceDocument extends SourceDocumentSummary {
  content: string;
  is_pdf?: boolean;
  raw_url?: string;
  metadata: Record<string, any>;
}

export interface Discrepancy {
  discrepancy_id: string;
  production_id: string;
  shoot_day: string;
  entity_type: string;
  entity_id: string;
  discrepancy_type: string;
  severity: Severity;
  description: string;
  witnesses: Record<string, any>[];
  is_resolved: boolean;
  resolved_card?: string | null;
  resolution_note?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  created_at: string;
}

export interface ResolveDiscrepancyPayload {
  production_id: string;
  shoot_day: string;
  entity_id?: string;
  resolved_card?: string;
  resolution_note?: string;
  resolved_by?: string;
}

export interface VideoFileInfo {
  camera: string;
  file_name: string;
  camera_roll?: string;
  reel_tape?: string;
  codec?: string;
  recording_date?: string;
  fps?: number;
  iso?: number;
  tstop?: string;
  thumbnail_url?: string;
  volume_name?: string;
  file_size_bytes?: number;
  checksum?: string;
}

export interface AudioFileInfo {
  file_name: string;
  sound_roll?: string;
  codec?: string;
  timecode_in?: string;
  duration?: string;
  tracks?: string;
  sample_rate?: string;
  bit_depth?: string;
  note?: string;
  volume_name?: string;
  file_size_bytes?: number;
  checksum?: string;
}

export interface CameraAngle {
  camera: string;
  camera_roll?: string;
  file_name: string;
  thumbnail_url?: string;
  dop_spec?: any; // Used to override DoP defaults on a specific camera
}

export interface TakeRecord {
  scene: string;
  slate: string;
  take_id: string;
  intent?: Record<string, any> | null;
  belief: {
    camera?: Record<string, any>;
    sound?: Record<string, any>;
    script?: Record<string, any>;
  };
  existence: {
    dit?: Record<string, any>;
    silverstack?: Record<string, any>;
  };
  camera_cards: string[];
  sound_cards: string[];
  storage_volumes: string[];
  video_files: VideoFileInfo[];
  audio_files: AudioFileInfo[];
  camera_angles: CameraAngle[];
  codec?: string;
  recording_date?: string;
  thumbnail_url?: string;
  matched_media_files: Array<{
    file_name: string;
    camera_roll?: string;
    reel_tape?: string;
    codec?: string;
    recording_date?: string;
    fps?: number;
    iso?: number;
    tstop?: string;
    volume_name?: string;
    file_size_bytes?: number;
    checksum?: string;
    thumbnail_b64?: string;
  }>;
  source_documents: Array<{
    doc_id?: string;
    filename: string;
    department: string;
  }>;
  is_starred: boolean;
  is_pickup: boolean;
  is_wild_track?: boolean;
  is_vfx?: boolean;
  is_mos?: boolean;
  requirements?: Requirement[];
  open_requirements_count?: number;
  resolved_requirements_count?: number;
}

export interface DocumentRef {
  filename: string;
  doc_id: string;
}

export interface SequenceRecord {
  sequence: string;
  location: string;
  description: string;
  shoot_day: string;
  /** Every day this sequence was shot, this row's day included. More than one
   *  means the row in front of you is part of the sequence, not all of it. */
  shoot_days?: string[];
  date: string;
  cards: string[];
  camera_cards: string[];
  sound_cards: string[];
  script_log_doc?: DocumentRef | null;
  camera_a_doc?: DocumentRef | null;
  camera_b_doc?: DocumentRef | null;
  camera_c_doc?: DocumentRef | null;
  sound_log_doc?: DocumentRef | null;
  silverstack_thumbnail_doc?: DocumentRef | null;
  silverstack_volume_doc?: DocumentRef | null;
  silverstack_clips_doc?: DocumentRef | null;
  comments: string;
  has_discrepancy: boolean;
  is_wild_track: boolean;
  is_vfx: boolean;
  is_mos?: boolean;
  takes_count: number;
  circled_takes?: string[];
  circled_takes_count?: number;
  takes: string[];
  requirements?: Requirement[];
  open_requirements_count?: number;
  resolved_requirements_count?: number;
}

export interface UserProfile {
  handle: string;
  name: string;
  email: string;
  role: string;
  avatar_color: string;
}

export type CrewDepartment = 'editorial' | 'camera' | 'sound' | 'dit' | 'vfx' | 'production' | 'general';

export interface ProductionCrewMember {
  production_id: string;
  handle: string;
  name: string;
  email: string;
  role: string;
  department: CrewDepartment;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export type RequirementPriority = 'low' | 'medium' | 'high' | 'critical';
export type RequirementCategory = 'sound' | 'vfx' | 'edit' | 'color' | 'reshoot' | 'legal' | 'general';
export type RequirementStatus = 'open' | 'in_progress' | 'resolved' | 'blocked';
export type RequirementTargetType = 'production' | 'scene' | 'shot' | 'take';

export interface Requirement {
  requirement_id: string;
  production_id: string;
  shoot_day: string;
  target_type: RequirementTargetType;
  target_id: string;
  target_label: string;
  title: string;
  description: string;
  priority: RequirementPriority;
  category: RequirementCategory;
  created_by: string;
  assigned_to: string;
  status: RequirementStatus;
  resolution_note?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolCallTrace {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  rows: number;
  error?: string | null;
}

export interface AgentStep {
  step: string;
  status: 'ok' | 'warning' | 'error';
  detail: string;
  tool_call?: ToolCallTrace | null;
}

export interface ClickHouseMCPStatus {
  configured: boolean;
  available: boolean;
  server_url?: string | null;
  health_url?: string | null;
  transport: string;
  package_installed: boolean;
  reason?: string | null;
}

export interface GeminiEnterpriseStatus {
  configured: boolean;
  genai_available: boolean;
  adk_available: boolean;
  model: string;
  provider: string;
  reason?: string | null;
}

export interface WrapRescueBlocker {
  source: 'discrepancy' | 'unacknowledged_requirement';
  source_key: string;
  production_id: string;
  shoot_day: string;
  target_type: string;
  target_id: string;
  target_label: string;
  title: string;
  description: string;
  priority: RequirementPriority;
  category: RequirementCategory;
  assigned_to: string;
  status: Exclude<RequirementStatus, 'resolved'>;
  severity: string;
  score: number;
  age_hours?: number | null;
  missing_acknowledgement: boolean;
  evidence: Record<string, unknown>;
}

export interface WrapRequirementAction {
  action: 'created' | 'updated' | 'unchanged';
  requirement_id: string;
  blocker_source: string;
  target_label: string;
  assigned_to: string;
  status: string;
  priority: string;
}

export interface WrapRescueResult {
  production_id: string;
  shoot_day: string;
  actor: string;
  mcp_status: ClickHouseMCPStatus;
  gemini_status: GeminiEnterpriseStatus;
  steps: AgentStep[];
  tool_calls: ToolCallTrace[];
  blockers: WrapRescueBlocker[];
  requirement_actions: WrapRequirementAction[];
  final_memo: string;
  generated_at: string;
}

export interface AssistantQueueScene {
  scene: string;
  shoot_days: string[];
  target_label: string;
  assigned_to: string;
  requirement_id?: string | null;
  status: RequirementStatus;
  takes_count: number;
  circled_takes_count: number;
  document_count: number;
  clean_score: number;
  reasons: string[];
  blockers: string[];
}

export interface AssistantQueueAction {
  action: 'created' | 'updated' | 'unchanged';
  requirement_id: string;
  scene: string;
  assigned_to: string;
  status: string;
  priority: string;
}

export interface AssistantQueueResult {
  production_id: string;
  shoot_day: string;
  actor: string;
  assignees: string[];
  assigned_to: string;
  production_status: string;
  scenes: AssistantQueueScene[];
  requirement_actions: AssistantQueueAction[];
  summary: string;
  generated_at: string;
}

/** One recorded transition of a requirement. Append-only; never edited. */
export interface RequirementEvent {
  event_id: string;
  requirement_id: string;
  production_id: string;
  action: 'created' | 'updated' | 'reassigned' | 'status_changed' | 'resolved' | 'reopened' | 'deleted';
  status: string;
  priority: string;
  assigned_to: string;
  /** What moved, as {field: [before, after]}. */
  changes: Record<string, [unknown, unknown]>;
  note?: string | null;
  actor?: string | null;
  created_at: string;
}

export interface NotificationItem {
  notification_id: string;
  production_id: string;
  recipient_handle: string;
  actor_handle: string;
  notification_type: 'ASSIGNED' | 'RESOLVED' | 'STATUS_CHANGED' | 'COMMENT';
  requirement_id: string;
  title: string;
  message: string;
  target_type: RequirementTargetType;
  target_id: string;
  target_label: string;
  is_read: boolean;
  created_at: string;
}

export interface NotificationResponse {
  recipient_handle: string;
  unread_count: number;
  notifications: NotificationItem[];
}


/**
 * One axis of a character's personality, read from the screenplay.
 *
 * `score` is null where the script does not support a reading — a character
 * with four lines does not contain five of them. Null is a real answer and
 * must not be rendered as zero: zero on a radar draws a point at the centre,
 * which reads as "none of this trait" and is a claim nobody made.
 */
export interface PersonalityAxis {
  score: number | null;
  evidence: string | null;
}

/** The five axes, always the same five. See PersonalityPolygon. */
export interface PersonalityAxes {
  openness?: PersonalityAxis;
  conscientiousness?: PersonalityAxis;
  extraversion?: PersonalityAxis;
  agreeableness?: PersonalityAxis;
  emotional_volatility?: PersonalityAxis;
}

/** One line a character speaks, and where in the script to find it. */
export interface CharacterLine {
  ordinal: number;
  scene_number: string;
  heading: string;
  index_in_scene: number;
  parenthetical: string | null;
  line: string;
}

export interface CharacterLines {
  script_id: string;
  character: string;
  /** Named anywhere in the script, whether or not they speak. */
  known_character: boolean;
  /** Has a character profile, which is built from dialogue cues. */
  has_profile: boolean;
  scenes_present: string[];
  line_count: number;
  lines: CharacterLine[];
}

/** One take read off a script supervisor's lined page. */
export interface LinedPageTake {
  take_id: string;
  camera_rolls: string[];
  is_starred: boolean;
  is_pickup: boolean;
  is_vfx: boolean;
  is_false_start: boolean;
  is_wild_track: boolean;
  notes?: string | null;
}

export interface LinedPage {
  scene: string;
  slates: string[];
  takes: LinedPageTake[];
  lining_notes?: string | null;
  page_number?: number | null;
}

export interface UploadFeedback {
  tone: 'success' | 'warning' | 'error';
  message: string;
  /** What was read off the page, when anything was. */
  detail?: string | null;
  /** Why nothing, or not everything, could be read. Never silently dropped. */
  warnings?: string[];
}

/** What POST /api/upload/file returns. */
export interface UploadResult {
  status: string;
  doc_id: string;
  checksum: string;
  filename: string;
  production_id: string;
  shoot_day: string;
  detected_doc_type: string;
  detected_department: string;
  detected_axis: string;
  /** Whether the document needs vision to be read at all. */
  is_multimodal: boolean;
  /** What vision actually read, or null. Distinct from is_multimodal. */
  lined_page?: LinedPage | null;
  /** Why a page came back unread. Empty when there was nothing to report. */
  lining_warnings?: string[];
}

/**
 * An in-app confirmation prompt.
 *
 * The browser's own confirm() is unusable here: embedded and sandboxed contexts
 * return false without ever showing a dialog, so a guarded action silently does
 * nothing and looks like a dead button.
 */
export interface ConfirmPrompt {
  title: string;
  message: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}


// ==========================================
// Editorial Tags
//
// Three separate questions about a piece of coverage: how far along it is, what
// work it still needs, and what kind of shot it is. Kept apart because folding
// them together makes "how much is left" unanswerable.
// ==========================================

export type TagTargetType = 'scene' | 'shot';

/** Served by the backend so these labels are spelled in one place only. */
export interface TagVocabularyEntry {
  key: string;
  label: string;
  description: string;
  ordinal?: number;
}

export interface TagVocabulary {
  target_types: TagTargetType[];
  statuses: TagVocabularyEntry[];
  needs: TagVocabularyEntry[];
  descriptors: TagVocabularyEntry[];
}

export interface EditorialTag {
  production_id: string;
  target_type: TagTargetType;
  /** A scene number ('117') or a slate ('27/7'). */
  target_id: string;
  status: string | null;
  needs: string[];
  descriptors: string[];
  note: string | null;
  updated_by: string | null;
  updated_at: string;
}

export interface TagSummary {
  production_id: string;
  tagged_targets: number;
  by_status: Record<string, number>;
  no_status: number;
  by_need: Record<string, number>;
  by_descriptor: Record<string, number>;
}


/** One recorded change to a tag. The trail is served newest first. */
export interface TagHistoryEntry {
  event_id: string;
  production_id: string;
  target_type: TagTargetType;
  target_id: string;
  action: 'set' | 'cleared';
  status: string | null;
  needs: string[];
  descriptors: string[];
  note: string | null;
  actor: string | null;
  created_at: string;
}


/** One axis of the board: shots, or scenes, counted against what exists. */
export interface ProgressAxis {
  known: number;
  by_status: Record<string, number>;
  no_status: number;
  /** Tagged, but the spine has never seen it — kept apart from the count. */
  tagged_but_unknown: string[];
}

export interface OutstandingTarget {
  target_type: TagTargetType;
  target_id: string;
  status: string;
}

export interface PreEditingAssistantProgress {
  handle: string;
  assigned: number;
  pending: number;
  completed: number;
  scenes_completed: number;
  shots_completed: number;
  last_completed_at?: string | null;
}

export interface PreEditingCompletion {
  requirement_id: string;
  target_type: 'scene' | 'shot';
  target_id: string;
  target_label: string;
  assigned_to: string;
  resolved_by: string;
  resolved_at?: string | null;
}

export interface PreEditingProgress {
  total: number;
  completed: number;
  pending: number;
  completion_percent: number;
  status_counts: Record<RequirementStatus, number>;
  by_assistant: PreEditingAssistantProgress[];
  recent_completed: PreEditingCompletion[];
}

export interface CrewWorkloadItem {
  requirement_id: string;
  title: string;
  target_type: RequirementTargetType;
  target_id: string;
  target_label: string;
  shoot_day: string;
  status: RequirementStatus;
  priority: RequirementPriority;
  category: RequirementCategory;
  updated_at: string;
  created_by: string;
  created_at: string;
  last_action: RequirementEvent['action'];
  last_actor?: string | null;
  last_activity_at?: string | null;
}

export interface CrewWorkloadMember {
  handle: string;
  name: string;
  role: string;
  department: CrewDepartment;
  active: boolean;
  assigned: number;
  open: number;
  in_progress: number;
  blocked: number;
  completed: number;
  latest_activity_at?: string | null;
  latest_activity_actor?: string | null;
  latest_activity_action?: RequirementEvent['action'] | null;
  current: CrewWorkloadItem[];
}

export interface CrewWorkload {
  total_open: number;
  totals: {
    crew: number;
    assigned: number;
    open: number;
    in_progress: number;
    blocked: number;
    completed: number;
  };
  by_member: CrewWorkloadMember[];
}

export interface ProductionDashboard {
  production_id: string;
  shots: ProgressAxis;
  scenes: ProgressAxis;
  outstanding: Record<string, OutstandingTarget[]>;
  pre_editing: PreEditingProgress;
  crew_workload: CrewWorkload;
  vocabulary: TagVocabulary;
  recent: TagHistoryEntry[];
  shoot_days: string[];
}


// ==========================================
// Script context: the scene behind a slate
// ==========================================

export interface ScriptHighlight {
  start: number;
  end: number;
  /** The words the match rests on. Empty for a whole-scene highlight. */
  terms: string[];
  score: number;
}

/** How a highlight was arrived at. 'description' is inferred, not recorded. */
export type ScriptHighlightBasis = 'scene' | 'description' | 'none';

export interface ScriptSceneContext {
  scene_number: string;
  heading: string;
  body: string;
  highlight: ScriptHighlight | null;
  highlight_basis: ScriptHighlightBasis;
  /** Why there is no highlight, when there is none. */
  note: string | null;
}

export type ScriptContextStatus =
  | 'ok'
  | 'no_script_linked'
  | 'scene_not_in_script'
  | 'unreadable_target';

export interface ScriptContext {
  production_id: string;
  target_type: TagTargetType;
  target_id: string;
  script_id: string | null;
  script_title: string | null;
  scenes: ScriptSceneContext[];
  status: ScriptContextStatus;
  message: string | null;
}

export interface LinkedScript {
  production_id: string;
  script_id: string;
  linked_at: string;
  title?: string | null;
  author?: string | null;
  filename?: string | null;
}


// ==========================================
// The analytical spine
// ==========================================

/** A query answers null when there is no ClickHouse; [] when there is nothing. */
export type AnalyticsRows<T> = T[] | null;

export interface ProductionAnalytics {
  production_id: string;
  available: boolean;
  /** Why not, when it is not. Shown instead of an empty chart. */
  reason?: string;
  shape?: AnalyticsRows<{ axis: string; department: string; events: number; days: number }>;
  arrivals?: AnalyticsRows<{
    shoot_day: string; department: string; events: number;
    first_filed: string; last_filed: string;
  }>;
  roll_disagreements?: AnalyticsRows<{
    shoot_day: string; slate: string; take_id: string; camera: string;
    rolls: string[]; witnesses: string[];
  }>;
  /* The acknowledgement axis. REQ-10 asks for a department sync matrix; it was
     a gauge that could never fill, because the only baseline available was a
     wrap time with no date on it. These answer the same question from
     something the product records: who saw what, and when they took it on. */
  /** The department sync matrix. `measurement` says whether a row describes a
   *  handover or a backfill — paperwork imported long after the shoot has a
   *  correct lag that says nothing about the night it was filed. */
  sync_matrix?: AnalyticsRows<{
    shoot_day: string; department: string; events: number;
    first_filed: string; shoot_date: string; wrap_time: string;
    wrapped_at: string | null; lag_seconds: number | null; lag_hours: number | null;
    measurement: 'handover' | 'backfill' | null; measurable: boolean;
  }>;
  time_to_acknowledge?: AnalyticsRows<{
    department: string; target_type: string; acknowledged: number;
    avg_minutes: number; median_minutes: number; slowest_minutes: number;
  }>;
  unacknowledged_requirements?: AnalyticsRows<{
    requirement_id: string; status: string; priority: string;
    assigned_to: string; raised_at: string; views: number; acknowledgements: number;
  }>;
  unreviewed_days?: AnalyticsRows<{
    shoot_day: string; spine_events: number; views: number;
    acknowledgements: number; seen_by: string[];
  }>;
  department_attention?: AnalyticsRows<{
    department: string; actor: string; views: number;
    acknowledgements: number; distinct_targets: number; last_seen: string;
  }>;
  scene_coverage?: AnalyticsRows<{
    scene: string; days: number; shoot_days: string[];
    slates: number; takes: number; departments: string[];
  }>;
  editorial_state?: AnalyticsRows<{ status: string; targets: number }>;
  /* The audit as it stands, deduplicated server-side. `open` and `resolved`
     are the two sides of one ledger; a finding is on exactly one of them. */
  discrepancy_health?: AnalyticsRows<{
    discrepancy_type: string; severity: string; open: number; resolved: number;
    open_days: string[]; example: string;
  }>;
  requirement_ageing?: AnalyticsRows<{
    category: string; requirements: number;
    avg_hours_open: number; longest_hours_open: number; ever_blocked: number;
  }>;
  /* Workload: what people did, from the activity ledger. `mutations` and
     `views` are separate on purpose and must never be summed. Rows whose actor
     was a server-side fallback are already excluded from the per-actor
     query. A count of actions is activity, not effort. */
  actions_by_actor_and_day?: AnalyticsRows<{
    actor: string; shoot_day: string; mutations: number; views: number;
    distinct_targets: number; first_action_at: string; last_action_at: string;
  }>;
  actions_by_department_and_hour?: AnalyticsRows<{
    department: string; hour: number; mutations: number; views: number;
  }>;
  first_touch_lag?: AnalyticsRows<{
    actor: string; requirements: number; touched: number;
    median_minutes: number | null; p90_minutes: number | null;
  }>;
  tables?: AnalyticsRows<{ table: string; rows: number }>;
}


/* ---------------------------------------------------------------------------
 * The screenplay and its breakdown.
 *
 * These lived in ScriptStudio.tsx and here at the same time. Three were byte
 * for byte the same; two were NOT -- `ScreenplayScene` had `dialogues` in one
 * file and `dialogue?` in the other, and `ShotProposal` disagreed about what a
 * camera is. Two types with one name and different shapes is a worse problem
 * than a duplicate: the compiler is happy either way and the mismatch only
 * shows up at runtime.
 *
 * The versions below are the ones that were actually in use. The copies here
 * were dead -- nothing imported them, in this file or out of it -- and went,
 * taking `CameraSetup` with them, which existed only to serve the dead
 * `ShotProposal`.
 * ------------------------------------------------------------------------ */

export interface DialogueLine {
  character: string;
  parenthetical?: string;
  line: string;
}

export interface CharacterRelationship {
  target_character: string;
  relationship_type: string;
  dynamic_description: string;
  shared_scenes: string[];
  interaction_count: number;
}

export interface CharacterProfile {
  id: string;
  name: string;
  role: string;
  actor_reference: string;
  look_and_costume: string;
  facial_features: string;
  personality_traits: string[];
  personality_axes?: PersonalityAxes | null;
  relationships?: CharacterRelationship[];
  dialogue_count: number;
  scenes_present: string[];
  avatar_url?: string;
  portrait_prompt?: string;
}

export interface ScreenplayScene {
  scene_number: string;
  heading: string;
  environment: string;
  location: string;
  time_of_day: string;
  action_blocks: string[];
  dialogues: DialogueLine[];
  characters?: string[];
  raw_content?: string;
}

export interface DoPSpecification {
  dop_preset: string;
  focal_length: number;
  lens_type: string;
  aperture: string;
  sensor_format: string;
  camera_body: string;
  fps: number;
  lighting_style: string;
  lighting_ratio: string;
  color_temperature_k: number;
  color_palette: string;
  lut_emulation: string;
  mood_notes: string;
}

export interface CameraAngleProposal {
  id: string;
  camera_letter: string; // "A", "B", "C"
  camera_role: string;
  shot_size: string;
  focal_length: number;
  aperture: string;
  camera_angle: string;
  camera_movement: string;
  coverage_description: string;
  prompt: string;
  image_url?: string;
  status: 'pending' | 'generating' | 'generated' | 'failed';
  dop_spec?: any;
}

export interface StoryboardFrame {
  image_url?: string;
  prompt: string;
  aspect_ratio: string;
  status: 'pending' | 'generating' | 'generated' | 'failed';
}

export interface ShotProposal {
  id: string;
  scene_number: string;
  shot_number: string;
  shot_name: string;
  shot_size: string;
  camera_angle: string;
  camera_movement: string;
  dramatic_beat: string;
  subject_description: string;
  characters?: string[];
  dop_spec: DoPSpecification;
  cameras: CameraAngleProposal[];
  active_camera: string;
  storyboard: StoryboardFrame;
}

/** Who saw one thing, and who took it on. */
export interface EntityActivity {
  production_id: string;
  target_type: string;
  target_id: string;
  events: {
    event_id: string; actor: string; action: string;
    department: string; created_at: string;
  }[];
  viewed_by: string[];
  /** Null when nobody has. Null rather than false: "not acknowledged" and
   *  "needs no acknowledgement" are different, and a boolean conflates them. */
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}
