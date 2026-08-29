import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, Ban, Check, ChevronDown, ChevronRight, Loader2, Search, Trash2,
  UserRound,
} from 'lucide-react';
import { Requirement, RequirementStatus, UserProfile } from '../types';
import {
  deleteRequirement, fetchRequirements, resolveRequirement, updateRequirement,
} from '../api';
import { elapsed, isOutstanding, sortByUrgency, summarizeRequirements } from '../requirementsBoard';

/**
 * Everything a production still owes, across every shoot day.
 *
 * The spine's requirements tab is one day at a time, which answers "what came
 * out of Tuesday". A production asks a different question -- what is
 * outstanding, and what is stuck -- and no single day can answer it, because a
 * requirement raised on day 11 is still owed on day 39.
 *
 * Blocked work is separated out rather than being another row in the list.
 * Something in progress is moving; something blocked is waiting for a person,
 * and that is the only part of this screen anyone has to act on today.
 */

const PRIORITY_STYLES: Record<string, string> = {
  critical: 'bg-red-600/80 text-white',
  high: 'bg-amber-600/80 text-white',
  medium: 'bg-slate-600/80 text-white',
  low: 'bg-slate-800 text-gray-400 border border-slate-700',
};

const STATUS_STYLES: Record<string, string> = {
  open: 'bg-blue-600/80 text-white',
  in_progress: 'bg-indigo-600/80 text-white',
  blocked: 'bg-red-700/80 text-white',
  resolved: 'bg-emerald-700/80 text-white',
};

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  blocked: 'Blocked',
  resolved: 'Resolved',
};

type Filter = 'outstanding' | 'blocked' | 'all' | RequirementStatus;

function Chip({ label, count, isActive, onClick, tone }: {
  label: string;
  count: number;
  isActive: boolean;
  onClick: () => void;
  tone?: string;
}) {
  return (
    <button
      onClick={onClick}
      // Named for a screen reader: the count alone reads as a bare number, and
      // the label beside it is a separate node.
      aria-label={`${label}: ${count}`}
      aria-pressed={isActive}
      className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition ${
        isActive
          ? 'border-spine-accent bg-spine-accent/15 text-white'
          : 'border-slate-800 text-gray-400 hover:border-slate-700 hover:text-gray-200'
      }`}
    >
      <span>{label}</span>
      <span className={`font-mono font-bold ${tone ?? ''}`}>{count}</span>
    </button>
  );
}

function RequirementRow({ requirement, team, currentUserHandle, onChanged }: {
  requirement: Requirement;
  team: UserProfile[];
  currentUserHandle: string;
  onChanged: () => void;
}) {
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isResolving, setIsResolving] = useState(false);
  const [note, setNote] = useState('');
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const run = async (work: () => Promise<unknown>) => {
    setIsBusy(true);
    setError(null);
    try {
      await work();
      onChanged();
    } catch (e: any) {
      setError(e?.detail ?? e?.message ?? 'That change did not go through');
    } finally {
      setIsBusy(false);
    }
  };

  const done = requirement.status === 'resolved';

  return (
    <div className={`rounded-xl border p-3 space-y-2 ${
      requirement.status === 'blocked'
        ? 'border-red-900/70 bg-red-950/20'
        : done
          ? 'border-slate-800/60 bg-slate-900/30'
          : 'border-slate-800 bg-slate-900/50'
    }`}>
      <div className="flex items-start gap-2">
        <button
          onClick={() => setIsExpanded(v => !v)}
          className="text-gray-500 hover:text-white mt-0.5 shrink-0"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${PRIORITY_STYLES[requirement.priority] ?? ''}`}>
              {requirement.priority}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${STATUS_STYLES[requirement.status] ?? ''}`}>
              {STATUS_LABELS[requirement.status] ?? requirement.status}
            </span>
            <span className="text-[10px] text-gray-500 font-mono">{requirement.category}</span>
            <span className="text-[10px] text-gray-500">·</span>
            <span className="text-[10px] font-mono text-gray-300">{requirement.target_label}</span>
            <span className="text-[10px] text-gray-500">Day {requirement.shoot_day}</span>
          </div>

          <p className={`text-sm ${done ? 'text-gray-500 line-through' : 'text-white'}`}>
            {requirement.title}
          </p>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-400">
            <span className="flex items-center gap-1">
              <UserRound className="w-3 h-3" aria-hidden />
              {requirement.assigned_to || 'nobody'}
            </span>
            <span>raised by {requirement.created_by}</span>
            {!done && <span>waiting {elapsed(requirement.created_at)}</span>}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="pl-6 space-y-2">
          {requirement.description && (
            <p className="text-[11px] text-gray-400 whitespace-pre-wrap">{requirement.description}</p>
          )}

          {done && (
            <p className="text-[11px] text-emerald-300/80">
              {requirement.resolved_by} resolved this
              {requirement.resolved_at ? ` ${elapsed(requirement.resolved_at)} ago` : ''}
              {requirement.resolution_note ? `: ${requirement.resolution_note}` : ''}
            </p>
          )}

          {error && (
            <p className="text-[11px] text-red-300 bg-red-950/40 border border-red-900 rounded-lg p-2">
              {error}
            </p>
          )}

          {isResolving ? (
            <div className="space-y-2">
              <textarea
                autoFocus
                value={note}
                onChange={e => setNote(e.target.value)}
                rows={2}
                placeholder="How was it dealt with?"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200"
              />
              <div className="flex items-center gap-2">
                <button
                  disabled={isBusy || !note.trim()}
                  onClick={() => run(async () => {
                    await resolveRequirement(requirement.requirement_id, note.trim(), currentUserHandle);
                    setIsResolving(false);
                    setNote('');
                  })}
                  className="flex items-center gap-1 text-xs bg-emerald-700 hover:bg-emerald-600 text-white px-2.5 py-1 rounded-lg disabled:opacity-50"
                >
                  {isBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                  Resolve
                </button>
                <button
                  onClick={() => { setIsResolving(false); setNote(''); }}
                  className="text-xs text-gray-400 hover:text-white px-2 py-1"
                >
                  Cancel
                </button>
                {/* A resolution with no account of what was done is a status
                    change pretending to be a record. */}
                <span className="text-[10px] text-gray-500">A note is required.</span>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {!done && (
                <>
                  <select
                    value={requirement.status}
                    disabled={isBusy}
                    onChange={e => run(() => updateRequirement(requirement.requirement_id, {
                      status: e.target.value as RequirementStatus,
                      updated_by: currentUserHandle,
                    }))}
                    className="bg-slate-950 border border-slate-700 text-[11px] px-2 py-1 rounded-lg text-gray-200"
                  >
                    <option value="open">Open</option>
                    <option value="in_progress">In progress</option>
                    <option value="blocked">Blocked</option>
                  </select>

                  <select
                    value={requirement.assigned_to}
                    disabled={isBusy}
                    onChange={e => run(() => updateRequirement(requirement.requirement_id, {
                      assigned_to: e.target.value,
                      updated_by: currentUserHandle,
                    }))}
                    className="bg-slate-950 border border-slate-700 text-[11px] px-2 py-1 rounded-lg text-gray-200"
                  >
                    {/* The current holder is listed even when they are not on
                        the team list, so reassigning never silently drops them. */}
                    {!team.some(u => u.handle === requirement.assigned_to) && (
                      <option value={requirement.assigned_to}>{requirement.assigned_to || 'nobody'}</option>
                    )}
                    {team.map(u => (
                      <option key={u.handle} value={u.handle}>{u.name} ({u.handle})</option>
                    ))}
                  </select>

                  <button
                    onClick={() => setIsResolving(true)}
                    className="flex items-center gap-1 text-[11px] text-emerald-300 hover:text-emerald-200 px-2 py-1 rounded-lg hover:bg-white/5"
                  >
                    <Check className="w-3 h-3" /> Resolve
                  </button>
                </>
              )}

              {done && (
                <button
                  disabled={isBusy}
                  onClick={() => run(() => updateRequirement(requirement.requirement_id, {
                    status: 'in_progress',
                    updated_by: currentUserHandle,
                  }))}
                  className="text-[11px] text-amber-300 hover:text-amber-200 px-2 py-1 rounded-lg hover:bg-white/5"
                >
                  Re-open
                </button>
              )}

              {isConfirmingDelete ? (
                <span className="flex items-center gap-2 text-[11px] text-gray-300">
                  Delete it?
                  <button
                    onClick={() => run(() => deleteRequirement(requirement.requirement_id))}
                    className="text-red-400 hover:text-red-300 font-semibold"
                  >
                    Yes
                  </button>
                  <button onClick={() => setIsConfirmingDelete(false)} className="text-gray-500 hover:text-white">
                    No
                  </button>
                </span>
              ) : (
                <button
                  onClick={() => setIsConfirmingDelete(true)}
                  title="Delete this requirement"
                  className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-red-300 px-2 py-1 rounded-lg hover:bg-white/5"
                >
                  <Trash2 className="w-3 h-3" /> Delete
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RequirementsBoard({ productionId, team, currentUserHandle, reloadKey, onChanged }: {
  productionId: string;
  team: UserProfile[];
  currentUserHandle: string;
  /** Changes when something may have moved a requirement. */
  reloadKey: number;
  /**
   * Called after this board changes a requirement.
   *
   * The board does not refetch on its own: the counts on the production cards
   * are read from the same data, so one owner of "when to reload" keeps them
   * from disagreeing with the list right under them.
   */
  onChanged: () => void;
}) {
  const [requirements, setRequirements] = useState<Requirement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [filter, setFilter] = useState<Filter>('outstanding');
  const [search, setSearch] = useState('');

  useEffect(() => {
    let live = true;
    setIsLoading(true);
    fetchRequirements({ production_id: productionId })
      .then(rows => { if (live) { setRequirements(rows); setError(null); } })
      .catch(e => { if (live) setError(e?.detail ?? e?.message ?? 'Could not load the requirements'); })
      .finally(() => { if (live) setIsLoading(false); });
    return () => { live = false; };
  }, [productionId, reloadKey]);

  const summary = useMemo(
    () => summarizeRequirements(requirements ?? []),
    [requirements],
  );

  const shown = useMemo(() => {
    let rows = requirements ?? [];
    if (filter === 'outstanding') rows = rows.filter(isOutstanding);
    else if (filter !== 'all') rows = rows.filter(r => r.status === filter);

    const needle = search.trim().toLowerCase();
    if (needle) {
      rows = rows.filter(r =>
        r.title.toLowerCase().includes(needle) ||
        r.description.toLowerCase().includes(needle) ||
        r.target_label.toLowerCase().includes(needle) ||
        r.assigned_to.toLowerCase().includes(needle) ||
        r.category.toLowerCase().includes(needle),
      );
    }
    return sortByUrgency(rows);
  }, [requirements, filter, search]);

  if (error) {
    return (
      <div className="flex items-start gap-2 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-2xl p-4">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
        <p>{error}</p>
      </div>
    );
  }

  if (requirements === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> Reading the requirements&hellip;
      </p>
    );
  }

  if (requirements.length === 0) {
    return (
      <p className="text-sm text-gray-400 bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
        Nothing has been asked of this production yet. Requirements raised on a take, a shot or a
        scene show up here.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {summary.blocked > 0 && (
        // Blocked work gets its own line above the list. It is the only part
        // of this screen that is waiting for a person rather than for time.
        <p className="flex items-start gap-2 text-sm text-red-200 bg-red-950/30 border border-red-900/70 rounded-xl p-3">
          <Ban className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
          <span>
            <span className="font-bold">{summary.blocked}</span>{' '}
            {summary.blocked === 1 ? 'requirement is' : 'requirements are'} blocked and will not
            move until somebody clears {summary.blocked === 1 ? 'it' : 'them'}.
          </span>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Chip label="Outstanding" count={summary.outstanding} isActive={filter === 'outstanding'} onClick={() => setFilter('outstanding')} />
        <Chip label="Blocked" count={summary.blocked} tone={summary.blocked ? 'text-red-300' : undefined} isActive={filter === 'blocked'} onClick={() => setFilter('blocked')} />
        <Chip label="Open" count={summary.open} isActive={filter === 'open'} onClick={() => setFilter('open')} />
        <Chip label="In progress" count={summary.in_progress} isActive={filter === 'in_progress'} onClick={() => setFilter('in_progress')} />
        <Chip label="Resolved" count={summary.resolved} isActive={filter === 'resolved'} onClick={() => setFilter('resolved')} />
        <Chip label="All" count={requirements.length} isActive={filter === 'all'} onClick={() => setFilter('all')} />

        <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 ml-auto">
          <Search className="w-3 h-3 text-gray-500" aria-hidden />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search title, slate, owner"
            className="bg-transparent text-xs text-gray-200 focus:outline-none w-48"
          />
        </div>
      </div>

      {summary.owners.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-400">
          <span className="text-gray-500">Waiting on</span>
          {summary.owners.map(owner => (
            <span key={owner.handle} className="flex items-center gap-1">
              <span className="text-gray-200">{owner.handle}</span>
              <span className="font-mono">{owner.outstanding}</span>
              {owner.blocked > 0 && (
                <span className="text-red-300 font-mono">({owner.blocked} blocked)</span>
              )}
            </span>
          ))}
        </div>
      )}

      {summary.oldestOutstanding && (
        <p className="text-[11px] text-gray-500">
          Longest outstanding: {summary.oldestOutstanding.target_label} —{' '}
          {summary.oldestOutstanding.title}, waiting {elapsed(summary.oldestOutstanding.created_at)}.
        </p>
      )}

      {isLoading && (
        <p className="flex items-center gap-2 text-[11px] text-gray-500">
          <Loader2 className="w-3 h-3 animate-spin" aria-hidden /> Refreshing&hellip;
        </p>
      )}

      <div className="space-y-2">
        {shown.map(requirement => (
          <RequirementRow
            key={requirement.requirement_id}
            requirement={requirement}
            team={team}
            currentUserHandle={currentUserHandle}
            onChanged={onChanged}
          />
        ))}
        {shown.length === 0 && (
          <p className="text-sm text-gray-400 bg-slate-900/60 border border-slate-800 rounded-xl p-4">
            {search.trim()
              ? 'Nothing matches that search.'
              : 'Nothing in this state.'}
          </p>
        )}
      </div>
    </div>
  );
}
