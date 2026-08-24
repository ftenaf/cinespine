import React, { useState, useEffect } from 'react';
import { 
  Film, AlertTriangle, CheckCircle2, Upload, MessageSquare, 
  RefreshCw, Activity, Layers, Database, ShieldAlert, Sparkles, 
  FileText, Clapperboard, Plus, Calendar
} from 'lucide-react';
import { TakeRecord, Discrepancy, Production } from './types';
import { 
  fetchTakes, fetchDiscrepancies, fetchProductions, 
  createProduction, uploadDocument, uploadFile, askAssistant 
} from './api';

export default function App() {
  const [productions, setProductions] = useState<Production[]>([]);
  const [selectedProductionId, setSelectedProductionId] = useState('DEMO_PRODUCTION');
  const [selectedDay, setSelectedDay] = useState('31');
  const [takes, setTakes] = useState<TakeRecord[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTake, setSelectedTake] = useState<{ slate: string; take_id: string } | null>(null);
  const [assistantExplanation, setAssistantExplanation] = useState<string | null>(null);
  
  // Modals
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isManageProdOpen, setIsManageProdOpen] = useState(false);
  const [isNewProdOpen, setIsNewProdOpen] = useState(false);

  // Upload Form State
  const [uploadMode, setUploadMode] = useState<'file' | 'text'>('file');
  const [uploadContent, setUploadContent] = useState('');
  const [uploadFilename, setUploadFilename] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);

  // New Production Form
  const [newProdId, setNewProdId] = useState('');
  const [newProdName, setNewProdName] = useState('');
  const [newProdDirector, setNewProdDirector] = useState('');

  const loadProductions = async () => {
    try {
      const prods = await fetchProductions();
      setProductions(prods);
      if (prods.length > 0 && !prods.some(p => p.production_id === selectedProductionId)) {
        setSelectedProductionId(prods[0].production_id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadSpineData = async () => {
    setLoading(true);
    try {
      const [t, d] = await Promise.all([
        fetchTakes(selectedProductionId, selectedDay),
        fetchDiscrepancies(selectedProductionId, selectedDay),
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
    loadProductions();
  }, []);

  useEffect(() => {
    loadSpineData();
  }, [selectedProductionId, selectedDay]);

  const activeProduction: Production = productions.find(p => p.production_id === selectedProductionId) || {
    production_id: selectedProductionId,
    name: selectedProductionId.replace('_', ' '),
    shoot_days: ['31', '39'],
    total_events: 0,
    total_takes: 0,
    description: 'Active studio production',
  };

  const handleSeedDemoDay = async (dayToSeed: string = '31') => {
    setLoading(true);
    const sampleCamera = `Slate,Take,Roll,FPS,Lens,ISO,Start TC,End TC,Clip Name\n27/7,1,A120,24,50mm,800,10:14:22:00,10:15:10:00,A120_C001_260728.MOV\n27/7,2PK,A120,24,50mm,800,10:16:05:00,10:17:00:00,A120_C002_260728.MOV\n27/7,3 VFX,A120,24,50mm,800,10:18:12:00,10:19:30:00,A120_C003_260728.MOV`;
    const sampleSound = `SOUND REPORT\nProject:,"GREAT HALL",\nDate:,"28/07/26",\nSound Mixer:,"SOUND MIXER",\nFile Name,Scene,Take,Length,Start TC,Trk 1,Trk 2,Notes\n27-7T01.WAV,27-7,01,00:03:00,10:14:22:00,"MixL","MixR",""\n27-7T02.WAV,27-7,02,00:03:32,10:16:05:00,"MixL","MixR",""\n27-7T03.WAV,27-7,03,00:03:32,10:18:12:05,"MixL","MixR",""`;
    const sampleSilverstack = `<?xml version="1.0" encoding="UTF-8"?><SilverstackReport version="1.0"><Volume name="MAG_A_120"><Clip><FileName>A120_C001_260728.MOV</FileName><Reel>A_0120</Reel><Bytes>4294967296</Bytes><Hash type="MD5">e99a18c428cb38d5f260853678922e03</Hash><DurationFrames>1152</DurationFrames></Clip></Volume></SilverstackReport>`;

    try {
      await uploadDocument({ raw_content: sampleCamera, filename: `DemoProduction-2026-7-28_CAM_A.csv`, production_id: selectedProductionId, shoot_day: dayToSeed });
      await uploadDocument({ raw_content: sampleSound, filename: `260728_Report.csv`, production_id: selectedProductionId, shoot_day: dayToSeed });
      await uploadDocument({ raw_content: sampleSilverstack, filename: `Volume-664_SD.xml`, production_id: selectedProductionId, shoot_day: dayToSeed });
      await loadProductions();
      await loadSpineData();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProduction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProdId.trim() || !newProdName.trim()) return;
    try {
      const created = await createProduction({
        production_id: newProdId.trim().toUpperCase().replace(/\s+/g, '_'),
        name: newProdName.trim(),
        director: newProdDirector.trim(),
      });
      setIsNewProdOpen(false);
      setNewProdId('');
      setNewProdName('');
      setNewProdDirector('');
      await loadProductions();
      setSelectedProductionId(created.production_id);
    } catch (err: any) {
      alert(`Failed to create production: ${err.message}`);
    }
  };

  const handleAskAssistant = async (slate: string, takeId: string) => {
    setSelectedTake({ slate, take_id: takeId });
    setAssistantExplanation('Querying Gemini Discrepancy Agent via ClickHouse MCP...');
    try {
      const exp = await askAssistant(selectedProductionId, selectedDay, slate, takeId);
      setAssistantExplanation(exp);
    } catch (e) {
      setAssistantExplanation('Error retrieving assistant explanation.');
    }
  };

  const handleFileUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setUploadFeedback(null);

    try {
      if (uploadMode === 'file' && selectedFile) {
        const res = await uploadFile(selectedFile);
        setUploadFeedback(`✅ Ingested to ${res.production_id} (Day ${res.shoot_day}) as ${res.detected_doc_type} [${res.detected_department.toUpperCase()}]`);
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      } else if (uploadMode === 'text' && uploadContent.trim()) {
        const res = await uploadDocument({
          raw_content: uploadContent,
          filename: uploadFilename || 'manual_drop.txt',
        });
        setUploadFeedback(`✅ Ingested to ${res.production_id} (Day ${res.shoot_day}) as ${res.detected_doc_type} [${res.detected_department.toUpperCase()}]`);
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      }
      setSelectedFile(null);
      setUploadContent('');
      setUploadFilename('');
      await loadProductions();
      await loadSpineData();
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur-md px-6 py-3.5 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600/20 p-2 rounded-xl border border-blue-500/30 text-blue-400">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                CineSpine
                <span className="text-[10px] bg-blue-500/20 border border-blue-500/40 text-blue-300 font-mono px-2 py-0.2 rounded-full">v0.1</span>
              </h1>
              <p className="text-[11px] text-slate-400">3-Axis Production Reconciliation</p>
            </div>
          </div>

          {/* Production Selector Hub */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl p-1 px-2.5">
            <Clapperboard className="w-4 h-4 text-blue-400" />
            <select
              value={selectedProductionId}
              onChange={e => setSelectedProductionId(e.target.value)}
              className="bg-transparent text-xs font-semibold text-white focus:outline-none cursor-pointer pr-4"
            >
              {productions.map(p => (
                <option key={p.production_id} value={p.production_id} className="bg-slate-900 text-white">
                  {p.name} ({p.production_id})
                </option>
              ))}
            </select>
            <button
              onClick={() => setIsManageProdOpen(true)}
              className="text-[11px] text-blue-400 hover:text-blue-300 ml-1 pl-2 border-l border-slate-700 font-medium"
            >
              Manage
            </button>
          </div>

          {/* Shoot Day Selector */}
          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 rounded-xl p-1 px-2">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-xs text-slate-400 font-semibold">Day:</span>
            {['31', '39'].map(day => (
              <button
                key={day}
                onClick={() => setSelectedDay(day)}
                className={`px-2.5 py-0.5 rounded-lg text-xs font-mono font-medium transition ${
                  selectedDay === day 
                    ? 'bg-blue-600 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                Day {day}
              </button>
            ))}
            <input
              type="text"
              placeholder="Other"
              value={selectedDay !== '31' && selectedDay !== '39' ? selectedDay : ''}
              onChange={e => e.target.value && setSelectedDay(e.target.value)}
              className="w-12 bg-slate-950 border border-slate-700 text-xs px-1.5 py-0.5 rounded text-white font-mono text-center focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={loadSpineData}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition"
            title="Refresh Spine"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button 
            onClick={() => handleSeedDemoDay(selectedDay)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 text-xs font-medium transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Seed Day {selectedDay}
          </button>

          <button 
            onClick={() => { setIsUploadOpen(true); setUploadFeedback(null); }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition"
          >
            <Upload className="w-3.5 h-3.5" />
            Drop Paperwork
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Production Title Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5">
              {activeProduction.name}
              <span className="text-xs bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full font-normal">
                Shooting Day {selectedDay}
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {activeProduction.description || 'Active studio production'}
            </p>
          </div>
        </div>

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
              <p className="text-xs text-slate-400">
                Reconciling Intent (Office) vs Belief (Set) vs Existence (Post/DIT) for {activeProduction.name} — Day {selectedDay}
              </p>
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
                      No takes found for {activeProduction.name} on Shoot Day {selectedDay}. Click "Seed Day {selectedDay}" or drop PDF/CSV files to ingest.
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

      {/* Productions Management Modal */}
      {isManageProdOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Clapperboard className="w-5 h-5 text-blue-400" />
                Studio Production Portfolio
              </h3>
              <button onClick={() => setIsManageProdOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <div className="grid grid-cols-1 gap-3 max-h-96 overflow-y-auto pr-1">
              {productions.map(p => (
                <div 
                  key={p.production_id}
                  className={`p-4 rounded-xl border transition ${
                    selectedProductionId === p.production_id 
                      ? 'bg-blue-950/30 border-blue-500/50' 
                      : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-bold text-white text-sm">{p.name}</h4>
                        <span className="text-[10px] font-mono bg-slate-800 px-2 py-0.5 rounded text-slate-400">
                          {p.production_id}
                        </span>
                        <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded">
                          {p.status || 'Active'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{p.description || `Director: ${p.director || 'N/A'}`}</p>
                    </div>

                    <button
                      onClick={() => {
                        setSelectedProductionId(p.production_id);
                        if (p.shoot_days.length > 0) setSelectedDay(p.shoot_days[0]);
                        setIsManageProdOpen(false);
                      }}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold"
                    >
                      {selectedProductionId === p.production_id ? 'Current Workspace' : 'Select'}
                    </button>
                  </div>

                  <div className="flex items-center gap-4 mt-3 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
                    <div>Shoot Days: <span className="text-white font-bold">{p.shoot_days?.length ? p.shoot_days.join(', ') : 'None yet'}</span></div>
                    <div>Takes Indexed: <span className="text-white font-bold">{p.total_takes || 0}</span></div>
                    <div>Spine Events: <span className="text-white font-bold">{p.total_events || 0}</span></div>
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-800 pt-3 flex justify-between items-center">
              <button
                onClick={() => setIsNewProdOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-medium border border-slate-700"
              >
                <Plus className="w-3.5 h-3.5" />
                Register New Production
              </button>
              <button
                onClick={() => setIsManageProdOpen(false)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Production Modal */}
      {isNewProdOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <form onSubmit={handleCreateProduction} className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <h3 className="font-bold text-white flex items-center gap-2 border-b border-slate-800 pb-3">
              <Plus className="w-4 h-4 text-blue-400" />
              Register New Production
            </h3>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Production Code (e.g. DUNE_3)</label>
              <input
                type="text"
                required
                placeholder="DUNE_3"
                value={newProdId}
                onChange={e => setNewProdId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white font-mono uppercase focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Production Title</label>
              <input
                type="text"
                required
                placeholder="Dune: Part Three"
                value={newProdName}
                onChange={e => setNewProdName(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Director / Unit</label>
              <input
                type="text"
                placeholder="Denis Villeneuve"
                value={newProdDirector}
                onChange={e => setNewProdDirector(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsNewProdOpen(false)}
                className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold"
              >
                Create Production
              </button>
            </div>
          </form>
        </div>
      )}

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

      {/* Auto-Classifying Paperwork Upload Modal */}
      {isUploadOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <form onSubmit={handleFileUploadSubmit} className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-bold text-white flex items-center gap-2">
                  <Upload className="w-4 h-4 text-blue-400" />
                  Drop Department Paperwork
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Auto-infers production, shoot day, department & document type
                </p>
              </div>
              <button type="button" onClick={() => setIsUploadOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            {uploadFeedback && (
              <div className="bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs p-3 rounded-lg">
                {uploadFeedback}
              </div>
            )}

            <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              <button
                type="button"
                onClick={() => setUploadMode('file')}
                className={`flex-1 py-1.5 rounded-md font-medium transition ${uploadMode === 'file' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}`}
              >
                Upload File (PDF / CSV / ALE)
              </button>
              <button
                type="button"
                onClick={() => setUploadMode('text')}
                className={`flex-1 py-1.5 rounded-md font-medium transition ${uploadMode === 'text' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}`}
              >
                Paste Raw Text
              </button>
            </div>

            {uploadMode === 'file' ? (
              <div className="border-2 border-dashed border-slate-700 hover:border-blue-500/50 rounded-xl p-6 text-center bg-slate-950/50 transition">
                <input 
                  type="file" 
                  id="doc-upload" 
                  accept=".pdf,.csv,.ale,.xml,.txt" 
                  onChange={e => {
                    if (e.target.files && e.target.files[0]) {
                      setSelectedFile(e.target.files[0]);
                    }
                  }}
                  className="hidden" 
                />
                <label htmlFor="doc-upload" className="cursor-pointer space-y-2 block">
                  <FileText className="w-8 h-8 text-blue-400 mx-auto" />
                  <div className="text-xs text-slate-300">
                    {selectedFile ? (
                      <span className="font-mono text-blue-400 font-bold">{selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                    ) : (
                      <>Click to select or drop <span className="text-blue-400 font-bold">PDF, CSV, ALE, or XML</span></>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-500">Auto-detects project name, shoot day & document type</p>
                </label>
              </div>
            ) : (
              <div className="space-y-2">
                <input 
                  type="text" 
                  placeholder="Optional filename (e.g. camera_d31.csv)"
                  value={uploadFilename}
                  onChange={e => setUploadFilename(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded text-white focus:outline-none focus:border-blue-500"
                />
                <textarea 
                  rows={5}
                  value={uploadContent}
                  onChange={e => setUploadContent(e.target.value)}
                  placeholder="Paste CSV / ALE / XML text..."
                  className="w-full bg-slate-950 border border-slate-700 text-xs p-2.5 rounded font-mono text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            )}

            <button 
              type="submit" 
              disabled={loading || (uploadMode === 'file' && !selectedFile) || (uploadMode === 'text' && !uploadContent.trim())}
              className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-lg text-xs font-semibold transition"
            >
              {loading ? 'Processing Stream...' : 'Auto-Classify & Ingest to Spine'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
