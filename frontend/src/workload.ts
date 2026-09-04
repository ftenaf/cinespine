import { ProductionAnalytics } from './types';

/**
 * Shapes the activity ledger into one row per person for the dashboard.
 *
 * Three rules, carried over from the SQL that feeds this and worth restating
 * where the numbers are drawn:
 *
 *   - Mutations and views are never summed. They sit in separate columns and
 *     a caller that adds them has made a number nobody asserted.
 *   - What arrives here is already free of rows whose actor was a server-side
 *     fallback, so every row names somebody who said it was them.
 *   - A count of actions is activity, not effort. The card says so in words;
 *     this module only keeps the counts honest.
 */

export interface WorkloadDay {
  shoot_day: string;
  mutations: number;
  views: number;
}

export interface WorkloadFirstTouch {
  requirements: number;
  touched: number;
  median_minutes: number | null;
  p90_minutes: number | null;
}

export interface WorkloadRow {
  actor: string;
  /** Oldest first, so a sparkline reads left to right. Days with no shoot day
   *  (a production rename, a crew change) are filed under ''. */
  days: WorkloadDay[];
  mutations: number;
  views: number;
  /** The most recent shoot day anybody on the production acted on. */
  latest: WorkloadDay | null;
  first_touch: WorkloadFirstTouch | null;
  last_action_at: string | null;
}

export interface WorkloadSummary {
  rows: WorkloadRow[];
  /** Every shoot day seen, oldest first; the sparkline's shared axis. */
  shoot_days: string[];
  latest_shoot_day: string | null;
}

/** '31' before '31A', both after '4'; '' (no day) always first. */
export function compareShootDays(a: string, b: string): number {
  if (a === b) return 0;
  if (a === '') return -1;
  if (b === '') return 1;
  const na = parseInt(a, 10);
  const nb = parseInt(b, 10);
  if (!Number.isNaN(na) && !Number.isNaN(nb) && na !== nb) return na - nb;
  return a.localeCompare(b);
}

function isFinite(n: number | null | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n);
}

export function summarizeWorkload(analytics: ProductionAnalytics | null | undefined): WorkloadSummary {
  const perDay = analytics?.actions_by_actor_and_day ?? [];
  const lag = analytics?.first_touch_lag ?? [];

  const shootDaySet = new Set<string>();
  const byActor = new Map<string, WorkloadRow>();

  for (const r of perDay) {
    shootDaySet.add(r.shoot_day);
    const row = byActor.get(r.actor) ?? {
      actor: r.actor, days: [], mutations: 0, views: 0, latest: null,
      first_touch: null, last_action_at: null,
    };
    row.days.push({ shoot_day: r.shoot_day, mutations: r.mutations, views: r.views });
    row.mutations += r.mutations;
    row.views += r.views;
    if (!row.last_action_at || r.last_action_at > row.last_action_at) {
      row.last_action_at = r.last_action_at;
    }
    byActor.set(r.actor, row);
  }

  // Somebody with requirements waiting on them and no action of their own
  // still belongs on the card: the gap is the point.
  for (const l of lag) {
    const row = byActor.get(l.actor) ?? {
      actor: l.actor, days: [], mutations: 0, views: 0, latest: null,
      first_touch: null, last_action_at: null,
    };
    row.first_touch = {
      requirements: l.requirements,
      touched: l.touched,
      median_minutes: isFinite(l.median_minutes) ? l.median_minutes : null,
      p90_minutes: isFinite(l.p90_minutes) ? l.p90_minutes : null,
    };
    byActor.set(l.actor, row);
  }

  const shoot_days = [...shootDaySet].sort(compareShootDays);
  const dated = shoot_days.filter(d => d !== '');
  const latest_shoot_day = dated.length ? dated[dated.length - 1] : null;

  const rows = [...byActor.values()].map(row => {
    row.days.sort((a, b) => compareShootDays(a.shoot_day, b.shoot_day));
    row.latest = latest_shoot_day
      ? row.days.find(d => d.shoot_day === latest_shoot_day) ?? { shoot_day: latest_shoot_day, mutations: 0, views: 0 }
      : null;
    return row;
  });

  rows.sort((a, b) =>
    b.mutations - a.mutations
    || b.views - a.views
    || (b.first_touch?.requirements ?? 0) - (a.first_touch?.requirements ?? 0)
    || a.actor.localeCompare(b.actor));

  return { rows, shoot_days, latest_shoot_day };
}

/** "12 min", "1.5 h", "2.1 d" -- or null when there is nothing to say. */
export function minutesLabel(minutes: number | null): string | null {
  if (minutes === null) return null;
  if (minutes < 90) return `${Math.round(minutes)} min`;
  if (minutes < 60 * 36) return `${(minutes / 60).toFixed(1)} h`;
  return `${(minutes / 60 / 24).toFixed(1)} d`;
}
