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
  created_at: string;
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
  codec?: string;
  recording_date?: string;
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
}
