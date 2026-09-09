import { useEffect, useState } from 'react';
import { Loader2, RefreshCw, AlertTriangle, PieChart, UsersRound } from 'lucide-react';
import {
  CrewWorkload,
  PreEditingProgress,
  ProductionDashboard as Board,
  ProgressAxis,
  TagVocabulary,
} from '../types';
import { fetchDashboard } from '../api';
import { collapseFeed } from '../tagFeed';
import { ActivityCard } from './ActivityCard';
import { StatusCard } from './StatusCard';

/**
 * Where a production has got to, and what it is waiting on.
 *
 * Two decisions shape everything here. Progress is measured against what the
 * spine says exists, not against what has been tagged -- otherwise three
 * mounted shots reads the same in a production of three as in one of two
 * hundred, and the largest useful number, what nobody has looked at, cannot be
 * shown at all. And scenes and shots are never merged: a scene marked finished
 * says nothing about the shots inside it, so averaging the two would put a
 * number on the board that nobody asserted.
 */

// Matches EditorialTagBar: cool through the cutting room, warm after picture
// lock. Both maps fall back to slate for a key they do not know, so a status
// added to the vocabulary renders rather than disappearing.
const STATUS_BAR: Record<string, string> = {
  finished_shooting: 'bg-slate-500',
  covered_per_script: 'bg-indigo-500',
  ready_to_edit: 'bg-blue-500',
  mounted: 'bg-emerald-600',
  finished: 'bg-emerald-400',
  picture_lock: 'bg-amber-500',
  colour_sound_vfx: 'bg-orange-500',
  conformed: 'bg-fuchsia-600',
  dcp: 'bg-violet-600',
};

const NEED_ICONS: Record<string, string> = { sfx: '🔊', subtitles: '💬', translation: '🌐' };
const WORK_STATUS_CLASS: Record<string, string> = {
  open: 'border-blue-700/50 text-blue-200 bg-blue-500/10',
  in_progress: 'border-emerald-700/50 text-emerald-200 bg-emerald-500/10',
  blocked: 'border-rose-700/50 text-rose-200 bg-rose-500/10',
};

function shortDateTime(value?: string | null): string {
  if (!value) return 'not yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function shootDayLabel(value: string): string {
  return value === 'ALL' ? 'All days' : `Day ${value}`;
}

function actionLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    created: 'created',
    updated: 'updated',
    reassigned: 'reassigned',
    status_changed: 'changed status',
    reopened: 'reopened',
    resolved: 'completed',
    deleted: 'deleted',
  };
  return value ? (labels[value] ?? value.split('_').join(' ')) : 'updated';
}

function PreEditingProgressCard({ progress }: { progress: PreEditingProgress }) {
  const percent = Math.max(0, Math.min(100, progress.completion_percent));
  const chartStyle = {
    background: `conic-gradient(#34d399 ${percent}%, #1e293b 0)`,
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-white flex items-center gap-2">
            <PieChart className="w-4 h-4 text-emerald-300" aria-hidden />
            Pre-editing phase
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {progress.completed} of {progress.total} assigned scene/shot card{progress.total === 1 ? '' : 's'} complete
          </p>
        </div>
        <div
          className="w-20 h-20 rounded-full border border-slate-700 grid place-items-center shrink-0"
          style={chartStyle}
          title={`${percent}% complete`}
        >
          <div className="w-14 h-14 rounded-full bg-slate-950 grid place-items-center">
            <span className="text-sm font-mono text-white">{percent}%</span>
          </div>
        </div>
      </div>

      {progress.total === 0 ? (
        <p className="mt-4 text-xs text-gray-400">
          No assistant editor queue cards have been assigned yet.
        </p>
      ) : (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {progress.by_assistant.map(row => (
            <div key={row.handle} className="border border-slate-800 rounded-xl p-3 bg-slate-950/50">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-xs font-semibold text-white truncate">{row.handle}</p>
                <p className="text-[11px] font-mono text-emerald-200">{row.completed} done</p>
              </div>
              <p className="text-[11px] text-gray-500 mt-1">
                {row.pending} running · {row.assigned} assigned
              </p>
              <p className="text-[11px] text-gray-400 mt-1">
                {row.scenes_completed} scene{row.scenes_completed === 1 ? '' : 's'} · {row.shots_completed} shot{row.shots_completed === 1 ? '' : 's'}
              </p>
              <p className="text-[10px] text-gray-500 mt-1">
                last completed {shortDateTime(row.last_completed_at)}
              </p>
            </div>
          ))}
        </div>
      )}

      {progress.recent_completed.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <p className="text-[11px] font-semibold text-gray-300 mb-2">Recent completions</p>
          <div className="space-y-1">
            {progress.recent_completed.map(item => (
              <p key={item.requirement_id} className="text-[11px] text-gray-500">
                <span className="text-gray-300">{item.resolved_by}</span> finished{' '}
                <span className="font-mono text-gray-300">
                  {item.target_type === 'scene' ? 'Sc ' : ''}{item.target_id}
                </span>{' '}
                {shortDateTime(item.resolved_at)}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CrewWorkloadCard({ workload }: { workload: CrewWorkload }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-3">
        <p className="text-sm font-semibold text-white flex items-center gap-2">
          <UsersRound className="w-4 h-4 text-blue-300" aria-hidden />
          Crew workload
        </p>
        <p className="text-xs text-gray-400">
          <span className="font-mono text-white">{workload.total_open}</span> active requirement{workload.total_open === 1 ? '' : 's'}
        </p>
      </div>

      {workload.by_member.length === 0 ? (
        <p className="text-xs text-gray-400">No crew has been assigned to this production yet.</p>
      ) : (
        <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
          {workload.by_member.map(member => {
            const activeCount = member.open + member.in_progress + member.blocked;
            return (
              <div key={member.handle} className="border border-slate-800 rounded-xl p-3 bg-slate-950/50">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{member.name}</p>
                    <p className="text-[11px] text-gray-500 truncate">
                      {member.handle} · {member.role}
                    </p>
                    {member.latest_activity_at ? (
                      <p className="text-[10px] text-gray-600 truncate">
                        last work {actionLabel(member.latest_activity_action)} by {member.latest_activity_actor ?? 'someone'} · {shortDateTime(member.latest_activity_at)}
                      </p>
                    ) : (
                      <p className="text-[10px] text-gray-600 truncate">no requirement activity yet</p>
                    )}
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5 text-[10px]">
                    <span className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-300 bg-slate-900">
                      {activeCount} active
                    </span>
                    {member.blocked > 0 && (
                      <span className="px-1.5 py-0.5 rounded border border-rose-700/50 text-rose-200 bg-rose-500/10">
                        {member.blocked} blocked
                      </span>
                    )}
                    <span className="px-1.5 py-0.5 rounded border border-emerald-700/50 text-emerald-200 bg-emerald-500/10">
                      {member.completed} done
                    </span>
                  </div>
                </div>

                {member.current.length === 0 ? (
                  <p className="mt-2 text-[11px] text-gray-500">No active work assigned.</p>
                ) : (
                  <div className="mt-2 space-y-1.5">
                    {member.current.map(item => (
                      <div key={item.requirement_id} className="flex items-start justify-between gap-2 text-[11px]">
                        <div className="min-w-0">
                          <p className="text-gray-300 truncate">{item.title}</p>
                          <p className="text-gray-500 truncate">
                            {shootDayLabel(item.shoot_day)} · {item.target_label} · {item.category}
                          </p>
                          <p className="text-gray-600 truncate">
                            {actionLabel(item.last_action)} by {item.last_actor ?? item.created_by} · {shortDateTime(item.last_activity_at ?? item.updated_at)}
                          </p>
                        </div>
                        <span className={`shrink-0 px-1.5 py-0.5 rounded border ${WORK_STATUS_CLASS[item.status] ?? 'border-slate-700 text-slate-300 bg-slate-900'}`}>
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ProgressBar({ axis, label, vocabulary }: {
  axis: ProgressAxis; label: string; vocabulary: TagVocabulary;
}) {
  const { known, by_status, no_status } = axis;

  if (known === 0) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
        <p className="text-sm font-semibold text-white mb-1">{label}</p>
        <p className="text-xs text-gray-400">
          No {label.toLowerCase()} in the spine yet — drop some paperwork in.
        </p>
      </div>
    );
  }

  const withStatus = known - no_status;

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-sm font-semibold text-white">{label}</p>
        <p className="text-xs text-gray-400">
          <span className="text-white font-mono">{withStatus}</span> of{' '}
          <span className="font-mono">{known}</span> marked
        </p>
      </div>

      <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-800 mb-3">
        {vocabulary.statuses.map(s => {
          const count = by_status[s.key] ?? 0;
          if (!count) return null;
          return (
            <div
              key={s.key}
              className={STATUS_BAR[s.key] ?? 'bg-slate-500'}
              style={{ width: `${(count / known) * 100}%` }}
              title={`${s.label}: ${count}`}
            />
          );
        })}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {vocabulary.statuses.map(s => (
          <span key={s.key} className="flex items-center gap-1.5 text-[11px]" title={s.description}>
            <span className={`w-2 h-2 rounded-full ${STATUS_BAR[s.key] ?? 'bg-slate-500'}`} />
            <span className="text-gray-300">{s.label}</span>
            <span className="font-mono text-white">{by_status[s.key] ?? 0}</span>
          </span>
        ))}
        {/* Not styled as a status, because it is not one: it is the absence of
            anybody's judgement, and on most days it is the real headline. */}
        <span className="flex items-center gap-1.5 text-[11px]">
          <span className="w-2 h-2 rounded-full bg-slate-800 border border-slate-600" />
          <span className="text-gray-500">Not marked</span>
          <span className="font-mono text-gray-400">{no_status}</span>
        </span>
      </div>

      {axis.tagged_but_unknown.length > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-[11px] text-amber-300/90">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
          <span>
            Tagged but not in the spine: {axis.tagged_but_unknown.join(', ')} — either the
            paperwork has not arrived, or the slate is spelled differently somewhere.
          </span>
        </p>
      )}
    </div>
  );
}

export function ProductionDashboardPanel({ productionId, reloadKey }: {
  productionId: string;
  /** Changes when a tag changes anywhere, so the board follows live edits. */
  reloadKey: number;
}) {
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const load = () => {
    setIsLoading(true);
    fetchDashboard(productionId)
      .then(b => { setBoard(b); setError(null); })
      .catch(e => setError(e?.detail || e?.message || 'Could not load the board'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [productionId, reloadKey]);

  if (error) {
    return (
      <div className="bg-slate-900/60 border border-spine-critical/40 rounded-2xl p-6">
        <p className="text-sm text-spine-critical">{error}</p>
        <button onClick={load} className="mt-2 text-xs text-spine-accent hover:underline">
          Try again
        </button>
      </div>
    );
  }

  if (!board) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400 mx-auto" />
      </div>
    );
  }

  const labelFor = (kind: 'statuses' | 'needs' | 'descriptors', key: string) =>
    board.vocabulary[kind].find(e => e.key === key)?.label ?? key;

  const outstandingTotal = Object.values(board.outstanding)
    .reduce((sum, list) => sum + list.length, 0);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">
          Across {board.shoot_days.length} shoot day{board.shoot_days.length === 1 ? '' : 's'}
          {board.shoot_days.length > 0 && ` (${board.shoot_days.join(', ')})`}.
          {' '}A shot is covered over whatever days it took, so this is not filtered by day.
        </p>
        <button
          onClick={load}
          disabled={isLoading}
          className="flex items-center gap-1.5 text-xs text-gray-300 hover:text-white transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* The producer's question first. Same endpoint the WebMCP tool reads. */}
      <StatusCard productionId={productionId} reloadKey={reloadKey} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ProgressBar axis={board.shots} label="Shots" vocabulary={board.vocabulary} />
        <ProgressBar axis={board.scenes} label="Scenes" vocabulary={board.vocabulary} />
      </div>

      <PreEditingProgressCard progress={board.pre_editing} />

      {/* What people own beside what they did. The second is read from the
          analytical spine and says so when there is none, without taking the
          board down with it. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CrewWorkloadCard workload={board.crew_workload} />
        <ActivityCard productionId={productionId} reloadKey={reloadKey} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-sm font-semibold text-white">Outstanding work</p>
            <p className="text-xs text-gray-400 font-mono">{outstandingTotal}</p>
          </div>

          {outstandingTotal === 0 ? (
            <p className="text-xs text-gray-400">Nothing is flagged as owing work.</p>
          ) : (
            <div className="space-y-3">
              {board.vocabulary.needs.map(need => {
                const targets = board.outstanding[need.key] ?? [];
                if (!targets.length) return null;
                return (
                  <div key={need.key}>
                    <p className="text-[11px] text-gray-300 mb-1.5">
                      {NEED_ICONS[need.key] ?? '•'} {need.label}
                      <span className="text-gray-500 font-mono"> · {targets.length}</span>
                    </p>
                    {/* The targets themselves, not a count: what is outstanding
                        is a job to be picked up, and a number cannot be worked
                        from. */}
                    <div className="flex flex-wrap gap-1">
                      {targets.map(t => (
                        <span
                          key={`${t.target_type}:${t.target_id}`}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-200 border border-rose-500/25"
                          title={t.status ? labelFor('statuses', t.status) : 'No status set'}
                        >
                          {t.target_type === 'scene' ? 'Sc ' : ''}{t.target_id}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
          <p className="text-sm font-semibold text-white mb-3">Recent changes</p>
          {board.recent.length === 0 ? (
            <p className="text-xs text-gray-400">
              Nothing recorded yet. Tagging a shot or a scene will show up here.
            </p>
          ) : (
            <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
              {collapseFeed(board.recent).slice(0, 15).map(({ entry, count }) => (
                <div key={entry.event_id} className="flex gap-2 text-[11px] leading-snug">
                  <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                    entry.action === 'cleared' ? 'bg-gray-600' : 'bg-spine-accent'}`} />
                  <div className="min-w-0">
                    <span className="text-gray-200">{entry.actor ?? 'someone'}</span>{' '}
                    <span className="text-gray-400">
                      {entry.action === 'cleared' ? 'removed the tag on' : 'tagged'}
                    </span>{' '}
                    <span className="font-mono text-gray-300">
                      {entry.target_type === 'scene' ? 'Sc ' : ''}{entry.target_id}
                    </span>
                    {entry.status && entry.action !== 'cleared' && (
                      <span className="text-gray-500"> · {labelFor('statuses', entry.status)}</span>
                    )}
                    {/* A repeated save is folded rather than dropped: the record
                        keeps every one, and the count says so without spending
                        a line on each. */}
                    {count > 1 && (
                      <span
                        className="ml-1 text-gray-500 font-mono"
                        title={`Saved ${count} times with no change between them`}
                      >
                        ×{count}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
