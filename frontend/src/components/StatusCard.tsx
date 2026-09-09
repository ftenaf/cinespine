import { useEffect, useState } from 'react';
import { Compass, Loader2 } from 'lucide-react';
import { fetchProductionStatus } from '../api';
import { ProductionStatus, StatusBucket, StatusItem } from '../types';
import { ageLabel, BUCKET_ORDER } from '../statusSummary';

/**
 * Where the production stands, in the five buckets the status endpoint
 * ranks: blocking, missing, running, left, done.
 *
 * The producer's question is "how are we doing", and until now the only
 * answer on screen was spread over four cards. This is the same endpoint the
 * WebMCP tool reads, drawn once, worst-and-oldest first, with the most
 * urgent item as the headline. "Missing" is inference and each item carries
 * the rule that inferred it as a tooltip.
 */

const BUCKET_STYLE: Record<StatusBucket, { label: string; chip: string; dot: string }> = {
  blocking: { label: 'Blocking', chip: 'border-rose-700/60 text-rose-200 bg-rose-500/10', dot: 'bg-rose-400' },
  missing: { label: 'Missing', chip: 'border-amber-700/60 text-amber-200 bg-amber-500/10', dot: 'bg-amber-400' },
  running: { label: 'Running', chip: 'border-sky-700/60 text-sky-200 bg-sky-500/10', dot: 'bg-sky-400' },
  left: { label: 'Left', chip: 'border-slate-600 text-slate-200 bg-slate-800/60', dot: 'bg-slate-400' },
  done: { label: 'Done', chip: 'border-emerald-700/60 text-emerald-200 bg-emerald-500/10', dot: 'bg-emerald-400' },
};

const SEVERITY_CLASS: Record<string, string> = {
  critical: 'text-rose-300',
  high: 'text-amber-300',
  medium: 'text-slate-300',
  low: 'text-slate-500',
};

function ItemRow({ item }: { item: StatusItem }) {
  const age = ageLabel(item.age_hours);
  return (
    <li className="flex items-start gap-2 text-[11px] leading-snug" title={item.detail ?? undefined}>
      <span className={`shrink-0 font-mono uppercase ${SEVERITY_CLASS[item.severity] ?? 'text-slate-300'}`}>{item.severity}</span>
      <span className="min-w-0 flex-1 text-gray-200 truncate">{item.title}</span>
      <span className="shrink-0 text-gray-500 font-mono">
        {item.shoot_day ? `d${item.shoot_day}` : ''}{item.owner ? ` ${item.owner}` : ''}{age ? ` ${age}` : ''}
      </span>
    </li>
  );
}

export function StatusCard({ productionId, reloadKey }: { productionId: string; reloadKey: number }) {
  const [status, setStatus] = useState<ProductionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState<StatusBucket>('blocking');

  useEffect(() => {
    let live = true;
    setIsLoading(true);
    fetchProductionStatus(productionId)
      .then(s => {
        if (!live) return;
        setStatus(s);
        setError(null);
        // Open the first bucket that has anything in it, in urgency order.
        const first = BUCKET_ORDER.find(b => (s[b] ?? []).length > 0);
        if (first) setOpen(first);
      })
      .catch(e => { if (live) setError(e?.detail || e?.message || 'Could not read the production status'); })
      .finally(() => { if (live) setIsLoading(false); });
    return () => { live = false; };
  }, [productionId, reloadKey]);

  const urgent = status?.urgent?.[0] ?? null;
  const items = status ? (status[open] ?? []) : [];

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-2">
        <p className="text-sm font-semibold text-white flex items-center gap-2">
          <Compass className="w-4 h-4 text-amber-300" aria-hidden />
          Where do we stand
          {isLoading && <Loader2 className="w-3 h-3 animate-spin text-gray-500" aria-label="loading" />}
        </p>
        {status && (
          <p className="text-[11px] text-gray-500">
            across {status.shoot_days.length} shoot day{status.shoot_days.length === 1 ? '' : 's'}; ranked by severity, then age
          </p>
        )}
      </div>

      {error ? (
        <p className="text-xs text-spine-critical">{error}</p>
      ) : !status ? (
        <p className="text-xs text-gray-400">Reading the spine…</p>
      ) : (
        <>
          {urgent ? (
            <p className="text-xs text-gray-200 mb-3" title={urgent.detail ?? undefined}>
              <span className="text-gray-500">Most urgent: </span>
              <span className={`font-mono uppercase mr-1 ${SEVERITY_CLASS[urgent.severity] ?? ''}`}>{urgent.severity}</span>
              {urgent.title}
              {urgent.age_hours !== null && urgent.age_hours !== undefined && (
                <span className="text-gray-500"> · open {ageLabel(urgent.age_hours)}</span>
              )}
            </p>
          ) : (
            <p className="text-xs text-emerald-300/90 mb-3">Nothing is blocking and nothing is missing.</p>
          )}

          <div className="flex flex-wrap gap-1.5 mb-3">
            {BUCKET_ORDER.map(b => (
              <button
                key={b}
                onClick={() => setOpen(b)}
                className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md border transition ${BUCKET_STYLE[b].chip} ${open === b ? 'ring-1 ring-white/40' : 'opacity-80 hover:opacity-100'}`}
                aria-pressed={open === b}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${BUCKET_STYLE[b].dot}`} />
                {BUCKET_STYLE[b].label}
                <span className="font-mono">{status.counts[b]}</span>
              </button>
            ))}
          </div>

          {items.length === 0 ? (
            <p className="text-[11px] text-gray-500">Nothing in {BUCKET_STYLE[open].label.toLowerCase()}.</p>
          ) : (
            <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {items.slice(0, 12).map(item => <ItemRow key={item.id} item={item} />)}
              {items.length > 12 && (
                <li className="text-[11px] text-gray-500">…and {items.length - 12} more</li>
              )}
            </ul>
          )}
          {open === 'missing' && items.length > 0 && (
            <p className="mt-2 text-[10px] text-gray-600">Missing is inferred. Hover an item for the rule that inferred it.</p>
          )}
        </>
      )}
    </div>
  );
}
