import { useEffect, useRef, useState } from 'react';
import { Tag as TagIcon, Check, X, Loader2 } from 'lucide-react';
import { EditorialTag, TagTargetType, TagVocabulary } from '../types';

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
  onClear: (targetType: TagTargetType, targetId: string) => Promise<void>;
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
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Reopening shows what is on the server, not what was typed and abandoned the
  // last time the panel was closed.
  useEffect(() => {
    if (!isOpen) return;
    setStatus(tag?.status ?? null);
    setNeeds(tag?.needs ?? []);
    setDescriptors(tag?.descriptors ?? []);
    setNote(tag?.note ?? '');
    setError(null);
  }, [isOpen, tag]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsOpen(false); };
    const onClickAway = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setIsOpen(false);
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
        if (tag) await onClear(targetType, targetId);
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
        onClick={() => setIsOpen(o => !o)}
        className="flex items-center gap-1.5 flex-wrap text-left w-full group"
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
      </button>

      {isOpen && vocabulary && (
        <div
          ref={panelRef}
          className="absolute z-40 mt-2 left-0 w-72 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-3 space-y-3"
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

          {tag?.updated_by && (
            <p className="text-[10px] text-gray-500">
              Last set by {tag.updated_by}
            </p>
          )}

          <button
            onClick={save}
            disabled={isSaving}
            className="w-full flex items-center justify-center gap-1.5 bg-spine-accent hover:bg-spine-accent/80 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition"
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            Save
          </button>
        </div>
      )}
    </div>
  );
}
