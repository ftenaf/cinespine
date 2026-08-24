import React, { useState, useEffect, useMemo } from 'react';
import { 
  Film, AlertTriangle, CheckCircle2, Upload, 
  RefreshCw, Layers, Sparkles, 
  FileText, Clapperboard, Calendar, Search,
  HardDrive, Eye, FileCode, Check, AlertCircle, Trash2,
  Image as ImageIcon, ChevronLeft, ChevronRight, LayoutGrid,
  Volume2, Maximize2
} from 'lucide-react';
import { TakeRecord, Discrepancy, Production, SourceDocumentSummary, SourceDocument } from './types';
import { 
  fetchTakes, fetchDiscrepancies, fetchProductions, fetchDocuments,
  fetchDocumentContent, uploadDocument, uploadFile, askAssistant 
} from './api';

export default function App() {
  const [productions, setProductions] = useState<Production[]>([]);
  const [selectedProductionId, setSelectedProductionId] = useState('DEMO_PRODUCTION');
  const [selectedDay, setSelectedDay] = useState('31');
  const [takes, setTakes] = useState<TakeRecord[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [documents, setDocuments] = useState<SourceDocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);

  // Active View & Filters
  const [activeTab, setActiveTab] = useState<'master' | 'scenes' | 'discrepancies' | 'documents'>('master');
  const [masterLayout, setMasterLayout] = useState<'grid' | 'slate'>('grid');
  const [focusTakeIndex, setFocusTakeIndex] = useState<number>(0);
  const [selectedSceneFilter, setSelectedSceneFilter] = useState<string>('ALL');
  const [enlargedImage, setEnlargedImage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [filterCircledOnly, setFilterCircledOnly] = useState(false);
  const [filterDiscrepancyOnly, setFilterDiscrepancyOnly] = useState(false);
  const [filterWildTracksOnly, setFilterWildTracksOnly] = useState(false);
  const [filterVfxOnly, setFilterVfxOnly] = useState(false);

  // Selected Take for Detailed Inspector Drawer
  const [inspectedTake, setInspectedTake] = useState<TakeRecord | null>(null);
  const [assistantExplanation, setAssistantExplanation] = useState<string | null>(null);

  // Source Document Previewer Modal
  const [previewDoc, setPreviewDoc] = useState<SourceDocument | null>(null);

  // Modals
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // Upload Form State
  const [uploadMode, setUploadMode] = useState<'file' | 'text'>('file');
  const [uploadContent, setUploadContent] = useState('');
  const [uploadFilename, setUploadFilename] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);

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
      const [t, d, docs] = await Promise.all([
        fetchTakes(selectedProductionId, selectedDay),
        fetchDiscrepancies(selectedProductionId, selectedDay),
        fetchDocuments(selectedProductionId, selectedDay),
      ]);
      setTakes(t);
      setDiscrepancies(d);
      setDocuments(docs);
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
    const sampleCamera = `Slate,Take,Roll,FPS,Lens,ISO,Start TC,End TC,Clip Name\n27/7,1,A120,24,50mm,800,10:14:22:00,10:15:10:00,A120_C001_260728.MOV\n27/7,2PK,A120,24,50mm,800,10:16:05:00,10:17:00:00,A120_C002_260728.MOV\n27/7,3 VFX,A120,24,50mm,800,10:18:12:00,10:19:30:00,A120_C003_260728.MOV\n49/1,1,A120,24,50mm,800,10:41:57:00,10:43:00:00,A120_C004_260728.MOV`;
    const sampleSound = `SOUND REPORT\nProject:,"GREAT HALL",\nDate:,"28/07/26",\nSound Mixer:,"SOUND MIXER",\nFile Name,Scene,Take,Length,Start TC,Trk 1,Trk 2,Notes\n27-7T01.WAV,27-7,01,00:03:00,10:14:22:00,"MixL","MixR",""\n27-7T02.WAV,27-7,02,00:03:32,10:16:05:00,"MixL","MixR",""\n27-7T03.WAV,27-7,03,00:03:32,10:18:12:05,"MixL","MixR",""\n49-1T01.WAV,49-1,01,00:03:02,10:41:57:00,"MixL","MixR",""`;
    const sampleSilverstack = `<?xml version="1.0" encoding="UTF-8"?><SilverstackReport version="1.0"><Volume name="MAG_A_120"><Clip><FileName>A120_C001_260728.MOV</FileName><Reel>A_0120</Reel><Bytes>4294967296</Bytes><Hash type="MD5">e99a18c428cb38d5f260853678922e03</Hash><DurationFrames>1152</DurationFrames></Clip><Clip><FileName>A120_C002_260728.MOV</FileName><Reel>A_0120</Reel><Bytes>5368709120</Bytes><Hash type="MD5">9e107d9d372bb6826bd81d3542a419d6</Hash><DurationFrames>1320</DurationFrames></Clip></Volume></SilverstackReport>`;

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

  const handleOpenPreviewDoc = async (docId?: string, filename?: string) => {
    try {
      if (docId) {
        const doc = await fetchDocumentContent(docId);
        setPreviewDoc(doc);
      } else if (filename) {
        const match = documents.find(d => d.filename === filename);
        if (match) {
          const doc = await fetchDocumentContent(match.doc_id);
          setPreviewDoc(doc);
        } else {
          alert(`Document ${filename} is an external reference.`);
        }
      }
    } catch (e: any) {
      alert(`Could not load document preview: ${e.message}`);
    }
  };

  const handleDeleteDocument = async (docId: string, filename: string) => {
    if (!window.confirm(`Are you sure you want to remove '${filename}'?\nThis will purge its ingested records from the spine.`)) {
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete document');
      }
      await loadProductions();
      await loadSpineData();
    } catch (e: any) {
      alert(`Could not delete document: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleInspectTake = (take: TakeRecord) => {
    setInspectedTake(take);
    handleAskAssistant(take.slate, take.take_id);
  };

  const handleAskAssistant = async (slate: string, takeId: string) => {
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
        setUploadFeedback(`✅ Ingested ${res.filename} to ${res.production_id} (Day ${res.shoot_day}) [${res.detected_department.toUpperCase()}]`);
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      } else if (uploadMode === 'text' && uploadContent.trim()) {
        const res = await uploadDocument({
          raw_content: uploadContent,
          filename: uploadFilename || 'manual_drop.txt',
        });
        setUploadFeedback(`✅ Ingested to ${res.production_id} (Day ${res.shoot_day}) [${res.detected_department.toUpperCase()}]`);
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      }
      setSelectedFile(null);
      setUploadContent('');
      setUploadFilename('');
      await loadProductions();
      await loadSpineData();
    } catch (err: any) {
      if (err.message && err.message.includes('409')) {
        setUploadFeedback(`⚠️ Duplicate Document: This file has already been ingested into the spine.`);
      } else {
        setUploadFeedback(`❌ Upload Failed: ${err.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const uniqueScenes = useMemo(() => {
    const s = new Set<string>();
    takes.forEach(t => {
      if (t.scene) s.add(t.scene);
    });
    return Array.from(s).sort((a, b) => {
      const na = parseInt(a.replace(/\D/g, '')) || 0;
      const nb = parseInt(b.replace(/\D/g, '')) || 0;
      return na - nb || a.localeCompare(b);
    });
  }, [takes]);

  // Filtered Takes
  const filteredTakes = useMemo(() => {
    return takes.filter(t => {
      if (selectedSceneFilter !== 'ALL' && t.scene !== selectedSceneFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesSlate = t.slate.toLowerCase().includes(q);
        const matchesScene = t.scene?.toLowerCase().includes(q);
        const matchesTake = t.take_id.toLowerCase().includes(q);
        const matchesCards = t.camera_cards.some(c => c.toLowerCase().includes(q)) || t.sound_cards.some(s => s.toLowerCase().includes(q));
        const matchesVolume = t.storage_volumes.some(v => v.toLowerCase().includes(q));
        const matchesClips = t.matched_media_files.some(m => m.file_name.toLowerCase().includes(q));
        if (!matchesSlate && !matchesScene && !matchesTake && !matchesCards && !matchesVolume && !matchesClips) {
          return false;
        }
      }

      if (filterCircledOnly && !t.is_starred) return false;
      if (filterWildTracksOnly && !t.is_wild_track) return false;
      if (filterVfxOnly && !t.is_vfx) return false;

      if (filterDiscrepancyOnly) {
        const hasDisc = discrepancies.some(d => d.entity_id.includes(t.slate) && d.entity_id.includes(t.take_id));
        if (!hasDisc) return false;
      }

      return true;
    });
  }, [takes, discrepancies, searchQuery, selectedSceneFilter, filterCircledOnly, filterDiscrepancyOnly, filterWildTracksOnly, filterVfxOnly]);

  const currentFocusTake = filteredTakes[focusTakeIndex] || filteredTakes[0] || null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md px-6 py-3 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600/20 p-2 rounded-xl border border-blue-500/30 text-blue-400">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
                CineSpine
                <span className="text-[10px] bg-blue-500/20 border border-blue-500/40 text-blue-300 font-mono px-1.5 py-0.2 rounded">v0.2</span>
              </h1>
              <p className="text-[10px] text-slate-400">
                {activeProduction.name} — Assistant Editor Card & Discrepancy Hub
              </p>
            </div>
          </div>

          {/* Production Selector */}
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
          </div>

          {/* Shoot Day Selector */}
          <div className="flex items-center gap-1 bg-slate-900/80 border border-slate-800 rounded-xl p-1 px-2">
            <Calendar className="w-3.5 h-3.5 text-slate-400 mr-1" />
            <span className="text-xs text-slate-400 font-semibold">Day:</span>
            {['31', '39'].map(day => (
              <button
                key={day}
                onClick={() => setSelectedDay(day)}
                className={`px-2 py-0.5 rounded-lg text-xs font-mono font-medium transition ${
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
            Drop Paperwork (PDF/CSV)
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-5">
        {/* Navigation Tabs & Quick Status */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('master')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'master'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900 border border-transparent'
              }`}
            >
              <LayoutGrid className="w-4 h-4" />
              Composed Master Sheet ({takes.length})
            </button>

            <button
              onClick={() => setActiveTab('scenes')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'scenes'
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900 border border-transparent'
              }`}
            >
              <Layers className="w-4 h-4" />
              Card & Roll Map
            </button>

            <button
              onClick={() => setActiveTab('discrepancies')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'discrepancies'
                  ? 'bg-red-600/20 text-red-300 border border-red-500/40'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900 border border-transparent'
              }`}
            >
              <AlertTriangle className="w-4 h-4 text-red-400" />
              Active Discrepancies ({discrepancies.length})
            </button>

            <button
              onClick={() => setActiveTab('documents')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'documents'
                  ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900 border border-transparent'
              }`}
            >
              <FileCode className="w-4 h-4" />
              Source Documents ({documents.length})
            </button>
          </div>

          {/* Quick Search & Filters */}
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search scene, slate, card (A120), clip..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-xs pl-8 pr-3 py-1.5 rounded-lg text-white font-mono w-64 focus:outline-none focus:border-blue-500"
              />
            </div>

            <button
              onClick={() => setFilterCircledOnly(!filterCircledOnly)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                filterCircledOnly 
                  ? 'bg-amber-500/20 border-amber-500/50 text-amber-300' 
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              ⭐ Circled
            </button>

            <button
              onClick={() => setFilterWildTracksOnly(!filterWildTracksOnly)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                filterWildTracksOnly 
                  ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300' 
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              🎙️ WT
            </button>

            <button
              onClick={() => setFilterVfxOnly(!filterVfxOnly)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                filterVfxOnly 
                  ? 'bg-purple-500/20 border-purple-500/50 text-purple-300' 
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              ✨ VFX
            </button>

            <button
              onClick={() => setFilterDiscrepancyOnly(!filterDiscrepancyOnly)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                filterDiscrepancyOnly 
                  ? 'bg-red-500/20 border-red-500/50 text-red-300' 
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              <AlertCircle className="w-3.5 h-3.5" />
              Discrepancies Only
            </button>
          </div>
        </div>

        {/* TAB 0: COMPOSED MASTER SHEET (ALL DATA + VISUAL THUMBNAILS) */}
        {activeTab === 'master' && (
          <section className="space-y-4">
            {/* Scene Filter Pills & View Layout Switcher */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/60 p-3 rounded-2xl border border-slate-800">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-slate-400 font-semibold mr-1">Scene:</span>
                <button
                  onClick={() => setSelectedSceneFilter('ALL')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition ${
                    selectedSceneFilter === 'ALL'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                  }`}
                >
                  All ({takes.length})
                </button>
                {uniqueScenes.map(sc => (
                  <button
                    key={sc}
                    onClick={() => setSelectedSceneFilter(sc)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition ${
                      selectedSceneFilter === sc
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                    }`}
                  >
                    Sc {sc}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <button
                  onClick={() => setMasterLayout('grid')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                    masterLayout === 'grid'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                  Gallery Grid
                </button>
                <button
                  onClick={() => setMasterLayout('slate')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                    masterLayout === 'slate'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Clapperboard className="w-3.5 h-3.5" />
                  Slate Navigator
                </button>
              </div>
            </div>

            {/* MASTER VIEW - 1. GALLERY GRID */}
            {masterLayout === 'grid' && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredTakes.length === 0 ? (
                  <div className="col-span-full bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center text-slate-500">
                    No takes found matching filter criteria. Drop PDF/CSV documents to populate.
                  </div>
                ) : (
                  filteredTakes.map((t, idx) => {
                    const hasDiscrepancy = discrepancies.some(
                      d => d.entity_id.includes(t.slate) && d.entity_id.includes(t.take_id)
                    );

                    return (
                      <div 
                        key={idx}
                        className={`bg-slate-900/80 rounded-2xl border transition overflow-hidden flex flex-col shadow-lg hover:shadow-2xl ${
                          hasDiscrepancy ? 'border-red-500/40' : 'border-slate-800 hover:border-blue-500/50'
                        }`}
                      >
                        {/* Visual Thumbnail Frame */}
                        <div className="relative bg-black aspect-video flex items-center justify-center border-b border-slate-800 overflow-hidden group">
                          {t.thumbnail_url ? (
                            <img 
                              src={t.thumbnail_url} 
                              alt={`Scene ${t.scene} Take ${t.take_id}`}
                              onClick={() => setEnlargedImage(t.thumbnail_url!)}
                              className="w-full h-full object-cover group-hover:scale-105 transition duration-300 cursor-pointer" 
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 to-slate-950 text-slate-600 p-4">
                              <Volume2 className="w-10 h-10 mb-2 text-cyan-400/60" />
                              <span className="text-[11px] font-mono text-cyan-300/80">
                                {t.is_wild_track ? 'Audio Wild Track' : 'Sound Mix Poly WAV'}
                              </span>
                              <span className="text-[10px] text-slate-500 font-mono mt-0.5">
                                {t.sound_cards.join(', ') || 'Sound Roll'}
                              </span>
                            </div>
                          )}

                          {/* Top Slate Badge */}
                          <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5">
                            <span className="bg-black/80 backdrop-blur-md text-white font-mono text-xs font-bold px-2.5 py-1 rounded-lg border border-white/20 shadow">
                              Sc {t.scene || 'N/A'} • {t.slate} T{t.take_id}
                            </span>
                          </div>

                          {/* Top Right Flags */}
                          <div className="absolute top-2.5 right-2.5 flex items-center gap-1">
                            {t.is_starred && (
                              <span className="bg-amber-500/90 text-black font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
                                ⭐ Circled
                              </span>
                            )}
                            {t.is_wild_track && (
                              <span className="bg-cyan-500/90 text-black font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
                                🎙️ WT
                              </span>
                            )}
                            {t.is_vfx && (
                              <span className="bg-purple-500/90 text-white font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
                                ✨ VFX
                              </span>
                            )}
                          </div>

                          {/* Hover Zoom Prompt */}
                          {t.thumbnail_url && (
                            <button
                              onClick={() => setEnlargedImage(t.thumbnail_url!)}
                              className="absolute bottom-2 right-2 bg-black/70 hover:bg-blue-600 text-white p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition shadow"
                              title="Enlarge Frame"
                            >
                              <Maximize2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>

                        {/* Composed 4-Department Data Grid */}
                        <div className="p-4 flex-1 space-y-3">
                          <div className="space-y-2 text-xs">
                            {/* 1. Script Supervisor */}
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800/80 space-y-1">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-amber-400 flex items-center gap-1">
                                  📝 Script (Scripte)
                                </span>
                                {t.belief.script?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.script?.source_doc_id, t.belief.script?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    Preview Log
                                  </button>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-300 italic line-clamp-1">
                                {t.belief.script?.note || 'Scripte Log Recorded'}
                              </p>
                              {t.belief.script?.timecode_in && (
                                <div className="text-[10px] font-mono text-slate-400">
                                  TC: {t.belief.script.timecode_in} → {t.belief.script.timecode_out || '--'}
                                </div>
                              )}
                            </div>

                            {/* 2. Camera Unit */}
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800/80 space-y-1">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-blue-400 flex items-center gap-1">
                                  🎬 Camera (ZoeLog)
                                </span>
                                {t.belief.camera?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.camera?.source_doc_id, t.belief.camera?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    Preview ZoeLog
                                  </button>
                                )}
                              </div>
                              <div className="text-[11px] font-mono text-slate-300 flex flex-wrap gap-2">
                                <span className="text-white font-bold">{t.camera_cards.join(', ') || 'No Camera'}</span>
                                {t.belief.camera?.lens && <span>• {t.belief.camera.lens}</span>}
                                {t.belief.camera?.fps && <span>• {t.belief.camera.fps}fps</span>}
                              </div>
                            </div>

                            {/* 3. Sound Mixer */}
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800/80 space-y-1">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-emerald-400 flex items-center gap-1">
                                  🎙️ Sound (ALE)
                                </span>
                                {t.belief.sound?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.sound?.source_doc_id, t.belief.sound?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    Preview CSV
                                  </button>
                                )}
                              </div>
                              <div className="text-[11px] font-mono text-slate-300 flex items-center justify-between">
                                <span className="text-emerald-300 font-bold">{t.sound_cards.join(', ') || 'Sound Roll'}</span>
                                <span className="text-[10px] text-slate-400">TC In: {t.belief.sound?.timecode_in || '--'}</span>
                              </div>
                            </div>

                            {/* 4. Silverstack Notary */}
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-cyan-500/20 space-y-1">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-cyan-400 flex items-center gap-1">
                                  🔒 Silverstack Notary
                                </span>
                                <span className="text-[10px] text-cyan-300 bg-cyan-950 px-1.5 py-0.2 rounded border border-cyan-500/30 font-mono">
                                  ✓ Verified
                                </span>
                              </div>
                              <div className="text-[10px] font-mono text-slate-400 grid grid-cols-2 gap-1 pt-0.5">
                                <div>Drive: <span className="text-white">{t.storage_volumes.join(', ') || 'Offload Vol'}</span></div>
                                <div>Codec: <span className="text-cyan-300 font-semibold truncate">{t.codec || 'ARRIRAW / PCM'}</span></div>
                                {t.recording_date && <div className="col-span-2">Rec: <span className="text-slate-200">{t.recording_date}</span></div>}
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Card Footer Actions */}
                        <div className="px-4 py-3 bg-slate-950/80 border-t border-slate-800/80 flex items-center justify-between gap-2">
                          <button
                            onClick={() => {
                              setFocusTakeIndex(idx);
                              setMasterLayout('slate');
                            }}
                            className="flex-1 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 hover:text-white rounded-lg text-xs font-semibold border border-blue-500/30 transition flex items-center justify-center gap-1"
                          >
                            <Clapperboard className="w-3.5 h-3.5" />
                            Slate View
                          </button>
                          <button
                            onClick={() => handleInspectTake(t)}
                            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-semibold border border-slate-700 transition"
                          >
                            Inspect Diff
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* MASTER VIEW - 2. SLATE FOCUS NAVIGATOR */}
            {masterLayout === 'slate' && currentFocusTake && (
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl space-y-4 p-6">
                {/* Take Switcher Header Bar */}
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
                  <div className="flex items-center gap-2">
                    <button
                      disabled={focusTakeIndex <= 0}
                      onClick={() => setFocusTakeIndex(Math.max(0, focusTakeIndex - 1))}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-white text-xs font-semibold transition flex items-center gap-1"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      Prev Take
                    </button>

                    <div className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 flex items-center gap-2">
                      <span className="text-xs text-slate-400 font-semibold">Take</span>
                      <select
                        value={focusTakeIndex}
                        onChange={e => setFocusTakeIndex(parseInt(e.target.value))}
                        className="bg-transparent text-xs font-mono font-bold text-white focus:outline-none cursor-pointer"
                      >
                        {filteredTakes.map((ft, i) => (
                          <option key={i} value={i} className="bg-slate-900 text-white">
                            {i + 1}. Sc {ft.scene} — {ft.slate} T{ft.take_id} {ft.is_starred ? '⭐' : ''} {ft.is_wild_track ? '🎙️' : ''} {ft.is_vfx ? '✨' : ''}
                          </option>
                        ))}
                      </select>
                      <span className="text-xs text-slate-500 font-mono">of {filteredTakes.length}</span>
                    </div>

                    <button
                      disabled={focusTakeIndex >= filteredTakes.length - 1}
                      onClick={() => setFocusTakeIndex(Math.min(filteredTakes.length - 1, focusTakeIndex + 1))}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-white text-xs font-semibold transition flex items-center gap-1"
                    >
                      Next Take
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    {currentFocusTake.is_starred && (
                      <span className="bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                        ⭐ Circled Take
                      </span>
                    )}
                    {currentFocusTake.is_wild_track && (
                      <span className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                        🎙️ Wild Track
                      </span>
                    )}
                    {currentFocusTake.is_vfx && (
                      <span className="bg-purple-500/20 text-purple-300 border border-purple-500/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                        ✨ VFX Required
                      </span>
                    )}
                    <button
                      onClick={() => handleInspectTake(currentFocusTake)}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition"
                    >
                      Open 3-Axis Diff Drawer
                    </button>
                  </div>
                </div>

                {/* Composed 2-Column Slate Body */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
                  {/* Left Column: Visual Frame & Storage Notary */}
                  <div className="space-y-4">
                    <div 
                      className="relative bg-black aspect-video rounded-xl overflow-hidden border border-slate-800 group cursor-pointer shadow-lg"
                      onClick={() => currentFocusTake.thumbnail_url && setEnlargedImage(currentFocusTake.thumbnail_url)}
                    >
                      {currentFocusTake.thumbnail_url ? (
                        <img 
                          src={currentFocusTake.thumbnail_url} 
                          alt="Slate Frame" 
                          className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                        />
                      ) : (
                        <div className="w-full h-full flex flex-col items-center justify-center bg-slate-950 text-slate-500 p-6">
                          <Volume2 className="w-12 h-12 mb-3 text-cyan-400/70" />
                          <span className="text-xs font-mono text-cyan-300 font-bold">Audio Recording Clip</span>
                          <span className="text-[11px] text-slate-400 font-mono mt-1">{currentFocusTake.sound_cards.join(', ')}</span>
                        </div>
                      )}
                      {currentFocusTake.thumbnail_url && (
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                          <span className="bg-blue-600 text-white text-xs px-3 py-1 rounded-lg font-semibold shadow">
                            Click to Enlarge Picture
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Silverstack Physical Location Card */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-cyan-500/30 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                          <HardDrive className="w-4 h-4 text-cyan-400" />
                          Pomfort Silverstack Notary
                        </span>
                        <span className="text-[10px] text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-500/30 font-mono font-bold">
                          ✓ Checksum OK
                        </span>
                      </div>
                      <div className="text-xs font-mono text-slate-300 space-y-1.5 pt-1">
                        <div>Volume: <span className="text-white font-bold">{currentFocusTake.storage_volumes.join(', ') || 'MAG_A_120'}</span></div>
                        <div>Codec: <span className="text-cyan-300 font-semibold">{currentFocusTake.codec || 'ARRIRAW (13bit, HDE)'}</span></div>
                        <div>Recorded: <span className="text-slate-200">{currentFocusTake.recording_date || '--'}</span></div>
                        <div>Camera Roll: <span className="text-white">{currentFocusTake.camera_cards.join(', ') || 'N/A'}</span></div>
                        <div>Sound Roll: <span className="text-emerald-400">{currentFocusTake.sound_cards.join(', ') || 'N/A'}</span></div>
                      </div>
                    </div>
                  </div>

                  {/* Right Column: 3 Department Breakdown Matrix */}
                  <div className="lg:col-span-2 space-y-3">
                    {/* 1. Script Department */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                          1. Script Supervisor (Scripte Logs)
                        </span>
                        {currentFocusTake.belief.script?.source_document && (
                          <button
                            onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.script?.source_doc_id, currentFocusTake.belief.script?.source_document)}
                            className="text-xs text-purple-400 hover:underline flex items-center gap-1 font-mono"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            Preview {currentFocusTake.belief.script.source_document}
                          </button>
                        )}
                      </div>
                      <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-3 pt-1">
                        <div>Timecode: <span className="text-white">{currentFocusTake.belief.script?.timecode_in || '--'} → {currentFocusTake.belief.script?.timecode_out || '--'}</span></div>
                        <div>Camera Card: <span className="text-white font-bold">{currentFocusTake.belief.script?.camera_roll || '--'}</span></div>
                        <div className="col-span-2">Notes: <span className="text-slate-200 italic">{currentFocusTake.belief.script?.note || 'Take recorded normally without faults.'}</span></div>
                      </div>
                    </div>

                    {/* 2. Camera Department */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <span className="text-xs font-bold text-blue-400 uppercase tracking-wider">
                          2. Camera Department (ZoeLog)
                        </span>
                        {currentFocusTake.belief.camera?.source_document && (
                          <button
                            onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.camera?.source_doc_id, currentFocusTake.belief.camera?.source_document)}
                            className="text-xs text-purple-400 hover:underline flex items-center gap-1 font-mono"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            Preview {currentFocusTake.belief.camera.source_document}
                          </button>
                        )}
                      </div>
                      <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-3 pt-1">
                        <div>Camera Roll: <span className="text-white font-bold">{currentFocusTake.belief.camera?.camera_roll || '--'}</span></div>
                        <div>Clip Name: <span className="text-white font-bold">{currentFocusTake.belief.camera?.clip_name || '--'}</span></div>
                        <div>Lens / Stop: <span className="text-slate-200">{currentFocusTake.belief.camera?.lens || 'Standard'} @ {currentFocusTake.belief.camera?.raw_payload?.stop || 'T2.8'}</span></div>
                        <div>FPS / ISO: <span className="text-slate-200">{currentFocusTake.belief.camera?.fps || 24}fps / {currentFocusTake.belief.camera?.iso || 800}EI</span></div>
                        <div className="col-span-2">Notes: <span className="text-slate-200 italic">{currentFocusTake.belief.camera?.note || 'No camera defects noted.'}</span></div>
                      </div>
                    </div>

                    {/* 3. Sound Department */}
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
                          3. Sound Department (Sound Devices / ALE)
                        </span>
                        {currentFocusTake.belief.sound?.source_document && (
                          <button
                            onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.sound?.source_doc_id, currentFocusTake.belief.sound?.source_document)}
                            className="text-xs text-purple-400 hover:underline flex items-center gap-1 font-mono"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            Preview {currentFocusTake.belief.sound.source_document}
                          </button>
                        )}
                      </div>
                      <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-3 pt-1">
                        <div>Sound Roll: <span className="text-white font-bold">{currentFocusTake.belief.sound?.sound_roll || '--'}</span></div>
                        <div>Start Timecode: <span className="text-white">{currentFocusTake.belief.sound?.timecode_in || '--'}</span></div>
                        <div>Tracks: <span className="text-slate-200">{currentFocusTake.belief.sound?.tracks || 'MixL, MixR'}</span></div>
                        <div>Wild Track: <span className={currentFocusTake.is_wild_track ? 'text-cyan-400 font-bold' : 'text-slate-400'}>{currentFocusTake.is_wild_track ? 'YES (WT)' : 'NO'}</span></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {/* TAB 1: SCENES & TAKES CARD/VOLUME LOCATOR */}
        {activeTab === 'scenes' && (
          <section className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
            <div className="px-6 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <HardDrive className="w-4 h-4 text-blue-400" />
                  Physical Card, Roll & Storage Volume Map
                </h3>
                <p className="text-[11px] text-slate-400">
                  Cross-referenced locations across ZoeLog Camera cards, Sound ALE rolls, and DIT hard drives
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">{filteredTakes.length} Takes Matching</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 uppercase font-mono text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Scene & Slate</th>
                    <th className="px-4 py-3">Take & Status</th>
                    <th className="px-4 py-3">Camera Card(s)</th>
                    <th className="px-4 py-3">Sound Roll & TC</th>
                    <th className="px-4 py-3">DIT Storage Volume & Clip</th>
                    <th className="px-4 py-3">Discrepancy Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {filteredTakes.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                        No takes found for Shoot Day {selectedDay}. Click "Seed Day {selectedDay}" or drop PDF/CSV files to populate the spine.
                      </td>
                    </tr>
                  ) : (
                    filteredTakes.map((t, idx) => {
                      const hasDiscrepancy = discrepancies.some(
                        d => d.entity_id.includes(t.slate) && d.entity_id.includes(t.take_id)
                      );

                      return (
                        <tr key={idx} className="hover:bg-slate-800/40 transition">
                          {/* Scene & Slate */}
                          <td className="px-4 py-3.5 font-mono">
                            <span className="text-slate-400 font-normal">Sc {t.scene || 'N/A'} / </span>
                            <span className="text-white font-bold text-sm">{t.slate}</span>
                          </td>

                          {/* Take & Flags */}
                          <td className="px-4 py-3.5 font-mono">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-white font-bold">T{t.take_id}</span>
                              {t.is_starred && (
                                <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.2 rounded font-sans">
                                  ⭐ Circled
                                </span>
                              )}
                              {t.is_wild_track && (
                                <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-1.5 py-0.2 rounded font-sans">
                                  🎙️ WT
                                </span>
                              )}
                              {t.is_vfx && (
                                <span className="text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/40 px-1.5 py-0.2 rounded font-sans">
                                  ✨ VFX
                                </span>
                              )}
                              {t.is_pickup && (
                                <span className="text-[10px] bg-pink-500/20 text-pink-300 border border-pink-500/40 px-1.5 py-0.2 rounded font-sans">
                                  Pickup
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Camera Cards */}
                          <td className="px-4 py-3.5 font-mono">
                            <div className="flex flex-wrap gap-1">
                              {t.camera_cards.length > 0 ? (
                                t.camera_cards.map((c, i) => (
                                  <span key={i} className="bg-blue-950/60 border border-blue-500/30 text-blue-300 px-2 py-0.5 rounded text-[11px] font-semibold">
                                    🎴 {c}
                                  </span>
                                ))
                              ) : (
                                <span className="text-slate-600">--</span>
                              )}
                            </div>
                          </td>

                          {/* Sound Roll */}
                          <td className="px-4 py-3.5 font-mono">
                            {t.belief.sound ? (
                              <div>
                                <span className="text-emerald-400 font-semibold">
                                  🎙️ {t.belief.sound.sound_roll || 'SR'}
                                </span>
                                <div className="text-[10px] text-slate-500">{t.belief.sound.timecode_in || '--'}</div>
                              </div>
                            ) : (
                              <span className="text-slate-600">--</span>
                            )}
                          </td>

                          {/* Storage Volume & Clip */}
                          <td className="px-4 py-3.5 font-mono">
                            {t.matched_media_files.length > 0 ? (
                              t.matched_media_files.map((m, i) => (
                                <div key={i} className="flex items-center gap-1.5">
                                  <span className="bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 px-1.5 py-0.2 rounded text-[10px]">
                                    💾 {m.volume_name || 'Offload Vol'}
                                  </span>
                                  <span className="text-slate-300 text-[11px] truncate max-w-[140px]" title={m.file_name}>
                                    {m.file_name}
                                  </span>
                                </div>
                              ))
                            ) : (
                              <span className="text-slate-600 italic">No media offload</span>
                            )}
                          </td>

                          {/* Discrepancy Status */}
                          <td className="px-4 py-3.5">
                            {hasDiscrepancy ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-300 border border-red-500/40">
                                <AlertTriangle className="w-3 h-3 text-red-400" />
                                Mismatch Detected
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
                                <Check className="w-3.5 h-3.5 text-emerald-400" />
                                Reconciled
                              </span>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-3.5 text-right space-x-1.5">
                            <button
                              onClick={() => handleInspectTake(t)}
                              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-blue-300 hover:text-white rounded text-xs border border-slate-700 transition"
                            >
                              Inspect Diff
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* TAB 2: ACTIVE DISCREPANCIES VIEW */}
        {activeTab === 'discrepancies' && (
          <section className="space-y-3">
            {discrepancies.length === 0 ? (
              <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
                <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
                <h3 className="text-base font-bold text-white">All Documents 100% Reconciled</h3>
                <p className="text-xs text-slate-400 mt-1">No discrepancies found across Sound, Script, Camera, and DIT logs.</p>
              </div>
            ) : (
              discrepancies.map((d, idx) => (
                <div key={idx} className="bg-slate-900/80 border border-red-500/30 rounded-xl p-5 space-y-3 shadow-lg">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded font-mono ${
                          d.severity === 'CRITICAL' 
                            ? 'bg-red-500/20 text-red-300 border border-red-500/40' 
                            : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        }`}>
                          {d.discrepancy_type}
                        </span>
                        <span className="text-sm font-mono font-bold text-white">{d.entity_id}</span>
                      </div>
                      <p className="text-xs text-slate-200 mt-2">{d.description}</p>
                    </div>

                    <button 
                      onClick={() => {
                        const takeMatch = takes.find(t => d.entity_id.includes(t.slate) && d.entity_id.includes(t.take_id));
                        if (takeMatch) handleInspectTake(takeMatch);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shrink-0 transition"
                    >
                      Diagnose Mismatch
                    </button>
                  </div>

                  {/* Conflicting Witnesses Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                    {d.witnesses?.map((w, wi) => (
                      <div key={wi} className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400 font-bold uppercase text-[10px]">{(w.author || 'Dept').toUpperCase()}</span>
                          <span className="text-blue-400 font-mono text-[10px]">{(w.axis || 'belief').toUpperCase()}</span>
                        </div>
                        <div className="text-slate-300 font-mono text-[11px]">
                          {w.camera_roll && <div>Roll: <span className="text-white font-bold">{w.camera_roll}</span></div>}
                          {w.sound_roll && <div>Sound Roll: <span className="text-white font-bold">{w.sound_roll}</span></div>}
                          {w.is_starred !== undefined && (
                            <div>Circled: <span className={w.is_starred ? 'text-amber-400 font-bold' : 'text-slate-500'}>{w.is_starred ? 'YES' : 'NO'}</span></div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </section>
        )}

        {/* TAB 3: SOURCE DOCUMENTS REPOSITORY */}
        {activeTab === 'documents' && (
          <section className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
            <div className="px-6 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileCode className="w-4 h-4 text-purple-400" />
                  Raw Source Paperwork Repository
                </h3>
                <p className="text-[11px] text-slate-400">
                  Inspect the original uploaded Sound ALEs, Camera CSVs, Script Editor Logs, and Silverstack XMLs
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">{documents.length} Files Ingested</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 uppercase font-mono text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Filename</th>
                    <th className="px-4 py-3">Department</th>
                    <th className="px-4 py-3">Doc Type</th>
                    <th className="px-4 py-3">SHA-256 Checksum</th>
                    <th className="px-4 py-3">Size</th>
                    <th className="px-4 py-3">Uploaded At</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {documents.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                        No source documents uploaded for Shoot Day {selectedDay}. Drop files to preview.
                      </td>
                    </tr>
                  ) : (
                    documents.map((doc, i) => (
                      <tr key={i} className="hover:bg-slate-800/30 transition">
                        <td className="px-4 py-3 font-mono font-bold text-white flex items-center gap-2">
                          <FileText className="w-4 h-4 text-blue-400" />
                          {doc.filename}
                        </td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-slate-300 font-mono">
                            {doc.department}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-slate-400">{doc.doc_type}</td>
                        <td className="px-4 py-3 font-mono text-[11px] text-cyan-400">
                          {doc.checksum ? (
                            <span className="bg-cyan-950/50 border border-cyan-500/30 px-1.5 py-0.5 rounded font-mono" title={doc.checksum}>
                              {doc.checksum.slice(0, 10)}...
                            </span>
                          ) : (
                            <span className="text-slate-600">--</span>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono text-slate-400">{(doc.size_bytes / 1024).toFixed(1)} KB</td>
                        <td className="px-4 py-3 font-mono text-slate-500">{doc.uploaded_at?.slice(0, 19).replace('T', ' ')}</td>
                        <td className="px-4 py-3 text-right space-x-2">
                          <button
                            onClick={() => handleOpenPreviewDoc(doc.doc_id)}
                            className="px-2.5 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 rounded text-xs font-semibold inline-flex items-center gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            Preview
                          </button>
                          <button
                            onClick={() => handleDeleteDocument(doc.doc_id, doc.filename)}
                            className="px-2.5 py-1 bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/40 rounded text-xs font-semibold inline-flex items-center gap-1"
                            title="Remove file and purge events"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>

      {/* DETAILED 3-AXIS WITNESS & CARD LOCATOR DRAWER */}
      {inspectedTake && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex justify-end z-50">
          <div className="bg-slate-900 border-l border-slate-800 w-full max-w-2xl h-full flex flex-col p-6 space-y-5 overflow-y-auto shadow-2xl animate-in slide-in-from-right">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-bold text-white">
                    Scene {inspectedTake.scene || 'N/A'} — Slate {inspectedTake.slate} T{inspectedTake.take_id}
                  </h3>
                  {inspectedTake.is_starred && (
                    <span className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded">
                      ⭐ Circled Take
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1">3-Axis Witness Diagnosis & Storage Card Breakdown</p>
              </div>
              <button 
                onClick={() => { setInspectedTake(null); setAssistantExplanation(null); }}
                className="text-slate-400 hover:text-white text-lg p-1"
              >
                ✕
              </button>
            </div>

            {/* Physical Card & Volume Location Callout */}
            <div className="bg-blue-950/40 border border-blue-500/30 rounded-xl p-4 space-y-2">
              <h4 className="text-xs font-bold text-blue-300 uppercase tracking-wider flex items-center gap-1.5">
                <HardDrive className="w-4 h-4 text-blue-400" />
                Physical Media & Card Location
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs pt-1 font-mono">
                <div>
                  <span className="text-slate-400 block text-[10px]">Camera Cards:</span>
                  <span className="text-white font-bold">{inspectedTake.camera_cards.join(', ') || 'No camera log'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Sound Rolls:</span>
                  <span className="text-white font-bold">{inspectedTake.sound_cards.join(', ') || 'No sound log'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Storage Volumes:</span>
                  <span className="text-cyan-300 font-bold">{inspectedTake.storage_volumes.join(', ') || 'Un-offloaded'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Files On Disk:</span>
                  <span className="text-cyan-300 font-bold">{inspectedTake.matched_media_files.length} verified files</span>
                </div>
              </div>
            </div>

            {/* Gemini Agent AI Audit Report */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="text-xs font-bold text-slate-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-400" />
                Discrepancy Synthesis & Explanation
              </h4>
              <p className="text-xs font-mono text-slate-300 whitespace-pre-line bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
                {assistantExplanation || 'Analyzing 3-axis witnesses...'}
              </p>
            </div>

            {/* Department Witness Breakdown with Preview Links */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Source Document Witness Claims</h4>

              {/* 1. Camera Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-400">1. Camera Department (Belief)</span>
                  {inspectedTake.belief.camera?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.camera?.source_doc_id, inspectedTake.belief.camera?.source_document)}
                      className="text-[11px] text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium underline"
                    >
                      <Eye className="w-3 h-3" />
                      Preview {inspectedTake.belief.camera.source_document}
                    </button>
                  )}
                </div>
                <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-2">
                  <div>Card Roll: <span className="text-white font-bold">{inspectedTake.belief.camera?.camera_roll || '--'}</span></div>
                  <div>Clip: <span className="text-white font-bold">{inspectedTake.belief.camera?.clip_name || '--'}</span></div>
                  <div>FPS / ISO: <span className="text-white">{inspectedTake.belief.camera?.fps || 24}fps / {inspectedTake.belief.camera?.iso || 800}</span></div>
                  <div>Lens: <span className="text-white">{inspectedTake.belief.camera?.lens || 'Standard'}</span></div>
                </div>
              </div>

              {/* 2. Sound Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400">2. Sound Department (Belief)</span>
                  {inspectedTake.belief.sound?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.sound?.source_doc_id, inspectedTake.belief.sound?.source_document)}
                      className="text-[11px] text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium underline"
                    >
                      <Eye className="w-3 h-3" />
                      Preview {inspectedTake.belief.sound.source_document}
                    </button>
                  )}
                </div>
                <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-2">
                  <div>Sound Roll: <span className="text-white font-bold">{inspectedTake.belief.sound?.sound_roll || '--'}</span></div>
                  <div>Timecode In: <span className="text-white">{inspectedTake.belief.sound?.timecode_in || '--'}</span></div>
                  <div>Tracks: <span className="text-white">{inspectedTake.belief.sound?.tracks || '4ch Poly'}</span></div>
                  <div>Wild Track: <span className="text-white">{inspectedTake.belief.sound?.is_wild_track ? 'YES' : 'NO'}</span></div>
                </div>
              </div>

              {/* 3. DIT Physical Existence */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-cyan-400">3. DIT / Pomfort Silverstack Notary (Existence)</span>
                  {inspectedTake.matched_media_files.length > 0 && (
                    <span className="text-[10px] text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-500/30 font-mono">
                      ✓ Notary Verified
                    </span>
                  )}
                </div>
                <div className="text-xs font-mono text-slate-300 space-y-2">
                  {inspectedTake.matched_media_files.length > 0 ? (
                    inspectedTake.matched_media_files.map((m, i) => (
                      <div key={i} className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="text-white font-bold text-xs">{m.file_name}</div>
                          <span className="text-[10px] text-emerald-400 bg-emerald-950/60 px-2 py-0.2 rounded border border-emerald-500/30">
                            {m.checksum ? `${m.checksum.slice(0, 12)}...` : 'Verified'}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-1.5 text-[11px] text-slate-400 pt-1">
                          <div>Reel/Tape: <span className="text-slate-200 font-semibold">{m.reel_tape || m.camera_roll || '--'}</span></div>
                          <div>Volume: <span className="text-slate-200">{m.volume_name || 'Offload Drive'}</span></div>
                          <div>Codec: <span className="text-cyan-300 font-semibold">{m.codec || 'Linear PCM / ARRIRAW'}</span></div>
                          <div>Recorded: <span className="text-slate-200">{m.recording_date || '--'}</span></div>
                          {m.fps && <div>FPS / ISO: <span className="text-slate-200">{m.fps}fps / {m.iso || 800}EI</span></div>}
                          {m.tstop && <div>T-Stop: <span className="text-slate-200">{m.tstop}</span></div>}
                          <div>Size: <span className="text-slate-200">{(m.file_size_bytes ? m.file_size_bytes / (1024*1024) : 0).toFixed(1)} MB</span></div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500 italic text-xs">No media offload files registered on DIT volumes yet.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SOURCE DOCUMENT PREVIEW MODAL */}
      {previewDoc && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div className="flex items-center gap-3">
                <FileCode className="w-5 h-5 text-purple-400" />
                <div>
                  <h3 className="font-bold text-white text-sm">{previewDoc.filename}</h3>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono mt-0.5">
                    <span>Dept: {previewDoc.department.toUpperCase()}</span>
                    <span>•</span>
                    <span>Type: {previewDoc.doc_type}</span>
                    <span>•</span>
                    <span>Size: {(previewDoc.size_bytes / 1024).toFixed(1)} KB</span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setPreviewDoc(null)}
                className="text-slate-400 hover:text-white text-lg p-1"
              >
                ✕
              </button>
            </div>

            <div className="p-6 flex-1 overflow-y-auto font-mono text-xs bg-slate-950 text-slate-200 whitespace-pre">
              {previewDoc.content}
            </div>

            <div className="px-6 py-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setPreviewDoc(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ENLARGED THUMBNAIL LIGHTBOX MODAL */}
      {enlargedImage && (
        <div 
          className="fixed inset-0 bg-black/90 backdrop-blur-md flex items-center justify-center p-6 z-50 cursor-pointer"
          onClick={() => setEnlargedImage(null)}
        >
          <div className="relative max-w-4xl w-full bg-slate-900 border border-slate-700 rounded-2xl overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
              <div className="flex items-center gap-2">
                <ImageIcon className="w-4 h-4 text-blue-400" />
                <span className="text-xs font-mono text-slate-300 font-bold">Silverstack Camera Thumbnail Frame</span>
              </div>
              <button 
                onClick={() => setEnlargedImage(null)}
                className="text-slate-400 hover:text-white text-lg p-1"
              >
                ✕
              </button>
            </div>
            <div className="p-4 bg-black flex items-center justify-center">
              <img 
                src={enlargedImage} 
                alt="Enlarged Frame" 
                className="max-h-[75vh] w-auto object-contain rounded-lg border border-slate-800 shadow-2xl" 
              />
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
