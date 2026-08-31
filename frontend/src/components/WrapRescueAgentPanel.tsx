import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, Bot, CheckCircle2, Database, FileText, Loader2, Play, RadioTower,
} from 'lucide-react';
import { runWrapRescueAgent } from '../api';
import { WrapRescueResult } from '../types';

const STEP_STYLE: Record<string, string> = {
  ok: 'text-emerald-300 bg-emerald-950/40 border-emerald-900',
  warning: 'text-amber-300 bg-amber-950/30 border-amber-900',
  error: 'text-red-300 bg-red-950/40 border-red-900',
};

function labelFromStep(step: string): string {
  return step.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function shortSql(args: Record<string, unknown>): string | null {
  const query = args.query;
  if (typeof query !== 'string') return null;
  return query.trim().replace(/\s+/g, ' ').slice(0, 180);
}

export function WrapRescueAgentPanel({
  productionId,
  shootDays,
  currentUserHandle,
  onChanged,
}: {
  productionId: string;
  shootDays: string[];
  currentUserHandle: string;
  onChanged: () => void;
}) {
  const defaultDay = useMemo(() => shootDays[shootDays.length - 1] ?? '31', [shootDays]);
  const [shootDay, setShootDay] = useState(defaultDay);
  const [result, setResult] = useState<WrapRescueResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    setShootDay(defaultDay);
    setResult(null);
    setError(null);
  }, [defaultDay, productionId]);

  const run = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const next = await runWrapRescueAgent({
        production_id: productionId,
        shoot_day: shootDay || defaultDay,
        actor: currentUserHandle || '@assistant_editor',
        max_blockers: 5,
      });
      setResult(next);
      onChanged();
    } catch (e: any) {
      setError(e?.detail ?? e?.message ?? 'Wrap Rescue Agent failed');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Bot className="w-4 h-4 text-cyan-300" aria-hidden />
            Wrap Rescue Agent
          </h3>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
            <span className="flex items-center gap-1">
              <Database className="w-3 h-3" aria-hidden />
              ClickHouse MCP
            </span>
            <span className="flex items-center gap-1">
              <RadioTower className="w-3 h-3" aria-hidden />
              Gemini Enterprise
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={shootDay}
            onChange={e => setShootDay(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-xs px-2 py-1.5 rounded-lg text-gray-200"
            aria-label="Shoot day"
          >
            {Array.from(new Set([defaultDay, ...shootDays, '31'])).map(day => (
              <option key={day} value={day}>Day {day}</option>
            ))}
          </select>
          <button
            onClick={run}
            disabled={isRunning}
            className="flex items-center gap-1.5 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run
          </button>
        </div>
      </div>

      {error && (
        <p className="flex items-start gap-2 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-xl p-3">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
          <span>{error}</span>
        </p>
      )}

      {!result && !error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px] text-gray-400">
          <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
            <p className="text-gray-200 font-semibold">Query</p>
            <p>audit_discrepancies and requirement_events</p>
          </div>
          <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
            <p className="text-gray-200 font-semibold">Rank</p>
            <p>severity, age, missing acknowledgement</p>
          </div>
          <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
            <p className="text-gray-200 font-semibold">Write</p>
            <p>requirements, notifications, audit event</p>
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
              <p className="text-[10px] uppercase tracking-wide text-gray-500">MCP</p>
              <p className={`text-sm font-semibold ${result.mcp_status.available ? 'text-emerald-300' : 'text-amber-300'}`}>
                {result.mcp_status.available ? 'Connected' : 'Unavailable'}
              </p>
              {result.mcp_status.server_url && (
                <p className="text-[10px] font-mono text-gray-500 truncate">{result.mcp_status.server_url}</p>
              )}
            </div>
            <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
              <p className="text-[10px] uppercase tracking-wide text-gray-500">Gemini</p>
              <p className="text-sm font-semibold text-cyan-200">{result.gemini_status.model}</p>
              <p className="text-[10px] text-gray-500">{result.gemini_status.provider}</p>
            </div>
            <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
              <p className="text-[10px] uppercase tracking-wide text-gray-500">Outcome</p>
              <p className="text-sm font-semibold text-white">
                {result.blockers.length} blockers, {result.requirement_actions.length} actions
              </p>
              <p className="text-[10px] text-gray-500">{new Date(result.generated_at).toLocaleString()}</p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-300" aria-hidden />
              Step Trace
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {result.steps.map((step, index) => (
                <div
                  key={`${step.step}-${index}`}
                  className={`border rounded-xl p-2.5 ${STEP_STYLE[step.status] ?? STEP_STYLE.ok}`}
                >
                  <p className="text-xs font-semibold">{labelFromStep(step.step)}</p>
                  <p className="text-[11px] opacity-90">{step.detail}</p>
                </div>
              ))}
            </div>
          </div>

          {result.tool_calls.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-cyan-300" aria-hidden />
                ClickHouse Tool Calls
              </p>
              <div className="space-y-2">
                {result.tool_calls.map((call, index) => (
                  <div key={`${call.tool}-${index}`} className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-mono text-gray-200">{call.tool}</span>
                      <span className={call.ok ? 'text-[11px] text-emerald-300' : 'text-[11px] text-red-300'}>
                        {call.ok ? `${call.rows} rows` : 'failed'}
                      </span>
                    </div>
                    {shortSql(call.arguments) && (
                      <p className="text-[10px] font-mono text-gray-500 mt-1">{shortSql(call.arguments)}</p>
                    )}
                    {call.error && <p className="text-[11px] text-red-300 mt-1">{call.error}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-300">Ranked Blockers</p>
            <div className="space-y-2">
              {result.blockers.map(blocker => (
                <div key={blocker.source_key} className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/50 text-red-200 border border-red-800">
                      {blocker.priority}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-gray-300">
                      score {blocker.score}
                    </span>
                    <span className="text-[10px] text-gray-500">{blocker.assigned_to}</span>
                  </div>
                  <p className="text-sm text-white mt-1">{blocker.title}</p>
                  <p className="text-[11px] text-gray-500">{blocker.target_label}</p>
                </div>
              ))}
              {result.blockers.length === 0 && (
                <p className="text-sm text-gray-400 bg-slate-900/60 border border-slate-800 rounded-xl p-4">
                  {result.mcp_status.available
                    ? 'No active blockers came back from the agent run.'
                    : 'ClickHouse MCP was unavailable, so the agent stopped before action.'}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-300">Requirement Actions</p>
            <div className="flex flex-wrap gap-2">
              {result.requirement_actions.map(action => (
                <span
                  key={`${action.requirement_id}-${action.action}`}
                  className="text-[11px] border border-slate-800 rounded-lg px-2 py-1 text-gray-300 bg-slate-900/50"
                >
                  {action.action} {action.requirement_id} for {action.assigned_to}
                </span>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-gray-400" aria-hidden />
              Handoff Memo
            </p>
            <pre className="whitespace-pre-wrap text-xs text-gray-200 bg-slate-900 border border-slate-800 rounded-xl p-3 font-sans">
              {result.final_memo}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
