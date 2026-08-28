import { TagHistoryEntry } from './types';

/**
 * A run of adjacent, identical changes shown as one line.
 *
 * The trail records every save, including one that changed nothing -- someone
 * having looked is worth keeping. On a per-target trail that reads fine, since
 * each line is described against the one below it. On the board's feed, which
 * runs across every target, the same save repeated came out as two identical
 * lines with nothing to tell them apart.
 */
export interface FeedRun {
  entry: TagHistoryEntry;
  /** How many adjacent saves this line stands for. 1 for most of them. */
  count: number;
  /** The oldest of the run; the entry itself carries the newest. */
  earliest: TagHistoryEntry;
}

function sameChange(a: TagHistoryEntry, b: TagHistoryEntry): boolean {
  return (
    a.actor === b.actor &&
    a.target_type === b.target_type &&
    a.target_id === b.target_id &&
    a.action === b.action &&
    a.status === b.status &&
    a.needs.join(' ') === b.needs.join(' ') &&
    a.descriptors.join(' ') === b.descriptors.join(' ')
  );
}

/**
 * Collapses only *adjacent* runs, never all matches in the list.
 *
 * Two saves of the same thing an hour apart, with other work between them, are
 * two separate moments and stay two lines. Folding those together would claim
 * something the record does not say.
 */
export function collapseFeed(entries: TagHistoryEntry[]): FeedRun[] {
  const runs: FeedRun[] = [];
  for (const entry of entries) {
    const last = runs[runs.length - 1];
    if (last && sameChange(last.entry, entry)) {
      last.count += 1;
      // The feed is newest first, so each further match is older than the last.
      last.earliest = entry;
      continue;
    }
    runs.push({ entry, count: 1, earliest: entry });
  }
  return runs;
}
