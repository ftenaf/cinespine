import React, { useState, useEffect, useMemo } from 'react';
import { 
  Film, AlertTriangle, CheckCircle2, Upload, 
  RefreshCw, Layers, Sparkles, 
  FileText, Clapperboard, Calendar, Search,
  HardDrive, Eye, FileCode, Check, AlertCircle, Trash2,
  Image as ImageIcon, ChevronLeft, ChevronRight, LayoutGrid,
  Maximize2, ExternalLink, Video, Mic, MapPin,
  Bell, CheckCheck, PlusCircle, ChevronDown, Send, ShieldAlert,
  Radio, ListTodo, ArrowRight
} from 'lucide-react';
import { 
  TakeRecord, Discrepancy, Production, SourceDocumentSummary, SourceDocument, SequenceRecord,
  UserProfile, Requirement, NotificationItem, RequirementPriority, RequirementCategory,
  UploadFeedback, LinedPage, ConfirmPrompt,
  EditorialTag, TagVocabulary, TagTargetType
} from './types';
import { 
  fetchTakes, fetchDiscrepancies, fetchProductions, fetchDocuments,
  fetchDocumentContent, uploadDocument, uploadFile, askAssistant, seedDemoDay, deleteDocument, ApiError,
  fetchSequences, resolveDiscrepancy, unresolveDiscrepancy,
  fetchTeamUsers, loginUser, createRequirement,
  resolveRequirement, fetchNotifications, fetchRequirements,
  updateRequirement, deleteRequirement,
  markNotificationRead, markAllNotificationsRead,
  fetchTagVocabulary, fetchTags, setTag as saveTag, clearTag as removeTag
} from './api';
import { ScriptStudio } from './components/ScriptStudio';
import { EditorialTagBar } from './components/EditorialTagBar';
import { ScriptSceneButton } from './components/ScriptContextPanel';
import { RequirementRow } from './components/RequirementsBoard';
import { identify, startAnalytics, trackView } from './analytics';
import { ProductionsHub } from './components/ProductionsHub';
import { HackathonDemo } from './components/HackathonDemo';



/**
 * One line describing what was read off a lined page.
 *
 * Returns null when nothing was read, so the caller shows the warnings instead
 * of a reassuring summary of an empty result.
 */
function describeLinedPage(page: LinedPage | null | undefined): string | null {
  if (!page || page.takes.length === 0) return null;

  const parts = [`${page.takes.length} take${page.takes.length === 1 ? '' : 's'} read`];
  if (page.scene) parts.push(`scene ${page.scene}`);
  if (page.slates.length > 0) parts.push(`slate ${page.slates.join(', ')}`);

  const circled = page.takes.filter(t => t.is_starred).map(t => t.take_id);
  if (circled.length > 0) parts.push(`circled ${circled.join(', ')}`);

  const falseStarts = page.takes.filter(t => t.is_false_start).length;
  if (falseStarts > 0) parts.push(`${falseStarts} false start${falseStarts === 1 ? '' : 's'}`);

  const rolls = Array.from(new Set(page.takes.flatMap(t => t.camera_rolls)));
  if (rolls.length > 0) parts.push(`rolls ${rolls.join(', ')}`);

  return parts.join(' • ');
}

export default function App() {
  const [productions, setProductions] = useState<Production[]>([]);
  const [selectedProductionId, setSelectedProductionId] = useState('DEMO_PRODUCTION');
  const [selectedDay, setSelectedDay] = useState('31');
  const [takes, setTakes] = useState<TakeRecord[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [documents, setDocuments] = useState<SourceDocumentSummary[]>([]);
  const [sequences, setSequences] = useState<SequenceRecord[]>([]);
  // Editorial tags are production-scoped, not day-scoped: a shot is covered
  // across whatever days it took, and where it has got to in the edit is a
  // property of the shot rather than of any one day's paperwork.
  const [tagVocabulary, setTagVocabulary] = useState<TagVocabulary | null>(null);
  const [tagsByTarget, setTagsByTarget] = useState<Record<string, EditorialTag>>({});
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

  // Requirements Hub State & Filters
  const [allRequirements, setAllRequirements] = useState<Requirement[]>([]);
  const [reqFilterStatus, setReqFilterStatus] = useState<string>('ALL');
  const [reqFilterAssignee, setReqFilterAssignee] = useState<string>('ALL');
  const [reqFilterPriority, setReqFilterPriority] = useState<string>('ALL');
  const [reqFilterCategory, setReqFilterCategory] = useState<string>('ALL');
  const [reqSearchQuery, setReqSearchQuery] = useState<string>('');

  // Top-Level Pillar Navigation: Pre-Production Studio vs Set & Editorial Spine vs Hackathon Demo
  const [currentPillar, setCurrentPillar] = useState<'studio' | 'spine' | 'productions' | 'demo'>('demo');
  // Active View & Filters for Set & Editorial Spine
  const [activeTab, setActiveTab] = useState<'master' | 'sequences' | 'scenes' | 'discrepancies' | 'documents' | 'requirements'>('master');

  // Bumped whenever a tag changes so the board reloads without a full refetch
  // of the spine behind it.
  const [tagRevision, setTagRevision] = useState(0);
  const [masterLayout, setMasterLayout] = useState<'grid' | 'slate'>('grid');
  const [focusTakeIndex, setFocusTakeIndex] = useState<number>(0);
  // The take a deep link asked for, kept until the reader expresses a new
  // intent. It stays reachable in the navigator even when their filters
  // exclude it: the jump has to land, and their search query is theirs.
  const [jumpedTakeKey, setJumpedTakeKey] = useState<string | null>(null);
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
  const [uploadFeedback, setUploadFeedback] = useState<UploadFeedback | null>(null);
  const [confirmPrompt, setConfirmPrompt] = useState<ConfirmPrompt | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

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
      const [t, d, docs, seqs, reqs, tags] = await Promise.all([
        fetchTakes(selectedProductionId, selectedDay),
        fetchDiscrepancies(selectedProductionId, selectedDay),
        fetchDocuments(selectedProductionId, selectedDay),
        fetchSequences(selectedProductionId, selectedDay),
        fetchRequirements({ production_id: selectedProductionId, shoot_day: selectedDay }),
        fetchTags(selectedProductionId),
      ]);
      setTakes(t);
      setDiscrepancies(d);
      setDocuments(docs);
      setSequences(seqs);
      setAllRequirements(reqs);
      setTagsByTarget(Object.fromEntries(tags.map(tg => [`${tg.target_type}:${tg.target_id}`, tg])));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };


  // The vocabulary is fetched rather than spelled here, so the words on a chip
  // and the words the backend will accept cannot drift apart.
  useEffect(() => {
    fetchTagVocabulary().then(setTagVocabulary).catch(e => console.error(e));
  }, []);

  const handleSaveTag = async (payload: Parameters<typeof saveTag>[0]) => {
    const saved = await saveTag(payload);
    setTagsByTarget(prev => ({ ...prev, [`${saved.target_type}:${saved.target_id}`]: saved }));
    setTagRevision(r => r + 1);
  };

  const handleClearTag = async (
    targetType: TagTargetType, targetId: string, clearedBy?: string | null,
  ) => {
    await removeTag(selectedProductionId, targetType, targetId,
                    clearedBy ?? currentUser.handle);
    setTagsByTarget(prev => {
      const next = { ...prev };
      // The server normalises the id, so drop by prefix rather than trusting
      // the spelling that came off the card.
      Object.keys(next).forEach(k => {
        if (k === `${targetType}:${targetId}`) delete next[k];
      });
      return next;
    });
    setTagRevision(r => r + 1);
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
    const finalTarget = targetForReq || (takes.length > 0 ? {
      target_type: 'take' as const,
      target_id: `${takes[0].slate}_${takes[0].take_id}`,
      target_label: `Take ${takes[0].slate} T${takes[0].take_id}`,
    } : null);

    if (!finalTarget || !newReqTitle.trim()) {
      alert('Please specify a title and select a target entity for the requirement.');
      return;
    }
    setIsSubmittingReq(true);
    try {
      await createRequirement({
        production_id: selectedProductionId,
        shoot_day: selectedDay,
        target_type: finalTarget.target_type,
        target_id: finalTarget.target_id,
        target_label: finalTarget.target_label,
        title: newReqTitle.trim(),
        description: newReqDesc.trim() || undefined,
        priority: newReqPriority,
        category: newReqCategory,
        created_by: currentUser.handle,
        assigned_to: newReqAssignee,
      });
      setIsCreateReqOpen(false);
      setNewReqTitle('');
      setNewReqDesc('');
      setTargetForReq(null);
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

  // Analytics, if a self-hosted PostHog is configured. Inert otherwise, which
  // is the normal state in development.
  useEffect(() => { startAnalytics(); }, []);
  useEffect(() => { identify(currentUser.handle); }, [currentUser.handle]);

  // Which surface someone is working in. Named rather than a URL: the pillars
  // are the app's own vocabulary, and a URL would carry the production id.
  useEffect(() => {
    trackView(currentPillar === 'spine' ? `spine:${activeTab}` : currentPillar, {
      layout: currentPillar === 'spine' ? masterLayout : null,
    });
  }, [currentPillar, activeTab, masterLayout]);

  /** How a take is named when one list has to point at another. */
  const takeKey = (take: TakeRecord) => `${take.slate}_${take.take_id}`;

  const jumpToTarget = (targetType: string, targetId: string) => {
    // 1. Close drawers and modals
    setIsNotifDrawerOpen(false);
    setViewingReqsList(null);
    setSelectedReqForResolve(null);

    // 2. The reader's search query and scene filter are left exactly as they
    //    are. Clearing them was the crude way to guarantee the target was
    //    reachable; pinning it below does that without throwing away what
    //    somebody typed.

    // 3. Switch to Set & Editorial Spine Pillar & Master View
    setCurrentPillar('spine');
    setActiveTab('master');
    setMasterLayout('slate');

    // 4. Find the matching take in takes list
    const cleanTargetId = (targetId || '').trim();
    let matchIndex = -1;

    if (targetType === 'take') {
      // Matches "49/WT_1" or "49_1" or "27/7_1"
      matchIndex = takes.findIndex(t => {
        const fullKey = `${t.slate}_${t.take_id}`;
        if (fullKey.toUpperCase() === cleanTargetId.toUpperCase()) return true;
        if (cleanTargetId.includes('_')) {
          const parts = cleanTargetId.split('_');
          const pSlate = parts[0];
          const pTake = parts[1];
          const slateMatch = t.slate.toUpperCase() === pSlate.toUpperCase() || 
                             t.slate.replace('/', '').toUpperCase() === pSlate.replace('/', '').toUpperCase();
          const takeMatch = t.take_id === pTake || parseInt(t.take_id) === parseInt(pTake);
          return slateMatch && takeMatch;
        }
        return t.take_id === cleanTargetId || t.slate.toUpperCase() === cleanTargetId.toUpperCase();
      });
    } else if (targetType === 'shot') {
      // Matches "49/WT" or "49WT" or "27/7"
      matchIndex = takes.findIndex(t => {
        if (t.slate.toUpperCase() === cleanTargetId.toUpperCase()) return true;
        if (t.slate.replace('/', '').toUpperCase() === cleanTargetId.replace('/', '').toUpperCase()) return true;
        return t.slate.toLowerCase().includes(cleanTargetId.toLowerCase());
      });
    } else if (targetType === 'scene') {
      // Matches "49" or "49WT" or "27"
      matchIndex = takes.findIndex(t => {
        if (!t.scene) return false;
        if (t.scene.toUpperCase() === cleanTargetId.toUpperCase()) return true;
        const sNum = t.scene.replace(/\D/g, '');
        const targetNum = cleanTargetId.replace(/\D/g, '');
        return Boolean(sNum && targetNum && sNum === targetNum);
      });
    } else {
      // Fallback search across slate/scene/take
      matchIndex = takes.findIndex(t => 
        t.slate.toLowerCase().includes(cleanTargetId.toLowerCase()) || 
        (t.scene && t.scene.toLowerCase().includes(cleanTargetId.toLowerCase())) || 
        t.take_id === cleanTargetId
      );
    }

    if (matchIndex !== -1) {
      // Pinned by identity, not by index. matchIndex is a position in `takes`
      // and the navigator reads `filteredTakes`, so setting it directly landed
      // on whatever happened to sit at that position once anything was
      // filtered -- which only looked correct because the filters had just
      // been cleared. The effect below positions on the take itself.
      setJumpedTakeKey(takeKey(takes[matchIndex]));
      setInspectedTake(takes[matchIndex]);
    } else {
      console.warn(`Target not found in current takes list: type=${targetType}, id=${targetId}`);
    }
  };

  const handleNotificationClick = async (notif: NotificationItem) => {
    // 1. Mark read
    if (!notif.is_read) {
      await markNotificationRead(notif.notification_id);
      await loadUsersAndNotifications(currentUser.handle);
    }
    // 2. Direct jump into Slate Navigator for this scene/shot/take
    jumpToTarget(notif.target_type, notif.target_id);
  };

  const handleDeleteRequirement = (reqId: string, reqTitle: string) => {
    setConfirmPrompt({
      title: 'Delete requirement',
      message: `Delete requirement "${reqTitle}"?`,
      confirmLabel: 'Delete',
      destructive: true,
      onConfirm: async () => {
        await deleteRequirement(reqId);
        await loadSpineData();
        await loadUsersAndNotifications(currentUser.handle);
      },
    });
  };

  const handleUpdateRequirementStatus = async (reqId: string, newStatus: string) => {
    try {
      await updateRequirement(reqId, { status: newStatus as any });
      await loadSpineData();
      await loadUsersAndNotifications(currentUser.handle);
    } catch (err: any) {
      alert(`Failed to update requirement status: ${err.message}`);
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

          // The board is not part of the spine reload, so a tag changed by
          // another editor would leave an open board showing yesterday's
          // numbers until it was reopened.
          if (String(liveEvent.event_type).startsWith('EDITORIAL_TAG_')) {
            setTagRevision(r => r + 1);
          }
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
      // The server says why when it refuses: source documents are not served
      // by default because they carry crew contact details and unreleased
      // material. Showing that beats a generic failure.
      alert(e?.detail ?? e?.message ?? 'Could not load document preview');
    }
  };

  const handleDeleteDocument = (docId: string, filename: string) => {
    setConfirmPrompt({
      title: 'Remove document',
      message: `Remove '${filename}'? Its ingested records are purged from the spine.`,
      confirmLabel: 'Remove',
      destructive: true,
      // Throws on failure rather than swallowing: the dialog stays open and
      // shows why. Reporting it into the upload panel would have hidden it,
      // since that panel is closed while a document is being deleted.
      onConfirm: async () => {
        setLoading(true);
        try {
          await deleteDocument(docId);
          await loadProductions();
          await loadSpineData();
        } finally {
          setLoading(false);
        }
      },
    });
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
        const warnings = res.lining_warnings || [];
        setUploadFeedback({
          // A page that was ingested but not read is not a clean success. Saying
          // so here is the whole point: an unread page and a page with nothing
          // on it look identical in the spine otherwise.
          tone: warnings.length > 0 ? 'warning' : 'success',
          message: `Ingested ${res.filename} to ${res.production_id} (Day ${res.shoot_day}) [${res.detected_department.toUpperCase()}]`,
          detail: describeLinedPage(res.lined_page),
          warnings,
        });
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      } else if (uploadMode === 'text' && uploadContent.trim()) {
        const res = await uploadDocument({
          raw_content: uploadContent,
          filename: uploadFilename || 'manual_drop.txt',
        });
        setUploadFeedback({
          tone: 'success',
          message: `Ingested to ${res.production_id} (Day ${res.shoot_day}) [${res.detected_department.toUpperCase()}]`,
        });
        if (res.production_id) setSelectedProductionId(res.production_id);
        if (res.shoot_day) setSelectedDay(res.shoot_day);
      }
      setSelectedFile(null);
      setUploadContent('');
      setUploadFilename('');
      await loadProductions();
      await loadSpineData();
    } catch (err: any) {
      // The backend answers 409 with the name it is already filed under. That
      // detail is the useful part, and it used to be discarded: uploadFile threw
      // a bare "File upload failed", so a deliberate refusal read as a crash.
      if (err instanceof ApiError && err.isDuplicate) {
        setUploadFeedback({ tone: 'warning', message: err.detail });
      } else {
        setUploadFeedback({ tone: 'error', message: `Upload failed: ${err.message}` });
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

  const activeDiscrepancies = useMemo(() => discrepancies.filter(d => !d.is_resolved), [discrepancies]);
  const resolvedDiscrepancies = useMemo(() => discrepancies.filter(d => d.is_resolved), [discrepancies]);

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

  // Requirements Hub Filtering & Metrics
  const filteredRequirements = useMemo(() => {
    return allRequirements.filter(req => {
      // 1. Status Filter
      if (reqFilterStatus !== 'ALL') {
        if (req.status !== reqFilterStatus) return false;
      }
      // 2. Assignee Filter
      if (reqFilterAssignee !== 'ALL') {
        if (reqFilterAssignee === '@me') {
          if (req.assigned_to?.toLowerCase() !== currentUser.handle.toLowerCase()) return false;
        } else if (req.assigned_to?.toLowerCase() !== reqFilterAssignee.toLowerCase()) {
          return false;
        }
      }
      // 3. Priority Filter
      if (reqFilterPriority !== 'ALL') {
        if (req.priority !== reqFilterPriority) return false;
      }
      // 4. Category Filter
      if (reqFilterCategory !== 'ALL') {
        if (req.category !== reqFilterCategory) return false;
      }
      // 5. Text Search
      if (reqSearchQuery.trim()) {
        const q = reqSearchQuery.toLowerCase();
        const matchesTitle = req.title.toLowerCase().includes(q);
        const matchesDesc = req.description?.toLowerCase().includes(q);
        const matchesTarget = req.target_label?.toLowerCase().includes(q) || req.target_id?.toLowerCase().includes(q);
        const matchesCreator = req.created_by?.toLowerCase().includes(q);
        const matchesAssignee = req.assigned_to?.toLowerCase().includes(q);
        if (!matchesTitle && !matchesDesc && !matchesTarget && !matchesCreator && !matchesAssignee) {
          return false;
        }
      }
      return true;
    });
  }, [allRequirements, reqFilterStatus, reqFilterAssignee, reqFilterPriority, reqFilterCategory, reqSearchQuery, currentUser.handle]);

  const reqMetrics = useMemo(() => {
    const total = allRequirements.length;
    const open = allRequirements.filter(r => r.status === 'open' || r.status === 'in_progress').length;
    const assignedToMe = allRequirements.filter(r => r.assigned_to?.toLowerCase() === currentUser.handle.toLowerCase() && r.status !== 'resolved').length;
    const criticalOrHigh = allRequirements.filter(r => (r.priority === 'critical' || r.priority === 'high') && r.status !== 'resolved').length;
    const resolved = allRequirements.filter(r => r.status === 'resolved').length;
    return { total, open, assignedToMe, criticalOrHigh, resolved };
  }, [allRequirements, currentUser.handle]);

  /**
   * The take a deep link pinned, when the reader's own filters exclude it.
   *
   * Shown rather than silently dropped: a jump that lands on nothing is worse
   * than the cleared search box it replaced. Named separately so the navigator
   * can say why this one is here.
   */
  const pinnedOutsideFilter = useMemo(() => {
    if (!jumpedTakeKey) return null;
    if (filteredTakes.some(t => takeKey(t) === jumpedTakeKey)) return null;
    return takes.find(t => takeKey(t) === jumpedTakeKey) ?? null;
  }, [jumpedTakeKey, filteredTakes, takes]);

  const navigableTakes = useMemo(
    () => (pinnedOutsideFilter ? [pinnedOutsideFilter, ...filteredTakes] : filteredTakes),
    [pinnedOutsideFilter, filteredTakes],
  );

  // Position on the pinned take once the list it lives in has settled. Doing
  // this in an effect rather than in the jump is what lets the target be found
  // in the filtered list instead of guessed at by index.
  useEffect(() => {
    if (!jumpedTakeKey) return;
    const index = navigableTakes.findIndex(t => takeKey(t) === jumpedTakeKey);
    if (index >= 0) setFocusTakeIndex(index);
  }, [jumpedTakeKey, navigableTakes]);

  const currentFocusTake = navigableTakes[focusTakeIndex] || navigableTakes[0] || null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">

      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-6 py-3 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-tr bg-spine-800 to-blue-600 p-2 rounded-xl border border-spine-accent/30 text-white shadow-lg shadow-purple-500/20">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
                CineSpine
                <span className="text-[10px] bg-spine-accent/20 border border-spine-accent/40 text-spine-accent font-mono px-1.5 py-0.2 rounded font-bold">v0.2</span>
              </h1>
              <p className="text-[10px] text-gray-300">
                {currentPillar === 'studio'
                  ? 'AI Screenplay Breakdown, Cast Profiler & Tri-Modal DoP Previz'
                  : currentPillar === 'demo'
                    ? 'Google Cloud Partner Showcase Demo'
                  : currentPillar === 'productions'
                    ? 'Production Registry & Progress'
                    : `${activeProduction.name} — Assistant Editor Card & Discrepancy Hub`}
              </p>
            </div>
          </div>
        </div>

        {/* Center: Top-Level Pillar Navigation Switcher (Hero Toggle) */}
        <div className="flex items-center bg-slate-950 p-1 rounded-2xl border border-slate-800 shadow-inner">
          <button
            onClick={() => setCurrentPillar('studio')}
            className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold transition shadow-sm ${
              currentPillar === 'studio'
                ? 'bg-gradient-to-r bg-spine-800 via-indigo-600 to-pink-600 text-white shadow-lg shadow-purple-600/30'
                : 'text-gray-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            <Sparkles className="w-4 h-4 text-spine-warning" />
            🎬 Screenplay &amp; Previz Studio
          </button>

          <button
            onClick={() => setCurrentPillar('spine')}
            className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold transition shadow-sm ${
              currentPillar === 'spine'
                ? 'bg-spine-accent text-white shadow-lg shadow-blue-600/30'
                : 'text-gray-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            <Clapperboard className="w-4 h-4 text-white" />
            🎞️ Set &amp; Editorial Spine
          </button>

          <button
            onClick={() => setCurrentPillar('productions')}
            className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold transition shadow-sm ${
              currentPillar === 'productions'
                ? 'bg-spine-accent text-white shadow-lg shadow-blue-600/30'
                : 'text-gray-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            Productions
          </button>
          
          <button
            onClick={() => setCurrentPillar('demo')}
            className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold transition shadow-sm ${
              currentPillar === 'demo'
                ? 'bg-gradient-to-r from-orange-500 to-red-500 text-white shadow-lg shadow-orange-500/30'
                : 'text-gray-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            Hackathon Demo
          </button>
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
            <span className={liveSyncStatus === 'connected' ? 'text-spine-success font-semibold' : 'text-gray-300'}>
              {liveSyncStatus === 'connected' ? 'Live Sync' : liveSyncStatus === 'connecting' ? 'Connecting...' : 'Offline'}
            </span>
          </div>

          {/* Notifications Bell */}
          <div className="relative">
            <button
              onClick={() => setIsNotifDrawerOpen(!isNotifDrawerOpen)}
              className="relative p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-gray-200 hover:text-white transition flex items-center justify-center"
              title="Alert Notifications"
            >
              <Bell className="w-4 h-4" />
              {unreadNotifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-spine-critical text-white text-[10px] font-black w-4 h-4 rounded-full flex items-center justify-center animate-pulse shadow-md">
                  {unreadNotifCount}
                </span>
              )}
            </button>

            {/* Notifications Dropdown Drawer */}
            {isNotifDrawerOpen && (
              <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-4 z-50 space-y-3 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                  <div className="flex items-center gap-2">
                    <Bell className="w-4 h-4 text-spine-accent" />
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
                    <p className="text-xs text-gray-400 text-center py-6">
                      No notifications or alerts.
                    </p>
                  ) : (
                    notifications.map(n => (
                      <div
                        key={n.notification_id}
                        onClick={() => handleNotificationClick(n)}
                        className={`p-3 rounded-xl border text-xs cursor-pointer transition ${
                          n.is_read
                            ? 'bg-slate-950/40 border-slate-800 text-gray-300 hover:bg-slate-800/40'
                            : 'bg-spine-900/30 border-spine-accent/40 text-gray-100 hover:bg-spine-900/40'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded font-mono ${
                            n.notification_type === 'RESOLVED' 
                              ? 'bg-spine-success/20 text-spine-success border border-spine-success/30' 
                              : 'bg-spine-accent/20 text-spine-accent border border-spine-accent/30'
                          }`}>
                            {n.notification_type}
                          </span>
                          <span className="text-[10px] text-gray-400 font-mono">
                            {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <h4 className="font-bold text-white text-xs leading-snug">{n.title}</h4>
                        <p className="text-[11px] text-gray-200 mt-1 leading-relaxed">{n.message}</p>
                        <div className="mt-2 flex items-center justify-between text-[10px] text-spine-accent font-medium">
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
                <p className="text-[10px] text-spine-accent font-mono leading-tight">{currentUser.handle}</p>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-gray-300" />
            </button>

            {/* User Switcher Dropdown */}
            {isUserMenuOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-3.5 z-50 space-y-3 animate-in fade-in zoom-in-95">
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-300 mb-1.5">
                    Switch Active User (Passwordless)
                  </h4>
                  <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
                    {teamUsers.map(u => (
                      <button
                        key={u.handle}
                        onClick={() => handleSwitchUser(u)}
                        className={`w-full flex items-center gap-2.5 p-2 rounded-xl text-left transition ${
                          currentUser.handle === u.handle
                            ? 'bg-spine-accent/30 border border-spine-accent/50 text-white'
                            : 'hover:bg-slate-800 text-gray-200 hover:text-white'
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
                          <p className="text-[10px] text-gray-300 font-mono truncate">{u.handle} • {u.role}</p>
                        </div>
                        {currentUser.handle === u.handle && (
                          <Check className="w-3.5 h-3.5 text-spine-accent shrink-0" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Custom Handle / Passwordless Login Input */}
                <form onSubmit={handleCustomLogin} className="pt-2 border-t border-slate-800 space-y-1.5">
                  <label className="text-[10px] font-medium text-gray-300 block">
                    Or Login with @handle / email:
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      placeholder="@editor_lead"
                      value={customLoginHandle}
                      onChange={e => setCustomLoginHandle(e.target.value)}
                      className="flex-1 bg-slate-950 border border-slate-700 text-xs px-2.5 py-1 rounded-lg text-white font-mono focus:outline-none focus:border-spine-accent"
                    />
                    <button
                      type="submit"
                      className="px-2.5 py-1 bg-spine-accent hover:bg-spine-accent text-white text-xs font-semibold rounded-lg transition"
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

      {/* ===================================================================== */}
      {/* PILLAR 1: SCREENPLAY & PREVIZ STUDIO (CLEAN, DISTRACTION-FREE WORKSPACE) */}
      {/* ===================================================================== */}
      {currentPillar === 'studio' && (
        <main className="flex-1 w-full h-[calc(100vh-65px)] overflow-hidden bg-[#090D16]">
          <ScriptStudio />
        </main>
      )}

      {/* ===================================================================== */}
      {/* PILLAR 3: PRODUCTIONS (REGISTRY & PROGRESS)                            */}
      {/* ===================================================================== */}
      {currentPillar === 'productions' && (
        <main className="flex-1 max-w-7xl w-full mx-auto p-6">
          <ProductionsHub
            productions={productions}
            selectedProductionId={selectedProductionId}
            onSelect={setSelectedProductionId}
            onOpen={productionId => {
              setSelectedProductionId(productionId);
              setCurrentPillar('spine');
            }}
            onChanged={loadProductions}
            tagRevision={tagRevision}
            team={teamUsers}
            currentUserHandle={currentUser.handle}
          />
        </main>
      )}

      {/* ===================================================================== */}
      {/* PILLAR 4: HACKATHON DEMO                                              */}
      {/* ===================================================================== */}
      {currentPillar === 'demo' && (
        <main className="flex-1 w-full h-[calc(100vh-65px)] overflow-y-auto bg-[#090D16]">
          <HackathonDemo />
        </main>
      )}

      {/* ===================================================================== */}
      {/* PILLAR 2: SET & EDITORIAL SPINE (DIT / POST ASSISTANT EDITOR HUB)      */}
      {/* ===================================================================== */}
      {currentPillar === 'spine' && (
        <main className={`flex-1 ${activeTab === 'sequences' ? 'w-full max-w-[100%] px-3 sm:px-5 lg:px-6 py-4' : 'max-w-7xl w-full mx-auto p-6'} space-y-5 transition-all duration-150`}>
          {/* Spine Toolbar: Production, Shoot Day & Ingest Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/60 p-3.5 rounded-2xl border border-slate-800">
            <div className="flex items-center gap-3">
              {/* Production Selector */}
              <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-xl p-1 px-3">
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
              <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-xl p-1 px-2.5">
                <Calendar className="w-3.5 h-3.5 text-gray-300 mr-1" />
                <span className="text-xs text-gray-300 font-semibold">Day:</span>
                {['31', '39'].map(day => (
                  <button
                    key={day}
                    onClick={() => setSelectedDay(day)}
                    className={`px-2 py-0.5 rounded-lg text-xs font-mono font-medium transition ${
                      selectedDay === day 
                        ? 'bg-spine-accent text-white shadow-sm' 
                        : 'text-gray-300 hover:text-white hover:bg-slate-800'
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
                  className="w-12 bg-slate-900 border border-slate-700 text-xs px-1.5 py-0.5 rounded text-white font-mono text-center focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button 
                onClick={loadSpineData}
                className="p-2 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-gray-200 hover:text-white transition"
                title="Refresh Spine"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>

              <button 
                onClick={() => handleSeedDemoDay(selectedDay)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-spine-success/20 hover:bg-spine-success/30 border border-spine-success/40 text-spine-success text-xs font-medium transition"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Seed Day {selectedDay}
              </button>

              <button 
                onClick={() => { setIsUploadOpen(true); setUploadFeedback(null); }}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-spine-accent hover:brightness-110 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition"
              >
                <Upload className="w-3.5 h-3.5" />
                Drop Paperwork
              </button>
            </div>
          </div>

          {/* Spine Sub-Navigation Tabs & Search Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setActiveTab('master')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'master'
                    ? 'bg-spine-accent text-white shadow-lg shadow-blue-600/30'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                <LayoutGrid className="w-4 h-4" />
                Composed Master Sheet ({takes.length})
              </button>

              <button
                onClick={() => setActiveTab('sequences')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'sequences'
                    ? 'bg-spine-accent text-white shadow-lg shadow-blue-600/30'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                <Film className="w-4 h-4 text-cyan-400" />
                Sequences Log Matrix ({sequences.length})
              </button>

              <button
                onClick={() => setActiveTab('scenes')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'scenes'
                    ? 'bg-spine-accent/20 text-white border border-blue-500/40'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                <Layers className="w-4 h-4" />
                Card &amp; Roll Map
              </button>

              <button
                onClick={() => setActiveTab('discrepancies')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'discrepancies'
                    ? activeDiscrepancies.length > 0
                      ? 'bg-spine-critical/20 text-spine-critical border border-spine-critical/40'
                      : 'bg-spine-success/20 text-spine-success border border-spine-success/40'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                {activeDiscrepancies.length > 0 ? (
                  <AlertTriangle className="w-4 h-4 text-spine-critical" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-spine-success" />
                )}
                Active Discrepancies ({activeDiscrepancies.length})
                {resolvedDiscrepancies.length > 0 && (
                  <span className="bg-spine-success/30 text-spine-success text-[10px] font-bold px-1.5 py-0.5 rounded-full border border-spine-success/40">
                    {resolvedDiscrepancies.length} resolved
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab('documents')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'documents'
                    ? 'bg-spine-accent/20 text-spine-accent border border-spine-accent/40'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                <FileCode className="w-4 h-4" />
                Source Documents ({documents.length})
              </button>

              <button
                onClick={() => setActiveTab('requirements')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  activeTab === 'requirements'
                    ? 'bg-spine-accent text-white shadow-lg shadow-purple-600/30'
                    : 'text-gray-300 hover:text-white hover:bg-slate-900 border border-transparent'
                }`}
              >
                <ListTodo className="w-4 h-4 text-spine-accent" />
                Requirements &amp; Alerts ({allRequirements.length})
                {reqMetrics.open > 0 && (
                  <span className="bg-spine-accent/30 text-spine-accent text-[10px] font-bold px-1.5 py-0.5 rounded-full border border-spine-accent/40">
                    {reqMetrics.open} open
                  </span>
                )}
                {/* Your own share of it, called out separately. Whether the
                    production owes forty things matters less to the person
                    reading than whether any of them are theirs. */}
                {reqMetrics.assignedToMe > 0 && (
                  <span
                    className="bg-cyan-500/20 text-cyan-200 text-[10px] font-bold px-1.5 py-0.5 rounded-full border border-cyan-500/40"
                    title={`${reqMetrics.assignedToMe} assigned to ${currentUser.handle}`}
                  >
                    {reqMetrics.assignedToMe} yours
                  </span>
                )}
              </button>

            </div>

            {/* Set & Editorial Quick Search & Filters */}
            <div className="flex items-center gap-2.5">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-300" />
                <input
                  type="text"
                  placeholder="Search scene, slate, card (A120), clip..."
                  value={searchQuery}
                  onChange={e => {
                    setSearchQuery(e.target.value);
                    // A new query is a new intent, so the deep link stops
                    // pinning its take above the results.
                    setJumpedTakeKey(null);
                  }}
                  className="bg-slate-900 border border-slate-700 text-xs pl-8 pr-3 py-1.5 rounded-lg text-white font-mono w-64 focus:outline-none focus:border-blue-500"
                />
              </div>

              <button
                onClick={() => setFilterCircledOnly(!filterCircledOnly)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                  filterCircledOnly 
                    ? 'bg-spine-warning/20 border-spine-warning/50 text-spine-warning' 
                    : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white'
                }`}
              >
                ⭐ Circled
              </button>

              <button
                onClick={() => setFilterWildTracksOnly(!filterWildTracksOnly)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                  filterWildTracksOnly 
                    ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300' 
                    : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white'
                }`}
              >
                🎙️ WT
              </button>

              <button
                onClick={() => setFilterVfxOnly(!filterVfxOnly)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                  filterVfxOnly 
                    ? 'bg-spine-accent/20 border-spine-accent/50 text-spine-accent' 
                    : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white'
                }`}
              >
                ✨ VFX
              </button>

              <button
                onClick={() => setFilterDiscrepancyOnly(!filterDiscrepancyOnly)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1 ${
                  filterDiscrepancyOnly 
                    ? 'bg-spine-critical/20 border-spine-critical/50 text-spine-critical' 
                    : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white'
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
                <span className="text-xs text-gray-300 font-semibold mr-1">Scene:</span>
                <button
                  onClick={() => setSelectedSceneFilter('ALL')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition ${
                    selectedSceneFilter === 'ALL'
                      ? 'bg-spine-accent text-white'
                      : 'bg-slate-950 text-gray-300 hover:text-white border border-slate-800'
                  }`}
                >
                  All ({takes.length})
                </button>
                {uniqueScenes.map(sc => {
                  const sceneTag = tagsByTarget[`scene:${sc}`];
                  return (
                    <button
                      key={sc}
                      onClick={() => setSelectedSceneFilter(sc)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition flex items-center gap-1.5 ${
                        selectedSceneFilter === sc
                          ? 'bg-spine-accent text-white'
                          : 'bg-slate-950 text-gray-300 hover:text-white border border-slate-800'
                      }`}
                      title={sceneTag ? 'This scene is tagged — select it to see or change the tag' : undefined}
                    >
                      Sc {sc}
                      {/* A dot rather than the labels themselves: the row is for
                          choosing a scene, and spelling every tag out here would
                          bury that. Selecting the scene shows the tag in full. */}
                      {sceneTag && (
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            sceneTag.needs.length ? 'bg-rose-400' : 'bg-emerald-400'
                          }`}
                        />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* The tag on the scene itself, not on any shot within it. Shown
                  only once a scene is chosen, since there is no one scene to
                  tag while the filter is on All. */}
              {selectedSceneFilter !== 'ALL' && (
                <div className="w-full flex items-center gap-2 pt-2 border-t border-slate-800">
                  <span className="text-xs text-gray-300 font-semibold shrink-0">
                    Scene {selectedSceneFilter}:
                  </span>
                  <EditorialTagBar
                    productionId={selectedProductionId}
                    targetType="scene"
                    targetId={selectedSceneFilter}
                    tag={tagsByTarget[`scene:${selectedSceneFilter}`]}
                    vocabulary={tagVocabulary}
                    currentUserHandle={currentUser.handle}
                    onSave={handleSaveTag}
                    onClear={handleClearTag}
                  />
                  {/* What the scene is about, read from the screenplay. The
                      paperwork on this page says how it was shot and never
                      what it is. */}
                  <ScriptSceneButton
                    productionId={selectedProductionId}
                    targetType="scene"
                    targetId={selectedSceneFilter}
                  />
                </div>
              )}

              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <button
                  onClick={() => setMasterLayout('grid')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                    masterLayout === 'grid'
                      ? 'bg-spine-accent text-white shadow-sm'
                      : 'text-gray-300 hover:text-white'
                  }`}
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                  Gallery Grid
                </button>
                <button
                  onClick={() => setMasterLayout('slate')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                    masterLayout === 'slate'
                      ? 'bg-spine-accent text-white shadow-sm'
                      : 'text-gray-300 hover:text-white'
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
                  <div className="col-span-full bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center text-gray-400">
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
                          hasDiscrepancy ? 'border-spine-critical/40' : 'border-slate-800 hover:border-blue-500/50'
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
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-gray-300 p-4 text-center">
                              <div className="p-2.5 rounded-xl bg-spine-warning/10 border border-spine-warning/30 text-spine-warning mb-1.5 shadow-sm">
                                <Film className="w-5 h-5" />
                              </div>
                              <span className="text-xs font-mono text-spine-warning font-bold">
                                {t.belief.script ? "Script Supervisor Slate Entry" : t.is_wild_track ? "Audio Wild Track" : "Awaiting Camera Offload"}
                              </span>
                              <div className="flex flex-wrap items-center justify-center gap-1.5 mt-1 font-mono text-[10px]">
                                {t.camera_cards.length > 0 && (
                                  <span className="bg-blue-950/70 border border-blue-500/40 text-white px-2 py-0.5 rounded">
                                    🎴 {t.camera_cards.join(', ')}
                                  </span>
                                )}
                                {t.belief.script?.timecode_in && (
                                  <span className="bg-slate-900 border border-slate-800 text-gray-300 px-2 py-0.5 rounded">
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
                                  className="mt-1.5 text-[10px] font-mono text-spine-accent hover:text-spine-accent underline flex items-center gap-1"
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
                              <span className="bg-spine-warning/90 text-black font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
                                ⭐ Circled
                              </span>
                            )}
                            {t.is_wild_track && (
                              <span className="bg-cyan-500/90 text-black font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
                                🎙️ WT
                              </span>
                            )}
                            {t.is_vfx && (
                              <span className="bg-spine-accent/90 text-white font-bold text-[10px] px-2 py-0.5 rounded-md shadow">
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
                                        ? 'bg-spine-accent text-white shadow'
                                        : 'text-gray-300 hover:text-white hover:bg-white/10'
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
                              className="absolute bottom-2.5 right-2.5 bg-black/70 hover:bg-spine-accent text-white p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition shadow z-10"
                              title="Enlarge Frame"
                            >
                              <Maximize2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>

                        {/* Composed Multi-Department Data Body */}
                        <div className="p-4 flex-1 space-y-3">
                          {/* Editorial status. It hangs on the shot, not on this
                              take: every take of a slate is coverage of the same
                              shot, so they all show the one tag. */}
                          <div className="flex items-center gap-2 flex-wrap">
                            <EditorialTagBar
                              productionId={selectedProductionId}
                              targetType="shot"
                              targetId={t.slate}
                              tag={tagsByTarget[`shot:${t.slate}`]}
                              vocabulary={tagVocabulary}
                              currentUserHandle={currentUser.handle}
                              onSave={handleSaveTag}
                              onClear={handleClearTag}
                            />
                            <ScriptSceneButton
                              productionId={selectedProductionId}
                              targetType="shot"
                              targetId={t.slate}
                            />
                          </div>

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
                                <span className="font-mono text-spine-success font-semibold flex items-center gap-1">
                                  🎙️ {t.audio_files.length} Audio File{t.audio_files.length > 1 ? 's' : ''}
                                </span>
                              ) : (
                                <span className="font-mono text-gray-400 flex items-center gap-1">
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
                                    className="text-[10px] text-spine-accent hover:underline font-mono"
                                  >
                                    ZoeLog
                                  </button>
                                )}
                              </div>

                              <div className="space-y-1">
                                {t.video_files.map((vf, vi) => (
                                  <div key={vi} className="bg-slate-900/70 p-1.5 rounded-lg border border-slate-800 text-[11px] font-mono flex items-center justify-between">
                                    <div className="flex items-center gap-1.5 overflow-hidden">
                                      <span className="bg-spine-accent/30 text-white font-bold px-1.5 py-0.2 rounded text-[10px]">
                                        Cam {vf.camera}
                                      </span>
                                      <span className="text-gray-200 truncate max-w-[160px]" title={vf.file_name}>
                                        {vf.file_name}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-1 text-[10px] text-gray-300 shrink-0">
                                      <span className="text-gray-200 font-semibold">{vf.camera_roll}</span>
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
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-spine-success/20 space-y-1.5">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-spine-success flex items-center gap-1">
                                  🎙️ Audio Sound Files ({t.audio_files.length})
                                </span>
                                {t.belief.sound?.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.sound?.source_doc_id, t.belief.sound?.source_document)}
                                    className="text-[10px] text-spine-accent hover:underline font-mono"
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
                                        <span className="bg-spine-success/30 text-spine-success font-bold px-1.5 py-0.2 rounded text-[10px]">
                                          WAV
                                        </span>
                                        <span className="text-spine-success font-semibold truncate max-w-[150px]" title={af.file_name}>
                                          {af.file_name}
                                        </span>
                                      </div>
                                      <span className="text-[10px] text-gray-300 font-mono">{af.duration || '00:03:00'}</span>
                                    </div>

                                    {/* Multi-Track Channel Badges */}
                                    {af.tracks && (
                                      <div className="flex flex-wrap gap-1 pt-0.5">
                                        {af.tracks.split(',').map((trk, ti) => (
                                          <span key={ti} className="bg-slate-950 border border-slate-800 text-[9px] font-mono text-gray-200 px-1.5 py-0.2 rounded">
                                            {trk.trim()}
                                          </span>
                                        ))}
                                      </div>
                                    )}

                                    {af.note && (
                                      <div className="text-[10px] text-spine-warning/90 italic font-mono bg-spine-warning/20 px-1.5 py-0.5 rounded border border-spine-warning/20">
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
                            <div className="bg-slate-950 p-2.5 rounded-xl border border-spine-warning/20 text-[11px] space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-spine-warning flex items-center gap-1 text-[11px]">
                                  📝 Script Supervisor (Scripte)
                                </span>
                                {t.belief.script.source_document && (
                                  <button
                                    onClick={() => handleOpenPreviewDoc(t.belief.script?.source_doc_id, t.belief.script?.source_document)}
                                    className="text-[10px] text-spine-accent hover:underline font-mono"
                                  >
                                    Preview Log
                                  </button>
                                )}
                              </div>
                              <p className="text-[11px] text-gray-200 italic line-clamp-2">
                                {t.belief.script.note || 'Scripte Log Recorded'}
                              </p>
                              {t.belief.script.timecode_in && (
                                <div className="text-[10px] font-mono text-gray-300">
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
                                  className="px-2 py-0.5 rounded-md bg-spine-warning/20 hover:bg-spine-warning/30 border border-spine-warning/40 text-spine-warning text-[10px] font-bold flex items-center gap-1 transition"
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
                                  className="px-2 py-0.5 rounded-md bg-spine-success/20 hover:bg-spine-success/30 border border-spine-success/40 text-spine-success text-[10px] font-semibold flex items-center gap-1 transition"
                                >
                                  <CheckCircle2 className="w-3 h-3" />
                                  {t.resolved_requirements_count} Resolved
                                </button>
                              ) : null}
                            </div>
                            <span className="text-[10px] text-gray-400 font-mono">
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
                            className="flex-1 py-1.5 bg-spine-accent/20 hover:bg-spine-accent/30 text-white hover:text-white rounded-lg text-xs font-semibold border border-blue-500/30 transition flex items-center justify-center gap-1"
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
                            className="px-2.5 py-1.5 bg-spine-accent/20 hover:bg-spine-accent/30 text-spine-accent hover:text-white rounded-lg text-xs font-semibold border border-spine-accent/30 transition flex items-center gap-1"
                            title="Add Requirement on this Take"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            + Req
                          </button>
                          <button
                            onClick={() => handleInspectTake(t)}
                            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-gray-200 hover:text-white rounded-lg text-xs font-semibold border border-slate-700 transition"
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
                  {/* A take reached by a deep link that the reader's own
                      filters exclude. Said out loud rather than quietly shown:
                      otherwise it looks like the filter is broken. */}
                  {pinnedOutsideFilter && currentFocusTake
                    && takeKey(currentFocusTake) === takeKey(pinnedOutsideFilter) && (
                    <p className="flex items-start gap-2 text-[11px] text-amber-300/90 bg-amber-950/20 border border-amber-900/50 rounded-lg p-2">
                      <ExternalLink className="w-3.5 h-3.5 mt-px shrink-0" aria-hidden />
                      <span>
                        Shown because you followed a link to it. Your current search and filters
                        exclude this take, and they have been left as they were.
                      </span>
                    </p>
                  )}

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
                        <span className="text-xs text-gray-300 font-semibold">Take</span>
                        <select
                          value={focusTakeIndex}
                          onChange={e => setFocusTakeIndex(parseInt(e.target.value))}
                          className="bg-transparent text-xs font-mono font-bold text-white focus:outline-none cursor-pointer"
                        >
                          {navigableTakes.map((ft, i) => (
                            <option key={i} value={i} className="bg-slate-900 text-white">
                              {i + 1}. Sc {ft.scene} — {ft.slate} T{ft.take_id} {ft.is_starred ? '⭐' : ''} {ft.is_wild_track ? '🎙️' : ''} {ft.is_vfx ? '✨' : ''}
                            </option>
                          ))}
                        </select>
                        <span className="text-xs text-gray-400 font-mono">of {navigableTakes.length}</span>
                      </div>

                      <button
                        disabled={focusTakeIndex >= navigableTakes.length - 1}
                        onClick={() => setFocusTakeIndex(Math.min(navigableTakes.length - 1, focusTakeIndex + 1))}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-white text-xs font-semibold transition flex items-center gap-1"
                      >
                        Next Take
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      {currentFocusTake.is_starred && (
                        <span className="bg-spine-warning/20 text-spine-warning border border-spine-warning/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                          ⭐ Circled Take
                        </span>
                      )}
                      {currentFocusTake.is_wild_track && (
                        <span className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                          🎙️ Wild Track
                        </span>
                      )}
                      {currentFocusTake.is_vfx && (
                        <span className="bg-spine-accent/20 text-spine-accent border border-spine-accent/40 px-2.5 py-1 rounded-lg text-xs font-bold">
                          ✨ VFX Required
                        </span>
                      )}
                      <button
                        onClick={() => handleInspectTake(currentFocusTake)}
                        className="px-3 py-1.5 bg-spine-accent hover:brightness-110 text-white rounded-lg text-xs font-semibold transition"
                      >
                        Open 3-Axis Diff Drawer
                      </button>
                    </div>
                  </div>

                  {/* Editorial status, the same shot-level tag the grid shows.
                      The navigator is where an assistant editor works through a
                      day take by take, so leaving it out meant switching layout
                      to mark anything. */}
                  <div className="flex items-center gap-2 -mt-1">
                    <span className="text-xs text-gray-300 font-semibold shrink-0">
                      Shot {currentFocusTake.slate}:
                    </span>
                    <EditorialTagBar
                      productionId={selectedProductionId}
                      targetType="shot"
                      targetId={currentFocusTake.slate}
                      tag={tagsByTarget[`shot:${currentFocusTake.slate}`]}
                      vocabulary={tagVocabulary}
                      currentUserHandle={currentUser.handle}
                      onSave={handleSaveTag}
                      onClear={handleClearTag}
                    />
                    <ScriptSceneButton
                      productionId={selectedProductionId}
                      targetType="shot"
                      targetId={currentFocusTake.slate}
                    />
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
                                      ? 'bg-spine-accent text-white shadow-lg'
                                      : 'text-gray-300 hover:text-white hover:bg-slate-900'
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
                            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-gray-300 p-6 text-center">
                              <div className="p-3 rounded-2xl bg-spine-warning/10 border border-spine-warning/30 text-spine-warning mb-2 shadow-sm">
                                <Clapperboard className="w-7 h-7" />
                              </div>
                              <span className="text-sm font-mono text-spine-warning font-bold">
                                {currentFocusTake.belief.script ? "Script Supervisor Continuity Slate" : "Awaiting Camera Thumbnail Offload"}
                              </span>
                              <div className="flex flex-wrap items-center justify-center gap-1.5 mt-2 font-mono text-xs">
                                {currentFocusTake.camera_cards?.length > 0 && (
                                  <span className="bg-blue-950/80 border border-blue-500/40 text-white px-2.5 py-0.5 rounded-lg">
                                    🎴 Cards: {currentFocusTake.camera_cards.join(', ')}
                                  </span>
                                )}
                                {currentFocusTake.belief.script?.timecode_in && (
                                  <span className="bg-slate-900 border border-slate-800 text-gray-200 px-2.5 py-0.5 rounded-lg">
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
                                  className="mt-2.5 text-xs font-mono text-spine-accent hover:text-spine-accent underline flex items-center gap-1.5 bg-spine-900/40 px-3 py-1 rounded-lg border border-spine-accent/30"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                  Preview Source: {currentFocusTake.belief.script.source_document}
                                </button>
                              )}
                            </div>
                          )}
                          {focusDisplayThumb && (
                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                              <span className="bg-spine-accent text-white text-xs px-3 py-1 rounded-lg font-semibold shadow">
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
                              ? 'text-spine-success bg-spine-success/20 border-spine-success/30' 
                              : 'text-spine-warning bg-spine-warning/60 border-spine-warning/30'
                          }`}>
                            {currentFocusTake.matched_media_files.length > 0 ? '✓ Checksum OK' : '📄 Paperwork Logged'}
                          </span>
                        </div>
                        <div className="text-xs font-mono text-gray-200 space-y-1.5 pt-1">
                          <div>Volumes: <span className="text-white font-bold">{currentFocusTake.storage_volumes?.length > 0 ? currentFocusTake.storage_volumes.join(', ') : 'Awaiting DIT Offload'}</span></div>
                          <div>Camera Cards: <span className="text-white font-bold">{currentFocusTake.camera_cards?.join(', ') || 'Awaiting ZoeLog'}</span></div>
                          <div>Sound Rolls: <span className={currentFocusTake.is_mos ? "text-indigo-400 font-bold" : "text-spine-success font-bold"}>{currentFocusTake.is_mos ? "None (MOS / Silent Take)" : (currentFocusTake.sound_cards?.join(', ') || 'Awaiting Sound ALE')}</span></div>
                          <div>Recorded Date: <span className="text-gray-100">{currentFocusTake.recording_date || '28/07/2026'}</span></div>
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
                              className="text-xs text-spine-accent hover:underline flex items-center gap-1 font-mono"
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
                                  <span className="bg-spine-accent text-white font-bold px-2 py-0.5 rounded text-[11px]">
                                    Cam {vf.camera}
                                  </span>
                                  <span className="text-white font-bold">{vf.file_name}</span>
                                </div>
                                <span className="text-cyan-400 font-bold">{vf.camera_roll}</span>
                              </div>
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-gray-200 pt-1 border-t border-slate-800/60">
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
                      <div className="bg-slate-950 p-4 rounded-xl border border-spine-success/20 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                          <span className="text-xs font-bold text-spine-success uppercase tracking-wider flex items-center gap-1.5">
                            <Mic className="w-4 h-4 text-spine-success" />
                            Sound WAV Files & Multi-Track Channels ({currentFocusTake.audio_files?.length || 0})
                          </span>
                          {currentFocusTake.belief.sound?.source_document && (
                            <button
                              onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.sound?.source_doc_id, currentFocusTake.belief.sound?.source_document)}
                              className="text-xs text-spine-accent hover:underline flex items-center gap-1 font-mono"
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
                                  <span className="bg-spine-success text-white font-bold px-2 py-0.5 rounded text-[11px]">
                                    WAV
                                  </span>
                                  <span className="text-spine-success font-bold">{af.file_name}</span>
                                </div>
                                <span className="text-spine-success font-bold">{af.sound_roll}</span>
                              </div>

                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-gray-200">
                                <div>Start TC: <span className="text-white">{af.timecode_in || '--'}</span></div>
                                <div>Length: <span className="text-white">{af.duration || '--'}</span></div>
                                <div>Sample Rate: <span className="text-gray-100">{af.sample_rate || '48kHz'}</span></div>
                                <div>Bit Depth: <span className="text-gray-100">{af.bit_depth || '24-bit'}</span></div>
                              </div>

                              {af.tracks && (
                                <div className="space-y-1 pt-1 border-t border-slate-800/60">
                                  <span className="text-[10px] text-gray-300 uppercase tracking-wider font-sans font-semibold">Active Channels / Tracks:</span>
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
                                <div className="text-[11px] text-spine-warning bg-spine-warning/20 p-2 rounded border border-spine-warning/20 italic">
                                  Mixer Note: "{af.note}"
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Script Supervisor Witness */}
                      {currentFocusTake.belief.script && (
                        <div className="bg-slate-950 p-4 rounded-xl border border-spine-warning/20 space-y-2">
                          <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                            <span className="text-xs font-bold text-spine-warning uppercase tracking-wider">
                              Script Supervisor Witness (Scripte Logs)
                            </span>
                            {currentFocusTake.belief.script.source_document && (
                              <button
                                onClick={() => handleOpenPreviewDoc(currentFocusTake.belief.script?.source_doc_id, currentFocusTake.belief.script?.source_document)}
                                className="text-xs text-spine-accent hover:underline flex items-center gap-1 font-mono"
                              >
                                <Eye className="w-3.5 h-3.5" />
                                Preview {currentFocusTake.belief.script.source_document}
                              </button>
                            )}
                          </div>
                          <div className="text-xs font-mono text-gray-200 grid grid-cols-2 gap-3 pt-1">
                            <div>Timecode: <span className="text-white">{currentFocusTake.belief.script.timecode_in || '--'} → {currentFocusTake.belief.script.timecode_out || '--'}</span></div>
                            <div>Camera Card: <span className="text-white font-bold">{currentFocusTake.belief.script.camera_roll || '--'}</span></div>
                            <div className="col-span-2">Notes: <span className="text-gray-100 italic">{currentFocusTake.belief.script.note || 'Take recorded normally without faults.'}</span></div>
                          </div>
                        </div>
                      )}

                      {/* Collaborative Requirements & Notes Section */}
                      <div className="bg-slate-950 p-4 rounded-xl border border-spine-accent/20 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="w-4 h-4 text-spine-accent" />
                            <span className="text-xs font-bold text-spine-accent uppercase tracking-wider">
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
                            className="text-xs text-spine-accent hover:text-white bg-spine-accent/30 hover:bg-spine-accent/50 border border-spine-accent/40 px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition font-semibold"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            + Add Requirement
                          </button>
                        </div>

                        {(!currentFocusTake.requirements || currentFocusTake.requirements.length === 0) ? (
                          <p className="text-xs text-gray-400 italic py-1">
                            No requirements assigned to this take. Click "+ Add Requirement" to assign one to an editor, mixer, or VFX artist.
                          </p>
                        ) : (
                          /* The same controls the production board has, not a
                             read-only copy of them. A requirement raised on a
                             take is the same object wherever it is looked at,
                             and being able to hand it on in one place and only
                             stare at it in another is a difference nobody can
                             hold in their head. */
                          <div className="space-y-2">
                            {currentFocusTake.requirements.map(req => (
                              <RequirementRow
                                key={req.requirement_id}
                                requirement={req}
                                team={teamUsers}
                                currentUserHandle={currentUser.handle}
                                onChanged={() => {
                                  loadSpineData();
                                  loadUsersAndNotifications(currentUser.handle);
                                }}
                              />
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
                <p className="text-[11px] text-gray-300">
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
                <thead className="bg-slate-950 text-gray-300 border-b border-slate-800 uppercase font-mono text-[10px] tracking-wider sticky top-0 z-10">
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
                      <td colSpan={14} className="px-4 py-16 text-center text-gray-400">
                        No sequence records found matching filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredSequences.map((seq, idx) => (
                      <tr 
                        key={idx} 
                        className={`hover:bg-slate-800/40 transition duration-150 ${
                          seq.has_discrepancy ? 'bg-spine-critical/10' : idx % 2 === 0 ? 'bg-slate-950/30' : 'bg-transparent'
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
                            <div className="text-[10px] text-gray-300 font-mono flex items-center gap-1.5">
                              <span>{seq.takes_count} {seq.takes_count === 1 ? 'take' : 'takes'}</span>
                              {seq.circled_takes_count && seq.circled_takes_count > 0 ? (
                                <span className="bg-spine-warning/20 text-spine-warning border border-spine-warning/40 px-1.5 py-0.2 rounded font-bold" title={`Chosen / Circled takes: ${seq.circled_takes?.join(', ')}`}>
                                  ⭐ {seq.circled_takes_count} chosen
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </td>

                        {/* 2. LOCATION */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="flex items-start gap-1.5 font-medium text-spine-warning/90 text-xs">
                            <MapPin className="w-3.5 h-3.5 text-spine-warning shrink-0 mt-0.5" />
                            <span>{seq.location}</span>
                          </div>
                        </td>

                        {/* 3. DESCRIPTION */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="text-gray-100 text-xs leading-relaxed max-w-sm">
                            {seq.description}
                          </div>
                        </td>

                        {/* 4. SHOOTING-DAY */}
                        <td className="px-3 py-3 align-top whitespace-nowrap font-mono text-xs text-gray-200">
                          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded w-fit">
                            <Calendar className="w-3 h-3 text-blue-400" />
                            {seq.shoot_day}
                          </div>
                          {/* A scene is rarely finished in one go. Without the
                              other days, this row reads as if the sequence
                              began and ended here. */}
                          {(seq.shoot_days?.length ?? 0) > 1 && (
                            <div className="mt-1 space-y-0.5">
                              <span className="text-[9px] text-gray-500 uppercase tracking-wide">
                                Also shot on
                              </span>
                              <div className="flex flex-wrap gap-1">
                                {seq.shoot_days!
                                  .filter(d => d !== selectedDay)
                                  .map(d => (
                                    <button
                                      key={d}
                                      onClick={() => setSelectedDay(d)}
                                      title={`Show day ${d} for this production`}
                                      className="px-1.5 py-0.5 rounded bg-blue-950/60 border border-blue-500/40 text-blue-300 hover:text-white hover:border-blue-400 text-[10px] font-bold transition"
                                    >
                                      Day {d}
                                    </button>
                                  ))}
                              </div>
                            </div>
                          )}
                        </td>

                        {/* 5. DATE */}
                        <td className="px-3 py-3 align-top whitespace-nowrap font-mono text-xs text-gray-300">
                          {seq.date}
                        </td>

                        {/* 6. CARDS */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="flex flex-wrap gap-1 max-w-xs font-mono text-[10px]">
                            {seq.camera_cards?.map((card, ci) => (
                              <span key={ci} className="bg-blue-950/60 border border-blue-500/30 text-white px-1.5 py-0.5 rounded">
                                {card}
                              </span>
                            ))}
                            {seq.sound_cards?.map((card, si) => (
                              <span key={si} className="bg-spine-success/60 border border-spine-success/30 text-spine-success px-1.5 py-0.5 rounded">
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
                              className="text-[11px] font-mono text-spine-accent hover:text-white bg-spine-900/40 hover:bg-spine-900/50 border border-spine-accent/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.script_log_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-spine-accent" />
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
                              className="text-[11px] font-mono text-white hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
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
                              className="text-[11px] font-mono text-white hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
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
                              className="text-[11px] font-mono text-white hover:text-white bg-blue-950/40 hover:bg-blue-900/50 border border-blue-500/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
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
                              className="text-[11px] font-mono text-spine-success hover:text-white bg-spine-success/40 hover:bg-emerald-900/50 border border-spine-success/30 px-2 py-1 rounded flex items-center gap-1.5 transition"
                              title={`Preview ${seq.sound_log_doc.filename}`}
                            >
                              <Eye className="w-3 h-3 text-spine-success" />
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
                                className="bg-spine-critical/20 hover:bg-spine-critical/30 border border-spine-critical/40 text-spine-critical px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 w-fit transition"
                                title="Click to resolve discrepancy"
                              >
                                <AlertCircle className="w-3 h-3 text-spine-critical" />
                                Solve Mismatch
                              </button>
                            ) : (
                              <span className="bg-spine-success/10 border border-spine-success/30 text-spine-success px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 w-fit">
                                <Check className="w-3 h-3 text-spine-success" />
                                Reconciled
                              </span>
                            )}

                            {/* Editorial status for the sequence. A row here is
                                a scene -- clicking the sequence filters the
                                master sheet by it -- so this is the scene tag,
                                the same one the scene filter row edits. */}
                            <EditorialTagBar
                              productionId={selectedProductionId}
                              targetType="scene"
                              targetId={seq.sequence}
                              tag={tagsByTarget[`scene:${seq.sequence}`]}
                              vocabulary={tagVocabulary}
                              currentUserHandle={currentUser.handle}
                              onSave={handleSaveTag}
                              onClear={handleClearTag}
                            />
                            <ScriptSceneButton
                              productionId={selectedProductionId}
                              targetType="scene"
                              targetId={seq.sequence}
                            />

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
                                  className="px-1.5 py-0.5 rounded bg-spine-warning/20 hover:bg-spine-warning/30 border border-spine-warning/40 text-spine-warning text-[9px] font-bold flex items-center gap-1"
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
                                  className="px-1.5 py-0.5 rounded bg-spine-success/20 hover:bg-spine-success/30 border border-spine-success/40 text-spine-success text-[9px] font-semibold flex items-center gap-1"
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
                                className="px-1.5 py-0.5 rounded bg-spine-accent/20 hover:bg-spine-accent/40 border border-spine-accent/30 text-spine-accent text-[9px] font-semibold flex items-center gap-0.5 transition"
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
                                <span className="bg-spine-accent/20 border border-spine-accent/40 text-spine-accent px-1.5 py-0.5 rounded text-[10px] font-bold font-mono">
                                  ✨ VFX
                                </span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* 14. COMMENTS */}
                        <td className="px-3.5 py-3 align-top">
                          <div className="text-gray-200 text-xs italic max-w-xs leading-relaxed">
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
                <p className="text-[11px] text-gray-300">
                  Cross-referenced locations across ZoeLog Camera cards, Sound ALE rolls, and DIT hard drives
                </p>
              </div>
              <span className="text-xs font-mono text-gray-300">{filteredTakes.length} Takes Matching</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-gray-300 border-b border-slate-800 uppercase font-mono text-[10px]">
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
                      <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
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
                            <span className="text-gray-300 font-normal">Sc {t.scene || 'N/A'} / </span>
                            <span className="text-white font-bold text-sm">{t.slate}</span>
                          </td>

                          {/* Take & Flags */}
                          <td className="px-4 py-3.5 font-mono">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-white font-bold">T{t.take_id}</span>
                              {t.is_starred && (
                                <span className="text-[10px] bg-spine-warning/20 text-spine-warning border border-spine-warning/40 px-1.5 py-0.2 rounded font-sans">
                                  ⭐ Circled
                                </span>
                              )}
                              {t.is_wild_track && (
                                <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-1.5 py-0.2 rounded font-sans">
                                  🎙️ WT
                                </span>
                              )}
                              {t.is_vfx && (
                                <span className="text-[10px] bg-spine-accent/20 text-spine-accent border border-spine-accent/40 px-1.5 py-0.2 rounded font-sans">
                                  ✨ VFX
                                </span>
                              )}
                              {t.is_mos && (
                                <span className="text-[10px] bg-spine-accent/20 text-indigo-300 border border-indigo-500/40 px-1.5 py-0.2 rounded font-sans">
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
                                  <span key={i} className="bg-blue-950/60 border border-blue-500/30 text-white px-2 py-0.5 rounded text-[11px] font-semibold">
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
                                <span className="text-spine-success font-semibold">
                                  🎙️ {t.belief.sound.sound_roll || 'SR'}
                                </span>
                                <div className="text-[10px] text-gray-400">{t.belief.sound.timecode_in || '--'}</div>
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
                                  <span className="text-gray-200 text-[11px] truncate max-w-[140px]" title={m.file_name}>
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
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-spine-critical/20 text-spine-critical border border-spine-critical/40">
                                <AlertTriangle className="w-3 h-3 text-spine-critical" />
                                Mismatch Detected
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-spine-success text-xs">
                                <Check className="w-3.5 h-3.5 text-spine-success" />
                                Reconciled
                              </span>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-3.5 text-right space-x-1.5">
                            <button
                              onClick={() => handleInspectTake(t)}
                              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-white hover:text-white rounded text-xs border border-slate-700 transition"
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
              <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center text-gray-300">
                <CheckCircle2 className="w-12 h-12 text-spine-success mx-auto mb-3" />
                <h3 className="text-base font-bold text-white">All Documents 100% Reconciled</h3>
                <p className="text-xs text-gray-300 mt-1">No discrepancies found across Sound, Script, Camera, and DIT logs.</p>
              </div>
            ) : (
              discrepancies.map((d, idx) => (
                <div 
                  key={idx} 
                  className={`rounded-xl p-5 space-y-3 shadow-lg transition ${
                    d.is_resolved 
                      ? 'bg-spine-success/20 border border-spine-success/40' 
                      : 'bg-slate-900/80 border border-spine-critical/30'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded font-mono ${
                          d.is_resolved
                            ? 'bg-spine-success/20 text-spine-success border border-spine-success/40'
                            : d.severity === 'CRITICAL' 
                              ? 'bg-spine-critical/20 text-spine-critical border border-spine-critical/40' 
                              : 'bg-spine-warning/20 text-spine-warning border border-spine-warning/40'
                        }`}>
                          {d.is_resolved ? '✓ RESOLVED' : d.discrepancy_type}
                        </span>
                        <span className="text-sm font-mono font-bold text-white">{d.entity_id}</span>
                        {d.is_resolved && (
                          <span className="text-xs font-mono font-bold text-spine-success bg-spine-success/80 border border-emerald-700/60 px-2 py-0.5 rounded flex items-center gap-1">
                            <HardDrive className="w-3 h-3" />
                            Target Card: {d.resolved_card || 'Manual Override'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-100">{d.description}</p>
                      {d.is_resolved && d.resolution_note && (
                        <p className="text-xs text-spine-success/90 italic bg-spine-success/40 p-2.5 rounded-lg border border-emerald-800/40">
                          "{d.resolution_note}" <span className="text-spine-success text-[11px] not-italic">— {d.resolved_by || 'Assistant Editor'} {d.resolved_at ? `(${new Date(d.resolved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})` : ''}</span>
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      {d.is_resolved ? (
                        <>
                          <button
                            onClick={() => openResolveModal(d)}
                            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-gray-200 hover:text-white text-xs font-semibold border border-slate-700 transition"
                          >
                            Edit Card / Note
                          </button>
                          <button
                            onClick={() => handleUnresolve(d.discrepancy_id)}
                            className="px-3 py-1.5 rounded-lg bg-spine-warning/20 hover:bg-spine-warning/30 text-spine-warning border border-spine-warning/30 text-xs font-semibold transition"
                          >
                            Re-open
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => openResolveModal(d)}
                          className="px-3.5 py-1.5 rounded-lg bg-spine-success hover:bg-spine-success text-white text-xs font-bold transition flex items-center gap-1.5 shadow"
                        >
                          <Check className="w-3.5 h-3.5" />
                          Resolve / Assign Card
                        </button>
                      )}
                      <button 
                        onClick={() => {
                          let takeMatch = takes.find(t => 
                            d.entity_id === `${t.slate}_${t.take_id}` ||
                            d.entity_id === t.slate ||
                            d.entity_id.startsWith(t.slate) ||
                            t.slate.startsWith(d.entity_id)
                          );
                          if (!takeMatch && d.witnesses) {
                            for (const w of d.witnesses) {
                              if (w.slates && Array.isArray(w.slates)) {
                                takeMatch = takes.find(t => w.slates.includes(t.slate));
                                if (takeMatch) break;
                              }
                            }
                          }
                          if (!takeMatch && takes.length > 0) {
                            takeMatch = takes[0];
                          }
                          if (takeMatch) handleInspectTake(takeMatch);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-spine-accent hover:brightness-110 text-white text-xs font-semibold transition"
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
                          <span className="text-gray-300 font-bold uppercase text-[10px]">{(w.author || 'Dept').toUpperCase()}</span>
                          <span className="text-blue-400 font-mono text-[10px]">{(w.axis || 'belief').toUpperCase()}</span>
                        </div>
                        <div className="text-gray-200 font-mono text-[11px]">
                          {w.camera_roll && <div>Roll: <span className="text-white font-bold">{w.camera_roll}</span></div>}
                          {w.sound_roll && <div>Sound Roll: <span className="text-white font-bold">{w.sound_roll}</span></div>}
                          {w.is_starred !== undefined && (
                            <div>Circled: <span className={w.is_starred ? 'text-spine-warning font-bold' : 'text-gray-400'}>{w.is_starred ? 'YES' : 'NO'}</span></div>
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
                  <FileCode className="w-4 h-4 text-spine-accent" />
                  Raw Source Paperwork Repository
                </h3>
                <p className="text-[11px] text-gray-300">
                  Inspect the original uploaded Sound ALEs, Camera CSVs, Script Editor Logs, and Silverstack XMLs
                </p>
              </div>
              <span className="text-xs font-mono text-gray-300">{documents.length} Files Ingested</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-gray-300 border-b border-slate-800 uppercase font-mono text-[10px]">
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
                      <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
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
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-gray-200 font-mono">
                            {doc.department}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-300">{doc.doc_type}</td>
                        <td className="px-4 py-3 font-mono text-[11px] text-cyan-400">
                          {doc.checksum ? (
                            <span className="bg-cyan-950/50 border border-cyan-500/30 px-1.5 py-0.5 rounded font-mono" title={doc.checksum}>
                              {doc.checksum.slice(0, 10)}...
                            </span>
                          ) : (
                            <span className="text-slate-600">--</span>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-300">{(doc.size_bytes / 1024).toFixed(1)} KB</td>
                        <td className="px-4 py-3 font-mono text-gray-400">{doc.uploaded_at?.slice(0, 19).replace('T', ' ')}</td>
                        <td className="px-4 py-3 text-right space-x-2">
                          <button
                            onClick={() => handleOpenPreviewDoc(doc.doc_id)}
                            className="px-2.5 py-1 bg-spine-accent/20 hover:bg-spine-accent/30 text-spine-accent border border-spine-accent/40 rounded text-xs font-semibold inline-flex items-center gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            Preview
                          </button>
                          <button
                            onClick={() => handleDeleteDocument(doc.doc_id, doc.filename)}
                            className="px-2.5 py-1 bg-spine-critical/20 hover:bg-spine-critical/30 text-spine-critical border border-spine-critical/40 rounded text-xs font-semibold inline-flex items-center gap-1"
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

        {/* TAB 4: REQUIREMENTS & ACTION ITEMS HUB */}
        {activeTab === 'requirements' && (
          <section className="space-y-4">
            {/* Header & KPI Summary */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-spine-accent/20 border border-spine-accent/40 flex items-center justify-center text-spine-accent">
                      <ListTodo className="w-4 h-4" />
                    </div>
                    <h2 className="text-base font-bold text-white">Collaborative Requirements & Action Items</h2>
                  </div>
                  <p className="text-xs text-gray-300">
                    Track director notes, sound cleanups, VFX plates, retakes, and editor tasks attached to scenes, shots, and slates.
                  </p>
                </div>

                <button
                  onClick={() => {
                    setTargetForReq(null);
                    setNewReqTitle('');
                    setNewReqDesc('');
                    setIsCreateReqOpen(true);
                  }}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-spine-accent hover:bg-spine-accent text-white text-xs font-bold shadow-lg shadow-purple-600/30 transition"
                >
                  <PlusCircle className="w-4 h-4" />
                  + Create Requirement
                </button>
              </div>

              {/* KPI Stats Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
                <div 
                  onClick={() => { setReqFilterStatus('ALL'); setReqFilterAssignee('ALL'); }}
                  className={`p-3.5 rounded-xl border cursor-pointer transition ${
                    reqFilterStatus === 'ALL' && reqFilterAssignee === 'ALL'
                      ? 'bg-spine-900/40 border-spine-accent/50 text-white'
                      : 'bg-slate-950/60 border-slate-800 text-gray-300 hover:bg-slate-900'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-gray-300">Total</span>
                  <span className="text-xl font-mono font-bold text-white">{reqMetrics.total}</span>
                </div>

                <div 
                  onClick={() => { setReqFilterStatus('open'); }}
                  className={`p-3.5 rounded-xl border cursor-pointer transition ${
                    reqFilterStatus === 'open'
                      ? 'bg-spine-warning/40 border-spine-warning/50 text-spine-warning'
                      : 'bg-slate-950/60 border-slate-800 text-gray-300 hover:bg-slate-900'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-spine-warning">Actionable Open</span>
                  <span className="text-xl font-mono font-bold text-spine-warning">{reqMetrics.open}</span>
                </div>

                <div 
                  onClick={() => { setReqFilterAssignee(reqFilterAssignee === '@me' ? 'ALL' : '@me'); }}
                  className={`p-3.5 rounded-xl border cursor-pointer transition ${
                    reqFilterAssignee === '@me'
                      ? 'bg-blue-950/40 border-blue-500/50 text-white'
                      : 'bg-slate-950/60 border-slate-800 text-gray-300 hover:bg-slate-900'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-blue-400">Assigned To Me</span>
                  <span className="text-xl font-mono font-bold text-white">{reqMetrics.assignedToMe}</span>
                </div>

                <div 
                  onClick={() => { setReqFilterPriority('high'); }}
                  className={`p-3.5 rounded-xl border cursor-pointer transition ${
                    reqFilterPriority === 'high'
                      ? 'bg-spine-critical/40 border-spine-critical/50 text-spine-critical'
                      : 'bg-slate-950/60 border-slate-800 text-gray-300 hover:bg-slate-900'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-spine-critical">Critical / High</span>
                  <span className="text-xl font-mono font-bold text-spine-critical">{reqMetrics.criticalOrHigh}</span>
                </div>

                <div 
                  onClick={() => { setReqFilterStatus('resolved'); }}
                  className={`p-3.5 rounded-xl border cursor-pointer transition ${
                    reqFilterStatus === 'resolved'
                      ? 'bg-spine-success/40 border-spine-success/50 text-spine-success'
                      : 'bg-slate-950/60 border-slate-800 text-gray-300 hover:bg-slate-900'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider block text-spine-success">Resolved</span>
                  <span className="text-xl font-mono font-bold text-spine-success">{reqMetrics.resolved}</span>
                </div>
              </div>
            </div>

            {/* Filter & Search Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/80 border border-slate-800 rounded-xl p-3">
              {/* Status Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                {(['ALL', 'open', 'in_progress', 'blocked', 'resolved'] as const).map(statusKey => (
                  <button
                    key={statusKey}
                    onClick={() => setReqFilterStatus(statusKey)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition uppercase font-mono ${
                      reqFilterStatus === statusKey
                        ? statusKey === 'resolved'
                          ? 'bg-spine-success text-white'
                          : statusKey === 'blocked'
                          ? 'bg-spine-critical text-white'
                          : 'bg-spine-accent text-white'
                        : 'text-gray-300 hover:text-white bg-slate-950 border border-slate-800'
                    }`}
                  >
                    {statusKey === 'ALL' ? 'All Status' : statusKey.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {/* Filters Dropdown & Search */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Assignee Filter */}
                <select
                  value={reqFilterAssignee}
                  onChange={e => setReqFilterAssignee(e.target.value)}
                  className="bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded-lg text-white font-mono focus:outline-none focus:border-spine-accent"
                >
                  <option value="ALL">All Assignees</option>
                  <option value="@me">👤 Assigned to Me ({currentUser.handle})</option>
                  {teamUsers.map(u => (
                    <option key={u.handle} value={u.handle}>
                      {u.handle} ({u.name})
                    </option>
                  ))}
                </select>

                {/* Priority Filter */}
                <select
                  value={reqFilterPriority}
                  onChange={e => setReqFilterPriority(e.target.value)}
                  className="bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded-lg text-white font-mono focus:outline-none focus:border-spine-accent"
                >
                  <option value="ALL">All Priorities</option>
                  <option value="critical">🔴 Critical</option>
                  <option value="high">🟠 High</option>
                  <option value="medium">🟡 Medium</option>
                  <option value="low">🔵 Low</option>
                </select>

                {/* Category Filter */}
                <select
                  value={reqFilterCategory}
                  onChange={e => setReqFilterCategory(e.target.value)}
                  className="bg-slate-950 border border-slate-700 text-xs px-2.5 py-1.5 rounded-lg text-white font-mono focus:outline-none focus:border-spine-accent"
                >
                  <option value="ALL">All Categories</option>
                  <option value="sound">🎙️ Sound</option>
                  <option value="edit">✂️ Editorial</option>
                  <option value="vfx">✨ VFX</option>
                  <option value="camera">🎥 Camera</option>
                  <option value="color">🎨 Color</option>
                  <option value="reshoot">🔄 Reshoot</option>
                  <option value="general">📝 General</option>
                </select>

                {/* Text Search */}
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Filter requirements..."
                    value={reqSearchQuery}
                    onChange={e => setReqSearchQuery(e.target.value)}
                    className="bg-slate-950 border border-slate-700 text-xs pl-8 pr-3 py-1.5 rounded-lg text-white font-mono w-44 focus:outline-none focus:border-spine-accent"
                  />
                </div>
              </div>
            </div>

            {/* Requirements Cards List */}
            {filteredRequirements.length === 0 ? (
              <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center text-gray-300 space-y-3">
                <CheckCircle2 className="w-12 h-12 text-spine-accent mx-auto opacity-70" />
                <h3 className="text-base font-bold text-white">No Requirements Found</h3>
                <p className="text-xs text-gray-300 max-w-md mx-auto">
                  No action items match the active filters. Create a new requirement on any scene, shot, or take.
                </p>
                <button
                  onClick={() => {
                    setTargetForReq(null);
                    setNewReqTitle('');
                    setNewReqDesc('');
                    setIsCreateReqOpen(true);
                  }}
                  className="px-4 py-2 bg-spine-accent hover:bg-spine-accent text-white text-xs font-bold rounded-xl transition"
                >
                  + Add Requirement
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredRequirements.map(req => {
                  const isResolved = req.status === 'resolved';


                  return (
                    <div
                      key={req.requirement_id}
                      className={`bg-slate-900/90 border border-slate-800  rounded-xl p-5 space-y-3 shadow-lg transition hover:border-slate-700`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1.5 flex-1 min-w-[280px]">
                          {/* Badges Bar */}
                          <div className="flex flex-wrap items-center gap-2">
                            {/* Status Badge */}
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase ${
                              isResolved
                                ? 'bg-spine-success/20 text-spine-success border border-spine-success/40'
                                : req.status === 'blocked'
                                ? 'bg-spine-critical/20 text-spine-critical border border-spine-critical/40'
                                : req.status === 'in_progress'
                                ? 'bg-blue-500/20 text-white border border-blue-500/40'
                                : 'bg-spine-warning/20 text-spine-warning border border-spine-warning/40'
                            }`}>
                              {req.status.replace('_', ' ')}
                            </span>

                            {/* Category Badge */}
                            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-spine-900/60 text-spine-accent border border-spine-accent/30 uppercase">
                              {req.category}
                            </span>

                            {/* Priority Badge */}
                            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase ${
                              req.priority === 'critical'
                                ? 'bg-spine-critical/80 text-spine-critical border border-spine-critical/40'
                                : req.priority === 'high'
                                ? 'bg-orange-950/80 text-orange-300 border border-orange-500/40'
                                : 'bg-slate-950 text-gray-300 border border-slate-800'
                            }`}>
                              {req.priority} Priority
                            </span>

                            {/* Target Entity Badge */}
                            <span className="text-xs font-mono font-bold text-cyan-300 bg-cyan-950/50 border border-cyan-500/30 px-2.5 py-0.5 rounded flex items-center gap-1.5">
                              <Clapperboard className="w-3 h-3 text-cyan-400" />
                              {req.target_label || `${req.target_type.toUpperCase()} ${req.target_id}`}
                            </span>
                          </div>

                          {/* Requirement Title */}
                          <h4 className="text-sm font-bold text-white pt-1">{req.title}</h4>

                          {/* Requirement Description */}
                          {req.description && (
                            <p className="text-xs text-gray-200 bg-slate-950/70 p-3 rounded-lg border border-slate-800/80 leading-relaxed font-sans">
                              {req.description}
                            </p>
                          )}

                          {/* Meta line: Creator, Assignee, Created Date */}
                          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-300 pt-1">
                            <span className="flex items-center gap-1.5 font-mono">
                              <span className="text-gray-400">Assigned to:</span>
                              <span className="text-spine-accent font-bold bg-spine-900/60 px-2 py-0.5 rounded border border-spine-accent/30">
                                {req.assigned_to}
                              </span>
                            </span>
                            <span className="text-slate-600">•</span>
                            <span className="text-gray-300 font-mono">
                              Created by <strong className="text-gray-100">{req.created_by}</strong>
                            </span>
                            <span className="text-slate-600">•</span>
                            <span className="text-gray-400 font-mono text-[11px]">
                              {new Date(req.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>

                          {/* Resolution Quote Callout (if resolved) */}
                          {isResolved && (
                            <div className="bg-spine-success/40 border border-spine-success/40 rounded-xl p-3 text-xs space-y-1 mt-2">
                              <div className="flex items-center gap-1.5 text-spine-success font-bold font-mono text-[11px]">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                Resolved by {req.resolved_by || 'Team Member'} {req.resolved_at ? `(${new Date(req.resolved_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })})` : ''}
                              </div>
                              {req.resolution_note && (
                                <p className="text-spine-success/90 italic pl-5">
                                  "{req.resolution_note}"
                                </p>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Action Buttons Toolbar */}
                        <div className="flex flex-col sm:flex-row items-end sm:items-center gap-2 shrink-0">
                          {/* DIRECT GO TO SLATE NAVIGATOR BUTTON */}
                          <button
                            onClick={() => jumpToTarget(req.target_type, req.target_id)}
                            className="px-3.5 py-1.5 bg-spine-accent/20 hover:bg-spine-accent/30 text-white hover:text-white border border-blue-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow"
                            title="Jump directly to Slate Navigator for this take/slate"
                          >
                            <Clapperboard className="w-3.5 h-3.5 text-blue-400" />
                            Slate Navigator
                            <ArrowRight className="w-3.5 h-3.5" />
                          </button>

                          {/* Resolve Button */}
                          {!isResolved ? (
                            <button
                              onClick={() => {
                                setSelectedReqForResolve(req);
                                setReqResolutionNote('');
                              }}
                              className="px-3.5 py-1.5 bg-spine-success hover:bg-spine-success text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition shadow"
                            >
                              <Check className="w-3.5 h-3.5" />
                              Resolve...
                            </button>
                          ) : (
                            <button
                              onClick={() => handleUpdateRequirementStatus(req.requirement_id, 'in_progress')}
                              className="px-3.5 py-1.5 bg-spine-warning/20 hover:bg-spine-warning/30 text-spine-warning border border-spine-warning/30 rounded-lg text-xs font-semibold transition"
                            >
                              Re-open
                            </button>
                          )}

                          {/* Status changer dropdown if not resolved */}
                          {!isResolved && (
                            <select
                              value={req.status}
                              onChange={e => handleUpdateRequirementStatus(req.requirement_id, e.target.value)}
                              className="bg-slate-950 border border-slate-700 text-xs px-2 py-1.5 rounded-lg text-gray-200 font-mono focus:outline-none focus:border-spine-accent"
                            >
                              <option value="open">Open</option>
                              <option value="in_progress">In Progress</option>
                              <option value="blocked">Blocked</option>
                            </select>
                          )}

                          {/* Delete button */}
                          <button
                            onClick={() => handleDeleteRequirement(req.requirement_id, req.title)}
                            className="p-1.5 bg-slate-950 hover:bg-spine-critical/60 text-gray-400 hover:text-spine-critical border border-slate-800 hover:border-spine-critical/30 rounded-lg transition"
                            title="Delete requirement"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* If Open: Resolve Input Section */}
                      {selectedReqForResolve?.requirement_id === req.requirement_id && (
                        <div className="pt-3 border-t border-slate-800 space-y-2 mt-3">
                          <div className="space-y-2 bg-slate-900 p-3 rounded-xl border border-spine-accent/40">
                            <label className="text-[11px] font-bold text-spine-success block">
                              Resolution Justification / Note:
                            </label>
                            <textarea
                              rows={2}
                              placeholder="e.g. Applied EQ filter to isolate lavalier, audio verified clean for edit..."
                              value={reqResolutionNote}
                              onChange={e => setReqResolutionNote(e.target.value)}
                              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-spine-success"
                              autoFocus
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => setSelectedReqForResolve(null)}
                                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs rounded-lg transition"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                disabled={isResolvingReqSubmitting || !reqResolutionNote.trim()}
                                onClick={() => handleResolveRequirementSubmit(req.requirement_id)}
                                className="px-3 py-1 bg-spine-success hover:bg-spine-success disabled:opacity-50 text-white text-xs font-bold rounded-lg flex items-center gap-1 transition shadow"
                              >
                                {isResolvingReqSubmitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                                Mark Resolved & Notify Caller ({req.created_by})
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}
      </main>
      )}


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
                    <span className="text-xs bg-spine-warning/20 text-spine-warning border border-spine-warning/40 px-2 py-0.5 rounded">
                      ⭐ Circled Take
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-300 mt-1">3-Axis Witness Diagnosis & Storage Card Breakdown</p>
              </div>
              <button 
                onClick={() => { setInspectedTake(null); setAssistantExplanation(null); }}
                className="text-gray-300 hover:text-white text-lg p-1"
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
                    ? 'bg-spine-success/40 border-spine-success/50 text-spine-success'
                    : 'bg-spine-critical/40 border-spine-critical/50 text-spine-critical'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                        matchedDisc.is_resolved ? 'bg-spine-success/20 text-spine-success' : 'bg-spine-critical/20 text-spine-critical'
                      }`}>
                        {matchedDisc.is_resolved ? '✓ RESOLVED' : matchedDisc.discrepancy_type}
                      </span>
                      {matchedDisc.is_resolved && (
                        <span className="text-xs font-mono font-bold text-white flex items-center gap-1">
                          <HardDrive className="w-3 h-3 text-spine-success" />
                          Assigned: {matchedDisc.resolved_card || 'Manual Override'}
                        </span>
                      )}
                    </div>
                    {matchedDisc.is_resolved ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => openResolveModal(matchedDisc)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-gray-200 hover:text-white text-xs font-semibold border border-slate-700 transition"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleUnresolve(matchedDisc.discrepancy_id)}
                          className="px-2.5 py-1 rounded bg-spine-warning/20 hover:bg-spine-warning/30 text-spine-warning border border-spine-warning/30 text-xs font-semibold transition"
                        >
                          Re-open
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => openResolveModal(matchedDisc)}
                        className="px-3 py-1.5 rounded-lg bg-spine-success hover:bg-spine-success text-white text-xs font-bold transition flex items-center gap-1 shadow"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Resolve Discrepancy
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-gray-100">{matchedDisc.description}</p>
                  {matchedDisc.is_resolved && matchedDisc.resolution_note && (
                    <p className="text-xs italic bg-spine-success/60 p-2 rounded text-spine-success/90 border border-spine-success/40">
                      "{matchedDisc.resolution_note}" <span className="text-spine-success text-[11px] not-italic">— {matchedDisc.resolved_by || 'Assistant Editor'}</span>
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Physical Card & Volume Location Callout */}
            <div className="bg-blue-950/40 border border-blue-500/30 rounded-xl p-4 space-y-2">
              <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <HardDrive className="w-4 h-4 text-blue-400" />
                Physical Media & Card Location
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs pt-1 font-mono">
                <div>
                  <span className="text-gray-300 block text-[10px]">Camera Cards:</span>
                  <span className="text-white font-bold">{inspectedTake.camera_cards.join(', ') || 'No camera log'}</span>
                </div>
                <div>
                  <span className="text-gray-300 block text-[10px]">Sound Rolls:</span>
                  <span className="text-white font-bold">{inspectedTake.sound_cards.join(', ') || 'No sound log'}</span>
                </div>
                <div>
                  <span className="text-gray-300 block text-[10px]">Storage Volumes:</span>
                  <span className="text-cyan-300 font-bold">{inspectedTake.storage_volumes.join(', ') || 'Un-offloaded'}</span>
                </div>
                <div>
                  <span className="text-gray-300 block text-[10px]">Files On Disk:</span>
                  <span className="text-cyan-300 font-bold">{inspectedTake.matched_media_files.length} verified files</span>
                </div>
              </div>
            </div>

            {/* Gemini Agent AI Audit Report */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-400" />
                Discrepancy Synthesis & Explanation
              </h4>
              <p className="text-xs font-mono text-gray-200 whitespace-pre-line bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
                {assistantExplanation || 'Analyzing 3-axis witnesses...'}
              </p>
            </div>

            {/* Department Witness Breakdown with Preview Links */}
            {/* Department Witness Breakdown with Preview Links */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-gray-200 uppercase tracking-wider">Source Document Witness Claims</h4>

              {/* 1. Script Supervisor Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-spine-warning">1. Script Supervisor (Editorial & Continuity)</span>
                  {inspectedTake.belief.script?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.script?.source_doc_id, inspectedTake.belief.script?.source_document)}
                      className="text-[11px] text-spine-accent hover:text-spine-accent flex items-center gap-1 font-medium underline"
                    >
                      <Eye className="w-3 h-3" />
                      Preview {inspectedTake.belief.script.source_document}
                    </button>
                  )}
                </div>
                {inspectedTake.belief.script ? (
                  <div className="space-y-2">
                    <div className="text-xs font-mono text-gray-200 grid grid-cols-2 gap-2">
                      <div>Camera Roll: <span className="text-white font-bold">{inspectedTake.belief.script.camera_roll || '--'}</span></div>
                      <div>Date: <span className="text-white">{inspectedTake.belief.script.recording_date || inspectedTake.recording_date || '--'}</span></div>
                      <div>Timecode In: <span className="text-white">{inspectedTake.belief.script.timecode_in || '--'}</span></div>
                      <div>Timecode Out: <span className="text-white">{inspectedTake.belief.script.timecode_out || '--'}</span></div>
                      <div>Circled Take: <span className={inspectedTake.belief.script.is_starred ? 'text-spine-warning font-bold' : 'text-gray-300'}>{inspectedTake.belief.script.is_starred ? '⭐ YES (Chosen)' : 'NO'}</span></div>
                      <div>MOS (Silent): <span className={inspectedTake.belief.script.is_mos ? 'text-indigo-400 font-bold' : 'text-gray-300'}>{inspectedTake.belief.script.is_mos ? '🔇 YES (MOS)' : 'NO (Sync Audio)'}</span></div>
                    </div>
                    {inspectedTake.belief.script.note && (
                      <div className="text-[11px] text-gray-200 italic pt-1 border-t border-slate-900">
                        "{inspectedTake.belief.script.note}"
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs font-mono text-gray-400 italic">No script supervisor log ingested for this slate yet.</div>
                )}
              </div>

              {/* 2. Camera Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-400">2. Camera Department (Belief)</span>
                  {inspectedTake.belief.camera?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.camera?.source_doc_id, inspectedTake.belief.camera?.source_document)}
                      className="text-[11px] text-spine-accent hover:text-spine-accent flex items-center gap-1 font-medium underline"
                    >
                      <Eye className="w-3 h-3" />
                      Preview {inspectedTake.belief.camera.source_document}
                    </button>
                  )}
                </div>
                {inspectedTake.belief.camera ? (
                  <div className="text-xs font-mono text-gray-200 grid grid-cols-2 gap-2">
                    <div>Card Roll: <span className="text-white font-bold">{inspectedTake.belief.camera?.camera_roll || '--'}</span></div>
                    <div>Clip: <span className="text-white font-bold">{inspectedTake.belief.camera?.clip_name || '--'}</span></div>
                    <div>FPS / ISO: <span className="text-white">{inspectedTake.belief.camera?.fps || 24}fps / {inspectedTake.belief.camera?.iso || 800}</span></div>
                    <div>Lens: <span className="text-white">{inspectedTake.belief.camera?.lens || 'Standard'}</span></div>
                  </div>
                ) : (
                  <div className="text-xs font-mono text-gray-400 italic">No camera log (ZoeLog / CSV) ingested for this slate yet.</div>
                )}
              </div>

              {/* 3. Sound Witness */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-spine-success">3. Sound Department (Belief)</span>
                  {inspectedTake.belief.sound?.source_document && (
                    <button
                      onClick={() => handleOpenPreviewDoc(inspectedTake.belief.sound?.source_doc_id, inspectedTake.belief.sound?.source_document)}
                      className="text-[11px] text-spine-accent hover:text-spine-accent flex items-center gap-1 font-medium underline"
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
                  <div className="text-xs font-mono text-gray-200 grid grid-cols-2 gap-2">
                    <div>Sound Roll: <span className="text-white font-bold">{inspectedTake.belief.sound?.sound_roll || '--'}</span></div>
                    <div>Timecode In: <span className="text-white">{inspectedTake.belief.sound?.timecode_in || '--'}</span></div>
                    <div>Tracks: <span className="text-white">{inspectedTake.belief.sound?.tracks || 'Poly WAV'}</span></div>
                    <div>Wild Track: <span className="text-white">{inspectedTake.belief.sound?.is_wild_track ? 'YES' : 'NO'}</span></div>
                  </div>
                ) : (
                  <div className="text-xs font-mono text-gray-400 italic">No sound report (Sound ALE / CSV) ingested for this slate yet.</div>
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
                <div className="text-xs font-mono text-gray-200 space-y-2">
                  {inspectedTake.matched_media_files.length > 0 ? (
                    inspectedTake.matched_media_files.map((m, i) => (
                      <div key={i} className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="text-white font-bold text-xs">{m.file_name}</div>
                          <span className="text-[10px] text-spine-success bg-spine-success/60 px-2 py-0.2 rounded border border-spine-success/30">
                            {m.checksum ? `${m.checksum.slice(0, 12)}...` : 'Verified'}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-1.5 text-[11px] text-gray-300 pt-1">
                          <div>Reel/Tape: <span className="text-gray-100 font-semibold">{m.reel_tape || m.camera_roll || '--'}</span></div>
                          <div>Volume: <span className="text-gray-100">{m.volume_name || 'Offload Drive'}</span></div>
                          <div>Codec: <span className="text-cyan-300 font-semibold">{m.codec || 'Linear PCM / ARRIRAW'}</span></div>
                          <div>Recorded: <span className="text-gray-100">{m.recording_date || '--'}</span></div>
                          {m.fps && <div>FPS / ISO: <span className="text-gray-100">{m.fps}fps / {m.iso || 800}EI</span></div>}
                          {m.tstop && <div>T-Stop: <span className="text-gray-100">{m.tstop}</span></div>}
                          <div>Size: <span className="text-gray-100">{(m.file_size_bytes ? m.file_size_bytes / (1024*1024) : 0).toFixed(1)} MB</span></div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-400 italic text-xs">No media offload files registered on DIT volumes yet.</div>
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
                <div className="p-2 rounded-lg bg-spine-accent/20 text-spine-accent border border-spine-accent/30">
                  <FileCode className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm flex items-center gap-2">
                    {previewDoc.filename}
                    {(previewDoc.is_pdf || previewDoc.filename.toLowerCase().endsWith('.pdf')) && (
                      <span className="text-[10px] bg-spine-critical/20 text-spine-critical border border-spine-critical/40 px-1.5 py-0.2 rounded font-mono font-bold">
                        PDF
                      </span>
                    )}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-gray-300 font-mono mt-0.5">
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
                          ? 'bg-spine-accent text-white shadow-sm'
                          : 'text-gray-300 hover:text-white'
                      }`}
                    >
                      📄 Visual PDF
                    </button>
                    <button
                      onClick={() => setPreviewViewMode('text')}
                      className={`px-3 py-1 rounded-md font-medium transition ${
                        previewViewMode === 'text'
                          ? 'bg-spine-accent text-white shadow-sm'
                          : 'text-gray-300 hover:text-white'
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
                  className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-gray-200 hover:text-white rounded-lg text-xs font-medium border border-slate-700 transition flex items-center gap-1.5"
                  title="Open in new tab / Download"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open Tab
                </a>

                <button 
                  onClick={() => setPreviewDoc(null)}
                  className="text-gray-300 hover:text-white text-lg p-1 ml-1"
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
              <div className="p-6 flex-1 overflow-y-auto font-mono text-xs bg-slate-950 text-gray-100 whitespace-pre leading-relaxed select-text">
                {previewDoc.content || '(No text content extracted)'}
              </div>
            )}

            {/* Modal Footer */}
            <div className="px-6 py-2.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-gray-400 font-mono">
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
                <span className="text-xs font-mono text-gray-200 font-bold">Silverstack Camera Thumbnail Frame</span>
              </div>
              <button 
                onClick={() => setEnlargedImage(null)}
                className="text-gray-300 hover:text-white text-lg p-1"
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
                <p className="text-[11px] text-gray-300 mt-0.5">
                  Auto-infers production, shoot day, department & document type
                </p>
              </div>
              <button type="button" onClick={() => setIsUploadOpen(false)} className="text-gray-300 hover:text-white">✕</button>
            </div>

            {uploadFeedback && (
              <div
                className={`text-xs p-3 rounded-lg border ${
                  uploadFeedback.tone === 'error'
                    ? 'bg-spine-critical/20 border-spine-critical/40 text-spine-critical'
                    : uploadFeedback.tone === 'warning'
                    ? 'bg-spine-warning/20 border-spine-warning/40 text-spine-warning'
                    : 'bg-spine-success/40 border-spine-success/40 text-spine-success'
                }`}
              >
                <div className="flex items-start gap-2">
                  <span aria-hidden="true">
                    {uploadFeedback.tone === 'error' ? '✕' : uploadFeedback.tone === 'warning' ? '!' : '✓'}
                  </span>
                  <span className="font-semibold">{uploadFeedback.message}</span>
                </div>

                {uploadFeedback.detail && (
                  <p className="mt-2 pl-5 text-gray-300 font-mono text-[11px] leading-relaxed">
                    {uploadFeedback.detail}
                  </p>
                )}

                {uploadFeedback.warnings && uploadFeedback.warnings.length > 0 && (
                  <ul className="mt-2 pl-5 space-y-1 list-disc list-inside text-spine-warning/90">
                    {uploadFeedback.warnings.map((warning, i) => (
                      <li key={i} className="leading-relaxed">{warning}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              <button
                type="button"
                onClick={() => setUploadMode('file')}
                className={`flex-1 py-1.5 rounded-md font-medium transition ${uploadMode === 'file' ? 'bg-spine-accent text-white' : 'text-gray-300 hover:text-white'}`}
              >
                Upload File (PDF / CSV / ALE)
              </button>
              <button
                type="button"
                onClick={() => setUploadMode('text')}
                className={`flex-1 py-1.5 rounded-md font-medium transition ${uploadMode === 'text' ? 'bg-spine-accent text-white' : 'text-gray-300 hover:text-white'}`}
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
                  <div className="text-xs text-gray-200">
                    {selectedFile ? (
                      <span className="font-mono text-blue-400 font-bold">{selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                    ) : (
                      <>Click to select or drop <span className="text-blue-400 font-bold">PDF, CSV, ALE, or XML</span></>
                    )}
                  </div>
                  <p className="text-[10px] text-gray-400">Auto-detects project name, shoot day & document type</p>
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
              className="w-full py-2 bg-spine-accent hover:brightness-110 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-lg text-xs font-semibold transition"
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
                <div className="w-8 h-8 rounded-lg bg-spine-success/20 border border-spine-success/40 flex items-center justify-center text-spine-success">
                  <Check className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Solve Discrepancy</h3>
                  <p className="text-xs text-gray-300 font-mono">{resolvingDiscrepancy.entity_id}</p>
                </div>
              </div>
              <button
                onClick={() => setResolvingDiscrepancy(null)}
                className="text-gray-300 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            {/* Discrepancy Info */}
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-spine-critical/20 text-spine-critical border border-spine-critical/40 font-bold">
                  {resolvingDiscrepancy.discrepancy_type}
                </span>
                <span className="text-gray-300">{resolvingDiscrepancy.entity_type}</span>
              </div>
              <p className="text-gray-100 text-xs leading-relaxed">{resolvingDiscrepancy.description}</p>
            </div>

            {/* Select Target Card / Roll */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-200 block">
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
                        ? 'bg-spine-accent border-blue-400 text-white shadow-sm font-bold'
                        : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white hover:border-slate-700'
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
                      ? 'bg-spine-accent border-blue-400 text-white font-bold'
                      : 'bg-slate-900 border-slate-800 text-gray-300 hover:text-white'
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
              <label className="text-xs font-bold text-gray-200 block">
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
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs font-medium transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isResolutionSubmitting || (resolutionCardChoice === 'CUSTOM' && !customCardInput.trim())}
                onClick={handleConfirmResolution}
                className="px-4 py-2 rounded-lg bg-spine-success hover:bg-spine-success text-white text-xs font-bold transition flex items-center gap-1.5 shadow disabled:opacity-50"
              >
                {isResolutionSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                Confirm & Reconcile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 1. CREATE REQUIREMENT MODAL */}
      {/* 1. CREATE REQUIREMENT MODAL */}
      {isCreateReqOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-spine-accent/20 border border-spine-accent/40 flex items-center justify-center text-spine-accent">
                  <PlusCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Add Requirement</h3>
                  <p className="text-xs text-spine-accent font-mono">
                    {targetForReq ? `Attaching to: ${targetForReq.target_label}` : 'Select Target Scene, Slate, or Take'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setIsCreateReqOpen(false);
                  setTargetForReq(null);
                }}
                className="text-gray-300 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateRequirementSubmit} className="space-y-3.5 text-xs">
              {/* Target Entity Selector (if opened globally from Requirements Hub) */}
              {!targetForReq && (
                <div className="space-y-1">
                  <label className="font-bold text-gray-200 block">Target Entity (Take or Scene):</label>
                  <select
                    onChange={e => {
                      const val = e.target.value;
                      if (!val) return;
                      const [type, id, label] = val.split('||');
                      setTargetForReq({ target_type: type as any, target_id: id, target_label: label });
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-spine-accent font-mono"
                    defaultValue=""
                  >
                    <option value="" disabled>-- Select a Take or Scene to attach requirement --</option>
                    <optgroup label="🎬 Takes">
                      {takes.map(t => (
                        <option key={`${t.slate}_${t.take_id}`} value={`take||${t.slate}_${t.take_id}||Take ${t.slate} T${t.take_id}`}>
                          Take {t.slate} T{t.take_id} (Scene {t.scene})
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="📜 Scenes">
                      {uniqueScenes.map(sc => (
                        <option key={sc} value={`scene||${sc}||Scene ${sc}`}>
                          Scene {sc}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </div>
              )}

              {/* Title */}
              <div className="space-y-1">
                <label className="font-bold text-gray-200 block">Requirement Title:</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Denoise clapper bleed, VFX cleanup on boom shadow, Re-sync audio..."
                  value={newReqTitle}
                  onChange={e => setNewReqTitle(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-spine-accent"
                  autoFocus
                />
              </div>


              {/* Responsible Assignee (with @ symbol) */}
              <div className="space-y-1">
                <label className="font-bold text-gray-200 flex items-center gap-1">
                  <span>Responsible Assignee:</span>
                  <span className="text-spine-accent font-mono">(receives instant alert)</span>
                </label>
                <select
                  value={newReqAssignee}
                  onChange={e => setNewReqAssignee(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-spine-accent font-mono"
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
                  <label className="font-bold text-gray-200 block">Priority Level:</label>
                  <select
                    value={newReqPriority}
                    onChange={e => setNewReqPriority(e.target.value as RequirementPriority)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-spine-accent"
                  >
                    <option value="low">Low (Editorial polish)</option>
                    <option value="medium">Medium (Standard request)</option>
                    <option value="high">High (Delivery critical)</option>
                    <option value="critical">Critical (Showstopper / Block)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-bold text-gray-200 block">Department Category:</label>
                  <select
                    value={newReqCategory}
                    onChange={e => setNewReqCategory(e.target.value as RequirementCategory)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-spine-accent"
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
                <label className="font-bold text-gray-200 block">Detailed Instructions / Description:</label>
                <textarea
                  rows={3}
                  placeholder="Provide precise instructions for the responsible artist or editor..."
                  value={newReqDesc}
                  onChange={e => setNewReqDesc(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-spine-accent"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreateReqOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingReq || !newReqTitle.trim()}
                  className="px-4 py-2 rounded-lg bg-spine-accent hover:bg-spine-accent disabled:opacity-50 text-white text-xs font-bold transition flex items-center gap-1.5 shadow"
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
                <div className="w-8 h-8 rounded-lg bg-spine-warning/20 border border-spine-warning/40 flex items-center justify-center text-spine-warning">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Requirements Hub</h3>
                  <p className="text-xs text-spine-warning font-mono">{viewingReqsList.target_label}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setViewingReqsList(null);
                  setSelectedReqForResolve(null);
                }}
                className="text-gray-300 hover:text-white p-1"
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
                      ? 'bg-spine-success/20 border-spine-success/30'
                      : 'bg-slate-950 border-slate-800'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase ${
                        req.status === 'resolved'
                          ? 'bg-spine-success/20 text-spine-success border border-spine-success/40'
                          : 'bg-spine-warning/20 text-spine-warning border border-spine-warning/40'
                      }`}>
                        {req.status}
                      </span>
                      <span className="font-bold text-white text-xs">{req.title}</span>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-spine-900/60 text-spine-accent border border-spine-accent/30">
                      {req.priority.toUpperCase()} • {req.category.toUpperCase()}
                    </span>
                  </div>

                  {req.description && (
                    <p className="text-gray-200 text-xs leading-relaxed bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                      {req.description}
                    </p>
                  )}

                  <div className="text-[10px] text-gray-300 font-mono flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/80">
                    <span>Created by <strong className="text-spine-accent">{req.created_by}</strong></span>
                    <span>Responsible: <strong className="text-white">{req.assigned_to}</strong></span>
                    <span>{new Date(req.created_at).toLocaleDateString()}</span>
                  </div>

                  {/* If Resolved: Show Resolution details */}
                  {req.status === 'resolved' && (
                    <div className="p-3 rounded-lg bg-spine-success/40 border border-spine-success/30 space-y-1 text-xs">
                      <div className="flex items-center gap-1.5 text-spine-success font-bold">
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
                        <div className="space-y-2 bg-slate-900 p-3 rounded-xl border border-spine-accent/40">
                          <label className="text-[11px] font-bold text-spine-success block">
                            Resolution Justification / Note:
                          </label>
                          <textarea
                            rows={2}
                            placeholder="e.g. Applied EQ filter to isolate lavalier, audio verified clean for edit..."
                            value={reqResolutionNote}
                            onChange={e => setReqResolutionNote(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-spine-success"
                            autoFocus
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setSelectedReqForResolve(null)}
                              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs rounded-lg"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={isResolvingReqSubmitting || !reqResolutionNote.trim()}
                              onClick={() => handleResolveRequirementSubmit(req.requirement_id)}
                              className="px-3 py-1 bg-spine-success hover:bg-spine-success disabled:opacity-50 text-white text-xs font-bold rounded-lg flex items-center gap-1 transition"
                            >
                              {isResolvingReqSubmitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                              Mark Resolved & Notify Caller ({req.created_by})
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-gray-400 italic">
                            Action required by {req.assigned_to}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedReqForResolve(req);
                              setReqResolutionNote('');
                            }}
                            className="px-3 py-1.5 bg-spine-success/20 hover:bg-spine-success/30 border border-spine-success/40 text-spine-success hover:text-white rounded-lg text-xs font-bold transition flex items-center gap-1"
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
                className="px-3.5 py-1.5 bg-spine-accent/20 hover:bg-spine-accent/30 border border-spine-accent/30 text-spine-accent text-xs font-semibold rounded-lg flex items-center gap-1.5 transition"
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
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs rounded-lg transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Real-Time Live Sync Notification Toast */}
      {liveToast && (

        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 border border-spine-accent/50 text-white px-4 py-3 rounded-2xl shadow-2xl flex items-center gap-3 animate-in fade-in slide-in-from-bottom-5">
          <div className="w-8 h-8 rounded-xl bg-spine-accent/20 border border-spine-accent/40 flex items-center justify-center text-spine-accent shrink-0">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-spine-accent uppercase tracking-wider font-mono">Live Event</span>
              <span className="text-[10px] text-gray-300 font-mono">• Auto-synced</span>
            </div>
            <p className="text-xs font-semibold text-slate-100">{liveToast.message}</p>
          </div>
          <button
            onClick={() => setLiveToast(null)}
            className="text-gray-300 hover:text-white p-1 ml-2 text-xs"
          >
            ✕
          </button>
        </div>
      )}

    {/* Confirmation prompt.
        An in-app dialog rather than window.confirm: embedded and sandboxed browser
        contexts return false from confirm() without ever showing anything, which
        made every guarded action look like a dead button. */}
    {confirmPrompt && (
      <div
        className="fixed inset-0 z-[100] bg-black/70 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={() => { if (!confirmBusy) { setConfirmPrompt(null); setConfirmError(null); } }}
      >
        <div
          className="bg-spine-800 border border-slate-700 rounded-xl shadow-2xl max-w-md w-full p-5"
          onClick={e => e.stopPropagation()}
        >
          <h3 id="confirm-title" className="text-sm font-bold text-white mb-2">{confirmPrompt.title}</h3>
          <p className="text-xs text-gray-300 leading-relaxed mb-4">{confirmPrompt.message}</p>
      {confirmError && (
        <p className="text-xs text-spine-critical bg-spine-critical/10 border border-spine-critical/30 rounded p-2 mb-4">
          {confirmError}
        </p>
      )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              disabled={confirmBusy}
              onClick={() => { setConfirmPrompt(null); setConfirmError(null); }}
              className="px-3 py-1.5 text-xs font-semibold rounded border border-slate-600 text-gray-300 hover:bg-slate-700 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={confirmBusy}
              onClick={async () => {
                const prompt = confirmPrompt;
                setConfirmBusy(true);
                setConfirmError(null);
                try {
                  await prompt.onConfirm();
                  setConfirmPrompt(null);
                } catch (e: any) {
                  // Kept open, showing why. Closing on failure would report the
                  // removal as done when nothing was removed.
                  setConfirmError(e?.message || 'That did not work.');
                } finally {
                  setConfirmBusy(false);
                }
              }}
              className={`px-3 py-1.5 text-xs font-semibold rounded border disabled:opacity-50 ${
                confirmPrompt.destructive
                  ? 'bg-spine-critical/20 border-spine-critical/40 text-spine-critical hover:bg-spine-critical/30'
                  : 'bg-spine-accent/20 border-spine-accent/40 text-spine-accent hover:bg-spine-accent/30'
              }`}
            >
              {confirmBusy ? 'Working...' : confirmPrompt.confirmLabel}
            </button>
          </div>
        </div>
      </div>
    )}

    </div>
  );
}

