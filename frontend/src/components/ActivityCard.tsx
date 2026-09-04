import { useEffect, useState } from 'react';
import { Activity, Database, Loader2 } from 'lucide-react';
import { fetchProductionAnalytics } from '../api';
import { ProductionAnalytics } from '../types';
import { minutesLabel, summarizeWorkload, WorkloadRow, WorkloadSummary } from '../workload';

/**
 * What each person did, beside what they own.
 *
 * The crew workload card counts assignments. This counts actions, from the
 * ledger every mutation route writes, and it draws two numbers per person
 * that must never be added: changes they made, and things they looked at.
 *
 * Its subtitle says the one thing the numbers cannot: a count of actions is
 * activity, not effort. A tag set in two seconds and a discrepancy resolved
 * after an hour's search are one row each. Read without that sentence, this
 * card becomes a score, and the person who resolves the hard ones loses.
 *
 * Loads on its own rather than through the board: the analytical spine can
 * be absent while the board is fine, and this card says so in its own space
 * instead of taking the board down with it.
 */

function Sparkline({ row, days }: { row: WorkloadRow; days: string[] }) {
  const byDay = new Map(row.days.map(d => [d.shoot_day, d]));
  const peak = Math.max(1, ...row.days.map(d => Math.max(d.mutations, d.views)));
  return (
    <div className="flex items-end gap-px h-5" aria-hidden>
      {days.map(day => {
        const d = byDay.get(day);
        const m = d ? (d.mutations / peak) * 100 : 0;
        const v = d ? (d.views / peak) * 100 : 0;
        return (
          <div key={day} className="flex items-end gap-px" title={`Day ${day || '—'}: ${d?.mutations ?? 0} changes, ${d?.views ?? 0} views`}>
            <span className="w-1 rounded-sm bg-emerald-400/80" style={{ height: `${Math.max(m, d?.mutations ? 8 : 0)}%` }} />
            <span className="w-1 rounded-sm bg-slate-500/70" style={{ height: `${Math.max(v, d?.views ? 8 : 0)}%` }} />
          </div>
        );
      })}
    </div>
  );
}

function FirstTouch({ row }: { row: WorkloadRow }) {
  const ft = row.first_touch;
  if (!ft || ft.requirements === 0) return <span className="text-gray-600">—</span>;
  const waiting = ft.requirements - ft.touched;
  const median = minutesLabel(ft.median_minutes);
  return (
    <span className="whitespace-nowrap">
      {median ? <span className="text-gray-300">{median}</span> : <span className="text-gray-600">—</span>}
      {waiting > 0 && (
        <span className="ml-1.5 px-1 py-px rounded border border-amber-700/50 text-amber-200 bg-amber-500/10">
          {waiting} untouched
        </span>
      )}
    </span>
  );
}

export function ActivityCard({ productionId, reloadKey }: { productionId: string; reloadKey: number }) {
  const [data, setData] = useState<ProductionAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setIsLoading(true);
    fetchProductionAnalytics(productionId)
      .then(d => { if (live) { setData(d); setError(null); } })
      .catch(e => { if (live) setError(e?.detail || e?.message || 'Could not read the activity ledger'); })
      .finally(() => { if (live) setIsLoading(false); });
    return () => { live = false; };
  }, [productionId, reloadKey]);

  const summary: WorkloadSummary = summarizeWorkload(data);

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-1">
        <p className="text-sm font-semibold text-white flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-300" aria-hidden />
          Activity
          {isLoading && <Loader2 className="w-3 h-3 animate-spin text-gray-500" aria-label="loading" />}
        </p>
        {summary.latest_shoot_day && (
          <p className="text-xs text-gray-400">latest: day <span className="font-mono text-white">{summary.latest_shoot_day}</span></p>
        )}
      </div>
      <p className="text-[11px] text-gray-500 mb-3">
        Counts actions, not effort. <span className="text-emerald-300/80">Changes</span> and{' '}
        <span className="text-slate-400">views</span> are kept apart on purpose.
      </p>

      {error ? (
        <p className="text-xs text-spine-critical">{error}</p>
      ) : data && !data.available ? (
        <div className="flex items-start gap-2 text-xs text-gray-400">
          <Database className="w-3.5 h-3.5 mt-px text-gray-500 shrink-0" aria-hidden />
          <p>{data.reason ?? 'No analytical spine is connected.'}</p>
        </div>
      ) : summary.rows.length === 0 ? (
        <p className="text-xs text-gray-400">
          {isLoading ? 'Reading the ledger…' : 'Nobody has done anything on this production yet.'}
        </p>
      ) : (
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-gray-500 text-left">
              <th className="font-normal pb-1.5">Who</th>
              <th className="font-normal pb-1.5 text-right" title="Changes on the latest shoot day">Changes</th>
              <th className="font-normal pb-1.5 text-right" title="Views on the latest shoot day">Views</th>
              <th className="font-normal pb-1.5 pl-3" title="Per shoot day, oldest first">Days</th>
              <th className="font-normal pb-1.5 pl-3 text-right" title="Median time from a requirement being raised to the assignee first touching it">First touch</th>
            </tr>
          </thead>
          <tbody>
            {summary.rows.map(row => (
              <tr key={row.actor} className="border-t border-slate-800/80">
                <td className="py-1.5 pr-2 text-gray-200 truncate max-w-[9rem]" title={row.actor}>{row.actor}</td>
                <td className="py-1.5 text-right font-mono text-emerald-200">
                  {row.latest?.mutations ?? row.mutations}
                  <span className="text-gray-600"> / {row.mutations}</span>
                </td>
                <td className="py-1.5 text-right font-mono text-slate-300">
                  {row.latest?.views ?? row.views}
                  <span className="text-gray-600"> / {row.views}</span>
                </td>
                <td className="py-1.5 pl-3"><Sparkline row={row} days={summary.shoot_days} /></td>
                <td className="py-1.5 pl-3 text-right"><FirstTouch row={row} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {summary.rows.length > 0 && (
        <p className="mt-2 text-[10px] text-gray-600">
          latest day / all days. Changes nobody could be credited with are left out of the per-person rows.
        </p>
      )}
    </div>
  );
}
