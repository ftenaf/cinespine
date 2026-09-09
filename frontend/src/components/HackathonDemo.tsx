import React, { useState } from 'react';
import { RefreshCw, PlayCircle, Terminal } from 'lucide-react';
import { useWebMCP } from '../hooks/useWebMCP';

const API_BASE_URL = '/api';

export const HackathonDemo: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const runDemo = async () => {
    setIsRunning(true);
    setLogs([]);
    try {
      addLog("Starting End-to-End Demo...");
      
      // 1. Wipe
      addLog("1. Wiping previous state...");
      const wipeRes = await fetch(`${API_BASE_URL}/demo/wipe`, { method: 'POST' });
      if (!wipeRes.ok) throw new Error(`Backend error (${wipeRes.status}): Make sure the backend server is running.`);
      const wipeData = await wipeRes.json();
      addLog(`Wipe Result: ${wipeData.message}`);

      // 2. Inject
      addLog("2. Injecting synthetic Screenplay and TCLog...");
      const injectRes = await fetch(`${API_BASE_URL}/events/demo`);
      if (!injectRes.ok) throw new Error(`Backend error (${injectRes.status}) during injection.`);
      const injectData = await injectRes.json();
      addLog(`Injection Result: ${injectData.message}`);

      // Wait a bit
      addLog("Waiting 5 seconds for events to settle in ClickHouse...");
      await new Promise(r => setTimeout(r, 5000));

      // 3. Agent
      addLog("3. Asking Wrap Rescue Agent (Gemini Flash) about discrepancies...");
      const agentRes = await fetch(`${API_BASE_URL}/wrap-rescue/demo`);
      if (!agentRes.ok) throw new Error(`Backend error (${agentRes.status}) during agent query.`);
      const agentData = await agentRes.json();
      addLog(`Agent Response:\n\n${agentData.response.response}`);
      
      addLog("Demo Completed Successfully!");
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err: any) {
      addLog(`Error during demo: ${err.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const factoryReset = async () => {
    setIsRunning(true);
    try {
      addLog("Initiating Factory Reset...");
      const res = await fetch(`${API_BASE_URL}/demo/wipe`, { method: 'POST' });
      if (!res.ok) throw new Error(`Backend error (${res.status}): Make sure the backend server is running.`);
      const data = await res.json();
      addLog(`Factory Reset: ${data.message}`);
      
      // The backend wipe drops all sqlite tables, but the frontend React
      // context doesn't know. Reload to ensure the productions list is updated.
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err: any) {
      addLog(`Error during reset: ${err.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  useWebMCP([
    {
      // Named for what it does. It truncates every table in the spine; the
      // 2026-09-06 data loss started with this button. The spec has no consent
      // step yet, so the page requires the agent to say it means it.
      name: 'wipe_all_production_data',
      description: 'IRREVERSIBLE. Deletes every production, requirement, screenplay and event in the spine, then reloads the page. Only for resetting a demo environment. Requires confirm=true.',
      inputSchema: {
        type: 'object',
        properties: {
          confirm: { type: 'boolean', description: 'Must be true. The agent should ask the user first.' }
        },
        required: ['confirm']
      },
      annotations: { destructiveHint: true },
      execute: async (inputs: { confirm?: boolean }) => {
        if (inputs?.confirm !== true) {
          return { error: 'Refused: confirm=true is required, and the user should be asked before wiping the spine.' };
        }
        await factoryReset();
        return { message: 'Factory reset initiated; the page will reload.' };
      }
    },
    {
      name: 'run_full_demo',
      description: 'Run the full end-to-end hackathon demo automatically.',
      inputSchema: { type: 'object', properties: {} },
      execute: async () => {
        await runDemo();
        return { message: 'Full demo initiated.' };
      }
    }
  ]);

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
        <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-2">
          <Terminal className="text-spine-accent" /> Hackathon Demo Runner
        </h2>
        <p className="text-gray-400 mb-6">
          Executes the end-to-end flow showcasing Google Cloud Document AI, Gemini Flash routing, and ClickHouse event spine ingestion.
        </p>

        <div className="flex gap-4 mb-8">
          <button
            onClick={runDemo}
            disabled={isRunning}
            className="flex items-center gap-2 px-6 py-3 bg-spine-accent hover:bg-blue-600 text-white font-bold rounded-xl transition disabled:opacity-50"
          >
            <PlayCircle size={20} />
            {isRunning ? 'Running Demo...' : 'Run Full Demo'}
          </button>
          <button
            onClick={() => {
              // Truncates every table in the spine; on 2026-09-06 this button
              // was the first step of a data-loss afternoon. The WebMCP tool
              // already demands confirm=true; the button now asks too.
              if (window.confirm('Factory Reset deletes every production, requirement, screenplay and event in the spine. This cannot be undone. Continue?')) {
                void factoryReset();
              }
            }}
            disabled={isRunning}
            className="flex items-center gap-2 px-6 py-3 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl border border-slate-700 transition disabled:opacity-50"
          >
            <RefreshCw size={20} />
            Factory Reset
          </button>
        </div>

        <div className="bg-black/50 rounded-xl p-4 border border-slate-800 h-[400px] overflow-y-auto font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-gray-500 italic">No logs yet. Click 'Run Full Demo' to begin.</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="text-green-400 mb-2 whitespace-pre-wrap">
                {log}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
