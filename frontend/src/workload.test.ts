import { describe, it, expect } from 'vitest';
import { compareShootDays, minutesLabel, summarizeWorkload } from './workload';
import { ProductionAnalytics } from './types';

function analytics(over: Partial<ProductionAnalytics> = {}): ProductionAnalytics {
  return { production_id: 'P', available: true, ...over };
}

describe('summarizeWorkload', () => {
  it('keeps mutations and views apart and never sums them', () => {
    const s = summarizeWorkload(analytics({
      actions_by_actor_and_day: [
        { actor: '@editor', shoot_day: '31', mutations: 1, views: 2, distinct_targets: 1, first_action_at: 'a', last_action_at: 'b' },
        { actor: '@editor', shoot_day: '32', mutations: 3, views: 0, distinct_targets: 2, first_action_at: 'c', last_action_at: 'd' },
      ],
    }));
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0].mutations).toBe(4);
    expect(s.rows[0].views).toBe(2);
    expect(s.rows[0].days.map(d => d.shoot_day)).toEqual(['31', '32']);
  });

  it('names the latest shoot day and fills a zero for anybody absent from it', () => {
    const s = summarizeWorkload(analytics({
      actions_by_actor_and_day: [
        { actor: '@editor', shoot_day: '31', mutations: 1, views: 0, distinct_targets: 1, first_action_at: 'a', last_action_at: 'a' },
        { actor: '@sound', shoot_day: '32', mutations: 2, views: 0, distinct_targets: 1, first_action_at: 'b', last_action_at: 'b' },
        { actor: '@sound', shoot_day: '', mutations: 1, views: 0, distinct_targets: 1, first_action_at: 'c', last_action_at: 'c' },
      ],
    }));
    expect(s.latest_shoot_day).toBe('32');
    expect(s.shoot_days).toEqual(['', '31', '32']);
    const editor = s.rows.find(r => r.actor === '@editor')!;
    expect(editor.latest).toEqual({ shoot_day: '32', mutations: 0, views: 0 });
  });

  it('lists somebody who has requirements waiting and no actions of their own', () => {
    const s = summarizeWorkload(analytics({
      actions_by_actor_and_day: [],
      first_touch_lag: [
        { actor: '@colorist', requirements: 2, touched: 0, median_minutes: null, p90_minutes: null },
      ],
    }));
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0].actor).toBe('@colorist');
    expect(s.rows[0].first_touch).toEqual({ requirements: 2, touched: 0, median_minutes: null, p90_minutes: null });
    expect(s.latest_shoot_day).toBeNull();
  });

  it('treats a NaN percentile as nothing to say', () => {
    const s = summarizeWorkload(analytics({
      first_touch_lag: [
        { actor: '@x', requirements: 1, touched: 0, median_minutes: NaN, p90_minutes: NaN },
      ],
    }));
    expect(s.rows[0].first_touch?.median_minutes).toBeNull();
  });

  it('sorts by mutations, then views, then requirements waiting', () => {
    const s = summarizeWorkload(analytics({
      actions_by_actor_and_day: [
        { actor: '@a', shoot_day: '1', mutations: 0, views: 5, distinct_targets: 1, first_action_at: 'a', last_action_at: 'a' },
        { actor: '@b', shoot_day: '1', mutations: 1, views: 0, distinct_targets: 1, first_action_at: 'a', last_action_at: 'a' },
      ],
      first_touch_lag: [{ actor: '@c', requirements: 9, touched: 0, median_minutes: null, p90_minutes: null }],
    }));
    expect(s.rows.map(r => r.actor)).toEqual(['@b', '@a', '@c']);
  });

  it('is empty, not broken, without an analytical spine', () => {
    expect(summarizeWorkload(null).rows).toEqual([]);
    expect(summarizeWorkload(analytics({ available: false })).rows).toEqual([]);
  });
});

describe('compareShootDays', () => {
  it('orders numerically, then lexically, with the dayless bucket first', () => {
    expect(['31A', '4', '', '31'].sort(compareShootDays)).toEqual(['', '4', '31', '31A']);
  });
});

describe('minutesLabel', () => {
  it('picks a unit a person would', () => {
    expect(minutesLabel(null)).toBeNull();
    expect(minutesLabel(12.4)).toBe('12 min');
    expect(minutesLabel(150)).toBe('2.5 h');
    expect(minutesLabel(60 * 48)).toBe('2.0 d');
  });
});
