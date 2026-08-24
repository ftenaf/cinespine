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

