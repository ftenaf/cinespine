import { useEffect, useMemo, useState } from 'react';
import {
  Clapperboard, Plus, Pencil, Trash2, Check, Loader2, AlertTriangle,
  BookOpen, CalendarDays, Layers, Film, ListTodo,
} from 'lucide-react';
import { LinkedScript, Production, Requirement, UserProfile } from '../types';
import {
  createProduction, deleteProduction, fetchLinkedScript, fetchProductionVocabulary,
  fetchRequirements, updateProduction,
} from '../api';
import { summarizeRequirements } from '../requirementsBoard';
import { ProductionDashboardPanel } from './ProductionDashboard';
import { RequirementsBoard } from './RequirementsBoard';

/**
 * The productions section: every production in one place, with the progress
 * board for whichever one is selected.
 *
 * Registering a production used to be possible and then quietly stopped being
 * so during a redesign, leaving the app able to create productions through its
 * API and not through its interface. Everything else -- takes, tags, the
 * linked screenplay -- hangs off a production id, so having nowhere to see or
 * name one was a hole in the middle of the app.
 */

const STATUS_STYLES: Record<string, string> = {
  'Active': 'bg-blue-600/80 text-white',
  'In Production': 'bg-indigo-600/80 text-white',
  'Principal Photography': 'bg-emerald-600/80 text-white',
  'Wrapped': 'bg-slate-600/80 text-white',
  'Archived': 'bg-slate-800 text-gray-400 border border-slate-700',
};

/** The form a production id is stored under, previewed as the user types. */
function normalizeId(raw: string): string {
  return raw.trim().toUpperCase().split(/\s+/).join('_');
}

function when(iso?: string | null): string {
  if (!iso) return 'never';
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

function Stat({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
      {icon}
      <span className="font-mono text-gray-200">{value}</span>
      <span>{label}</span>
    </div>
  );
}

interface CardProps {
  production: Production;
  script: LinkedScript | null;
  requirements: Requirement[];
  isSelected: boolean;
  statuses: string[];
  onSelect: () => void;
  onOpen: () => void;
  onChanged: () => void;
}

function ProductionCard({
  production, script, requirements, isSelected, statuses, onSelect, onOpen, onChanged,
}: CardProps) {
  const owed = summarizeRequirements(requirements);
  const [mode, setMode] = useState<'idle' | 'editing' | 'confirming'>('idle');
  const [draft, setDraft] = useState({
    name: production.name,
    director: production.director ?? '',
    status: production.status ?? 'Active',
    description: production.description ?? '',
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEditing = () => {
    setDraft({
      name: production.name,
      director: production.director ?? '',
      status: production.status ?? 'Active',
      description: production.description ?? '',
    });
    setError(null);
    setMode('editing');
  };

  const save = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await updateProduction(production.production_id, draft);
      setMode('idle');
      onChanged();
    } catch (e: any) {
      setError(e?.detail ?? e?.message ?? 'Could not save this production');
    } finally {
      setIsSaving(false);
    }
  };

  const remove = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await deleteProduction(production.production_id);
      setMode('idle');
      onChanged();
    } catch (e: any) {
      // A 409 explains exactly what is still filed under this production.
      setError(e?.detail ?? e?.message ?? 'Could not delete this production');
      setMode('idle');
    } finally {
      setIsSaving(false);
    }
  };

  const isEmpty = production.total_events === 0;

  return (
    <div
      onClick={onSelect}
      className={`rounded-2xl border p-4 space-y-3 cursor-pointer transition ${
        isSelected
          ? 'bg-slate-900 border-spine-accent shadow-lg shadow-blue-900/20'
          : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
      }`}
    >
      {mode === 'editing' ? (
        <div className="space-y-2" onClick={e => e.stopPropagation()}>
          <input
            value={draft.name}
            onChange={e => setDraft({ ...draft, name: e.target.value })}
            placeholder="Production name"
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
          />
          <div className="flex gap-2">
            <input
              value={draft.director}
              onChange={e => setDraft({ ...draft, director: e.target.value })}
              placeholder="Director"
              className="flex-1 min-w-0 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200"
            />
            <select
              value={draft.status}
              onChange={e => setDraft({ ...draft, status: e.target.value })}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200"
            >
              {statuses.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <textarea
            value={draft.description}
            onChange={e => setDraft({ ...draft, description: e.target.value })}
            placeholder="What this production is"
            rows={2}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={save}
              disabled={isSaving || !draft.name.trim()}
              className="flex items-center gap-1 text-xs bg-spine-accent hover:bg-blue-600 text-white px-2.5 py-1 rounded-lg disabled:opacity-50"
            >
              {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
              Save
            </button>
            <button
              onClick={() => { setMode('idle'); setError(null); }}
              className="text-xs text-gray-400 hover:text-white px-2 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-bold text-white truncate">{production.name}</p>
              <p className="text-[10px] font-mono text-gray-500">{production.production_id}</p>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-md shrink-0 ${
              STATUS_STYLES[production.status ?? 'Active'] ?? 'bg-slate-700 text-white'
            }`}>
              {production.status ?? 'Active'}
            </span>
          </div>

          {production.director && (
            <p className="text-[11px] text-gray-400">Dir. {production.director}</p>
          )}
          {production.description && (
            <p className="text-[11px] text-gray-500 line-clamp-2">{production.description}</p>
          )}

          {production.origin === 'auto' && (
            <p className="text-[10px] text-amber-300/70 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 shrink-0" aria-hidden />
              Created from an uploaded filename, not registered by anyone.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 border-t border-slate-800">
            <Stat
              icon={<CalendarDays className="w-3 h-3" />}
              value={String(production.shoot_days.length)}
              label={production.shoot_days.length === 1 ? 'shoot day' : 'shoot days'}
            />
            <Stat icon={<Film className="w-3 h-3" />} value={String(production.total_takes)} label="takes" />
            <Stat icon={<Layers className="w-3 h-3" />} value={String(production.total_events)} label="events" />
            <span className="text-[11px] text-gray-500">Last activity {when(production.last_activity)}</span>
          </div>

          {/* What this production still owes, so the list answers "where are
              the impediments" without opening each one in turn. */}
          <p className="text-[11px] flex items-center gap-1.5">
            <ListTodo className="w-3 h-3 shrink-0 text-gray-500" aria-hidden />
            {owed.outstanding === 0 ? (
              <span className="text-gray-500">Nothing outstanding</span>
            ) : (
              <span className="text-gray-300">
                {owed.outstanding} outstanding
                {owed.blocked > 0 && (
                  <span className="text-red-300"> · {owed.blocked} blocked</span>
                )}
              </span>
            )}
          </p>

          <p className="text-[11px] flex items-center gap-1.5">
            <BookOpen className="w-3 h-3 shrink-0 text-gray-500" aria-hidden />
            {script ? (
              <span className="text-gray-300 truncate">{script.title ?? script.script_id}</span>
            ) : (
              <span className="text-gray-500">
                No screenplay attached — attach one in the Screenplay Studio.
              </span>
            )}
          </p>

          {error && (
            <p className="text-[11px] text-red-300 bg-red-950/40 border border-red-900 rounded-lg p-2">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2 pt-1" onClick={e => e.stopPropagation()}>
            <button
              onClick={onOpen}
              className="text-xs bg-spine-accent hover:bg-blue-600 text-white px-2.5 py-1 rounded-lg"
            >
              Open in Spine
            </button>
            <button
              onClick={startEditing}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-white px-2 py-1 rounded-lg hover:bg-white/5"
            >
              <Pencil className="w-3 h-3" /> Edit
            </button>
            {mode === 'confirming' ? (
              <span className="flex items-center gap-2 text-xs text-gray-300">
                Delete it?
                <button onClick={remove} className="text-red-400 hover:text-red-300 font-semibold">
                  Yes
                </button>
                <button onClick={() => setMode('idle')} className="text-gray-500 hover:text-white">
                  No
                </button>
              </span>
            ) : (
              <button
                onClick={() => { setError(null); setMode('confirming'); }}
                title={isEmpty
                  ? 'Delete this production'
                  : 'This production holds work; deleting it will be refused'}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-300 px-2 py-1 rounded-lg hover:bg-white/5"
              >
                <Trash2 className="w-3 h-3" /> Delete
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function NewProductionForm({ onCreated, onCancel }: {
  onCreated: (productionId: string) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({ production_id: '', name: '', director: '', description: '' });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalized = normalizeId(form.production_id || form.name);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!normalized || !form.name.trim()) return;
    setIsSaving(true);
    setError(null);
    try {
      const created = await createProduction({
        production_id: normalized,
        name: form.name.trim(),
        director: form.director.trim() || undefined,
        description: form.description.trim() || undefined,
      });
      onCreated(created.production_id);
    } catch (e: any) {
      setError(e?.detail ?? e?.message ?? 'Could not create this production');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-spine-accent/50 bg-slate-900 p-4 space-y-3"
    >
      <p className="text-sm font-bold text-white">New production</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          autoFocus
          value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })}
          placeholder="Production name"
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
        />
        <input
          value={form.director}
          onChange={e => setForm({ ...form, director: e.target.value })}
          placeholder="Director"
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-gray-200"
        />
      </div>
      <input
        value={form.production_id}
        onChange={e => setForm({ ...form, production_id: e.target.value })}
        placeholder="Production ID (defaults to the name)"
        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-sm font-mono text-gray-200"
      />
      {normalized && (
        // Shown before saving, because this id is what every take, tag and
        // filename will be filed under and it cannot be changed afterwards.
        <p className="text-[11px] text-gray-500">
          Filed under <span className="font-mono text-gray-300">{normalized}</span> — this cannot be
          changed later, since every take and tag is filed under it.
        </p>
      )}
      <textarea
        value={form.description}
        onChange={e => setForm({ ...form, description: e.target.value })}
        placeholder="What this production is"
        rows={2}
        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200"
      />
      {error && (
        <p className="text-[11px] text-red-300 bg-red-950/40 border border-red-900 rounded-lg p-2">
          {error}
        </p>
      )}
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={isSaving || !form.name.trim() || !normalized}
          className="flex items-center gap-1 text-xs bg-spine-accent hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
        >
          {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          Create production
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-gray-400 hover:text-white px-2 py-1.5">
          Cancel
        </button>
      </div>
    </form>
  );
}

interface HubProps {
  productions: Production[];
  selectedProductionId: string;
  onSelect: (productionId: string) => void;
  /** Select the production and switch to the spine view. */
  onOpen: (productionId: string) => void;
  /** Reload the production list after a create, edit or delete. */
  onChanged: () => void;
  /** Changes when a tag changes anywhere, so the board follows live edits. */
  tagRevision: number;
  /** Who the requirements can be handed to. */
  team: UserProfile[];
  currentUserHandle: string;
}

export function ProductionsHub({
  productions, selectedProductionId, onSelect, onOpen, onChanged, tagRevision,
  team, currentUserHandle,
}: HubProps) {
  const [isCreating, setIsCreating] = useState(false);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [scripts, setScripts] = useState<Record<string, LinkedScript | null>>({});
  const [requirements, setRequirements] = useState<Record<string, Requirement[]>>({});
  // Bumped whenever the board changes something, so the cards' counts follow.
  const [requirementRevision, setRequirementRevision] = useState(0);

  useEffect(() => {
    fetchProductionVocabulary()
      .then(v => setStatuses(v.statuses))
      // The edit form falls back to the production's current status alone,
      // which is still editable in every other field.
      .catch(() => setStatuses([]));
  }, []);

  const productionIds = useMemo(
    () => productions.map(p => p.production_id).join(','),
    [productions],
  );

  useEffect(() => {
    let live = true;
    Promise.all(
      productions.map(p =>
        fetchLinkedScript(p.production_id)
          .then(script => [p.production_id, script] as const)
          .catch(() => [p.production_id, null] as const),
      ),
    ).then(pairs => {
      if (live) setScripts(Object.fromEntries(pairs));
    });
    return () => { live = false; };
  }, [productionIds]);

  useEffect(() => {
    let live = true;
    Promise.all(
      productions.map(p =>
        fetchRequirements({ production_id: p.production_id })
          .then(rows => [p.production_id, rows] as const)
          // A production whose requirements cannot be read shows no count
          // rather than a wrong one.
          .catch(() => [p.production_id, [] as Requirement[]] as const),
      ),
    ).then(pairs => {
      if (live) setRequirements(Object.fromEntries(pairs));
    });
    return () => { live = false; };
  }, [productionIds, tagRevision, requirementRevision]);

  const selected = productions.find(p => p.production_id === selectedProductionId);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Clapperboard className="w-5 h-5 text-blue-400" />
            Productions
          </h2>
          <p className="text-xs text-gray-400">
            Every production in the spine, and how far along the one you pick is.
          </p>
        </div>
        {!isCreating && (
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-1.5 text-xs font-semibold bg-spine-accent hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg"
          >
            <Plus className="w-3.5 h-3.5" /> New production
          </button>
        )}
      </div>

      {isCreating && (
        <NewProductionForm
          onCancel={() => setIsCreating(false)}
          onCreated={productionId => {
            setIsCreating(false);
            onChanged();
            onSelect(productionId);
          }}
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {productions.map(p => (
          <ProductionCard
            key={p.production_id}
            production={p}
            script={scripts[p.production_id] ?? null}
            requirements={requirements[p.production_id] ?? []}
            isSelected={p.production_id === selectedProductionId}
            statuses={statuses.length ? statuses : [p.status ?? 'Active']}
            onSelect={() => onSelect(p.production_id)}
            onOpen={() => onOpen(p.production_id)}
            onChanged={onChanged}
          />
        ))}
      </div>

      {productions.length === 0 && (
        <p className="text-sm text-gray-400 bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
          No productions yet. Register one to start filing paperwork against it.
        </p>
      )}

      {selected && (
        <div className="space-y-3 pt-2 border-t border-slate-800">
          <div className="flex items-baseline gap-2">
            <h3 className="text-sm font-bold text-white">Progress</h3>
            <span className="text-xs text-gray-400">{selected.name}</span>
          </div>
          {/* The board reads a whole production, not one shoot day, which is
              why it belongs here rather than beside the day-by-day views. */}
          <ProductionDashboardPanel productionId={selected.production_id} reloadKey={tagRevision} />

          <div className="flex items-baseline gap-2 pt-2">
            <h3 className="text-sm font-bold text-white">Requirements</h3>
            <span className="text-xs text-gray-400">
              What {selected.name} still owes, across every shoot day
            </span>
          </div>
          <RequirementsBoard
            productionId={selected.production_id}
            team={team}
            currentUserHandle={currentUserHandle}
            reloadKey={tagRevision + requirementRevision}
            onChanged={() => setRequirementRevision(v => v + 1)}
          />
        </div>
      )}
    </section>
  );
}
