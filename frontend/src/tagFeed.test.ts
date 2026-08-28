import { describe, it, expect } from 'vitest';
import { collapseFeed } from './tagFeed';
import { TagHistoryEntry } from './types';

let clock = 0;

function entry(over: Partial<TagHistoryEntry> = {}): TagHistoryEntry {
  clock += 1;
  return {
    event_id: `e${clock}`,
    production_id: 'P',
    target_type: 'shot',
    target_id: '27/7',
    action: 'set',
    status: 'mounted',
    needs: [],
    descriptors: [],
    note: null,
    actor: '@ana',
    created_at: new Date(clock * 1000).toISOString(),
    ...over,
  };
}

describe('collapseFeed', () => {
  it('shows a single change as one line', () => {
    const runs = collapseFeed([entry()]);
    expect(runs).toHaveLength(1);
    expect(runs[0].count).toBe(1);
  });

  it('folds a repeated save into one line with a count', () => {
    const runs = collapseFeed([entry(), entry(), entry()]);
    expect(runs).toHaveLength(1);
    expect(runs[0].count).toBe(3);
  });

  it('keeps the newest of the run as the line, and remembers the oldest', () => {
    const newest = entry();
    const middle = entry();
    const oldest = entry();
    const [run] = collapseFeed([newest, middle, oldest]);
    expect(run.entry.event_id).toBe(newest.event_id);
    expect(run.earliest.event_id).toBe(oldest.event_id);
  });

  it('does not fold two people making the same change', () => {
    const runs = collapseFeed([entry({ actor: '@ana' }), entry({ actor: '@ben' })]);
    expect(runs).toHaveLength(2);
  });

  it('does not fold the same change on different targets', () => {
    const runs = collapseFeed([entry({ target_id: '27/7' }), entry({ target_id: '49/1' })]);
    expect(runs).toHaveLength(2);
  });

  it('does not fold a set and a clear', () => {
    const runs = collapseFeed([entry({ action: 'cleared' }), entry({ action: 'set' })]);
    expect(runs).toHaveLength(2);
  });

  it('does not fold a change of status', () => {
    const runs = collapseFeed([entry({ status: 'mounted' }), entry({ status: 'ready_to_edit' })]);
    expect(runs).toHaveLength(2);
  });

  it('does not fold a change of needs', () => {
    const runs = collapseFeed([entry({ needs: ['sfx'] }), entry({ needs: [] })]);
    expect(runs).toHaveLength(2);
  });

  it('does not fold a change of descriptors', () => {
    const runs = collapseFeed([
      entry({ descriptors: ['establishment'] }),
      entry({ descriptors: [] }),
    ]);
    expect(runs).toHaveLength(2);
  });

  it('folds only adjacent runs, never all matches in the list', () => {
    // The same save twice, an hour and other work apart, is two moments. Folding
    // them would claim something the record does not say.
    const runs = collapseFeed([
      entry({ target_id: '27/7' }),
      entry({ target_id: '49/1' }),
      entry({ target_id: '27/7' }),
    ]);
    expect(runs.map(r => r.entry.target_id)).toEqual(['27/7', '49/1', '27/7']);
    expect(runs.every(r => r.count === 1)).toBe(true);
  });

  it('handles several runs in one feed', () => {
    const runs = collapseFeed([
      entry({ target_id: '27/7' }),
      entry({ target_id: '27/7' }),
      entry({ target_id: '49/1' }),
      entry({ target_id: '49/1' }),
      entry({ target_id: '49/1' }),
    ]);
    expect(runs.map(r => r.count)).toEqual([2, 3]);
  });

  it('returns nothing for an empty feed', () => {
    expect(collapseFeed([])).toEqual([]);
  });
});
