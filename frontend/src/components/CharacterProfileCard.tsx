import React from 'react';
import { ShieldCheck, Save, CheckCircle2, X, Maximize2, RotateCw, Sparkles, Users } from 'lucide-react';
import { CharacterProfile } from '../types';
import { PersonalityPolygon } from './PersonalityPolygon';
import { CharacterLinesPanel } from './CharacterLinesPanel';

interface CharacterProfileCardProps {
  selectedCharacter: CharacterProfile;
  characters: CharacterProfile[];
  setCharacters: React.Dispatch<React.SetStateAction<CharacterProfile[]>>;
  savingCharId: string | null;
  charSaveSuccess: string | null;
  charSaveError: string | null;
  handleUpdateCharacter: (char: CharacterProfile) => void;
  generatingPortraitMap: Record<string, boolean>;
  handleGenerateCharacterPortrait: (char: CharacterProfile) => void;
  setEnlargedImage: (img: {url: string, prompt: string, title: string}) => void;
  setSelectedCharId: (id: string) => void;
  /** Which screenplay this cast belongs to. Needed to look up lines. */
  scriptId?: string;
  /** Optional: lets the surrounding view follow a selected line. */
  onGoToScene?: (sceneNumber: string) => void;
}

export function CharacterProfileCard({
  selectedCharacter,
  characters,
  setCharacters,
  savingCharId,
  charSaveSuccess,
  charSaveError,
  handleUpdateCharacter,
  generatingPortraitMap,
  handleGenerateCharacterPortrait,
  setEnlargedImage,
  setSelectedCharId,
  scriptId,
  onGoToScene
}: CharacterProfileCardProps) {
  return (
    <div className="max-w-3xl space-y-6">
      {/* Header Profile Bar */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr bg-spine-800 via-indigo-600 to-pink-500 flex items-center justify-center font-black text-xl text-white shadow-xl shadow-purple-600/30">
            {selectedCharacter.name.charAt(0)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black text-white tracking-wider">{selectedCharacter.name}</h2>
              <span className="px-2 py-0.5 text-[10px] font-extrabold bg-spine-success/20 text-spine-success border border-spine-success/30 rounded-full flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-spine-success" />
                Visual Consistency Locked
              </span>
            </div>
            <p className="text-xs text-gray-300 mt-0.5">
              Dialogue Cues: <strong className="text-spine-accent">{selectedCharacter.dialogue_count}</strong> • Scenes Present: <strong className="text-spine-accent">{selectedCharacter.scenes_present.join(', ') || '1'}</strong>
            </p>
          </div>
        </div>

        <button
          onClick={() => handleUpdateCharacter(selectedCharacter)}
          disabled={savingCharId === selectedCharacter.id}
          className="px-4 py-2 text-xs font-bold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-lg shadow-lg shadow-emerald-600/20 transition flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {savingCharId === selectedCharacter.id ? 'Saving...' : 'Save & Lock Appearance'}
        </button>
      </div>

      {charSaveSuccess && (
        <div className="p-3 bg-spine-success/60 border border-spine-success/40 rounded-lg flex items-center gap-2 text-xs text-spine-success">
          <CheckCircle2 className="w-4 h-4 text-spine-success" />
          Saved. This look is stored against the screenplay and reused in every Gen-AI render featuring this character.
        </div>
      )}

      {charSaveError && (
        <div className="p-3 bg-spine-critical/60 border border-spine-critical/40 rounded-lg flex items-center gap-2 text-xs text-spine-critical">
          <X className="w-4 h-4 text-spine-critical shrink-0" />
          {charSaveError}
        </div>
      )}

      {/* Portrait Showcase Card & Generation */}
      <div className="p-4 bg-slate-900/90 border border-slate-800 rounded-2xl flex items-center justify-between gap-6 shadow-xl">
        <div className="flex items-center gap-5">
          <div className="relative w-28 h-28 rounded-xl overflow-hidden border-2 border-spine-accent/50 bg-black shrink-0 shadow-lg group">
            {selectedCharacter.avatar_url ? (
              <img
                src={selectedCharacter.avatar_url}
                alt={selectedCharacter.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-spine-800 font-black text-3xl text-spine-accent">
                {selectedCharacter.name.charAt(0)}
              </div>
            )}
            {selectedCharacter.avatar_url && (
              <button
                onClick={() =>
                  setEnlargedImage({
                    url: selectedCharacter.avatar_url!,
                    prompt: selectedCharacter.portrait_prompt || `Photorealistic portrait of ${selectedCharacter.name}`,
                    title: `${selectedCharacter.name} - 35mm Master Headshot`
                  })
                }
                className="absolute top-1.5 right-1.5 p-1 bg-black/80 hover:bg-black text-white rounded opacity-0 group-hover:opacity-100 transition"
              >
                <Maximize2 className="w-3 h-3" />
              </button>
            )}
          </div>
          <div>
            <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-spine-accent/20 text-spine-accent border border-spine-accent/30 rounded-full">
              35mm Cinematic Character Still
            </span>
            <h3 className="text-sm font-bold text-white mt-1.5">Photorealistic Portrait &amp; Lookbook Headshot</h3>
            <p className="text-xs text-gray-300 mt-0.5">
              Generates a dedicated 85mm T1.4 portrait frame locking the actor's facial likeness and wardrobe for all camera coverage.
            </p>
          </div>
        </div>

        <button
          onClick={() => handleGenerateCharacterPortrait(selectedCharacter)}
          disabled={generatingPortraitMap[selectedCharacter.id]}
          className="px-4 py-2.5 text-xs font-bold bg-gradient-to-r bg-spine-800 via-indigo-600 to-pink-600 hover:bg-spine-800 hover:to-pink-500 text-white rounded-xl shadow-lg shadow-purple-600/30 transition flex items-center gap-2 shrink-0 disabled:opacity-50"
        >
          {generatingPortraitMap[selectedCharacter.id] ? (
            <>
              <RotateCw className="w-4 h-4 animate-spin" />
              Rendering 35mm Portrait...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Generate AI Portrait Still
            </>
          )}
        </button>
      </div>

      {/* Form Fields */}
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-bold text-gray-200 mb-1">Role / Narrative Archetype</label>
          <input
            type="text"
            value={selectedCharacter.role}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, role: val } : c)));
            }}
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-spine-accent"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-bold text-gray-200">Actor Screen Reference &amp; Physical Appearance</label>
            <span className="text-[10px] font-medium text-spine-accent">Gender, Age &amp; Build</span>
          </div>
          <textarea
            rows={2}
            value={selectedCharacter.actor_reference}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, actor_reference: val } : c)));
            }}
            placeholder="e.g. Early 30s woman, 5'7&quot; wiry athletic build, dark cropped hair, resolute bearing, intense gaze..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-spine-accent font-sans"
          />
          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-wider">Quick Traits:</span>
            {[
              'Woman',
              'Man',
              'Non-Binary',
              '20s',
              '30s',
              '40s',
              '50s+',
              'Athletic build',
              'Wiry frame',
              'Tall & commanding',
              'Broad shoulders'
            ].map(tag => (
              <button
                key={tag}
                type="button"
                onClick={() => {
                  const current = (selectedCharacter.actor_reference || '').trim();
                  const updated = current ? `${current}, ${tag.toLowerCase()}` : `${tag}, `;
                  setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, actor_reference: updated } : c)));
                }}
                className="px-2 py-0.5 text-[10px] font-semibold bg-slate-800 hover:bg-spine-900/60 hover:text-spine-accent text-gray-200 border border-slate-700 hover:border-spine-accent/40 rounded-md transition"
              >
                + {tag}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-gray-300 mt-1">Defines actor gender presentation (e.g. woman, man, non-binary), age, physique, build, hair, and baseline screen presence.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-200 mb-1">Costume, Wardrobe &amp; Props</label>
          <textarea
            rows={2}
            value={selectedCharacter.look_and_costume}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, look_and_costume: val } : c)));
            }}
            placeholder="e.g. Drenched dark linen shirt with rolled-up sleeves, charcoal wool vest, silver pocket watch..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-spine-accent font-sans"
          />
          <p className="text-[10px] text-gray-300 mt-1">Wardrobe textures, fabrics, tailoring, distress level, and accessories.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-200 mb-1">Facial Features &amp; Catchlights</label>
          <textarea
            rows={2}
            value={selectedCharacter.facial_features}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, facial_features: val } : c)));
            }}
            placeholder="e.g. Sharp cheekbones, subtle 5 o'clock shadow, piercing hazel eyes filled with obsessive fervor..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-spine-accent font-sans"
          />
          <p className="text-[10px] text-gray-300 mt-1">Eyes, cheekbones, complexion, expressions, and key facial lighting marks.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-200 mb-1">Personality Traits (Comma-separated)</label>
          <input
            type="text"
            value={selectedCharacter.personality_traits.join(', ')}
            onChange={e => {
              const traits = e.target.value.split(',').map(t => t.trim()).filter(Boolean);
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, personality_traits: traits } : c)));
            }}
            placeholder="e.g. Obsessive, Perfectionist, Haunted, Virtuoso"
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-spine-accent"
          />
        </div>
      </div>

      {/* Personality, and the lines it was read from.
          Kept together deliberately: the polygon is a reading and the lines
          are its evidence, and a reading nobody can check is an assertion
          with a chart around it. */}
      <div className="pt-6 border-t border-slate-800 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PersonalityPolygon
          axes={selectedCharacter.personality_axes}
          name={selectedCharacter.name}
        />
        {scriptId ? (
          <CharacterLinesPanel
            scriptId={scriptId}
            characterName={selectedCharacter.name}
            onGoToScene={onGoToScene}
          />
        ) : (
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-xs text-gray-500">
            Lines appear once this cast is opened from a stored screenplay.
          </div>
        )}
      </div>

      {/* Character Relationship Network Section */}
      <div className="pt-6 border-t border-slate-800 space-y-3.5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Users className="w-4 h-4 text-spine-accent" />
              Dramatic Relationships &amp; Co-Occurrences ({selectedCharacter.relationships?.length || 0})
            </h3>
            <p className="text-xs text-gray-300">
              Tracks co-present scene blocks, dialogue interaction turns, and dramatic relational dynamics.
            </p>
          </div>
        </div>

        {selectedCharacter.relationships && selectedCharacter.relationships.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {selectedCharacter.relationships.map((rel, rIdx) => {
              const targetObj = characters.find(c => c.name === rel.target_character);
              return (
                <div
                  key={rIdx}
                  className="p-3.5 bg-slate-900/70 border border-slate-800 rounded-xl space-y-2 hover:border-spine-accent/50 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-spine-900 border border-spine-accent/40 flex items-center justify-center font-bold text-xs text-spine-accent">
                        {rel.target_character.charAt(0)}
                      </div>
                      <h4 className="text-xs font-bold text-white">{rel.target_character}</h4>
                    </div>
                    {targetObj && (
                      <button
                        onClick={() => setSelectedCharId(targetObj.id)}
                        className="text-[10px] font-bold text-spine-accent hover:text-spine-accent transition"
                      >
                        Inspect →
                      </button>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1">
                    <span className="px-1.5 py-0.5 text-[9px] font-extrabold bg-spine-accent/20 text-spine-accent rounded border border-spine-accent/30">
                      {rel.relationship_type}
                    </span>
                    <span className="px-1.5 py-0.5 text-[9px] font-bold bg-slate-800 text-gray-200 rounded border border-slate-700">
                      {rel.shared_scenes.length > 0 ? `Scenes: ${rel.shared_scenes.join(', ')}` : 'Shared Scene'}
                    </span>
                    {rel.interaction_count > 0 && (
                      <span className="px-1.5 py-0.5 text-[9px] font-bold bg-spine-success/20 text-spine-success rounded border border-spine-success/30">
                        {rel.interaction_count} Dialogue Turns
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-gray-200 line-clamp-2 leading-relaxed">
                    {rel.dynamic_description}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl text-center text-xs text-gray-300">
            No direct multi-character interactions detected in script for {selectedCharacter.name}.
          </div>
        )}
      </div>
    </div>
  );
}
