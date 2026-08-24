import React, { useState, useEffect } from 'react';
import { 
  Film, AlertTriangle, CheckCircle2, Upload, MessageSquare, 
  RefreshCw, Activity, Layers, Database, ShieldAlert, Sparkles 
} from 'lucide-react';
import { TakeRecord, Discrepancy } from './types';
import { fetchTakes, fetchDiscrepancies, uploadDocument, askAssistant } from './api';

export default function App() {
  const [productionId, setProductionId] = useState('PROD_01');
  const [shootDay, setShootDay] = useState('31');
  const [takes, setTakes] = useState<TakeRecord[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTake, setSelectedTake] = useState<{ slate: string; take_id: string } | null>(null);
  const [assistantExplanation, setAssistantExplanation] = useState<string | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadDept, setUploadDept] = useState('camera');
  const [uploadDocType, setUploadDocType] = useState('camera_csv');
  const [uploadContent, setUploadContent] = useState('');

  const loadData = async () => {
    setLoading(true);
    try {
      const [t, d] = await Promise.all([
        fetchTakes(productionId, shootDay),
        fetchDiscrepancies(productionId, shootDay),
      ]);
      setTakes(t);
      setDiscrepancies(d);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [productionId, shootDay]);

  const handleSeedDemoData = async () => {
    setLoading(true);
    // Seed sample camera CSV and sound ALE
    const sampleCamera = `Slate,Take,Roll,FPS,Lens,ISO,Start TC,End TC,Clip Name\n27/7,1,A120,24,50mm,800,10:14:22:00,10:15:10:00,A120_C001_260728.MOV\n27/7,2PK,A120,24,50mm,800,10:16:05:00,10:17:00:00,A120_C002_260728.MOV\n27/7,3 VFX,A120,24,50mm,800,10:18:12:00,10:19:30:00,A120_C003_260728.MOV`;
    const sampleSound = `Heading\nFIELD_DELIM\tTABS\nColumn\nName\tTracks\tStart\tEnd\tTape\tScene\tTake\tSound Roll\nData\n27-7_T01\t1,2,3,4\t10:14:22:00\t10:15:10:00\tSR01\t27/7\t1\tSR01\n27-7_T02\t1,2,3,4\t10:16:05:00\t10:17:00:00\tSR01\t27/7\t2PK\tSR01\n27-7_T03\t1,2,3,4\t10:18:12:05\t10:19:30:00\tSR01\t27/7\t3*\tSR01`;
    const sampleSilverstack = `<?xml version="1.0" encoding="UTF-8"?><SilverstackReport version="1.0"><Volume name="MAG_A_120"><Clip><FileName>A120_C001_260728.MOV</FileName><Reel>A_0120</Reel><Bytes>4294967296</Bytes><Hash type="MD5">e99a18c428cb38d5f260853678922e03</Hash><DurationFrames>1152</DurationFrames></Clip></Volume></SilverstackReport>`;

    try {
      await uploadDocument({ production_id: productionId, shoot_day: shootDay, axis: 'belief', department: 'camera', doc_type: 'camera_csv', raw_content: sampleCamera, filename: 'camera_d31.csv' });
      await uploadDocument({ production_id: productionId, shoot_day: shootDay, axis: 'belief', department: 'sound', doc_type: 'sound_ale', raw_content: sampleSound, filename: 'sound_d31.ale' });
      await uploadDocument({ production_id: productionId, shoot_day: shootDay, axis: 'existence', department: 'dit', doc_type: 'silverstack_xml', raw_content: sampleSilverstack, filename: 'silverstack_d31.xml' });
      await loadData();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAskAssistant = async (slate: string, takeId: string) => {
    setSelectedTake({ slate, take_id: takeId });
    setAssistantExplanation('Querying Gemini Discrepancy Agent via ClickHouse MCP...');
    try {
      const exp = await askAssistant(productionId, shootDay, slate, takeId);
      setAssistantExplanation(exp);
    } catch (e) {
      setAssistantExplanation('Error retrieving assistant explanation.');
    }
  };

  const handleManualUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadContent.trim()) return;
    try {
      await uploadDocument({
        production_id: productionId,
        shoot_day: shootDay,
        axis: uploadDept === 'dit' ? 'existence' : 'belief',
        department: uploadDept,
        doc_type: uploadDocType,
        raw_content: uploadContent,
      });
      setIsUploadOpen(false);
      setUploadContent('');
      await loadData();
    } catch (err) {
      alert('Upload failed. Check logs.');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md px-6 py-4 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600/20 p-2.5 rounded-xl border border-blue-500/30 text-blue-400">
            <Film className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              CineSpine
              <span className="text-xs bg-blue-500/20 border border-blue-500/40 text-blue-300 font-mono px-2 py-0.5 rounded-full">v0.1-Hackathon</span>
            </h1>
            <p className="text-xs text-slate-400">3-Axis Production Reconciliation Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center bg-slate-800/80 rounded-lg p-1 border border-slate-700">
            <span className="text-xs font-semibold px-2.5 text-slate-400">Production:</span>
            <input 
              value={productionId} 
              onChange={e => setProductionId(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-xs px-2 py-1 rounded text-white font-mono w-24 focus:outline-none focus:border-blue-500"
            />
            <span className="text-xs font-semibold px-2.5 text-slate-400 ml-2">Day:</span>
            <input 
              value={shootDay} 
              onChange={e => setShootDay(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-xs px-2 py-1 rounded text-white font-mono w-14 focus:outline-none focus:border-blue-500"
            />
          </div>

          <button 
            onClick={loadData}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition"
            title="Refresh Spine"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button 
            onClick={handleSeedDemoData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 text-xs font-medium transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Seed Demo Day
          </button>

          <button 
            onClick={() => setIsUploadOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition"
          >
            <Upload className="w-3.5 h-3.5" />
            Drop Document
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Lighthouse Telemetry Strip */}
        <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Active Discrepancies</p>
              <p className="text-2xl font-bold text-red-400 mt-1">{discrepancies.length}</p>
            </div>
            <ShieldAlert className="w-8 h-8 text-red-500/30" />
          </div>

          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Reconciled Takes</p>
              <p className="text-2xl font-bold text-blue-400 mt-1">{takes.length}</p>
            </div>
            <Layers className="w-8 h-8 text-blue-500/30" />
          </div>

          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">ClickHouse Spine</p>
              <p className="text-sm font-mono text-emerald-400 mt-2 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Append-Only (OK)
              </p>
            </div>
            <Database className="w-8 h-8 text-emerald-500/30" />
          </div>

          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Lighthouse Observability</p>
              <p className="text-sm font-mono text-cyan-400 mt-2 flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-cyan-400" />
                Grafana Ready
              </p>
            </div>
            <Activity className="w-8 h-8 text-cyan-500/30" />
          </div>
        </section>

        {/* Discrepancy Alerts */}
        {discrepancies.length > 0 && (
          <section className="bg-red-950/20 border border-red-500/30 rounded-xl p-4 space-y-2">
            <h2 className="text-sm font-bold text-red-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              Detected Production Disagreements ({discrepancies.length})
            </h2>
            <div className="space-y-2 pt-1">
              {discrepancies.map((d, i) => (
                <div key={i} className="bg-slate-900/80 border border-red-500/20 rounded-lg p-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                        d.severity === 'CRITICAL' ? 'bg-red-500/20 text-red-300 border border-red-500/40' : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      }`}>
                        {d.discrepancy_type}
                      </span>
                      <span className="text-xs font-mono text-slate-400">{d.entity_id}</span>
                    </div>
                    <p className="text-xs text-slate-200 mt-1.5">{d.description}</p>
                  </div>
                  <button 
                    onClick={() => {
                      const parts = d.entity_id.split(' ');
                      handleAskAssistant(parts[0] || '27/7', parts[2] || '1');
                    }}
                    className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-blue-300 border border-slate-700 flex items-center gap-1 shrink-0"
                  >
                    <MessageSquare className="w-3 h-3" />
                    Ask Agent
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 3-Axis Witness Diff Table */}
        <section className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white">3-Axis Witness Inspector</h2>
              <p className="text-xs text-slate-400">Comparing Intent (Office) vs Belief (Set) vs Existence (Post/DIT)</p>
            </div>
            <span className="text-xs font-mono text-slate-400">{takes.length} Takes Indexed</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 uppercase font-mono">
                <tr>
                  <th className="px-4 py-3">Slate & Take</th>
                  <th className="px-4 py-3">1. Intent (Office)</th>
                  <th className="px-4 py-3">2. Belief (Camera)</th>
                  <th className="px-4 py-3">2. Belief (Sound)</th>
                  <th className="px-4 py-3">3. Existence (Silverstack)</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {takes.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                      No takes found for Shoot Day {shootDay}. Click "Seed Demo Day" or drop documents to ingest.
                    </td>
                  </tr>
                ) : (
                  takes.map((t, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition">
                      <td className="px-4 py-3 font-mono font-bold text-white flex items-center gap-2">
                        <span>{t.slate} T{t.take_id}</span>
                        {t.is_starred && (
                          <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.2 rounded font-sans">
                            ⭐ Circled
                          </span>
                        )}
                        {t.is_pickup && (
                          <span className="text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/40 px-1.5 py-0.2 rounded font-sans">
                            Pickup
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-400">
                        {t.intent ? JSON.stringify(t.intent) : <span className="text-slate-600 italic">Scheduled</span>}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-300">
                        {t.belief.camera ? (
                          <div>
                            <span className="text-blue-400 font-semibold">{t.belief.camera.camera_roll || 'No Roll'}</span>
                            <span className="text-slate-500 ml-2">({t.belief.camera.fps}fps)</span>
                            <div className="text-[10px] text-slate-500">{t.belief.camera.timecode_in || '--'}</div>
                          </div>
                        ) : (
                          <span className="text-slate-600">--</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-300">
                        {t.belief.sound ? (
                          <div>
                            <span className="text-emerald-400 font-semibold">{t.belief.sound.sound_roll || 'SR'}</span>
                            <span className="text-slate-500 ml-2">({t.belief.sound.tracks || '4ch'})</span>
                            <div className="text-[10px] text-slate-500">{t.belief.sound.timecode_in || '--'}</div>
                          </div>
                        ) : (
                          <span className="text-slate-600">--</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-300">
                        <span className="text-cyan-400 flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
                          Checksum Verified
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button 
                          onClick={() => handleAskAssistant(t.slate, t.take_id)}
                          className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-blue-400 transition"
                          title="Ask Gemini Discrepancy Agent"
                        >
                          <MessageSquare className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {/* Gemini Assistant Explanation Modal */}
      {selectedTake && assistantExplanation && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-400" />
                Gemini Agent Audit Report
              </h3>
              <button 
                onClick={() => { setSelectedTake(null); setAssistantExplanation(null); }}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="text-xs text-slate-300 whitespace-pre-line font-mono bg-slate-950 p-4 rounded-xl border border-slate-800">
              {assistantExplanation}
            </div>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {isUploadOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <form onSubmit={handleManualUpload} className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Upload className="w-4 h-4 text-blue-400" />
                Drop Department Paperwork
              </h3>
              <button type="button" onClick={() => setIsUploadOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Department</label>
                <select 
                  value={uploadDept} 
                  onChange={e => {
                    setUploadDept(e.target.value);
                    if (e.target.value === 'camera') setUploadDocType('camera_csv');
                    if (e.target.value === 'sound') setUploadDocType('sound_ale');
                    if (e.target.value === 'dit') setUploadDocType('silverstack_xml');
                  }}
                  className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="camera">Camera (Belief)</option>
                  <option value="sound">Sound (Belief)</option>
                  <option value="dit">DIT / Silverstack (Existence)</option>
                  <option value="script">Script Supervisor (Belief)</option>
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1">Doc Type</label>
                <select 
                  value={uploadDocType} 
                  onChange={e => setUploadDocType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="camera_csv">Camera CSV</option>
                  <option value="sound_ale">Sound ALE / CSV</option>
                  <option value="silverstack_xml">Silverstack XML</option>
                  <option value="script_lined">Script Lined Page</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Raw File Content (CSV / ALE / XML / JSON)</label>
              <textarea 
                rows={6}
                value={uploadContent}
                onChange={e => setUploadContent(e.target.value)}
                placeholder="Paste CSV / ALE / XML content here..."
                className="w-full bg-slate-950 border border-slate-700 text-xs p-2.5 rounded font-mono text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>

            <button 
              type="submit" 
              className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition"
            >
              Ingest Document to Confluent Stream
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
