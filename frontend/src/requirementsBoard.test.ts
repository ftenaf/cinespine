import { describe, it, expect } from 'vitest';
import { elapsed, isOutstanding, sortByUrgency, summarizeRequirements } from './requirementsBoard';
import { Requirement } from './types';

let clock = 0;

function req(over: Partial<Requirement> = {}): Requirement {
  clock += 1;
  return {
    requirement_id: `req_${clock}`,
    production_id: 'P',
    shoot_day: '31',
    target_type: 'shot',
    target_id: '27/7',
    target_label: 'Slate 27/7',
    title: `Requirement ${clock}`,
    description: '',
    priority: 'medium',
    category: 'general',
    created_by: '@director',
    assigned_to: '@sound_supervisor',
    status: 'open',
    created_at: new Date(clock * 1000).toISOString(),
    updated_at: new Date(clock * 1000).toISOString(),
    ...over,
  };
}

describe('summarizeRequirements', () => {
  it('counts an empty production as nothing outstanding', () => {
    const summary = summarizeRequirements([]);
    expect(summary.outstanding).toBe(0);
    expect(summary.owners).toEqual([]);
    expect(summary.oldestOutstanding).toBeNull();
  });

  it('counts each status', () => {
    const summary = summarizeRequirements([
      req({ status: 'open' }), req({ status: 'open' }),
      req({ status: 'in_progress' }), req({ status: 'blocked' }), req({ status: 'resolved' }),
    ]);
    expect([summary.open, summary.in_progress, summary.blocked, summary.resolved])
      .toEqual([2, 1, 1, 1]);
  });

  it('counts everything unresolved as still owed', () => {
    const summary = summarizeRequirements([
      req({ status: 'open' }), req({ status: 'in_progress' }),
      req({ status: 'blocked' }), req({ status: 'resolved' }),
    ]);
    expect(summary.outstanding).toBe(3);
  });

  it('does not count resolved work against anybody', () => {
    const summary = summarizeRequirements([req({ status: 'resolved', assigned_to: '@ana' })]);
    expect(summary.owners).toEqual([]);
  });

  it('puts whoever is holding blocked work at the top of the load list', () => {
    const summary = summarizeRequirements([
      req({ assigned_to: '@ana' }), req({ assigned_to: '@ana' }), req({ assigned_to: '@ana' }),
      req({ assigned_to: '@ben', status: 'blocked' }),
    ]);
    expect(summary.owners[0].handle).toBe('@ben');
    expect(summary.owners[0].blocked).toBe(1);
  });

  it('counts unassigned work under a name rather than dropping it', () => {
    // Work nobody holds is owed by the production, and is the easiest kind to
    // lose sight of.
    const summary = summarizeRequirements([req({ assigned_to: '' })]);
    expect(summary.owners[0]).toMatchObject({ handle: 'unassigned', outstanding: 1 });
  });

  it('finds the outstanding requirement that has waited longest', () => {
    const oldest = req({ status: 'open' });
    const newer = req({ status: 'open' });
    expect(summarizeRequirements([newer, oldest]).oldestOutstanding?.requirement_id)
      .toBe(oldest.requirement_id);
  });

  it('does not offer a resolved requirement as the longest waiting', () => {
    const ancient = req({ status: 'resolved' });
    const current = req({ status: 'open' });
    expect(summarizeRequirements([ancient, current]).oldestOutstanding?.requirement_id)
      .toBe(current.requirement_id);
  });

  it('groups outstanding work by category, largest first', () => {
    const summary = summarizeRequirements([
      req({ category: 'sound' }), req({ category: 'sound' }), req({ category: 'vfx' }),
    ]);
    expect(summary.categories.map(c => c.category)).toEqual(['sound', 'vfx']);
  });
});

describe('sortByUrgency', () => {
  it('puts blocked work above everything else that is outstanding', () => {
    // A critical requirement someone is working on is moving. A low-priority
    // one that is blocked is not, and only the second needs a person.
    const blocked = req({ status: 'blocked', priority: 'low' });
    const critical = req({ status: 'open', priority: 'critical' });
    expect(sortByUrgency([critical, blocked])[0].requirement_id).toBe(blocked.requirement_id);
  });

  it('orders unblocked work by priority', () => {
    const low = req({ priority: 'low' });
    const critical = req({ priority: 'critical' });
    const medium = req({ priority: 'medium' });
    expect(sortByUrgency([low, critical, medium]).map(r => r.priority))
      .toEqual(['critical', 'medium', 'low']);
  });

  it('puts the oldest first among equals', () => {
    const older = req({ priority: 'high' });
    const newer = req({ priority: 'high' });
    expect(sortByUrgency([newer, older])[0].requirement_id).toBe(older.requirement_id);
  });

  it('sorts resolved work to the end whatever its priority', () => {
    const resolvedCritical = req({ status: 'resolved', priority: 'critical' });
    const openLow = req({ status: 'open', priority: 'low' });
    expect(sortByUrgency([resolvedCritical, openLow]).map(r => r.status))
      .toEqual(['open', 'resolved']);
  });

  it('shows the most recently resolved first among resolved work', () => {
    const earlier = req({ status: 'resolved', resolved_at: '2026-08-01T00:00:00Z' });
    const later = req({ status: 'resolved', resolved_at: '2026-08-20T00:00:00Z' });
    expect(sortByUrgency([earlier, later])[0].requirement_id).toBe(later.requirement_id);
  });

  it('leaves the list it was given alone', () => {
    const given = [req({ priority: 'low' }), req({ priority: 'critical' })];
    const order = given.map(r => r.requirement_id);
    sortByUrgency(given);
    expect(given.map(r => r.requirement_id)).toEqual(order);
  });

  it('handles an empty list', () => {
    expect(sortByUrgency([])).toEqual([]);
  });
});

describe('isOutstanding', () => {
  it('counts blocked work as still owed', () => {
    expect(isOutstanding(req({ status: 'blocked' }))).toBe(true);
  });

  it('counts resolved work as done', () => {
    expect(isOutstanding(req({ status: 'resolved' }))).toBe(false);
  });
});

describe('elapsed', () => {
  const now = Date.parse('2026-08-29T12:00:00Z');
  const ago = (ms: number) => new Date(now - ms).toISOString();

  it('reads as a duration in days once a day has passed', () => {
    expect(elapsed(ago(3 * 86400000), now)).toBe('3d');
  });

  it('reads as hours within a day', () => {
    expect(elapsed(ago(5 * 3600000), now)).toBe('5h');
  });

  it('reads the same before "ago" and after "waiting"', () => {
    // 'today' made one of the two ungrammatical: "resolved this today ago".
    const phrase = elapsed(ago(60000), now);
    expect(`waiting ${phrase}`).toBe('waiting under an hour');
    expect(`resolved ${phrase} ago`).toBe('resolved under an hour ago');
  });

  it('never reads as negative for a timestamp in the future', () => {
    expect(elapsed(new Date(now + 86400000).toISOString(), now)).toBe('under an hour');
  });
});
