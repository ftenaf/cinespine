import { ProductionStatus, StatusBucket, StatusItem } from './types';

/**
 * The production status as a paragraph an agent can read out.
 *
 * The backend already ranks every bucket worst-and-oldest first; this only
 * decides how much of each to say. Ages come from the server's clock so two
 * readers get the same words.
 */

export const BUCKET_ORDER: StatusBucket[] = ['blocking', 'missing', 'running', 'left', 'done'];

const BUCKET_LEAD: Record<StatusBucket, string> = {
  blocking: 'Blocking',
  missing: 'Missing',
  running: 'Running',
  left: 'Left to do',
  done: 'Done',
};

export function ageLabel(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '';
  if (hours < 1) return 'just now';
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function itemLine(item: StatusItem): string {
  const bits = [`[${item.severity}]`, item.title];
  const where: string[] = [];
  if (item.shoot_day) where.push(`day ${item.shoot_day}`);
  if (item.owner) where.push(`${item.owner}`);
  const age = ageLabel(item.age_hours);
  if (age) where.push(age);
  if (where.length) bits.push(`(${where.join(', ')})`);
  return bits.join(' ');
}

export function formatStatusSummary(status: ProductionStatus, limit = 5): string {
  const lines: string[] = [`${status.production_id}: ${status.headline}`];
  for (const bucket of BUCKET_ORDER) {
    const items = status[bucket] ?? [];
    if (items.length === 0) continue;
    const shown = items.slice(0, Math.max(1, limit));
    lines.push('');
    lines.push(`${BUCKET_LEAD[bucket]} (${items.length}):`);
    for (const item of shown) lines.push(`- ${itemLine(item)}`);
    if (items.length > shown.length) lines.push(`- …and ${items.length - shown.length} more`);
  }
  return lines.join('\n');
}
