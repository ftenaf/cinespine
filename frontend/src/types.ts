export type Severity = 'CRITICAL' | 'WARNING' | 'INFO';

export interface Production {
  production_id: string;
  name: string;
  director?: string;
  status?: string;
  description?: string;
  shoot_days: string[];
  total_events: number;
  total_takes: number;
  last_activity?: string | null;
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

export type RequirementPriority = 'low' | 'medium' | 'high' | 'critical';
export type RequirementCategory = 'sound' | 'vfx' | 'edit' | 'color' | 'reshoot' | 'legal' | 'general';
export type RequirementStatus = 'open' | 'in_progress' | 'resolved' | 'blocked';
export type RequirementTargetType = 'scene' | 'shot' | 'take';

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


