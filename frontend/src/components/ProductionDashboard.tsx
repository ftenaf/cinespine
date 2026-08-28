import { useEffect, useState } from 'react';
import { Loader2, RefreshCw, AlertTriangle } from 'lucide-react';
import { ProductionDashboard as Board, ProgressAxis, TagVocabulary } from '../types';
import { fetchDashboard } from '../api';
import { collapseFeed } from '../tagFeed';

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

const STATUS_BAR: Record<string, string> = {
  finished_shooting: 'bg-slate-500',
  covered_per_script: 'bg-indigo-500',
  ready_to_edit: 'bg-blue-500',
  mounted: 'bg-emerald-600',
  finished: 'bg-emerald-400',
};

const NEED_ICONS: Record<string, string> = { sfx: '🔊', subtitles: '💬', translation: '🌐' };

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ProgressBar axis={board.shots} label="Shots" vocabulary={board.vocabulary} />
        <ProgressBar axis={board.scenes} label="Scenes" vocabulary={board.vocabulary} />
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
