import { Requirement, RequirementPriority, RequirementStatus } from './types';

/**
 * Reading a production's requirements as a list of impediments.
 *
 * The spine's own requirements view is one shoot day at a time, which answers
 * "what came out of Tuesday". The question a production asks is different --
 * what is outstanding, and what is stuck -- and it cannot be answered a day at
 * a time, because a requirement raised on day 11 is still owed on day 39.
 */

/** Everything that is not resolved is still owed by someone. */
export const OUTSTANDING_STATUSES: RequirementStatus[] = ['open', 'in_progress', 'blocked'];

const PRIORITY_RANK: Record<RequirementPriority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function isOutstanding(requirement: Requirement): boolean {
  return requirement.status !== 'resolved';
}

export interface OwnerLoad {
  handle: string;
  outstanding: number;
  blocked: number;
}

export interface RequirementsSummary {
  open: number;
  in_progress: number;
  blocked: number;
  resolved: number;
  /** Everything still owed, whatever stage it is at. */
  outstanding: number;
  /** Outstanding work by the person holding it, heaviest first. */
  owners: OwnerLoad[];
  /** Outstanding work by category, largest first. */
  categories: Array<{ category: string; outstanding: number }>;
  /** The outstanding requirement that has been waiting longest, if any. */
  oldestOutstanding: Requirement | null;
}

export function summarizeRequirements(requirements: Requirement[]): RequirementsSummary {
  const summary: RequirementsSummary = {
    open: 0,
    in_progress: 0,
    blocked: 0,
    resolved: 0,
    outstanding: 0,
    owners: [],
    categories: [],
    oldestOutstanding: null,
  };

  const owners = new Map<string, OwnerLoad>();
  const categories = new Map<string, number>();

  for (const requirement of requirements) {
    if (requirement.status in summary) {
      (summary as any)[requirement.status] += 1;
    }
    if (!isOutstanding(requirement)) continue;

    summary.outstanding += 1;

    // Unassigned work is owed by the production rather than by nobody, so it
    // is counted under a name of its own instead of being dropped.
    const handle = requirement.assigned_to || 'unassigned';
    const owner = owners.get(handle) ?? { handle, outstanding: 0, blocked: 0 };
    owner.outstanding += 1;
    if (requirement.status === 'blocked') owner.blocked += 1;
    owners.set(handle, owner);

    categories.set(requirement.category, (categories.get(requirement.category) ?? 0) + 1);

    const oldest = summary.oldestOutstanding;
    if (!oldest || requirement.created_at < oldest.created_at) {
      summary.oldestOutstanding = requirement;
    }
  }

  summary.owners = [...owners.values()].sort(
    (a, b) => b.blocked - a.blocked || b.outstanding - a.outstanding || a.handle.localeCompare(b.handle),
  );
  summary.categories = [...categories.entries()]
    .map(([category, outstanding]) => ({ category, outstanding }))
    .sort((a, b) => b.outstanding - a.outstanding || a.category.localeCompare(b.category));

  return summary;
}

/**
 * Most urgent first.
 *
 * Blocked outranks priority on purpose. A critical requirement someone is
 * working on is moving; a low-priority one that is blocked is not, and only
 * the second needs a person to come and unblock it. Within a band the oldest
 * comes first -- the longer something has been owed, the more likely it is to
 * be the thing nobody has looked at.
 *
 * Resolved requirements sort to the end rather than being filtered out, so a
 * caller that wants to show them keeps one ordering to reason about.
 */
export function sortByUrgency(requirements: Requirement[]): Requirement[] {
  return [...requirements].sort((a, b) => {
    const aDone = a.status === 'resolved';
    const bDone = b.status === 'resolved';
    if (aDone !== bDone) return aDone ? 1 : -1;

    if (!aDone) {
      const aBlocked = a.status === 'blocked';
      const bBlocked = b.status === 'blocked';
      if (aBlocked !== bBlocked) return aBlocked ? -1 : 1;

      const byPriority = (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9);
      if (byPriority !== 0) return byPriority;

      return a.created_at.localeCompare(b.created_at);
    }

    // Resolved: most recently dealt with first, which is what a reader
    // scanning for "did that get done" is looking for.
    return (b.resolved_at ?? b.updated_at).localeCompare(a.resolved_at ?? a.updated_at);
  });
}


/**
 * How long something has been waiting, as a phrase that reads the same whether
 * it is followed by "ago" or preceded by "waiting".
 *
 * Returning "today" for the first hour broke that: "resolved this today ago".
 */
export function elapsed(iso: string, now: number = Date.now()): string {
  const ms = Math.max(0, now - new Date(iso).getTime());
  const days = Math.floor(ms / 86400000);
  if (days >= 1) return `${days}d`;
  const hours = Math.floor(ms / 3600000);
  if (hours >= 1) return `${hours}h`;
  return 'under an hour';
}
