import { TakeRecord, Discrepancy } from './types';

const API_BASE = '/api';

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
  production_id: string;
  shoot_day: string;
  raw_content: string;
  filename?: string;
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

export async function uploadFile(productionId: string, shootDay: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('production_id', productionId);
  formData.append('shoot_day', shootDay);

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
