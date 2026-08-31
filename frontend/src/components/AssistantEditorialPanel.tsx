import { useEffect, useMemo, useState } from 'react';
import {
  Check, Loader2, Play, Plus, Trash2, UsersRound, Wand2,
} from 'lucide-react';
import {
  deleteProductionCrewMember,
  fetchProductionCrew,
  runAssistantEditorQueue,
  updateProductionCrewMember,
  upsertProductionCrewMember,
} from '../api';
import {
  AssistantQueueResult, CrewDepartment, Production, ProductionCrewMember,
} from '../types';

const ACTIVE_STATUSES = new Set(['Active', 'In Production', 'Principal Photography']);
const DEFAULT_CREW_ROLE = 'Assistant Editor';

type CrewRoleOption = {
  role: string;
  department: CrewDepartment;
};

type CrewRoleGroup = {
  phase: 'Preproduction' | 'Production' | 'Postproduction';
  roles: CrewRoleOption[];
};

function crewRole(role: string, department: CrewDepartment): CrewRoleOption {
  return { role, department };
}

const ROLE_GROUPS: CrewRoleGroup[] = [
  {
    phase: 'Postproduction',
    roles: [
      crewRole('Post-Production Supervisor', 'editorial'),
      crewRole('Post-Production Coordinator', 'editorial'),
      crewRole('Editor', 'editorial'),
      crewRole('Assistant Editor', 'editorial'),
      crewRole('Additional Editor', 'editorial'),
      crewRole('Online Editor', 'editorial'),
      crewRole('Conform Editor', 'editorial'),
      crewRole('Colorist', 'editorial'),
      crewRole('Dailies Colorist', 'editorial'),
      crewRole('VFX Producer', 'vfx'),
      crewRole('VFX Editor', 'vfx'),
      crewRole('Compositor', 'vfx'),
      crewRole('Motion Graphics Artist', 'vfx'),
      crewRole('Supervising Sound Editor', 'sound'),
      crewRole('Dialogue Editor', 'sound'),
      crewRole('ADR Supervisor', 'sound'),
      crewRole('Foley Artist', 'sound'),
      crewRole('Sound Designer', 'sound'),
      crewRole('Re-recording Mixer', 'sound'),
      crewRole('Music Supervisor', 'sound'),
      crewRole('Composer', 'sound'),
      crewRole('Music Editor', 'sound'),
      crewRole('Deliverables Coordinator', 'editorial'),
    ],
  },
  {
    phase: 'Preproduction',
    roles: [
      crewRole('Executive Producer', 'production'),
      crewRole('Producer', 'production'),
      crewRole('Co-Producer', 'production'),
      crewRole('Line Producer', 'production'),
      crewRole('Unit Production Manager', 'production'),
      crewRole('Production Coordinator', 'production'),
      crewRole('Production Accountant', 'production'),
      crewRole('Screenwriter', 'production'),
      crewRole('Casting Director', 'production'),
      crewRole('Casting Associate', 'production'),
      crewRole('Casting Assistant', 'production'),
      crewRole('Location Manager', 'production'),
      crewRole('Location Scout', 'production'),
      crewRole('Production Designer', 'production'),
      crewRole('Art Director', 'production'),
      crewRole('Set Decorator', 'production'),
      crewRole('Costume Designer', 'production'),
      crewRole('Hair Department Head', 'production'),
      crewRole('Makeup Department Head', 'production'),
      crewRole('Storyboard Artist', 'production'),
      crewRole('Previsualization Artist', 'vfx'),
      crewRole('VFX Supervisor', 'vfx'),
      crewRole('Stunt Coordinator', 'production'),
      crewRole('Intimacy Coordinator', 'production'),
    ],
  },
  {
    phase: 'Production',
    roles: [
      crewRole('Director', 'production'),
      crewRole('1st Assistant Director', 'production'),
      crewRole('2nd Assistant Director', 'production'),
      crewRole('2nd 2nd Assistant Director', 'production'),
      crewRole('Script Supervisor', 'production'),
      crewRole('Production Assistant', 'production'),
      crewRole('Director of Photography', 'camera'),
      crewRole('Camera Operator', 'camera'),
      crewRole('Steadicam Operator', 'camera'),
      crewRole('1st Assistant Camera', 'camera'),
      crewRole('2nd Assistant Camera', 'camera'),
      crewRole('Digital Imaging Technician', 'dit'),
      crewRole('Video Assist Operator', 'camera'),
      crewRole('Still Photographer', 'camera'),
      crewRole('Gaffer', 'camera'),
      crewRole('Best Boy Electric', 'camera'),
      crewRole('Electrician', 'camera'),
      crewRole('Key Grip', 'camera'),
      crewRole('Best Boy Grip', 'camera'),
      crewRole('Dolly Grip', 'camera'),
      crewRole('Production Sound Mixer', 'sound'),
      crewRole('Boom Operator', 'sound'),
      crewRole('Sound Utility', 'sound'),
      crewRole('Prop Master', 'production'),
      crewRole('Wardrobe Supervisor', 'production'),
      crewRole('Set Costumer', 'production'),
      crewRole('Key Makeup Artist', 'production'),
      crewRole('Makeup Artist', 'production'),
      crewRole('Key Hair Stylist', 'production'),
      crewRole('Hair Stylist', 'production'),
      crewRole('Special Effects Supervisor', 'production'),
      crewRole('Stunt Performer', 'production'),
      crewRole('Location Assistant', 'production'),
      crewRole('Transportation Coordinator', 'production'),
      crewRole('Craft Services', 'production'),
    ],
  },
];

function departmentForRole(role: string): CrewDepartment {
  for (const group of ROLE_GROUPS) {
    const option = group.roles.find(candidate => candidate.role === role);
    if (option) return option.department;
  }
  return 'general';
}

function isEditorial(member: ProductionCrewMember): boolean {
  return member.department === 'editorial' || member.role.toLowerCase().includes('editor');
}

function defaultCrewForm() {
  return {
    handle: '',
    name: '',
    email: '',
    role: DEFAULT_CREW_ROLE,
    department: departmentForRole(DEFAULT_CREW_ROLE),
  };
}

function messageFromError(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'object' && err && 'detail' in err && typeof err.detail === 'string') {
    return err.detail;
  }
  return fallback;
}

export function AssistantEditorialPanel({
  production,
  shootDays,
  currentUserHandle,
  onChanged,
}: {
  production: Production;
  shootDays: string[];
  currentUserHandle: string;
  onChanged: () => void;
}) {
  const [crew, setCrew] = useState<ProductionCrewMember[]>([]);
  const [crewForm, setCrewForm] = useState(defaultCrewForm);
  const [shootDay, setShootDay] = useState(shootDays[shootDays.length - 1] ?? '31');
  const [assignee, setAssignee] = useState(currentUserHandle);
  const [result, setResult] = useState<AssistantQueueResult | null>(null);
  const [isLoadingCrew, setIsLoadingCrew] = useState(false);
  const [isSavingCrew, setIsSavingCrew] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit = ACTIVE_STATUSES.has(production.status ?? 'Active');
  const defaultDay = useMemo(() => shootDays[shootDays.length - 1] ?? '31', [shootDays]);
  const eligibleEditors = useMemo(
    () => crew.filter(member => member.active && isEditorial(member)),
    [crew],
  );
  const canPlan = canEdit && eligibleEditors.some(
    member => member.handle.toLowerCase() === assignee.toLowerCase(),
  );

  useEffect(() => {
    setShootDay(defaultDay);
    setResult(null);
  }, [defaultDay, production.production_id]);

  useEffect(() => {
    let live = true;
    setIsLoadingCrew(true);
    fetchProductionCrew(production.production_id)
      .then(rows => {
        if (!live) return;
        setCrew(rows);
        setAssignee(current => {
          const currentAssignee = rows.find(
            member => member.active && member.handle.toLowerCase() === current.toLowerCase()
              && isEditorial(member),
          );
          const firstEditor = rows.find(member => member.active && isEditorial(member));
          return (currentAssignee ?? firstEditor)?.handle ?? currentUserHandle;
        });
      })
      .catch(err => {
        if (live) setError(messageFromError(err, 'Could not load production crew'));
      })
      .finally(() => {
        if (live) setIsLoadingCrew(false);
      });
    return () => { live = false; };
  }, [production.production_id, currentUserHandle]);

  const reloadCrew = async () => {
    const rows = await fetchProductionCrew(production.production_id);
    setCrew(rows);
  };

  const updateCrewRole = (role: string) => {
    setCrewForm({ ...crewForm, role, department: departmentForRole(role) });
  };

  const addCrew = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!crewForm.handle.trim() || !crewForm.name.trim()) return;
    setIsSavingCrew(true);
    setError(null);
    try {
      await upsertProductionCrewMember(production.production_id, crewForm);
      setCrewForm(defaultCrewForm());
      await reloadCrew();
      onChanged();
    } catch (err: unknown) {
      setError(messageFromError(err, 'Could not save crew member'));
    } finally {
      setIsSavingCrew(false);
    }
  };

  const toggleCrew = async (member: ProductionCrewMember) => {
    setError(null);
    try {
      await updateProductionCrewMember(production.production_id, member.handle, { active: !member.active });
      await reloadCrew();
      onChanged();
    } catch (err: unknown) {
      setError(messageFromError(err, 'Could not update crew member'));
    }
  };

  const removeCrew = async (member: ProductionCrewMember) => {
    setError(null);
    try {
      await deleteProductionCrewMember(production.production_id, member.handle);
      await reloadCrew();
      onChanged();
    } catch (err: unknown) {
      setError(messageFromError(err, 'Could not remove crew member'));
    }
  };

  const runQueue = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const next = await runAssistantEditorQueue({
        production_id: production.production_id,
        shoot_day: shootDay || defaultDay,
        actor: currentUserHandle,
        assignee,
        max_scenes: 6,
      });
      setResult(next);
      onChanged();
    } catch (err: unknown) {
      setError(messageFromError(err, 'Assistant Editor Queue failed'));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <UsersRound className="w-4 h-4 text-blue-300" aria-hidden />
            Assistant Editorial
          </h3>
          <p className="text-[11px] text-gray-400">
            Production crew and clean-scene batches for end-of-day turnover.
          </p>
        </div>
        <span className={`text-[10px] px-2 py-1 rounded-md border ${
          canEdit
            ? 'text-emerald-200 border-emerald-800 bg-emerald-950/30'
            : 'text-slate-300 border-slate-700 bg-slate-900'
        }`}>
          {canEdit ? 'Active production' : 'Finished production'}
        </span>
      </div>

      {error && (
        <p className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-xl p-3">
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_1.05fr] gap-4">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-300">Production Crew</p>
            {isLoadingCrew && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-500" />}
          </div>

          <div className="space-y-2">
            {crew.map(member => (
              <div
                key={member.handle}
                className={`flex items-center justify-between gap-3 border rounded-xl px-3 py-2 ${
                  member.active ? 'border-slate-800 bg-slate-900/50' : 'border-slate-900 bg-slate-950 opacity-60'
                }`}
              >
                <div className="min-w-0">
                  <p className="text-sm text-white truncate">{member.name}</p>
                  <p className="text-[10px] text-gray-500 truncate">
                    {member.handle} · {member.role}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => toggleCrew(member)}
                    disabled={!canEdit}
                    className="w-7 h-7 inline-flex items-center justify-center rounded-lg border border-slate-700 text-gray-300 disabled:opacity-40"
                    title={member.active ? 'Make inactive' : 'Make active'}
                  >
                    <Check className={`w-3.5 h-3.5 ${member.active ? 'text-emerald-300' : 'text-slate-600'}`} />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeCrew(member)}
                    disabled={!canEdit}
                    className="w-7 h-7 inline-flex items-center justify-center rounded-lg border border-slate-700 text-gray-500 hover:text-red-300 disabled:opacity-40"
                    title="Remove from crew"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            {crew.length === 0 && (
              <p className="text-sm text-gray-400 border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                No crew has been assigned to this production yet.
              </p>
            )}
          </div>

          <form onSubmit={addCrew} className="grid grid-cols-1 sm:grid-cols-2 gap-2 border border-slate-800 rounded-xl p-3 bg-slate-900/40">
            <input
              value={crewForm.name}
              onChange={e => setCrewForm({ ...crewForm, name: e.target.value })}
              disabled={!canEdit}
              placeholder="Name"
              className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white disabled:opacity-40"
            />
            <input
              value={crewForm.handle}
              onChange={e => setCrewForm({ ...crewForm, handle: e.target.value })}
              disabled={!canEdit}
              placeholder="@handle"
              className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white disabled:opacity-40"
            />
            <select
              value={crewForm.role}
              onChange={e => updateCrewRole(e.target.value)}
              disabled={!canEdit}
              className="sm:col-span-2 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 disabled:opacity-40"
              aria-label="Crew role"
            >
              {ROLE_GROUPS.map(group => (
                <optgroup key={group.phase} label={group.phase}>
                  {group.roles.map(({ role }) => (
                    <option key={`${group.phase}-${role}`} value={role}>{role}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            <input
              value={crewForm.email}
              onChange={e => setCrewForm({ ...crewForm, email: e.target.value })}
              disabled={!canEdit}
              placeholder="email"
              className="sm:col-span-2 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 disabled:opacity-40"
            />
            <button
              type="submit"
              disabled={!canEdit || isSavingCrew || !crewForm.name.trim() || !crewForm.handle.trim()}
              className="sm:col-span-2 inline-flex items-center justify-center gap-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
            >
              {isSavingCrew ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Add crew member
            </button>
          </form>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
            <Wand2 className="w-3.5 h-3.5 text-cyan-300" aria-hidden />
            Assistant Editor Queue
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-[0.75fr_1fr_auto] gap-2">
            <select
              value={shootDay}
              onChange={e => setShootDay(e.target.value)}
              disabled={!canEdit}
              className="bg-slate-900 border border-slate-700 text-xs px-2 py-1.5 rounded-lg text-gray-200 disabled:opacity-40"
              aria-label="Assistant queue shoot day"
            >
              {Array.from(new Set([defaultDay, ...shootDays, '31'])).map(day => (
                <option key={day} value={day}>Day {day}</option>
              ))}
            </select>
            <select
              value={assignee}
              onChange={e => setAssignee(e.target.value)}
              disabled={!canEdit || eligibleEditors.length === 0}
              className="bg-slate-900 border border-slate-700 text-xs px-2 py-1.5 rounded-lg text-gray-200 disabled:opacity-40"
              aria-label="Assistant queue responsible editor"
            >
              {eligibleEditors.length === 0 ? (
                <option value={currentUserHandle}>Add editorial crew first</option>
              ) : eligibleEditors.map(member => (
                <option key={member.handle} value={member.handle}>
                  {member.handle} - {member.role}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={runQueue}
              disabled={!canPlan || isRunning}
              title={canPlan ? 'Plan assistant editor batch' : 'Add an active assistant editor to this production crew first'}
              className="inline-flex items-center justify-center gap-1.5 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
            >
              {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Plan
            </button>
          </div>

          {result && (
            <div className="space-y-3">
              <p className="text-sm text-gray-200 border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                {result.summary}
              </p>
              <div className="space-y-2">
                {result.scenes.map(scene => (
                  <div key={scene.scene} className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-white">{scene.target_label}</p>
                      <span className="text-[10px] text-cyan-200 border border-cyan-900 rounded px-1.5 py-0.5">
                        score {scene.clean_score}
                      </span>
                      <span className="text-[10px] text-gray-500">{scene.assigned_to}</span>
                    </div>
                    <p className="text-[11px] text-gray-400 mt-1">
                      {scene.takes_count} take(s), {scene.circled_takes_count} circled, {scene.document_count} document(s)
                    </p>
                    <p className="text-[11px] text-gray-500 mt-1">{scene.reasons.join('; ')}</p>
                  </div>
                ))}
                {result.scenes.length === 0 && (
                  <p className="text-sm text-gray-400 border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                    No clean scene batch was ready for this day.
                  </p>
                )}
              </div>
              {result.requirement_actions.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {result.requirement_actions.map(action => (
                    <span
                      key={`${action.requirement_id}-${action.action}`}
                      className="text-[11px] border border-slate-800 rounded-lg px-2 py-1 text-gray-300 bg-slate-900/50"
                    >
                      {action.action} {action.requirement_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {!result && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] text-gray-400">
              <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                <p className="text-gray-200 font-semibold">Find clean scenes</p>
                <p>paperwork, audio, offload, no blockers</p>
              </div>
              <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                <p className="text-gray-200 font-semibold">Prioritize</p>
                <p>circled takes and evidence density</p>
              </div>
              <div className="border border-slate-800 rounded-xl p-3 bg-slate-900/50">
                <p className="text-gray-200 font-semibold">Assign</p>
                <p>scene tasks owned by the assistant editor</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
