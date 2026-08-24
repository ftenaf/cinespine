export type Severity = 'CRITICAL' | 'WARNING' | 'INFO';

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
  slate: string;
  take_id: string;
  intent?: Record<string, any> | null;
  belief: {
    camera?: Record<string, any>;
    sound?: Record<string, any>;
    script?: Record<string, any>;
  };
  existence: {
    silverstack?: Record<string, any>;
  };
  is_starred: boolean;
  is_pickup: boolean;
}
