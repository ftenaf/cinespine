import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Tag as TagIcon, Check, X, Loader2, History, ChevronDown } from 'lucide-react';
import { EditorialTag, TagHistoryEntry, TagTargetType, TagVocabulary } from '../types';
import { fetchTagHistory } from '../api';

/**
 * The editorial tag on one scene or shot: how far along it is, what work it
 * still needs, and what kind of shot it is.
 *
 * The three axes are shown apart rather than as one row of chips, because they
 * are read for different reasons -- progress, outstanding work, and what the
 * shot is -- and a single undifferentiated row makes "what is left to do"
 * something the reader has to work out.
 */

const STATUS_STYLES: Record<string, string> = {
  finished_shooting: 'bg-slate-600/90 text-white',
  covered_per_script: 'bg-indigo-600/90 text-white',
  ready_to_edit: 'bg-blue-600/90 text-white',
  mounted: 'bg-emerald-600/90 text-white',
  finished: 'bg-emerald-400/90 text-black',
};

const NEED_ICONS: Record<string, string> = {
  sfx: '🔊',
  subtitles: '💬',
  translation: '🌐',
};

/** "4m", "3h", "2d" — enough to place a change without spelling out a date. */
function howLongAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

/**
 * What this entry changed, against the one before it.
 *
 * The trail stores whole states, so showing them raw would leave the reader to
 * work out what actually moved. An entry that repeats the state before it says
 * nothing and is described as such rather than being dropped, because a save
 * that changed nothing is still someone having looked.
 */
function describeChange(
  entry: TagHistoryEntry,
  previous: TagHistoryEntry | undefined,
  labelFor: (kind: 'statuses' | 'needs' | 'descriptors', key: string) => string,
): string[] {
  if (entry.action === 'cleared') return ['removed the tag'];

  const parts: string[] = [];
  if (entry.status !== (previous?.status ?? null)) {
    parts.push(entry.status ? `set ${labelFor('statuses', entry.status)}` : 'cleared the status');
  }

  const moved = (kind: 'needs' | 'descriptors') => {
    const before = new Set(previous?.[kind] ?? []);
    const after = new Set(entry[kind]);
    for (const key of after) if (!before.has(key)) parts.push(`added ${labelFor(kind, key)}`);
    for (const key of before) if (!after.has(key)) parts.push(`cleared ${labelFor(kind, key)}`);
  };
  moved('needs');
  moved('descriptors');

  if ((entry.note ?? null) !== (previous?.note ?? null)) {
    parts.push(entry.note ? 'changed the note' : 'removed the note');
  }

  return parts.length ? parts : ['saved without changing anything'];
}

interface Props {
  productionId: string;
  targetType: TagTargetType;
  targetId: string;
  /** The tag as last read from the server, or undefined when untagged. */
  tag?: EditorialTag;
  vocabulary: TagVocabulary | null;
  currentUserHandle?: string;
  onSave: (payload: {
    production_id: string;
    target_type: TagTargetType;
    target_id: string;
    status: string | null;
    needs: string[];
    descriptors: string[];
    note: string | null;
    updated_by?: string | null;
  }) => Promise<void>;
  onClear: (targetType: TagTargetType, targetId: string, clearedBy?: string | null) => Promise<void>;
}

export function EditorialTagBar({
  productionId, targetType, targetId, tag, vocabulary, currentUserHandle, onSave, onClear,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<string | null>(tag?.status ?? null);
  const [needs, setNeeds] = useState<string[]>(tag?.needs ?? []);
  const [descriptors, setDescriptors] = useState<string[]>(tag?.descriptors ?? []);
  const [note, setNote] = useState(tag?.note ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trail, setTrail] = useState<TagHistoryEntry[] | null>(null);
  const [isTrailOpen, setIsTrailOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);

  // Reopening shows what is on the server, not what was typed and abandoned the
  // last time the panel was closed.
  useEffect(() => {
    if (!isOpen) return;
    setStatus(tag?.status ?? null);
    setNeeds(tag?.needs ?? []);
    setDescriptors(tag?.descriptors ?? []);
    setNote(tag?.note ?? '');
    setError(null);
    setIsTrailOpen(false);
    setTrail(null);
  }, [isOpen, tag]);

  // Fetched when the trail is asked for, not when the panel opens: most opens
  // are to change something, and a request per card would be a request per take
  // on the page.
  useEffect(() => {
    if (!isTrailOpen || trail) return;
    let cancelled = false;
    fetchTagHistory(productionId, targetType, targetId)
      .then(entries => { if (!cancelled) setTrail(entries); })
      .catch(() => { if (!cancelled) setTrail([]); });
    return () => { cancelled = true; };
  }, [isTrailOpen, trail, productionId, targetType, targetId]);

  // The panel is rendered into the body rather than inside the card, because
  // the card and the main column are both overflow-hidden and a clip cannot be
  // escaped with z-index. Living outside the card means positioning it by hand
  // against the button that opened it.
  useLayoutEffect(() => {
    if (!isOpen) { setAnchor(null); return; }

    const place = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const width = 288;        // w-72
      const estimated = 420;    // tall enough for the panel with its trail open
      const margin = 8;

      // Pulled back from the right edge, and flipped above the button when it
      // would otherwise run off the bottom, so a card at the edge of the grid
      // still opens a whole panel rather than a clipped one.
      const left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
      const below = rect.bottom + margin;
      const top = below + estimated > window.innerHeight
        ? Math.max(margin, rect.top - estimated - margin)
        : below;
      setAnchor({ top, left });
    };

    place();
    // Capture phase, so the panel follows a scroll in any container rather than
    // only the window.
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsOpen(false); };
    const onClickAway = (e: MouseEvent) => {
      const target = e.target as Node;
      // The trigger is outside the panel now, so a click on it must not be
      // read as a click away -- that would close and reopen in one gesture.
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClickAway);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClickAway);
    };
  }, [isOpen]);

  const labelFor = (kind: 'statuses' | 'needs' | 'descriptors', key: string) =>
    vocabulary?.[kind].find(e => e.key === key)?.label ?? key;

  const toggle = (list: string[], key: string) =>
    list.includes(key) ? list.filter(k => k !== key) : [...list, key];

  const save = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const isEmpty = !status && needs.length === 0 && descriptors.length === 0 && !note.trim();
      // Tagged with nothing and never tagged read the same on a board, so an
      // emptied tag is removed rather than stored as a blank row.
      if (isEmpty) {
        if (tag) await onClear(targetType, targetId, currentUserHandle ?? null);
      } else {
        await onSave({
          production_id: productionId,
          target_type: targetType,
          target_id: targetId,
          status,
          needs,
          descriptors,
          note: note.trim() || null,
          updated_by: currentUserHandle ?? null,
        });
      }
      setIsOpen(false);
    } catch (e: any) {
      setError(e?.detail || e?.message || 'Could not save');
    } finally {
      setIsSaving(false);
    }
  };

  const hasAnything = !!(tag && (tag.status || tag.needs.length || tag.descriptors.length));

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(o => !o)}
        className="flex items-center gap-1.5 flex-wrap text-left w-full group rounded-md px-1 -mx-1 py-0.5 hover:bg-white/5 transition"
        title={`Editorial status for ${targetType} ${targetId}`}
      >
        {tag?.status && (
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
            STATUS_STYLES[tag.status] ?? 'bg-slate-600/90 text-white'}`}>
            {labelFor('statuses', tag.status)}
          </span>
        )}

        {tag?.descriptors.map(key => (
          <span key={key}
            className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-200 border border-amber-500/30">
            {labelFor('descriptors', key)}
          </span>
        ))}

        {/* Outstanding work reads as a to-do, so it is styled as one rather than
            as another status chip. */}
        {tag?.needs.map(key => (
          <span key={key}
            className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-rose-500/15 text-rose-200 border border-rose-500/30"
            title={`Still needs ${labelFor('needs', key).toLowerCase()}`}>
            {NEED_ICONS[key] ?? '•'} {labelFor('needs', key)}
          </span>
        ))}

        {!hasAnything && (
          <span className="text-[10px] text-gray-500 group-hover:text-gray-300 flex items-center gap-1 transition">
            <TagIcon className="w-3 h-3" /> Tag {targetType}
          </span>
        )}

        {/* An affordance that survives being tagged. Untagged, "Tag shot" reads
            as a control on its own; tagged, the chips alone are indistinguishable
            from the read-only badges beside them -- ⭐ Circled Take and the rest
            -- so wherever somebody meets this already tagged, it reads as a
            display and nobody tries to click it. */}
        {hasAnything && (
          <ChevronDown
            className="w-3 h-3 text-gray-600 group-hover:text-gray-300 transition shrink-0"
            aria-hidden
          />
        )}
      </button>

      {isOpen && vocabulary && anchor && createPortal(
        <div
          ref={panelRef}
          style={{ top: anchor.top, left: anchor.left }}
          className="fixed z-[100] w-72 max-h-[80vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-3 space-y-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white">
              {targetType === 'shot' ? 'Shot' : 'Scene'} {targetId}
            </span>
            <button onClick={() => setIsOpen(false)} className="text-gray-500 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Progress</p>
            <div className="flex flex-wrap gap-1">
              {vocabulary.statuses.map(s => (
                <button
                  key={s.key}
                  title={s.description}
                  onClick={() => setStatus(status === s.key ? null : s.key)}
                  className={`text-[10px] px-2 py-1 rounded-md border transition ${
                    status === s.key
                      ? 'bg-spine-accent text-white border-spine-accent'
                      : 'border-slate-700 text-gray-300 hover:border-slate-500'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Still needs</p>
            <div className="flex flex-wrap gap-1">
              {vocabulary.needs.map(n => (
                <button
                  key={n.key}
                  title={n.description}
                  onClick={() => setNeeds(toggle(needs, n.key))}
                  className={`text-[10px] px-2 py-1 rounded-md border transition ${
                    needs.includes(n.key)
                      ? 'bg-rose-500/20 text-rose-200 border-rose-500/50'
                      : 'border-slate-700 text-gray-300 hover:border-slate-500'
                  }`}
                >
                  {NEED_ICONS[n.key] ?? '•'} {n.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Kind of shot</p>
            <div className="flex flex-wrap gap-1">
              {vocabulary.descriptors.map(d => (
                <button
                  key={d.key}
                  title={d.description}
                  onClick={() => setDescriptors(toggle(descriptors, d.key))}
                  className={`text-[10px] px-2 py-1 rounded-md border transition ${
                    descriptors.includes(d.key)
                      ? 'bg-amber-500/20 text-amber-200 border-amber-500/50'
                      : 'border-slate-700 text-gray-300 hover:border-slate-500'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <textarea
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Note (optional)"
            rows={2}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-spine-accent resize-none"
          />

          {error && <p className="text-[10px] text-spine-critical">{error}</p>}

          {/* The trail. A tag says what is true now; this says who said so and
              when, which is the question asked when a board and the floor
              disagree. Offered on every target, not only tagged ones: a tag
              that was removed still has a history worth reading. */}
          <div className="border-t border-slate-800 pt-2">
            <button
              onClick={() => setIsTrailOpen(o => !o)}
              className="flex items-center gap-1.5 text-[10px] text-gray-400 hover:text-white transition"
            >
              <History className="w-3 h-3" />
              {isTrailOpen ? 'Hide history' : 'History'}
              {tag?.updated_by && !isTrailOpen && (
                <span className="text-gray-500">· last by {tag.updated_by}</span>
              )}
            </button>

            {isTrailOpen && (
              <div className="mt-2 max-h-40 overflow-y-auto pr-1 space-y-1.5">
                {trail === null && (
                  <p className="text-[10px] text-gray-500 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Reading the trail…
                  </p>
                )}
                {trail?.length === 0 && (
                  // Recording started when the feature did, so a tag set before
                  // that has no trail. Saying nothing here would read as a bug.
                  <p className="text-[10px] text-gray-500">
                    Nothing recorded yet for this {targetType}.
                  </p>
                )}
                {trail?.map((entry, i) => (
                  <div key={entry.event_id} className="flex gap-2 text-[10px] leading-snug">
                    <span
                      className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${
                        entry.action === 'cleared' ? 'bg-gray-600' : 'bg-spine-accent'
                      }`}
                    />
                    <div className="min-w-0">
                      <span className="text-gray-200">
                        {entry.actor ?? 'someone'}
                      </span>{' '}
                      <span className="text-gray-400">
                        {describeChange(entry, trail[i + 1], labelFor).join(', ')}
                      </span>
                      <span className="text-gray-600" title={entry.created_at}>
                        {' · '}{howLongAgo(entry.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={save}
            disabled={isSaving}
            className="w-full flex items-center justify-center gap-1.5 bg-spine-accent hover:bg-spine-accent/80 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition"
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            Save
          </button>
        </div>,
        document.body,
      )}
    </div>
  );
}
