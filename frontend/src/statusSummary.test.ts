import { describe, it, expect } from 'vitest';
import { ageLabel, formatStatusSummary, itemLine } from './statusSummary';
import { ProductionStatus, StatusItem } from './types';

function item(over: Partial<StatusItem>): StatusItem {
  return { bucket: 'left', kind: 'requirement', id: 'x', title: 'Thing', severity: 'medium', since: null, age_hours: null, ...over };
}

function status(over: Partial<ProductionStatus> = {}): ProductionStatus {
  return {
    production_id: 'P', generated_at: 't', shoot_days: ['31'],
    counts: { done: 0, running: 0, blocking: 0, left: 0, missing: 0 },
    headline: '0 done, 0 running, 0 blocking, 0 left, 0 missing.',
    urgent: [], done: [], running: [], blocking: [], left: [], missing: [], ...over,
  };
}

describe('ageLabel', () => {
  it('speaks in hours under two days, then days', () => {
    expect(ageLabel(null)).toBe('');
    expect(ageLabel(0.4)).toBe('just now');
    expect(ageLabel(30)).toBe('30h');
    expect(ageLabel(72)).toBe('3d');
  });
});

describe('itemLine', () => {
  it('leads with severity and keeps day, owner and age in one bracket', () => {
    expect(itemLine(item({ severity: 'critical', title: 'Timecode drift', shoot_day: '31', owner: '@sound', age_hours: 50 })))
      .toBe('[critical] Timecode drift (day 31, @sound, 2d)');
    expect(itemLine(item({ title: 'No crew' }))).toBe('[medium] No crew');
  });
});

describe('formatStatusSummary', () => {
  it('says blocking first, skips empty buckets, and counts what it left out', () => {
    const s = status({
      blocking: [item({ bucket: 'blocking', severity: 'high', title: 'B1' }), item({ bucket: 'blocking', title: 'B2' })],
      done: [item({ bucket: 'done', title: 'D1' })],
    });
    const text = formatStatusSummary(s, 1);
    const lines = text.split('\n');
    expect(lines[0]).toBe('P: 0 done, 0 running, 0 blocking, 0 left, 0 missing.');
    expect(lines.indexOf('Blocking (2):')).toBeLessThan(lines.indexOf('Done (1):'));
    expect(text).toContain('- …and 1 more');
    expect(text).not.toContain('Running');
  });

  it('preserves the server order rather than re-sorting', () => {
    const s = status({ left: [item({ title: 'first' }), item({ title: 'second', severity: 'critical' })] });
    const text = formatStatusSummary(s);
    expect(text.indexOf('first')).toBeLessThan(text.indexOf('second'));
  });
});
