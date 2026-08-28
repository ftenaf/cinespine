import { TakeRecord, Discrepancy, Production, SourceDocumentSummary, SourceDocument, UploadResult } from './types';

const API_BASE = '/api';

/**
 * An error carrying the HTTP status and the server's own explanation.
 *
 * Without the status the caller can only show "upload failed", which is what
 * turned a deliberate 409 -- this exact file is already in the spine -- into a
 * generic failure the user could do nothing about.
 */
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  get isDuplicate(): boolean {
    return this.status === 409;
  }
}

/** Reads FastAPI's `detail` off a failed response, falling back to the status. */
async function apiError(res: Response, fallback: string): Promise<ApiError> {
  let detail = fallback;
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch {
    // Not JSON; the fallback stands.
  }
  return new ApiError(res.status, detail);
}


export async function fetchProductions(): Promise<Production[]> {
  const res = await fetch(`${API_BASE}/productions`);
  if (!res.ok) throw new Error('Failed to fetch productions');
  return res.json();
}

export async function createProduction(payload: {
  production_id: string;
  name: string;
  director?: string;
  description?: string;
}): Promise<Production> {
  const res = await fetch(`${API_BASE}/productions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create production');
  return res.json();
}

export async function fetchDocuments(productionId: string, shootDay: string): Promise<SourceDocumentSummary[]> {
  const res = await fetch(`${API_BASE}/documents?production_id=${productionId}&shoot_day=${shootDay}`);
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

export async function fetchDocumentContent(docId: string): Promise<SourceDocument> {
  const res = await fetch(`${API_BASE}/documents/${docId}`);
  if (!res.ok) throw new Error('Failed to fetch document content');
  return res.json();
}

export async function fetchTakes(productionId: string, shootDay: string): Promise<TakeRecord[]> {
  const res = await fetch(`${API_BASE}/takes?production_id=${productionId}&shoot_day=${shootDay}`);
  if (!res.ok) throw new Error('Failed to fetch takes');
  return res.json();
}

export async function fetchDiscrepancies(productionId: string, shootDay: string): Promise<Discrepancy[]> {
  const res = await fetch(`${API_BASE}/discrepancies?production_id=${productionId}&shoot_day=${shootDay}`);
  if (!res.ok) throw new Error('Failed to fetch discrepancies');
  return res.json();
}

export async function uploadDocument(payload: {
  raw_content: string;
  filename?: string;
  production_id?: string;
  shoot_day?: string;
  axis?: string;
  department?: string;
  doc_type?: string;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await apiError(res, 'Upload failed');
  return res.json();
}

export async function uploadFile(file: File, productionId?: string, shootDay?: string): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (productionId) formData.append('production_id', productionId);
  if (shootDay) formData.append('shoot_day', shootDay);

  const res = await fetch(`${API_BASE}/upload/file`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw await apiError(res, 'File upload failed');
  return res.json();
}

export async function askAssistant(productionId: string, shootDay: string, slate: string, takeId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/assistant/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ production_id: productionId, shoot_day: shootDay, slate, take_id: takeId }),
  });
  if (!res.ok) throw new Error('Assistant query failed');
  const data = await res.json();
  return data.explanation;
}

export async function seedDemoDay(productionId: string, shootDay: string): Promise<any> {
  const res = await fetch(`${API_BASE}/seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ production_id: productionId, shoot_day: shootDay }),
  });
  if (!res.ok) throw new Error('Failed to seed demo day');
  return res.json();
}

export async function fetchSequences(productionId: string, shootDay: string): Promise<import('./types').SequenceRecord[]> {
  const res = await fetch(`${API_BASE}/sequences?production_id=${productionId}&shoot_day=${shootDay}`);
  if (!res.ok) throw new Error('Failed to fetch sequences');
  return res.json();
}

export async function resolveDiscrepancy(discrepancyId: string, payload: import('./types').ResolveDiscrepancyPayload): Promise<any> {
  const res = await fetch(`${API_BASE}/discrepancies/${discrepancyId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to resolve discrepancy');
  return res.json();
}

export async function unresolveDiscrepancy(discrepancyId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/discrepancies/${discrepancyId}/unresolve`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to re-open discrepancy');
  return res.json();
}

// ==========================================
// Collaborative Users, Requirements & Alerts
// ==========================================
export async function fetchTeamUsers(): Promise<import('./types').UserProfile[]> {
  const res = await fetch(`${API_BASE}/users`);
  if (!res.ok) throw new Error('Failed to fetch team users');
  return res.json();
}

export async function loginUser(handleOrEmail: string): Promise<{ user: import('./types').UserProfile; token: string }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ handle_or_email: handleOrEmail }),
  });
  if (!res.ok) throw new Error('Failed to authenticate');
  return res.json();
}

export async function fetchCurrentUser(handle?: string): Promise<import('./types').UserProfile> {
  const url = handle ? `${API_BASE}/auth/me?handle=${encodeURIComponent(handle)}` : `${API_BASE}/auth/me`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch current user');
  return res.json();
}

export async function fetchRequirements(params: {
  production_id?: string;
  shoot_day?: string;
  target_type?: string;
  target_id?: string;
  assigned_to?: string;
  created_by?: string;
  status?: string;
}): Promise<import('./types').Requirement[]> {
  const q = new URLSearchParams();
  if (params.production_id) q.set('production_id', params.production_id);
  if (params.shoot_day) q.set('shoot_day', params.shoot_day);
  if (params.target_type) q.set('target_type', params.target_type);
  if (params.target_id) q.set('target_id', params.target_id);
  if (params.assigned_to) q.set('assigned_to', params.assigned_to);
  if (params.created_by) q.set('created_by', params.created_by);
  if (params.status) q.set('status', params.status);

  const res = await fetch(`${API_BASE}/requirements?${q.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch requirements');
  return res.json();
}

export async function createRequirement(payload: {
  production_id?: string;
  shoot_day?: string;
  target_type: string;
  target_id: string;
  target_label?: string;
  title: string;
  description?: string;
  priority?: string;
  category?: string;
  created_by?: string;
  assigned_to: string;
}): Promise<import('./types').Requirement> {
  const res = await fetch(`${API_BASE}/requirements`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to create requirement');
  return res.json();
}

export async function updateRequirement(requirementId: string, updates: Partial<import('./types').Requirement>): Promise<import('./types').Requirement> {
  const res = await fetch(`${API_BASE}/requirements/${requirementId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('Failed to update requirement');
  return res.json();
}

export async function resolveRequirement(requirementId: string, resolutionNote: string, resolvedBy: string): Promise<import('./types').Requirement> {
  const res = await fetch(`${API_BASE}/requirements/${requirementId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution_note: resolutionNote, resolved_by: resolvedBy }),
  });
  if (!res.ok) throw new Error('Failed to resolve requirement');
  return res.json();
}

export async function deleteRequirement(requirementId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/requirements/${requirementId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete requirement');
  return res.json();
}

export async function fetchNotifications(userHandle: string, unreadOnly?: boolean): Promise<import('./types').NotificationResponse> {
  const q = new URLSearchParams({ user_handle: userHandle });
  if (unreadOnly) q.set('unread_only', 'true');
  const res = await fetch(`${API_BASE}/notifications?${q.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch notifications');
  return res.json();
}

export async function markNotificationRead(notificationId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to mark notification read');
  return res.json();
}

export async function markAllNotificationsRead(userHandle: string): Promise<any> {
  const res = await fetch(`${API_BASE}/notifications/read-all?user_handle=${encodeURIComponent(userHandle)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to mark all notifications read');
  return res.json();
}

export async function suggestDoPPreset(params: {
  focal_length?: number;
  aperture?: string;
  color_temperature_k?: number;
  white_balance_k?: number;
  lighting_ratio?: string;
  sensor_format?: string;
  lut_emulation?: string;
  custom_prompt?: string;
  aspect_ratio?: string;
}): Promise<{ name: string; tagline: string; description: string; prompt_style_tag: string }> {
  const res = await fetch(`${API_BASE}/script/presets/suggest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to generate DoP preset suggestions');
  return res.json();
}

export async function deleteDocument(docId: string): Promise<{ status: string; doc_id: string }> {
  const res = await fetch(`${API_BASE}/documents/${docId}`, { method: 'DELETE' });
  if (!res.ok) throw await apiError(res, 'Failed to delete document');
  return res.json();
}


// ==========================================
// Editorial Tags
// ==========================================

export async function fetchTagVocabulary(): Promise<import('./types').TagVocabulary> {
  const res = await fetch(`${API_BASE}/tags/vocabulary`);
  if (!res.ok) throw await apiError(res, 'Failed to fetch the tag vocabulary');
  return res.json();
}

export async function fetchTags(productionId: string): Promise<import('./types').EditorialTag[]> {
  const res = await fetch(`${API_BASE}/tags?production_id=${encodeURIComponent(productionId)}`);
  if (!res.ok) throw await apiError(res, 'Failed to fetch tags');
  return res.json();
}

export async function setTag(payload: {
  production_id: string;
  target_type: import('./types').TagTargetType;
  target_id: string;
  status?: string | null;
  needs?: string[];
  descriptors?: string[];
  note?: string | null;
  updated_by?: string | null;
}): Promise<import('./types').EditorialTag> {
  const res = await fetch(`${API_BASE}/tags`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await apiError(res, 'Failed to save the tag');
  return res.json();
}

export async function clearTag(
  productionId: string,
  targetType: import('./types').TagTargetType,
  targetId: string,
  clearedBy?: string | null,
): Promise<void> {
  const q = new URLSearchParams({
    production_id: productionId, target_type: targetType, target_id: targetId,
  });
  if (clearedBy) q.set('cleared_by', clearedBy);
  const res = await fetch(`${API_BASE}/tags?${q.toString()}`, { method: 'DELETE' });
  if (!res.ok) throw await apiError(res, 'Failed to clear the tag');
}

export async function fetchTagSummary(productionId: string): Promise<import('./types').TagSummary> {
  const res = await fetch(`${API_BASE}/tags/summary?production_id=${encodeURIComponent(productionId)}`);
  if (!res.ok) throw await apiError(res, 'Failed to fetch the tag summary');
  return res.json();
}

export async function fetchTagHistory(
  productionId: string,
  targetType: import('./types').TagTargetType,
  targetId: string,
): Promise<import('./types').TagHistoryEntry[]> {
  const q = new URLSearchParams({
    production_id: productionId, target_type: targetType, target_id: targetId,
  });
  const res = await fetch(`${API_BASE}/tags/history?${q.toString()}`);
  if (!res.ok) throw await apiError(res, 'Failed to fetch the tag history');
  return res.json();
}

export async function fetchDashboard(productionId: string): Promise<import('./types').ProductionDashboard> {
  const res = await fetch(`${API_BASE}/dashboard?production_id=${encodeURIComponent(productionId)}`);
  if (!res.ok) throw await apiError(res, 'Failed to fetch the dashboard');
  return res.json();
}
