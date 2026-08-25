import React, { useState, useEffect, useMemo } from 'react';
import { 
  Film, AlertTriangle, CheckCircle2, Upload, 
  RefreshCw, Layers, Sparkles, 
  FileText, Clapperboard, Calendar, Search,
  HardDrive, Eye, FileCode, Check, AlertCircle, Trash2,
  Image as ImageIcon, ChevronLeft, ChevronRight, LayoutGrid,
  Maximize2, ExternalLink, Video, Mic, MapPin,
  Bell, CheckCheck, PlusCircle, ChevronDown, Send, ShieldAlert,
  Radio
} from 'lucide-react';
import { 
  TakeRecord, Discrepancy, Production, SourceDocumentSummary, SourceDocument, SequenceRecord,
  UserProfile, Requirement, NotificationItem, RequirementPriority, RequirementCategory
} from './types';
import { 
  fetchTakes, fetchDiscrepancies, fetchProductions, fetchDocuments,
  fetchDocumentContent, uploadDocument, uploadFile, askAssistant, seedDemoDay,
  fetchSequences, resolveDiscrepancy, unresolveDiscrepancy,
  fetchTeamUsers, loginUser, createRequirement,
  resolveRequirement, fetchNotifications,
  markNotificationRead, markAllNotificationsRead
} from './api';

export default function App() {
  const [productions, setProductions] = useState<Production[]>([]);
  const [selectedProductionId, setSelectedProductionId] = useState('DEMO_PRODUCTION');
  const [selectedDay, setSelectedDay] = useState('31');
  const [takes, setTakes] = useState<TakeRecord[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [documents, setDocuments] = useState<SourceDocumentSummary[]>([]);
  const [sequences, setSequences] = useState<SequenceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  // Collaborative User Identity & Passwordless State
  const [teamUsers, setTeamUsers] = useState<UserProfile[]>([]);
  const [currentUser, setCurrentUser] = useState<UserProfile>({
    handle: '@director',
    name: 'Director',
    email: 'director@example.com',
    role: 'Director',
    avatar_color: '#8b5cf6',
  });
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [customLoginHandle, setCustomLoginHandle] = useState('');

  // Real-Time Events & SSE Live Subscription State
  const [liveSyncStatus, setLiveSyncStatus] = useState<'connected' | 'connecting' | 'disconnected'>('connecting');
  const [liveToast, setLiveToast] = useState<{ message: string; type?: string } | null>(null);

  // Notifications & Real-Time Alerts State
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadNotifCount, setUnreadNotifCount] = useState<number>(0);
  const [isNotifDrawerOpen, setIsNotifDrawerOpen] = useState(false);

  // Requirements Modal & Resolution State
  const [isCreateReqOpen, setIsCreateReqOpen] = useState(false);
  const [targetForReq, setTargetForReq] = useState<{
    target_type: 'scene' | 'shot' | 'take';
    target_id: string;
    target_label: string;
  } | null>(null);
  const [newReqTitle, setNewReqTitle] = useState('');
  const [newReqDesc, setNewReqDesc] = useState('');
  const [newReqAssignee, setNewReqAssignee] = useState('@sound_supervisor');
  const [newReqPriority, setNewReqPriority] = useState<RequirementPriority>('medium');
  const [newReqCategory, setNewReqCategory] = useState<RequirementCategory>('general');
  const [isSubmittingReq, setIsSubmittingReq] = useState(false);

  const [viewingReqsList, setViewingReqsList] = useState<{
    target_label: string;
    target_type: 'scene' | 'shot' | 'take';
    target_id: string;
    requirements: Requirement[];
  } | null>(null);
  const [selectedReqForResolve, setSelectedReqForResolve] = useState<Requirement | null>(null);
  const [reqResolutionNote, setReqResolutionNote] = useState('');
  const [isResolvingReqSubmitting, setIsResolvingReqSubmitting] = useState(false);


  // Active View & Filters
  const [activeTab, setActiveTab] = useState<'master' | 'sequences' | 'scenes' | 'discrepancies' | 'documents'>('master');
  const [masterLayout, setMasterLayout] = useState<'grid' | 'slate'>('grid');
  const [focusTakeIndex, setFocusTakeIndex] = useState<number>(0);
  const [selectedSceneFilter, setSelectedSceneFilter] = useState<string>('ALL');
  const [enlargedImage, setEnlargedImage] = useState<string | null>(null);
  const [selectedCameraAngle, setSelectedCameraAngle] = useState<Record<string, string>>({});


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
  const [previewViewMode, setPreviewViewMode] = useState<'visual' | 'text'>('visual');

  // Modals
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // Discrepancy Resolution Modal State
  const [resolvingDiscrepancy, setResolvingDiscrepancy] = useState<Discrepancy | null>(null);
  const [resolutionCardChoice, setResolutionCardChoice] = useState<string>('');
  const [customCardInput, setCustomCardInput] = useState<string>('');
  const [resolutionNoteInput, setResolutionNoteInput] = useState<string>('');
  const [isResolutionSubmitting, setIsResolutionSubmitting] = useState<boolean>(false);

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
      const [t, d, docs, seqs] = await Promise.all([
        fetchTakes(selectedProductionId, selectedDay),
        fetchDiscrepancies(selectedProductionId, selectedDay),
        fetchDocuments(selectedProductionId, selectedDay),
        fetchSequences(selectedProductionId, selectedDay),
      ]);
      setTakes(t);
      setDiscrepancies(d);
      setDocuments(docs);
      setSequences(seqs);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadUsersAndNotifications = async (userHandle: string = currentUser.handle) => {
    try {
      const [users, notifData] = await Promise.all([
        fetchTeamUsers(),
        fetchNotifications(userHandle),
      ]);
      setTeamUsers(users);
      setNotifications(notifData.notifications || []);
      setUnreadNotifCount(notifData.unread_count || 0);
    } catch (e) {
      console.error('Error loading team users/notifications:', e);
    }
  };

  const handleSwitchUser = async (user: UserProfile) => {
    setCurrentUser(user);
    setIsUserMenuOpen(false);
    await loadUsersAndNotifications(user.handle);
  };

  const handleCustomLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customLoginHandle.trim()) return;
    try {
      const { user } = await loginUser(customLoginHandle.trim());
      setCurrentUser(user);
      setCustomLoginHandle('');
      setIsUserMenuOpen(false);
      await loadUsersAndNotifications(user.handle);
    } catch (err: any) {
      alert(`Login failed: ${err.message}`);
    }
  };

  const handleCreateRequirementSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetForReq || !newReqTitle.trim()) return;
    setIsSubmittingReq(true);
    try {
      await createRequirement({
        production_id: selectedProductionId,
        shoot_day: selectedDay,
        target_type: targetForReq.target_type,
        target_id: targetForReq.target_id,
        target_label: targetForReq.target_label,
        title: newReqTitle.trim(),
        description: newReqDesc.trim(),
        priority: newReqPriority,
        category: newReqCategory,
        created_by: currentUser.handle,
        assigned_to: newReqAssignee,
      });
      setIsCreateReqOpen(false);
      setNewReqTitle('');
      setNewReqDesc('');
      await loadSpineData();
      await loadUsersAndNotifications(currentUser.handle);
    } catch (err: any) {
      alert(`Failed to create requirement: ${err.message}`);
    } finally {
      setIsSubmittingReq(false);
    }
  };

  const handleResolveRequirementSubmit = async (reqId: string) => {
    if (!reqResolutionNote.trim()) {
      alert('Please enter a resolution note detailing how this requirement was addressed.');
      return;
    }
    setIsResolvingReqSubmitting(true);
    try {
      await resolveRequirement(reqId, reqResolutionNote.trim(), currentUser.handle);
      setViewingReqsList(null);
      setSelectedReqForResolve(null);
      setReqResolutionNote('');
      await loadSpineData();
      await loadUsersAndNotifications(currentUser.handle);
    } catch (err: any) {
      alert(`Failed to resolve requirement: ${err.message}`);
    } finally {
      setIsResolvingReqSubmitting(false);
    }
  };

  const handleNotificationClick = async (notif: NotificationItem) => {
    // 1. Mark read
    if (!notif.is_read) {
      await markNotificationRead(notif.notification_id);
      await loadUsersAndNotifications(currentUser.handle);
    }
    // 2. Jump to target
    setIsNotifDrawerOpen(false);
    if (notif.target_type === 'scene') {
      setActiveTab('sequences');
      setSearchQuery(notif.target_id);
    } else if (notif.target_type === 'take') {
      setActiveTab('master');
      setSearchQuery(notif.target_id.replace('_', ' '));
    } else {
      setActiveTab('master');
      setSearchQuery(notif.target_id);
    }
  };

  const handleMarkAllNotifsRead = async () => {
    try {
      await markAllNotificationsRead(currentUser.handle);
      await loadUsersAndNotifications(currentUser.handle);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadProductions();
    loadUsersAndNotifications();
  }, []);

  useEffect(() => {
    loadSpineData();
    loadUsersAndNotifications(currentUser.handle);
  }, [selectedProductionId, selectedDay, currentUser.handle]);

  // Real-time SSE Live Event Subscription
  useEffect(() => {
    setLiveSyncStatus('connecting');
    const sseUrl = `/api/events/subscribe?production_id=${encodeURIComponent(selectedProductionId)}&shoot_day=${encodeURIComponent(selectedDay)}&user_handle=${encodeURIComponent(currentUser.handle)}`;
    const eventSource = new EventSource(sseUrl);

    eventSource.addEventListener('connected', () => {
      setLiveSyncStatus('connected');
    });

    eventSource.addEventListener('message', (event) => {
      try {
        const liveEvent = JSON.parse(event.data);
        if (liveEvent && liveEvent.event_type) {
          // 1. Show floating real-time toast
          setLiveToast({
            message: liveEvent.summary || `Live sync: ${liveEvent.event_type}`,
            type: liveEvent.event_type,
          });
          setTimeout(() => {
            setLiveToast(null);
          }, 4500);

          // 2. Automatically refresh spine & notifications without page reload
          loadSpineData();
          loadUsersAndNotifications(currentUser.handle);
        }
      } catch (err) {
        console.error('Error handling SSE live event:', err);
      }
    });

    eventSource.onerror = () => {
      setLiveSyncStatus('disconnected');
    };

    return () => {
      eventSource.close();
    };
  }, [selectedProductionId, selectedDay, currentUser.handle]);


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
    try {
      await seedDemoDay(selectedProductionId, dayToSeed);
      await loadProductions();
      await loadSpineData();
    } catch (err: any) {
      console.error(err);
      alert(`Could not seed demo paperwork: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenPreviewDoc = async (docId?: string, filename?: string) => {
    try {
      if (docId) {
        const doc = await fetchDocumentContent(docId);
        setPreviewDoc(doc);
        const isPdf = doc.is_pdf || doc.filename.toLowerCase().endsWith('.pdf') || doc.doc_type === 'pdf';
        setPreviewViewMode(isPdf ? 'visual' : 'text');
      } else if (filename) {
        const match = documents.find(d => d.filename === filename);
        if (match) {
          const doc = await fetchDocumentContent(match.doc_id);
          setPreviewDoc(doc);
          const isPdf = doc.is_pdf || doc.filename.toLowerCase().endsWith('.pdf') || doc.doc_type === 'pdf';
          setPreviewViewMode(isPdf ? 'visual' : 'text');
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

  const availableCards = useMemo(() => {
    const cards = new Set<string>();
    takes.forEach(t => {
      t.camera_cards?.forEach(c => cards.add(c.replace('Card ', '')));
      t.sound_cards?.forEach(s => cards.add(s.replace('Sound ', '')));
    });
    ['A120', 'A121', 'A122', 'A123', 'B039', 'B040', 'B041', 'C005', 'C006', 'C007', '26Y07M27', '26Y06M18', 'SR280726'].forEach(c => cards.add(c));
    return Array.from(cards).filter(Boolean);
  }, [takes]);

  const openResolveModal = (disc: Discrepancy) => {
    setResolvingDiscrepancy(disc);
    if (disc.resolved_card) {
      setResolutionCardChoice(disc.resolved_card);
      setCustomCardInput(disc.resolved_card);
    } else {
      const witnessCard = disc.witnesses?.find(w => w.camera_roll)?.camera_roll || disc.witnesses?.find(w => w.sound_roll)?.sound_roll;
      if (witnessCard && availableCards.includes(witnessCard)) {
        setResolutionCardChoice(witnessCard);
      } else {
        setResolutionCardChoice(availableCards[0] || 'CUSTOM');
      }
      setCustomCardInput('');
    }
    setResolutionNoteInput(disc.resolution_note || '');
  };

  const handleConfirmResolution = async () => {
    if (!resolvingDiscrepancy) return;
    setIsResolutionSubmitting(true);
    try {
      const finalCard = resolutionCardChoice === 'CUSTOM' ? customCardInput.trim() : resolutionCardChoice;
      await resolveDiscrepancy(resolvingDiscrepancy.discrepancy_id, {
        production_id: selectedProductionId,
        shoot_day: selectedDay,
        entity_id: resolvingDiscrepancy.entity_id,
        resolved_card: finalCard || undefined,
        resolution_note: resolutionNoteInput.trim() || undefined,
        resolved_by: 'Assistant Editor',
      });
      setResolvingDiscrepancy(null);
      await loadSpineData();
    } catch (err: any) {
      alert(`Failed to resolve discrepancy: ${err.message}`);
    } finally {
      setIsResolutionSubmitting(false);
    }
  };

  const handleUnresolve = async (discId: string) => {
    try {
      await unresolveDiscrepancy(discId);
      await loadSpineData();
    } catch (err: any) {
      alert(`Failed to re-open discrepancy: ${err.message}`);
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

  const filteredSequences = useMemo(() => {
    return sequences.filter(s => {
      if (filterWildTracksOnly && !s.is_wild_track) return false;
      if (filterVfxOnly && !s.is_vfx) return false;
      if (filterDiscrepancyOnly && !s.has_discrepancy) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchesSeq = s.sequence.toLowerCase().includes(q);
        const matchesLoc = s.location.toLowerCase().includes(q);
        const matchesDesc = s.description.toLowerCase().includes(q);
        const matchesCards = s.cards.some(c => c.toLowerCase().includes(q));
        const matchesTakes = s.takes.some(tk => tk.toLowerCase().includes(q));
        return matchesSeq || matchesLoc || matchesDesc || matchesCards || matchesTakes;
      }
      return true;
    });
  }, [sequences, filterWildTracksOnly, filterVfxOnly, filterDiscrepancyOnly, searchQuery]);

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

        <div className="flex items-center gap-2.5">
          {/* Real-time Live Sync Indicator */}
          <div 
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono select-none"
            title={`Real-Time SSE Channel: ${liveSyncStatus}`}
          >
            <span className={`w-2 h-2 rounded-full ${
              liveSyncStatus === 'connected'
                ? 'bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/80'
                : liveSyncStatus === 'connecting'
                ? 'bg-amber-400 animate-ping'
                : 'bg-slate-600'
            }`} />
            <span className={liveSyncStatus === 'connected' ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
              {liveSyncStatus === 'connected' ? 'Live Sync' : liveSyncStatus === 'connecting' ? 'Connecting...' : 'Offline'}
            </span>
          </div>

          <button 
            onClick={loadSpineData}
            className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition"
            title="Refresh Spine"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button 
            onClick={() => handleSeedDemoDay(selectedDay)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 text-xs font-medium transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Seed Day {selectedDay}
          </button>

          <button 
            onClick={() => { setIsUploadOpen(true); setUploadFeedback(null); }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition"
          >
            <Upload className="w-3.5 h-3.5" />
            Drop Paperwork
          </button>


          {/* Notifications Bell */}
          <div className="relative">
            <button
              onClick={() => setIsNotifDrawerOpen(!isNotifDrawerOpen)}
              className="relative p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition flex items-center justify-center"
              title="Alert Notifications"
            >
              <Bell className="w-4 h-4" />
              {unreadNotifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-black w-4 h-4 rounded-full flex items-center justify-center animate-pulse shadow-md">
                  {unreadNotifCount}
                </span>
              )}
            </button>

            {/* Notifications Dropdown Drawer */}
            {isNotifDrawerOpen && (
              <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-4 z-50 space-y-3 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                  <div className="flex items-center gap-2">
                    <Bell className="w-4 h-4 text-purple-400" />
                    <h3 className="text-xs font-bold text-white">
                      Alerts for {currentUser.handle}
                    </h3>
                  </div>
                  {unreadNotifCount > 0 && (
                    <button
                      onClick={handleMarkAllNotifsRead}
                      className="text-[10px] text-blue-400 hover:underline flex items-center gap-1"
                    >
                      <CheckCheck className="w-3 h-3" />
                      Mark all read
                    </button>
                  )}
                </div>

                <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                  {notifications.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center py-6">
                      No notifications or alerts.
                    </p>
                  ) : (
                    notifications.map(n => (
                      <div
                        key={n.notification_id}
                        onClick={() => handleNotificationClick(n)}
                        className={`p-3 rounded-xl border text-xs cursor-pointer transition ${
                          n.is_read
                            ? 'bg-slate-950/40 border-slate-800 text-slate-400 hover:bg-slate-800/40'
                            : 'bg-purple-950/30 border-purple-500/40 text-slate-200 hover:bg-purple-900/40'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded font-mono ${
                            n.notification_type === 'RESOLVED' 
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' 
                              : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                          }`}>
                            {n.notification_type}
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <h4 className="font-bold text-white text-xs leading-snug">{n.title}</h4>
                        <p className="text-[11px] text-slate-300 mt-1 leading-relaxed">{n.message}</p>
                        <div className="mt-2 flex items-center justify-between text-[10px] text-purple-400 font-medium">
                          <span>Target: {n.target_label}</span>
                          <span className="underline">Jump to target →</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Collaborative User Profile & Passwordless Switcher */}
          <div className="relative">
            <button
              onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
              className="flex items-center gap-2 p-1.5 pr-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 transition text-left"
            >
              <div 
                className="w-6 h-6 rounded-lg flex items-center justify-center text-white text-[10px] font-bold shadow"
                style={{ backgroundColor: currentUser.avatar_color || '#8b5cf6' }}
              >
                {currentUser.name.charAt(0)}
              </div>
              <div className="hidden sm:block">
                <p className="text-xs font-bold text-white leading-none">{currentUser.name}</p>
                <p className="text-[10px] text-purple-400 font-mono leading-tight">{currentUser.handle}</p>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {/* User Switcher Dropdown */}
            {isUserMenuOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-3.5 z-50 space-y-3 animate-in fade-in zoom-in-95">
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Switch Active User (Passwordless)
                  </h4>
                  <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
                    {teamUsers.map(u => (
                      <button
                        key={u.handle}
                        onClick={() => handleSwitchUser(u)}
                        className={`w-full flex items-center gap-2.5 p-2 rounded-xl text-left transition ${
                          currentUser.handle === u.handle
                            ? 'bg-purple-600/30 border border-purple-500/50 text-white'
                            : 'hover:bg-slate-800 text-slate-300 hover:text-white'
                        }`}
                      >
                        <div 
                          className="w-6 h-6 rounded-lg flex items-center justify-center text-white text-[10px] font-bold shrink-0"
                          style={{ backgroundColor: u.avatar_color || '#8b5cf6' }}
                        >
                          {u.name.charAt(0)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold truncate leading-none">{u.name}</p>
                          <p className="text-[10px] text-slate-400 font-mono truncate">{u.handle} • {u.role}</p>
                        </div>
                        {currentUser.handle === u.handle && (
                          <Check className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Custom Handle / Passwordless Login Input */}
                <form onSubmit={handleCustomLogin} className="pt-2 border-t border-slate-800 space-y-1.5">
                  <label className="text-[10px] font-medium text-slate-400 block">
                    Or Login with @handle / email:
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      placeholder="@editor_lead"
                      value={customLoginHandle}
                      onChange={e => setCustomLoginHandle(e.target.value)}
                      className="flex-1 bg-slate-950 border border-slate-700 text-xs px-2.5 py-1 rounded-lg text-white font-mono focus:outline-none focus:border-purple-500"
                    />
                    <button
                      type="submit"
                      className="px-2.5 py-1 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-lg transition"
                    >
                      Login
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className={`flex-1 ${activeTab === 'sequences' ? 'w-full max-w-[100%] px-3 sm:px-5 lg:px-6 py-4' : 'max-w-7xl w-full mx-auto p-6'} space-y-5 transition-all duration-150`}>
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
              onClick={() => setActiveTab('sequences')}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'sequences'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900 border border-transparent'
              }`}
            >
              <Film className="w-4 h-4 text-cyan-400" />
              Sequences Log Matrix ({sequences.length})
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

                    const takeKey = `${t.slate}_${t.take_id}`;
                    const activeCam = selectedCameraAngle[takeKey] || (t.camera_angles && t.camera_angles.length > 0 ? t.camera_angles[0].camera : 'A');
                    const activeAngle = t.camera_angles?.find(ca => ca.camera === activeCam) || (t.camera_angles && t.camera_angles.length > 0 ? t.camera_angles[0] : null);
                    const displayThumb = activeAngle?.thumbnail_url || t.thumbnail_url;

                    return (
                      <div 
                        key={idx}
                        className={`bg-slate-900/90 rounded-2xl border transition overflow-hidden flex flex-col shadow-lg hover:shadow-2xl ${
                          hasDiscrepancy ? 'border-red-500/40' : 'border-slate-800 hover:border-blue-500/50'
                        }`}
                      >
                        {/* Visual Thumbnail Frame & Camera Angle Switcher */}
                        <div className="relative bg-black aspect-video flex items-center justify-center border-b border-slate-800 overflow-hidden group">
                          {displayThumb ? (
                            <img 
                              src={displayThumb} 
                              alt={`Scene ${t.scene} Take ${t.take_id} Cam ${activeCam}`}
                              onClick={() => setEnlargedImage(displayThumb)}
                              className="w-full h-full object-cover group-hover:scale-105 transition duration-300 cursor-pointer" 
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-slate-400 p-4 text-center">
                              <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 mb-1.5 shadow-sm">
                                <Film className="w-5 h-5" />
                              </div>
                              <span className="text-xs font-mono text-amber-300 font-bold">
                                {t.belief.script ? "Script Supervisor Slate Entry" : t.is_wild_track ? "Audio Wild Track" : "Awaiting Camera Offload"}
                              </span>
                              <div className="flex flex-wrap items-center justify-center gap-1.5 mt-1 font-mono text-[10px]">
                                {t.camera_cards.length > 0 && (
                                  <span className="bg-blue-950/70 border border-blue-500/40 text-blue-300 px-2 py-0.5 rounded">
                                    🎴 {t.camera_cards.join(', ')}
                                  </span>
                                )}
                                {t.belief.script?.timecode_in && (
                                  <span className="bg-slate-900 border border-slate-800 text-slate-400 px-2 py-0.5 rounded">
                                    TC {t.belief.script.timecode_in}
                                  </span>
                                )}
                              </div>
                              {t.belief.script?.source_document && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenPreviewDoc(t.belief.script?.source_doc_id, t.belief.script?.source_document);
                                  }}
                                  className="mt-1.5 text-[10px] font-mono text-purple-400 hover:text-purple-300 underline flex items-center gap-1"
                                  title={`Preview ${t.belief.script.source_document}`}
                                >
                                  <Eye className="w-3 h-3" />
                                  <span className="truncate max-w-[180px]">{t.belief.script.source_document}</span>
                                </button>
                              )}
                            </div>
                          )}

                          {/* Top Slate Badge */}
                          <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 z-10">
                            <span className="bg-black/85 backdrop-blur-md text-white font-mono text-xs font-bold px-2.5 py-1 rounded-lg border border-white/20 shadow">
                              Sc {t.scene || 'N/A'} • {t.slate} T{t.take_id}
                            </span>
                          </div>

                          {/* Top Right Flags */}
                          <div className="absolute top-2.5 right-2.5 flex items-center gap-1 z-10">
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

                          {/* Multi-Camera Angle Pill Switcher on Frame */}
                          {t.camera_angles && t.camera_angles.length > 1 && (
                            <div className="absolute bottom-2.5 left-2.5 flex items-center gap-1 z-10 bg-black/75 backdrop-blur-md p-1 rounded-lg border border-white/15 shadow-lg">
                              {t.camera_angles.map(ca => {
                                const isSelected = (activeAngle?.camera || 'A') === ca.camera;
                                return (
                                  <button
                                    key={ca.camera}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedCameraAngle(prev => ({ ...prev, [takeKey]: ca.camera }));
                                    }}
                                    className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition ${
                                      isSelected
                                        ? 'bg-blue-600 text-white shadow'
                                        : 'text-slate-400 hover:text-white hover:bg-white/10'
                                    }`}
                                    title={`Preview Camera ${ca.camera}`}
                                  >
                                    Cam {ca.camera}
                                  </button>
                                );
                              })}
                            </div>
                          )}

                          {/* Hover Zoom Prompt */}
                          {displayThumb && (
                            <button
                              onClick={() => setEnlargedImage(displayThumb)}
                              className="absolute bottom-2.5 right-2.5 bg-black/70 hover:bg-blue-600 text-white p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition shadow z-10"
                              title="Enlarge Frame"
                            >
                              <Maximize2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>

                        {/* Composed Multi-Department Data Body */}
                        <div className="p-4 flex-1 space-y-3">
                          {/* Header Summary Badges */}
                          <div className="flex items-center justify-between text-[11px] pb-1 border-b border-slate-800/80">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-blue-400 font-semibold flex items-center gap-1">
                                🎥 {t.camera_cards?.length || t.video_files?.length || 1} Cam{(t.camera_cards?.length || 1) > 1 ? 's' : ''}
                                {t.camera_cards?.length > 0 && ` (${t.camera_cards.join(', ')})`}
                              </span>
                              <span className="text-slate-600">•</span>
                              {t.is_mos ? (
                                <span className="font-mono text-indigo-400 font-semibold flex items-center gap-1">
                                  🔇 MOS (Silent)
                                </span>
                              ) : t.audio_files?.length > 0 ? (
                                <span className="font-mono text-emerald-400 font-semibold flex items-center gap-1">
                                  🎙️ {t.audio_files.length} Audio File{t.audio_files.length > 1 ? 's' : ''}
                                </span>
                              ) : (
                                <span className="font-mono text-slate-500 flex items-center gap-1">
                                  🎙️ No audio report
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] font-mono text-cyan-300">
                              {t.storage_volumes?.length > 0 ? t.storage_volumes.join(', ') : 'Paperwork Logged'}
                            </span>
                          </div>

                          {/* 1. Video Files Section */}
                          {t.video_files && t.video_files.length > 0 && (
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-blue-500/20 space-y-1.5">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-blue-400 flex items-center gap-1">
                                  🎬 Video Media Clips ({t.video_files.length})
                                </span>
                                {t.belief.camera?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.camera?.source_doc_id, t.belief.camera?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    ZoeLog
                                  </button>
                                )}
                              </div>

                              <div className="space-y-1">
                                {t.video_files.map((vf, vi) => (
                                  <div key={vi} className="bg-slate-900/70 p-1.5 rounded-lg border border-slate-800 text-[11px] font-mono flex items-center justify-between">
                                    <div className="flex items-center gap-1.5 overflow-hidden">
                                      <span className="bg-blue-600/30 text-blue-300 font-bold px-1.5 py-0.2 rounded text-[10px]">
                                        Cam {vf.camera}
                                      </span>
                                      <span className="text-slate-300 truncate max-w-[160px]" title={vf.file_name}>
                                        {vf.file_name}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-1 text-[10px] text-slate-400 shrink-0">
                                      <span className="text-slate-300 font-semibold">{vf.camera_roll}</span>
                                      <span>•</span>
                                      <span className="text-cyan-400 font-semibold">{vf.fps}fps</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 2. Audio Files Section */}
                          {t.audio_files && t.audio_files.length > 0 && (
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-emerald-500/20 space-y-1.5">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-emerald-400 flex items-center gap-1">
                                  🎙️ Audio Sound Files ({t.audio_files.length})
                                </span>
                                {t.belief.sound?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.sound?.source_doc_id, t.belief.sound?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    Sound CSV
                                  </button>
                                )}
                              </div>

                              <div className="space-y-1.5">
                                {t.audio_files.map((af, ai) => (
                                  <div key={ai} className="bg-slate-900/70 p-2 rounded-lg border border-slate-800 space-y-1">
                                    <div className="flex items-center justify-between text-[11px] font-mono">
                                      <div className="flex items-center gap-1.5">
                                        <span className="bg-emerald-600/30 text-emerald-300 font-bold px-1.5 py-0.2 rounded text-[10px]">
                                          WAV
                                        </span>
                                        <span className="text-emerald-300 font-semibold truncate max-w-[150px]" title={af.file_name}>
                                          {af.file_name}
                                        </span>
                                      </div>
                                      <span className="text-[10px] text-slate-400 font-mono">{af.duration || '00:03:00'}</span>
                                    </div>

                                    {/* Multi-Track Channel Badges */}
                                    {af.tracks && (
                                      <div className="flex flex-wrap gap-1 pt-0.5">
                                        {af.tracks.split(',').map((trk, ti) => (
                                          <span key={ti} className="bg-slate-950 border border-slate-800 text-[9px] font-mono text-slate-300 px-1.5 py-0.2 rounded">
                                            {trk.trim()}
                                          </span>
                                        ))}
                                      </div>
                                    )}

                                    {af.note && (
                                      <div className="text-[10px] text-amber-300/90 italic font-mono bg-amber-950/20 px-1.5 py-0.5 rounded border border-amber-500/20">
                                        Mixer Note: "{af.note}"
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 3. Script Department Note */}
                          {t.belief.script && (
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-amber-500/20 text-[11px] space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-amber-400 flex items-center gap-1 text-[11px]">
                                  📝 Script Supervisor (Scripte)
                                </span>
                                {t.belief.script.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.script?.source_doc_id, t.belief.script?.source_document)}
                                    className="text-[10px] text-purple-400 hover:underline font-mono"
                                  >
                                    Preview Log
                                  </button>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-300 italic line-clamp-2">
                                {t.belief.script.note || 'Scripte Log Recorded'}
                              </p>
                              {t.belief.script.timecode_in && (
                                <div className="text-[10px] font-mono text-slate-400">
                                  TC: {t.belief.script.timecode_in} → {t.belief.script.timecode_out || '--'}
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Requirements Status Bar */}
                        {t.requirements && t.requirements.length > 0 && (
                          <div className="px-4 py-1.5 bg-slate-950/70 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-1.5">
                            <div className="flex items-center gap-1.5">
                              {t.open_requirements_count ? (
                                <button
                                  onClick={() => setViewingReqsList({
                                    target_label: `Take ${t.slate} T${t.take_id}`,
                                    target_type: 'take',
                                    target_id: `${t.slate}_${t.take_id}`,
                                    requirements: t.requirements || [],
                                  })}
                                  className="px-2 py-0.5 rounded-md bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-[10px] font-bold flex items-center gap-1 transition"
                                >
                                  <AlertTriangle className="w-3 h-3" />
                                  {t.open_requirements_count} Open Req
                                </button>
                              ) : null}
                              {t.resolved_requirements_count ? (
                                <button
                                  onClick={() => setViewingReqsList({
                                    target_label: `Take ${t.slate} T${t.take_id}`,
                                    target_type: 'take',
                                    target_id: `${t.slate}_${t.take_id}`,
                                    requirements: t.requirements || [],
                                  })}
                                  className="px-2 py-0.5 rounded-md bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-[10px] font-semibold flex items-center gap-1 transition"
                                >
                                  <CheckCircle2 className="w-3 h-3" />
                                  {t.resolved_requirements_count} Resolved
                                </button>
                              ) : null}
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono">
                              Assignee: {t.requirements[0].assigned_to}
                            </span>
                          </div>
                        )}

                        {/* Card Footer Actions */}
                        <div className="px-4 py-3 bg-slate-950/90 border-t border-slate-800 flex items-center justify-between gap-2">
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
                            onClick={() => {
                              setTargetForReq({
                                target_type: 'take',
                                target_id: `${t.slate}_${t.take_id}`,
                                target_label: `Take ${t.slate} T${t.take_id}`,
                              });
                              setNewReqTitle('');
                              setNewReqDesc('');
                              setIsCreateReqOpen(true);
                            }}
                            className="px-2.5 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 hover:text-white rounded-lg text-xs font-semibold border border-purple-500/30 transition flex items-center gap-1"
                            title="Add Requirement on this Take"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            + Req
                          </button>
                          <button
                            onClick={() => handleInspectTake(t)}
                            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-semibold border border-slate-700 transition"
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
            {masterLayout === 'slate' && currentFocusTake && (() => {
              const focusKey = `${currentFocusTake.slate}_${currentFocusTake.take_id}`;
              const focusActiveCam = selectedCameraAngle[focusKey] || (currentFocusTake.camera_angles && currentFocusTake.camera_angles.length > 0 ? currentFocusTake.camera_angles[0].camera : 'A');
              const focusActiveAngle = currentFocusTake.camera_angles?.find(ca => ca.camera === focusActiveCam) || (currentFocusTake.camera_angles && currentFocusTake.camera_angles.length > 0 ? currentFocusTake.camera_angles[0] : null);
              const focusDisplayThumb = focusActiveAngle?.thumbnail_url || currentFocusTake.thumbnail_url;

              return (
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

                  {/* Composed Multi-Angle Slate Body */}
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
                    {/* Left Column: Visual Frame with Angle Switcher Tabs & Storage Notary */}
                    <div className="space-y-4">
                      <div className="space-y-2">
                        {/* Angle Switcher Tabs */}
                        {currentFocusTake.camera_angles && currentFocusTake.camera_angles.length > 1 && (
                          <div className="flex items-center gap-1.5 bg-slate-950 p-1.5 rounded-xl border border-slate-800">
                            {currentFocusTake.camera_angles.map(ca => {
                              const isSelected = (focusActiveAngle?.camera || 'A') === ca.camera;
                              return (
                                <button
                                  key={ca.camera}
                                  onClick={() => setSelectedCameraAngle(prev => ({ ...prev, [focusKey]: ca.camera }))}
                                  className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-mono font-bold transition flex items-center justify-center gap-1.5 ${
                                    isSelected
                                      ? 'bg-blue-600 text-white shadow-lg'
                                      : 'text-slate-400 hover:text-white hover:bg-slate-900'
                                  }`}
                                >
                                  <Video className="w-3.5 h-3.5" />
                                  Camera {ca.camera} ({ca.camera_roll})
                                </button>
                              );
                            })}
                          </div>
                        )}

                        <div 
                          className="relative bg-black aspect-video rounded-xl overflow-hidden border border-slate-800 group cursor-pointer shadow-lg"
                          onClick={() => focusDisplayThumb && setEnlargedImage(focusDisplayThumb)}
                        >
                          {focusDisplayThumb ? (
                            <img 
                              src={focusDisplayThumb} 
                              alt="Slate Frame" 
                              className="w-full h-full object-cover group-hover:scale-105 transition duration-300" 
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-slate-400 p-6 text-center">
                              <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400 mb-2 shadow-sm">
                                <Clapperboard className="w-7 h-7" />
                              </div>
                              <span className="text-sm font-mono text-amber-300 font-bold">
                                {currentFocusTake.belief.script ? "Script Supervisor Continuity Slate" : "Awaiting Camera Thumbnail Offload"}
                              </span>
                              <div className="flex flex-wrap items-center justify-center gap-1.5 mt-2 font-mono text-xs">
                                {currentFocusTake.camera_cards?.length > 0 && (
                                  <span className="bg-blue-950/80 border border-blue-500/40 text-blue-300 px-2.5 py-0.5 rounded-lg">
                                    🎴 Cards: {currentFocusTake.camera_cards.join(', ')}
                                  </span>
                                )}
                                {currentFocusTake.belief.script?.timecode_in && (
                                  <span className="bg-slate-900 border border-slate-800 text-slate-300 px-2.5 py-0.5 rounded-lg">
                                    TC: {currentFocusTake.belief.script.timecode_in} → {currentFocusTake.belief.script.timecode_out || '--'}
                                  </span>
                                )}
                              </div>
                              {currentFocusTake.belief.script?.source_document && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenPreviewDoc(currentFocusTake.belief.script?.source_doc_id, currentFocusTake.belief.script?.source_document);
                                  }}
                                  className="mt-2.5 text-xs font-mono text-purple-400 hover:text-purple-300 underline flex items-center gap-1.5 bg-purple-950/40 px-3 py-1 rounded-lg border border-purple-500/30"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                  Preview Source: {currentFocusTake.belief.script.source_document}
                                </button>
                              )}
                            </div>
                          )}
                          {focusDisplayThumb && (
                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                              <span className="bg-blue-600 text-white text-xs px-3 py-1 rounded-lg font-semibold shadow">
                                Click to Enlarge Camera {focusActiveCam} Frame
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Physical Location Card */}
                      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                            <HardDrive className="w-4 h-4 text-cyan-400" />
                            Storage & Physical Media Location
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded border font-mono font-bold ${
                            currentFocusTake.matched_media_files.length > 0 
                              ? 'text-emerald-400 bg-emerald-950 border-emerald-500/30' 
                              : 'text-amber-400 bg-amber-950/60 border-amber-500/30'
                          }`}>
                            {currentFocusTake.matched_media_files.length > 0 ? '✓ Checksum OK' : '📄 Paperwork Logged'}
                          </span>
                        </div>
                        <div className="text-xs font-mono text-slate-300 space-y-1.5 pt-1">
                          <div>Volumes: <span className="text-white font-bold">{currentFocusTake.storage_volumes?.length > 0 ? currentFocusTake.storage_volumes.join(', ') : 'Awaiting DIT Offload'}</span></div>
                          <div>Camera Cards: <span className="text-blue-300 font-bold">{currentFocusTake.camera_cards?.join(', ') || 'Awaiting ZoeLog'}</span></div>
                          <div>Sound Rolls: <span className={currentFocusTake.is_mos ? "text-indigo-400 font-bold" : "text-emerald-400 font-bold"}>{currentFocusTake.is_mos ? "None (MOS / Silent Take)" : (currentFocusTake.sound_cards?.join(', ') || 'Awaiting Sound ALE')}</span></div>
                          <div>Recorded Date: <span className="text-slate-200">{currentFocusTake.recording_date || '28/07/2026'}</span></div>
                        </div>
                      </div>
                    </div>

                    {/* Right Column: Multi-Camera Video Files & Sound Audio Files Tables */}
                    <div className="lg:col-span-2 space-y-4">
                      {/* Video Files Matrix */}
                      <div className="bg-slate-950 p-4 rounded-xl border border-blue-500/20 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                          <span className="text-xs font-bold text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
                            <Video className="w-4 h-4 text-blue-400" />
                            Camera Video Files Offloaded ({currentFocusTake.video_files?.length || 0})
                          </span>
                          {currentFocusTake.belief.camera?.source_document && (
                            <button
                              onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.camera?.source_doc_id, currentFocusTake.belief.camera?.source_document)}
                              className="text-xs text-purple-400 hover:underline flex items-center gap-1 font-mono"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              ZoeLog
                            </button>
                          )}
                        </div>

                        <div className="space-y-2">
                          {currentFocusTake.video_files?.map((vf, vi) => (
                            <div key={vi} className="bg-slate-900/80 p-3 rounded-lg border border-slate-800 space-y-1.5 font-mono text-xs">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="bg-blue-600 text-white font-bold px-2 py-0.5 rounded text-[11px]">
                                    Cam {vf.camera}
                                  </span>
                                  <span className="text-white font-bold">{vf.file_name}</span>
                                </div>
                                <span className="text-cyan-400 font-bold">{vf.camera_roll}</span>
                              </div>
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-slate-300 pt-1 border-t border-slate-800/60">
                                <div>Codec: <span className="text-slate-100">{vf.codec}</span></div>
                                <div>FPS: <span className="text-slate-100">{vf.fps}fps</span></div>
                                <div>ISO: <span className="text-slate-100">{vf.iso}EI</span></div>
                                <div>T-Stop: <span className="text-slate-100">{vf.tstop}</span></div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Audio Files & Tracks Matrix */}
                      <div className="bg-slate-950 p-4 rounded-xl border border-emerald-500/20 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                          <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                            <Mic className="w-4 h-4 text-emerald-400" />
                            Sound WAV Files & Multi-Track Channels ({currentFocusTake.audio_files?.length || 0})
                          </span>
                          {currentFocusTake.belief.sound?.source_document && (
                            <button
                              onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.sound?.source_doc_id, currentFocusTake.belief.sound?.source_document)}
                              className="text-xs text-purple-400 hover:underline flex items-center gap-1 font-mono"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              Sound Report
                            </button>
                          )}
                        </div>

                        <div className="space-y-2">
                          {currentFocusTake.audio_files?.map((af, ai) => (
                            <div key={ai} className="bg-slate-900/80 p-3 rounded-lg border border-slate-800 space-y-2 font-mono text-xs">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="bg-emerald-600 text-white font-bold px-2 py-0.5 rounded text-[11px]">
                                    WAV
                                  </span>
                                  <span className="text-emerald-300 font-bold">{af.file_name}</span>
                                </div>
                                <span className="text-emerald-400 font-bold">{af.sound_roll}</span>
                              </div>

                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-slate-300">
                                <div>Start TC: <span className="text-white">{af.timecode_in || '--'}</span></div>
                                <div>Length: <span className="text-white">{af.duration || '--'}</span></div>
                                <div>Sample Rate: <span className="text-slate-200">{af.sample_rate || '48kHz'}</span></div>
                                <div>Bit Depth: <span className="text-slate-200">{af.bit_depth || '24-bit'}</span></div>
                              </div>

                              {af.tracks && (
                                <div className="space-y-1 pt-1 border-t border-slate-800/60">
                                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-sans font-semibold">Active Channels / Tracks:</span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {af.tracks.split(',').map((trk, ti) => (
                                      <span key={ti} className="bg-slate-950 border border-slate-800 text-[10px] text-cyan-300 px-2 py-0.5 rounded font-mono font-medium">
                                        {trk.trim()}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {af.note && (
                                <div className="text-[11px] text-amber-300 bg-amber-950/20 p-2 rounded border border-amber-500/20 italic">
                                  Mixer Note: "{af.note}"
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Script Supervisor Witness */}
                      {currentFocusTake.belief.script && (
                        <div className="bg-slate-950 p-4 rounded-xl border border-amber-500/20 space-y-2">
                          <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                            <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                              Script Supervisor Witness (Scripte Logs)
                            </span>
                            {currentFocusTake.belief.script.source_document && (
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
                            <div>Timecode: <span className="text-white">{currentFocusTake.belief.script.timecode_in || '--'} → {currentFocusTake.belief.script.timecode_out || '--'}</span></div>
                            <div>Camera Card: <span className="text-white font-bold">{currentFocusTake.belief.script.camera_roll || '--'}</span></div>
                            <div className="col-span-2">Notes: <span className="text-slate-200 italic">{currentFocusTake.belief.script.note || 'Take recorded normally without faults.'}</span></div>
                          </div>
                        </div>
                      )}

                      {/* Collaborative Requirements & Notes Section */}
                      <div className="bg-slate-950 p-4 rounded-xl border border-purple-500/20 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="w-4 h-4 text-purple-400" />
                            <span className="text-xs font-bold text-purple-400 uppercase tracking-wider">
                              Collaborative Requirements ({currentFocusTake.requirements?.length || 0})
                            </span>
                          </div>
                          <button
                            onClick={() => {
                              setTargetForReq({
                                target_type: 'take',
                                target_id: `${currentFocusTake.slate}_${currentFocusTake.take_id}`,
                                target_label: `Take ${currentFocusTake.slate} T${currentFocusTake.take_id}`,
                              });
                              setNewReqTitle('');
                              setNewReqDesc('');
                              setIsCreateReqOpen(true);
                            }}
                            className="text-xs text-purple-300 hover:text-white bg-purple-600/30 hover:bg-purple-600/50 border border-purple-500/40 px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition font-semibold"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            + Add Requirement
                          </button>
                        </div>

                        {(!currentFocusTake.requirements || currentFocusTake.requirements.length === 0) ? (
                          <p className="text-xs text-slate-500 italic py-1">
                            No requirements assigned to this take. Click "+ Add Requirement" to assign one to an editor, mixer, or VFX artist.
                          </p>
                        ) : (
                          <div className="space-y-2">
                            {currentFocusTake.requirements.map(req => (
                              <div
                                key={req.requirement_id}
                                className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                                  req.status === 'resolved'
                                    ? 'bg-emerald-950/20 border-emerald-500/30 text-slate-300'
                                    : 'bg-slate-900 border-slate-800 text-slate-200'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase ${
                                      req.status === 'resolved'
                                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                    }`}>
                                      {req.status}
                                    </span>
                                    <span className="font-bold text-white text-xs">{req.title}</span>
                                  </div>
                                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-purple-950/60 text-purple-300 border border-purple-500/30">
                                    {req.priority.toUpperCase()}
                                  </span>
                                </div>
                                <p className="text-[11px] text-slate-300 leading-relaxed">{req.description}</p>
                                <div className="text-[10px] text-slate-400 font-mono flex items-center justify-between pt-1 border-t border-slate-800/60">
                                  <span>Created by <strong className="text-purple-300">{req.created_by}</strong> → Assigned to <strong className="text-blue-300">{req.assigned_to}</strong></span>
                                  {req.status !== 'resolved' && (
                                    <button
                                      onClick={() => {
                                        setSelectedReqForResolve(req);
                                        setReqResolutionNote('');
                                        setViewingReqsList({
                                          target_label: `Take ${currentFocusTake.slate} T${currentFocusTake.take_id}`,
                                          target_type: 'take',
                                          target_id: `${currentFocusTake.slate}_${currentFocusTake.take_id}`,
                                          requirements: currentFocusTake.requirements || [],
                                        });
                                      }}
                                      className="text-emerald-400 hover:text-emerald-300 font-bold underline flex items-center gap-1"
                                    >
                                      <Check className="w-3 h-3" />
                                      Resolve Requirement
                                    </button>
                                  )}
                                </div>
                                {req.status === 'resolved' && (
                                  <div className="mt-1.5 p-2 rounded bg-emerald-950/40 border border-emerald-500/30 text-[10px] text-emerald-200">
                                    <strong>✓ Resolved by {req.resolved_by}:</strong> "{req.resolution_note}"
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
          </section>
        )}

        {/* TAB: SEQUENCES LOG MATRIX */}
        {activeTab === 'sequences' && (
          <section className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden shadow-xl space-y-0">
            <div className="px-6 py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 bg-slate-900/70">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Film className="w-4 h-4 text-cyan-400" />
                  Sequence Log & Multi-Department Witness Matrix
                </h3>
                <p className="text-[11px] text-slate-400">
                  Comprehensive sequence list cross-referenced with Location, Script description, Camera A/B/C logs, Sound reports, and Silverstack DIT checksums.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-cyan-300 bg-cyan-950/40 border border-cyan-500/30 px-2.5 py-1 rounded-lg">
                  {filteredSequences.length} Sequences Recorded
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase font-mono text-[10px] tracking-wider sticky top-0 z-10">
                  <tr>
                    <th className="px-3.5 py-3 whitespace-nowrap">SEQUENCE</th>
                    <th className="px-3.5 py-3 whitespace-nowrap">LOCATION</th>
                    <th className="px-3.5 py-3 min-w-[220px]">DESCRIPTION</th>
                    <th className="px-3 py-3 whitespace-nowrap">SHOOTING DAY</th>
                    <th className="px-3 py-3 whitespace-nowrap">DATE</th>
                    <th className="px-3.5 py-3 min-w-[140px]">CARDS</th>
                    <th className="px-3 py-3 whitespace-nowrap">SCRIPTLOG FILE</th>
                    <th className="px-3 py-3 whitespace-nowrap">CAM A LOG</th>
                    <th className="px-3 py-3 whitespace-nowrap">CAM B LOG</th>
                    <th className="px-3 py-3 whitespace-nowrap">CAM C LOG</th>
                    <th className="px-3 py-3 whitespace-nowrap">SOUND LOG</th>
                    <th className="px-3 py-3 whitespace-nowrap">SILVERSTACK THUMBNAIL</th>
                    <th className="px-3.5 py-3 whitespace-nowrap">STATUS & FLAGS</th>
                    <th className="px-3.5 py-3 min-w-[180px]">COMMENTS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70 font-sans">
                  {filteredSequences.length === 0 ? (
                    <tr>
                      <td colSpan={14} className="px-4 py-16 text-center text-slate-500">
                        No sequence records found matching filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredSequences.map((seq, idx) => (
                      <tr 
                        key={idx} 
                        className={`hover:bg-slate-800/40 transition duration-150 ${
                          seq.has_discrepancy ? 'bg-red-950/10' : idx % 2 === 0 ? 'bg-slate-950/30' : 'bg-transparent'
                        }`}
                      >
                        {/* 1. SEQUENCE */}
                        <td className="px-3.5 py-3 align-top whitespace-nowrap">
                          <div className="space-y-1">
                            <button
                              onClick={() => {
                                setSelectedSceneFilter(seq.sequence);
                                setActiveTab('master');
                              }}
                              className="font-mono text-xs font-bold text-cyan-300 hover:text-white hover:underline flex items-center gap-1.5"
                              title="Click to view all takes for this sequence in Master Sheet"
                            >
                              <span className="bg-cyan-950/60 border border-cyan-500/40 px-2 py-0.5 rounded text-cyan-300">
                                {seq.sequence}
                              </span>
                              <ExternalLink className="w-3 h-3 text-cyan-400/70" />
                            </button>
                            <div className="text-[10px] text-slate-400 font-mono flex items-center gap-1.5">
                              <span>{seq.takes_count} {seq.takes_count === 1 ? 'take' : 'takes'}</span>
                              {seq.circled_takes_count && seq.circled_takes_count > 0 ? (
                                <span className="bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.2 rounded font-bold" title={`Chosen / Circled takes: ${seq.circled_takes?.join(', ')}`}>
                                  ⭐ {seq.circled_takes_count} chosen
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </td>

                        {/* 2. LOCATION */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="flex items-start gap-1.5 font-medium text-amber-300/90 text-xs">
                            <MapPin className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                            <span>{seq.location}</span>
                          </div>
                        </td>

                        {/* 3. DESCRIPTION */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="text-slate-200 text-xs leading-relaxed max-w-sm">
                            {seq.description}
                          </div>
                        </td>

                        {/* 4. SHOOTING-DAY */}
                        <td className="px-3 py-3 align-top whitespace-nowrap font-mono text-xs text-slate-300">
                          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded w-fit">
                            <Calendar className="w-3 h-3 text-blue-400" />
                            {seq.shoot_day}
                          </div>
                        </td>

                        {/* 5. DATE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap font-mono text-xs text-slate-400">
                          {seq.date}
                        </td>

                        {/* 6. CARDS */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="flex flex-wrap gap-1 max-w-xs font-mono text-[10px]">
                            {seq.camera_cards?.map((card, ci) => (
                              <span key={ci} className="bg-blue-950/60 border border-blue-500/30 text-blue-300 px-1.5 py-0.5 rounded">
                                {card}
                              </span>
                            ))}
                            {seq.sound_cards?.map((card, si) => (
                              <span key={si} className="bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 px-1.5 py-0.5 rounded">
                                {card}
                              </span>
                            ))}
                            {(!seq.camera_cards || seq.camera_cards.length === 0) && (!seq.sound_cards || seq.sound_cards.length === 0) && (
                              <span className="text-slate-600">--</span>
                            )}
                          </div>
                        </td>

                        {/* 7. SCRIPTLOG-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.script_log_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.script_log_doc?.doc_id, seq.script_log_doc?.filename)}
                              className="text-[11px] font-mono text-purple-300 hover:text-white bg-purple-950/40 hover:bg-purple-900/50 border border-purple-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.script_log_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-purple-400" />
                              <span className="truncate max-w-[130px]">{seq.script_log_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 8. CAMERAA LOG-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.camera_a_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.camera_a_doc?.doc_id, seq.camera_a_doc?.filename)}
                              className="text-[11px] font-mono text-blue-300 hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.camera_a_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-blue-400" />
                              <span className="truncate max-w-[130px]">{seq.camera_a_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 9. CAMERAB LOG-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.camera_b_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.camera_b_doc?.doc_id, seq.camera_b_doc?.filename)}
                              className="text-[11px] font-mono text-blue-300 hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.camera_b_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-blue-400" />
                              <span className="truncate max-w-[130px]">{seq.camera_b_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 10. CAMERAC LOG-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.camera_c_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.camera_c_doc?.doc_id, seq.camera_c_doc?.filename)}
                              className="text-[11px] font-mono text-blue-300 hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.camera_c_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-blue-400" />
                              <span className="truncate max-w-[130px]">{seq.camera_c_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 11. SOUND-LOG-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.sound_log_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.sound_log_doc?.doc_id, seq.sound_log_doc?.filename)}
                              className="text-[11px] font-mono text-emerald-300 hover:text-white bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.sound_log_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-emerald-400" />
                              <span className="truncate max-w-[130px]">{seq.sound_log_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 12. SILVERSTACK THUMBNAIL-FILE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap">
                          {seq.silverstack_thumbnail_doc ? (
                            <button
                              onClick={() => handleOpenPreviewDoc(seq.silverstack_thumbnail_doc?.doc_id, seq.silverstack_thumbnail_doc?.filename)}
                              className="text-[11px] font-mono text-cyan-300 hover:text-white bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.silverstack_thumbnail_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-cyan-400" />
                              <span className="truncate max-w-[140px]">{seq.silverstack_thumbnail_doc.filename}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600 font-mono text-[11px]">--</span>
                          )}
                        </td>

                        {/* 13. STATUS & FLAGS (Discrepancy, WT, VFX, Requirements) */}
                        <td className="px-3.5 py-3 align-top whitespace-nowrap">
                          <div className="flex flex-col gap-1.5">
                            {seq.has_discrepancy ? (
                              <button
                                onClick={() => {
                                  const matchingDisc = discrepancies.find(d => seq.takes.some(t => d.entity_id.includes(t.split(' ')[0])) && !d.is_resolved);
                                  if (matchingDisc) {
                                    openResolveModal(matchingDisc);
                                  } else {
                                    setActiveTab('discrepancies');
                                  }
                                }}
                                className="bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 text-red-300 px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 w-fit transition"
                                title="Click to resolve discrepancy"
                              >
                                <AlertCircle className="w-3 h-3 text-red-400" />
                                Solve Mismatch
                              </button>
                            ) : (
                              <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 w-fit">
                                <Check className="w-3 h-3 text-emerald-400" />
                                Reconciled
                              </span>
                            )}

                            {/* Requirements Badges for Sequence */}
                            <div className="flex flex-wrap items-center gap-1">
                              {seq.open_requirements_count ? (
                                <button
                                  onClick={() => setViewingReqsList({
                                    target_label: `Scene ${seq.sequence}`,
                                    target_type: 'scene',
                                    target_id: seq.sequence,
                                    requirements: seq.requirements || [],
                                  })}
                                  className="px-1.5 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-[9px] font-bold flex items-center gap-1"
                                >
                                  <AlertTriangle className="w-2.5 h-2.5" />
                                  {seq.open_requirements_count} Req
                                </button>
                              ) : null}
                              {seq.resolved_requirements_count ? (
                                <button
                                  onClick={() => setViewingReqsList({
                                    target_label: `Scene ${seq.sequence}`,
                                    target_type: 'scene',
                                    target_id: seq.sequence,
                                    requirements: seq.requirements || [],
                                  })}
                                  className="px-1.5 py-0.5 rounded bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-[9px] font-semibold flex items-center gap-1"
                                >
                                  <CheckCircle2 className="w-2.5 h-2.5" />
                                  {seq.resolved_requirements_count}
                                </button>
                              ) : null}
                              <button
                                onClick={() => {
                                  setTargetForReq({
                                    target_type: 'scene',
                                    target_id: seq.sequence,
                                    target_label: `Scene ${seq.sequence}`,
                                  });
                                  setNewReqTitle('');
                                  setNewReqDesc('');
                                  setIsCreateReqOpen(true);
                                }}
                                className="px-1.5 py-0.5 rounded bg-purple-600/20 hover:bg-purple-600/40 border border-purple-500/30 text-purple-300 text-[9px] font-semibold flex items-center gap-0.5 transition"
                                title="Add Requirement for Scene"
                              >
                                <PlusCircle className="w-2.5 h-2.5" />
                                + Req
                              </button>
                            </div>

                            <div className="flex items-center gap-1">
                              {seq.is_wild_track && (
                                <span className="bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 px-1.5 py-0.5 rounded text-[10px] font-bold font-mono">
                                  🎙️ WT
                                </span>
                              )}
                              {seq.is_vfx && (
                                <span className="bg-purple-500/20 border border-purple-500/40 text-purple-300 px-1.5 py-0.5 rounded text-[10px] font-bold font-mono">
                                  ✨ VFX
                                </span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* 14. COMMENTS */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="text-slate-300 text-xs italic max-w-xs leading-relaxed">
                            "{seq.comments}"
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
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
                              {t.is_mos && (
                                <span className="text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 px-1.5 py-0.2 rounded font-sans">
                                  🔇 MOS
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
                            {t.is_mos ? (
                              <span className="text-indigo-300/80 font-mono text-[11px] flex items-center gap-1">
                                <span>🔇</span> MOS (Silent Take)
                              </span>
                            ) : t.belief.sound ? (
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
                <div 
                  key={idx} 
                  className={`rounded-xl p-5 space-y-3 shadow-lg transition ${
                    d.is_resolved 
                      ? 'bg-emerald-950/20 border border-emerald-500/40' 
                      : 'bg-slate-900/80 border border-red-500/30'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded font-mono ${
                          d.is_resolved
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : d.severity === 'CRITICAL' 
                              ? 'bg-red-500/20 text-red-300 border border-red-500/40' 
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        }`}>
                          {d.is_resolved ? '✓ RESOLVED' : d.discrepancy_type}
                        </span>
                        <span className="text-sm font-mono font-bold text-white">{d.entity_id}</span>
                        {d.is_resolved && (
                          <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-950/80 border border-emerald-700/60 px-2 py-0.5 rounded flex items-center gap-1">
                            <HardDrive className="w-3 h-3" />
                            Target Card: {d.resolved_card || 'Manual Override'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-200">{d.description}</p>
                      {d.is_resolved && d.resolution_note && (
                        <p className="text-xs text-emerald-300/90 italic bg-emerald-950/40 p-2.5 rounded-lg border border-emerald-800/40">
                          "{d.resolution_note}" <span className="text-emerald-500 text-[11px] not-italic">— {d.resolved_by || 'Assistant Editor'} {d.resolved_at ? `(${new Date(d.resolved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})` : ''}</span>
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      {d.is_resolved ? (
                        <>
                          <button
                            onClick={() => openResolveModal(d)}
                            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold border border-slate-700 transition"
                          >
                            Edit Card / Note
                          </button>
                          <button
                            onClick={() => handleUnresolve(d.discrepancy_id)}
                            className="px-3 py-1.5 rounded-lg bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/30 text-xs font-semibold transition"
                          >
                            Re-open
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => openResolveModal(d)}
                          className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow"
                        >
                          <Check className="w-3.5 h-3.5" />
                          Resolve / Assign Card
                        </button>
                      )}
                      <button 
                        onClick={() => {
                          const takeMatch = takes.find(t => d.entity_id.includes(t.slate) && d.entity_id.includes(t.take_id));
                          if (takeMatch) handleInspectTake(takeMatch);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition"
                      >
                        Diagnose
                      </button>
                    </div>
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

            {/* Active Discrepancy Status & Resolution Callout in Inspector Drawer */}
            {(() => {
              const matchedDisc = discrepancies.find(d => 
                (d.entity_id.includes(inspectedTake.slate) && d.entity_id.includes(inspectedTake.take_id)) ||
                (d.entity_id.includes(inspectedTake.slate) && d.entity_type === 'take')
              );
              if (!matchedDisc) return null;

              return (
                <div className={`p-4 rounded-xl border space-y-2.5 shadow-md ${
                  matchedDisc.is_resolved
                    ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-200'
                    : 'bg-red-950/40 border-red-500/50 text-red-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                        matchedDisc.is_resolved ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                      }`}>
                        {matchedDisc.is_resolved ? '✓ RESOLVED' : matchedDisc.discrepancy_type}
                      </span>
                      {matchedDisc.is_resolved && (
                        <span className="text-xs font-mono font-bold text-white flex items-center gap-1">
                          <HardDrive className="w-3 h-3 text-emerald-400" />
                          Assigned: {matchedDisc.resolved_card || 'Manual Override'}
                        </span>
                      )}
                    </div>
                    {matchedDisc.is_resolved ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => openResolveModal(matchedDisc)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold border border-slate-700 transition"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleUnresolve(matchedDisc.discrepancy_id)}
                          className="px-2.5 py-1 rounded bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/30 text-xs font-semibold transition"
                        >
                          Re-open
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => openResolveModal(matchedDisc)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1 shadow"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Resolve Discrepancy
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-slate-200">{matchedDisc.description}</p>
                  {matchedDisc.is_resolved && matchedDisc.resolution_note && (
                    <p className="text-xs italic bg-emerald-950/60 p-2 rounded text-emerald-300/90 border border-emerald-900/40">
                      "{matchedDisc.resolution_note}" <span className="text-emerald-400 text-[11px] not-italic">— {matchedDisc.resolved_by || 'Assistant Editor'}</span>
                    </p>
                  )}
                </div>
              );
            })()}

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
            {/* Department Witness Breakdown with Preview Links */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Source Document Witness Claims</h4>

              {/* 1. Script Supervisor Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-400">1. Script Supervisor (Editorial & Continuity)</span>
                  {inspectedTake.belief.script?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.script?.source_doc_id, inspectedTake.belief.script?.source_document)}
                      className="text-[11px] text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium underline"
                    >
                      <Eye className="w-3 h-3" />
                      Preview {inspectedTake.belief.script.source_document}
                    </button>
                  )}
                </div>
                {inspectedTake.belief.script ? (
                  <div className="space-y-2">
                    <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-2">
                      <div>Camera Roll: <span className="text-white font-bold">{inspectedTake.belief.script.camera_roll || '--'}</span></div>
                      <div>Date: <span className="text-white">{inspectedTake.belief.script.recording_date || inspectedTake.recording_date || '--'}</span></div>
                      <div>Timecode In: <span className="text-white">{inspectedTake.belief.script.timecode_in || '--'}</span></div>
                      <div>Timecode Out: <span className="text-white">{inspectedTake.belief.script.timecode_out || '--'}</span></div>
                      <div>Circled Take: <span className={inspectedTake.belief.script.is_starred ? 'text-amber-400 font-bold' : 'text-slate-400'}>{inspectedTake.belief.script.is_starred ? '⭐ YES (Chosen)' : 'NO'}</span></div>
                      <div>MOS (Silent): <span className={inspectedTake.belief.script.is_mos ? 'text-indigo-400 font-bold' : 'text-slate-400'}>{inspectedTake.belief.script.is_mos ? '🔇 YES (MOS)' : 'NO (Sync Audio)'}</span></div>
                    </div>
                    {inspectedTake.belief.script.note && (
                      <div className="text-[11px] text-slate-300 italic pt-1 border-t border-slate-900">
                        "{inspectedTake.belief.script.note}"
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs font-mono text-slate-500 italic">No script supervisor log ingested for this slate yet.</div>
                )}
              </div>

              {/* 2. Camera Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-400">2. Camera Department (Belief)</span>
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
                {inspectedTake.belief.camera ? (
                  <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-2">
                    <div>Card Roll: <span className="text-white font-bold">{inspectedTake.belief.camera?.camera_roll || '--'}</span></div>
                    <div>Clip: <span className="text-white font-bold">{inspectedTake.belief.camera?.clip_name || '--'}</span></div>
                    <div>FPS / ISO: <span className="text-white">{inspectedTake.belief.camera?.fps || 24}fps / {inspectedTake.belief.camera?.iso || 800}</span></div>
                    <div>Lens: <span className="text-white">{inspectedTake.belief.camera?.lens || 'Standard'}</span></div>
                  </div>
                ) : (
                  <div className="text-xs font-mono text-slate-500 italic">No camera log (ZoeLog / CSV) ingested for this slate yet.</div>
                )}
              </div>

              {/* 3. Sound Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400">3. Sound Department (Belief)</span>
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
                {inspectedTake.is_mos ? (
                  <div className="text-xs font-mono text-indigo-300/90 bg-indigo-950/40 p-2.5 rounded-lg border border-indigo-500/30">
                    🔇 MOS Take — Filmed without sync sound on set as directed.
                  </div>
                ) : inspectedTake.belief.sound ? (
                  <div className="text-xs font-mono text-slate-300 grid grid-cols-2 gap-2">
                    <div>Sound Roll: <span className="text-white font-bold">{inspectedTake.belief.sound?.sound_roll || '--'}</span></div>
                    <div>Timecode In: <span className="text-white">{inspectedTake.belief.sound?.timecode_in || '--'}</span></div>
                    <div>Tracks: <span className="text-white">{inspectedTake.belief.sound?.tracks || 'Poly WAV'}</span></div>
                    <div>Wild Track: <span className="text-white">{inspectedTake.belief.sound?.is_wild_track ? 'YES' : 'NO'}</span></div>
                  </div>
                ) : (
                  <div className="text-xs font-mono text-slate-500 italic">No sound report (Sound ALE / CSV) ingested for this slate yet.</div>
                )}
              </div>

              {/* 4. DIT Physical Existence */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-cyan-400">4. DIT / Pomfort Silverstack Notary (Existence)</span>
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
        <div className="fixed inset-0 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 lg:p-6 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-5xl w-full h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-purple-600/20 text-purple-400 border border-purple-500/30">
                  <FileCode className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm flex items-center gap-2">
                    {previewDoc.filename}
                    {(previewDoc.is_pdf || previewDoc.filename.toLowerCase().endsWith('.pdf')) && (
                      <span className="text-[10px] bg-red-500/20 text-red-300 border border-red-500/40 px-1.5 py-0.2 rounded font-mono font-bold">
                        PDF
                      </span>
                    )}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono mt-0.5">
                    <span>Dept: {previewDoc.department.toUpperCase()}</span>
                    <span>•</span>
                    <span>Type: {previewDoc.doc_type}</span>
                    <span>•</span>
                    <span>Size: {(previewDoc.size_bytes / 1024).toFixed(1)} KB</span>
                  </div>
                </div>
              </div>

              {/* View Switcher & Action Controls */}
              <div className="flex items-center gap-2">
                {(previewDoc.is_pdf || previewDoc.filename.toLowerCase().endsWith('.pdf')) && (
                  <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
                    <button
                      onClick={() => setPreviewViewMode('visual')}
                      className={`px-3 py-1 rounded-md font-medium transition ${
                        previewViewMode === 'visual'
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      📄 Visual PDF
                    </button>
                    <button
                      onClick={() => setPreviewViewMode('text')}
                      className={`px-3 py-1 rounded-md font-medium transition ${
                        previewViewMode === 'text'
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      🔤 Parsed Text
                    </button>
                  </div>
                )}

                <a
                  href={`/api/documents/${previewDoc.doc_id}/raw`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-medium border border-slate-700 transition flex items-center gap-1.5"
                  title="Open in new tab / Download"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open Tab
                </a>

                <button 
                  onClick={() => setPreviewDoc(null)}
                  className="text-slate-400 hover:text-white text-lg p-1 ml-1"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Document Body */}
            {previewViewMode === 'visual' && (previewDoc.is_pdf || previewDoc.filename.toLowerCase().endsWith('.pdf')) ? (
              <div className="flex-1 w-full h-full bg-slate-950 flex flex-col">
                <iframe
                  src={`/api/documents/${previewDoc.doc_id}/raw#toolbar=1&navpanes=1`}
                  className="w-full flex-1 border-0 bg-slate-950"
                  title={previewDoc.filename}
                />
              </div>
            ) : (
              <div className="p-6 flex-1 overflow-y-auto font-mono text-xs bg-slate-950 text-slate-200 whitespace-pre leading-relaxed select-text">
                {previewDoc.content || '(No text content extracted)'}
              </div>
            )}

            {/* Modal Footer */}
            <div className="px-6 py-2.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-500 font-mono">
              <span>{previewDoc.checksum ? `SHA-256: ${previewDoc.checksum.slice(0, 16)}...` : 'Verified Source Paperwork'}</span>
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

      {/* INTERACTIVE DISCREPANCY RESOLUTION MODAL */}
      {resolvingDiscrepancy && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl animate-in fade-in zoom-in-95">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
                  <Check className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Solve Discrepancy</h3>
                  <p className="text-xs text-slate-400 font-mono">{resolvingDiscrepancy.entity_id}</p>
                </div>
              </div>
              <button
                onClick={() => setResolvingDiscrepancy(null)}
                className="text-slate-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            {/* Discrepancy Info */}
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/40 font-bold">
                  {resolvingDiscrepancy.discrepancy_type}
                </span>
                <span className="text-slate-400">{resolvingDiscrepancy.entity_type}</span>
              </div>
              <p className="text-slate-200 text-xs leading-relaxed">{resolvingDiscrepancy.description}</p>
            </div>

            {/* Select Target Card / Roll */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-300 block">
                Assign to Target Card / Roll:
              </label>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto p-1 bg-slate-950/60 rounded-xl border border-slate-800/80">
                {availableCards.map(card => (
                  <button
                    key={card}
                    type="button"
                    onClick={() => setResolutionCardChoice(card)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium border transition ${
                      resolutionCardChoice === card
                        ? 'bg-blue-600 border-blue-400 text-white shadow-sm font-bold'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'
                    }`}
                  >
                    {card}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setResolutionCardChoice('CUSTOM')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium border transition ${
                    resolutionCardChoice === 'CUSTOM'
                      ? 'bg-blue-600 border-blue-400 text-white font-bold'
                      : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  ✏️ Set Manually...
                </button>
              </div>

              {/* Manual Input if Custom Selected */}
              {resolutionCardChoice === 'CUSTOM' && (
                <div className="pt-1">
                  <input
                    type="text"
                    placeholder="Type custom card or roll name (e.g. Card A120 or Sound Roll 26Y07M27)..."
                    value={customCardInput}
                    onChange={e => setCustomCardInput(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 font-mono focus:outline-none focus:border-blue-500"
                    autoFocus
                  />
                </div>
              )}
            </div>

            {/* Resolution Rationale / Notes */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-300 block">
                Resolution Note & Justification:
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Confirmed with DIT: Sound was offloaded to Card 26Y07M27 during roll transition."
                value={resolutionNoteInput}
                onChange={e => setResolutionNoteInput(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setResolvingDiscrepancy(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isResolutionSubmitting || (resolutionCardChoice === 'CUSTOM' && !customCardInput.trim())}
                onClick={handleConfirmResolution}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow disabled:opacity-50"
              >
                {isResolutionSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                Confirm & Reconcile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 1. CREATE REQUIREMENT MODAL */}
      {isCreateReqOpen && targetForReq && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400">
                  <PlusCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Add Requirement</h3>
                  <p className="text-xs text-purple-300 font-mono">Attaching to: {targetForReq.target_label}</p>
                </div>
              </div>
              <button
                onClick={() => setIsCreateReqOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateRequirementSubmit} className="space-y-3.5 text-xs">
              {/* Title */}
              <div className="space-y-1">
                <label className="font-bold text-slate-300 block">Requirement Title:</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Denoise clapper bleed, VFX cleanup on boom shadow, Re-sync audio..."
                  value={newReqTitle}
                  onChange={e => setNewReqTitle(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  autoFocus
                />
              </div>

              {/* Responsible Assignee (with @ symbol) */}
              <div className="space-y-1">
                <label className="font-bold text-slate-300 flex items-center gap-1">
                  <span>Responsible Assignee:</span>
                  <span className="text-purple-400 font-mono">(receives instant alert)</span>
                </label>
                <select
                  value={newReqAssignee}
                  onChange={e => setNewReqAssignee(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500 font-mono"
                >
                  {teamUsers.map(u => (
                    <option key={u.handle} value={u.handle} className="bg-slate-900 text-white">
                      {u.handle} — {u.name} ({u.role})
                    </option>
                  ))}
                </select>
              </div>

              {/* Priority & Category Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-bold text-slate-300 block">Priority Level:</label>
                  <select
                    value={newReqPriority}
                    onChange={e => setNewReqPriority(e.target.value as RequirementPriority)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="low">Low (Editorial polish)</option>
                    <option value="medium">Medium (Standard request)</option>
                    <option value="high">High (Delivery critical)</option>
                    <option value="critical">Critical (Showstopper / Block)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-bold text-slate-300 block">Department Category:</label>
                  <select
                    value={newReqCategory}
                    onChange={e => setNewReqCategory(e.target.value as RequirementCategory)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="sound">🎙️ Sound / Audio</option>
                    <option value="vfx">✨ VFX / Cleanplate</option>
                    <option value="edit">🎬 Editorial / Cut</option>
                    <option value="color">🎨 Color / Grading</option>
                    <option value="reshoot">🔄 Reshoot / Pickup</option>
                    <option value="general">📝 General / Paperwork</option>
                  </select>
                </div>
              </div>

              {/* Description */}
              <div className="space-y-1">
                <label className="font-bold text-slate-300 block">Detailed Instructions / Description:</label>
                <textarea
                  rows={3}
                  placeholder="Provide precise instructions for the responsible artist or editor..."
                  value={newReqDesc}
                  onChange={e => setNewReqDesc(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreateReqOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingReq || !newReqTitle.trim()}
                  className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-bold transition flex items-center gap-1.5 shadow"
                >
                  {isSubmittingReq ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  Assign Requirement & Dispatch Alert
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 2. VIEW & RESOLVE REQUIREMENTS LIST MODAL */}
      {viewingReqsList && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-6 space-y-4 shadow-2xl animate-in fade-in zoom-in-95 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Requirements Hub</h3>
                  <p className="text-xs text-amber-300 font-mono">{viewingReqsList.target_label}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setViewingReqsList(null);
                  setSelectedReqForResolve(null);
                }}
                className="text-slate-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            {/* List Body */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {viewingReqsList.requirements.map(req => (
                <div
                  key={req.requirement_id}
                  className={`p-4 rounded-xl border text-xs space-y-2.5 transition ${
                    req.status === 'resolved'
                      ? 'bg-emerald-950/20 border-emerald-500/30'
                      : 'bg-slate-950 border-slate-800'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase ${
                        req.status === 'resolved'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      }`}>
                        {req.status}
                      </span>
                      <span className="font-bold text-white text-xs">{req.title}</span>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-500/30">
                      {req.priority.toUpperCase()} • {req.category.toUpperCase()}
                    </span>
                  </div>

                  {req.description && (
                    <p className="text-slate-300 text-xs leading-relaxed bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                      {req.description}
                    </p>
                  )}

                  <div className="text-[10px] text-slate-400 font-mono flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/80">
                    <span>Created by <strong className="text-purple-300">{req.created_by}</strong></span>
                    <span>Responsible: <strong className="text-blue-300">{req.assigned_to}</strong></span>
                    <span>{new Date(req.created_at).toLocaleDateString()}</span>
                  </div>

                  {/* If Resolved: Show Resolution details */}
                  {req.status === 'resolved' && (
                    <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30 space-y-1 text-xs">
                      <div className="flex items-center gap-1.5 text-emerald-300 font-bold">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Resolved by {req.resolved_by} on {req.resolved_at ? new Date(req.resolved_at).toLocaleString() : 'recently'}</span>
                      </div>
                      <p className="text-emerald-100 italic text-[11px]">
                        "{req.resolution_note || 'Resolved and verified'}"
                      </p>
                    </div>
                  )}

                  {/* If Open: Resolve Input Section */}
                  {req.status !== 'resolved' && (
                    <div className="pt-2 border-t border-slate-800 space-y-2">
                      {selectedReqForResolve?.requirement_id === req.requirement_id ? (
                        <div className="space-y-2 bg-slate-900 p-3 rounded-xl border border-purple-500/40">
                          <label className="text-[11px] font-bold text-emerald-300 block">
                            Resolution Justification / Note:
                          </label>
                          <textarea
                            rows={2}
                            placeholder="e.g. Applied EQ filter to isolate lavalier, audio verified clean for edit..."
                            value={reqResolutionNote}
                            onChange={e => setReqResolutionNote(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                            autoFocus
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setSelectedReqForResolve(null)}
                              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={isResolvingReqSubmitting || !reqResolutionNote.trim()}
                              onClick={() => handleResolveRequirementSubmit(req.requirement_id)}
                              className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg flex items-center gap-1 transition"
                            >
                              {isResolvingReqSubmitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                              Mark Resolved & Notify Caller ({req.created_by})
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-slate-500 italic">
                            Action required by {req.assigned_to}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedReqForResolve(req);
                              setReqResolutionNote('');
                            }}
                            className="px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 hover:text-white rounded-lg text-xs font-bold transition flex items-center gap-1"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Resolve Requirement...
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => {
                  setTargetForReq({
                    target_type: viewingReqsList.target_type,
                    target_id: viewingReqsList.target_id,
                    target_label: viewingReqsList.target_label,
                  });
                  setNewReqTitle('');
                  setNewReqDesc('');
                  setViewingReqsList(null);
                  setIsCreateReqOpen(true);
                }}
                className="px-3.5 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                + Add Another Requirement
              </button>
              <button
                type="button"
                onClick={() => {
                  setViewingReqsList(null);
                  setSelectedReqForResolve(null);
                }}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Real-Time Live Sync Notification Toast */}
      {liveToast && (

        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 border border-purple-500/50 text-white px-4 py-3 rounded-2xl shadow-2xl flex items-center gap-3 animate-in fade-in slide-in-from-bottom-5">
          <div className="w-8 h-8 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400 shrink-0">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider font-mono">Live Event</span>
              <span className="text-[10px] text-slate-400 font-mono">• Auto-synced</span>
            </div>
            <p className="text-xs font-semibold text-slate-100">{liveToast.message}</p>
          </div>
          <button
            onClick={() => setLiveToast(null)}
            className="text-slate-400 hover:text-white p-1 ml-2 text-xs"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

