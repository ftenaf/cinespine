import { TakeRecord, Discrepancy, Production, SourceDocumentSummary, SourceDocument } from './types';

const API_BASE = '/api';

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
  if (!res.ok) throw new Error('Upload failed');
  return res.json();
}

export async function uploadFile(file: File, productionId?: string, shootDay?: string): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  if (productionId) formData.append('production_id', productionId);
  if (shootDay) formData.append('shoot_day', shootDay);

  const res = await fetch(`${API_BASE}/upload/file`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('File upload failed');
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



