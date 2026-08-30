import { useEffect, useState } from 'react';
import { AlertTriangle, Database, Loader2 } from 'lucide-react';
import { ProductionAnalytics } from '../types';
import { fetchProductionAnalytics } from '../api';

/**
 * The questions the analytical spine answers.
 *
 * Every other view in this app is one shoot day. These are the whole
 * production at once -- what each department has filed, across every day, on
 * which axis -- which is the kind of question a column store exists for and
 * the kind the day-scoped path cannot ask.
 *
 * When there is no ClickHouse the panel says so. It does not draw an empty
 * chart: a panel that cannot fill looks exactly like a production with nothing
 * in it, and those need opposite responses.
 */

const AXIS_STYLES: Record<string, string> = {
  intent: 'bg-amber-600/80 text-white',
  belief: 'bg-blue-600/80 text-white',
  existence: 'bg-emerald-600/80 text-white',
};

function when(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}

function Section({ title, subtitle, children }: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 space-y-2">
      <div>
        <h4 className="text-xs font-bold text-white uppercase tracking-wide">{title}</h4>
        <p className="text-[11px] text-gray-400">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

/** A query that came back null could not be asked; that is not "nothing". */
function Rows<T>({ rows, empty, render }: {
  rows: T[] | null | undefined;
  empty: string;
  render: (row: T, index: number) => React.ReactNode;
}) {
  if (rows === null || rows === undefined) {
    return <p className="text-[11px] text-amber-300/80">This question could not be asked.</p>;
  }
  if (rows.length === 0) {
    return <p className="text-[11px] text-gray-500">{empty}</p>;
  }
  return <div className="space-y-1">{rows.map(render)}</div>;
}

export function AnalyticsPanel({ productionId, reloadKey }: {
  productionId: string;
  reloadKey: number;
}) {
  const [data, setData] = useState<ProductionAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setIsLoading(true);
    fetchProductionAnalytics(productionId)
      .then(body => { if (live) { setData(body); setError(null); } })
      .catch(e => { if (live) setError(e?.detail ?? e?.message ?? 'Could not read the analytical spine'); })
      .finally(() => { if (live) setIsLoading(false); });
    return () => { live = false; };
  }, [productionId, reloadKey]);

  if (isLoading && !data) {
    return (
      <p className="flex items-center gap-2 text-sm text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> Asking the analytical spine&hellip;
      </p>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-xl p-4">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
        <p>{error}</p>
      </div>
    );
  }

  if (!data?.available) {
    return (
      <div className="flex items-start gap-2 text-sm text-gray-300 bg-slate-900/60 border border-slate-800 rounded-xl p-4">
        <Database className="w-4 h-4 mt-0.5 text-gray-500 shrink-0" aria-hidden />
        <p>{data?.reason ?? 'No analytical spine is connected.'}</p>
      </div>
    );
  }

  const totalRows = (data.tables ?? []).reduce((sum, t) => sum + Number(t.rows ?? 0), 0);

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-gray-500">
        Answered from the analytical spine over{' '}
        <span className="font-mono text-gray-300">{totalRows.toLocaleString()}</span> rows, across
        every shoot day at once.
      </p>

      <Section
        title="What each department has said"
        subtitle="The three axes, counted. An axis with nothing on it is a department whose paperwork is not arriving."
      >
        <Rows
          rows={data.shape}
          empty="Nothing has been filed for this production yet."
          render={(row, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <span className={`px-1.5 py-0.5 rounded text-[10px] w-20 text-center ${AXIS_STYLES[row.axis] ?? 'bg-slate-700 text-white'}`}>
                {row.axis}
              </span>
              <span className="text-gray-200 w-24">{row.department}</span>
              <span className="font-mono text-gray-300">{row.events.toLocaleString()}</span>
              <span className="text-gray-500">
                events over {row.days} {row.days === 1 ? 'day' : 'days'}
              </span>
            </div>
          )}
        />
      </Section>

      <Section
        title="When each department filed"
        subtitle="Arrival times, not a lag from wrap: the report states a time of day and this records an ingest, and subtracting one from the other would invent a number."
      >
        <Rows
          rows={data.arrivals}
          empty="No paperwork has arrived yet."
          render={(row, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-3 text-[11px]">
              <span className="font-mono text-gray-400 w-14">Day {row.shoot_day}</span>
              <span className="text-gray-200 w-24">{row.department}</span>
              <span className="text-gray-500">first {when(row.first_filed)}</span>
            </div>
          )}
        />
      </Section>

      <Section
        title="Where witnesses disagree on a roll"
        subtitle="Grouped by camera. A take shot on three cameras carries three rolls and agrees with itself; the disagreement is two departments describing one camera differently."
      >
        <Rows
          rows={data.roll_disagreements}
          empty="Every witness agrees on every camera, across every day."
          render={(row, i) => (
            <div key={i} className="text-[11px] bg-red-950/20 border border-red-900/60 rounded-lg p-2">
              <span className="font-mono text-white">{row.slate} T{row.take_id}</span>{' '}
              <span className="text-gray-400">day {row.shoot_day}, camera {row.camera}</span>
              <div className="text-red-300">
                {row.rolls.join(' vs ')} — claimed by {row.witnesses.join(', ')}
              </div>
            </div>
          )}
        />
      </Section>

      <Section
        title="What each scene cost"
        subtitle="Across every day it was shot on, which no single day's view can show."
      >
        <Rows
          rows={data.scene_coverage}
          empty="No takes have been filed yet."
          render={(row, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-3 text-[11px]">
              <span className="font-mono text-cyan-300 w-14">Sc {row.scene}</span>
              <span className="text-gray-300">{row.takes} takes</span>
              <span className="text-gray-500">{row.slates} slates</span>
              <span className="text-gray-500">
                {row.days === 1 ? `day ${row.shoot_days[0]}` : `days ${row.shoot_days.join(', ')}`}
              </span>
              <span className="text-gray-600">{row.departments.join(', ')}</span>
            </div>
          )}
        />
      </Section>

      <Section
        title="How long work sits"
        subtitle="Read from the requirement trail rather than the current rows, so something blocked for a week and then resolved still says so."
      >
        <Rows
          rows={data.requirement_ageing}
          empty="Nothing has been asked of this production yet."
          render={(row, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-3 text-[11px]">
              <span className="text-gray-200 w-20">{row.category}</span>
              <span className="text-gray-300">{row.requirements} raised</span>
              <span className="text-gray-500">avg {row.avg_hours_open}h open</span>
              <span className="text-gray-500">longest {row.longest_hours_open}h</span>
              {row.ever_blocked > 0 && (
                <span className="text-red-300">{row.ever_blocked} were blocked</span>
              )}
            </div>
          )}
        />
      </Section>
    </div>
  );
}
