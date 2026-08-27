import React from 'react';
import { ShieldCheck, Save, CheckCircle2, X, Maximize2, RotateCw, Sparkles, Users } from 'lucide-react';
import { CharacterProfile } from '../types';

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
  setSelectedCharId
}: CharacterProfileCardProps) {
  return (
    <div className="max-w-3xl space-y-6">
      {/* Header Profile Bar */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-pink-500 flex items-center justify-center font-black text-xl text-white shadow-xl shadow-purple-600/30">
            {selectedCharacter.name.charAt(0)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black text-white tracking-wider">{selectedCharacter.name}</h2>
              <span className="px-2 py-0.5 text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-full flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                Visual Consistency Locked
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Dialogue Cues: <strong className="text-purple-300">{selectedCharacter.dialogue_count}</strong> • Scenes Present: <strong className="text-purple-300">{selectedCharacter.scenes_present.join(', ') || '1'}</strong>
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
        <div className="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-lg flex items-center gap-2 text-xs text-emerald-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          Saved. This look is stored against the screenplay and reused in every Gen-AI render featuring this character.
        </div>
      )}

      {charSaveError && (
        <div className="p-3 bg-red-950/60 border border-red-500/40 rounded-lg flex items-center gap-2 text-xs text-red-200">
          <X className="w-4 h-4 text-red-400 shrink-0" />
          {charSaveError}
        </div>
      )}

      {/* Portrait Showcase Card & Generation */}
      <div className="p-4 bg-slate-900/90 border border-slate-800 rounded-2xl flex items-center justify-between gap-6 shadow-xl">
        <div className="flex items-center gap-5">
          <div className="relative w-28 h-28 rounded-xl overflow-hidden border-2 border-purple-500/50 bg-black shrink-0 shadow-lg group">
            {selectedCharacter.avatar_url ? (
              <img
                src={selectedCharacter.avatar_url}
                alt={selectedCharacter.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-tr from-purple-900 to-indigo-900 font-black text-3xl text-purple-200">
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
            <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-full">
              35mm Cinematic Character Still
            </span>
            <h3 className="text-sm font-bold text-white mt-1.5">Photorealistic Portrait &amp; Lookbook Headshot</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Generates a dedicated 85mm T1.4 portrait frame locking the actor's facial likeness and wardrobe for all camera coverage.
            </p>
          </div>
        </div>

        <button
          onClick={() => handleGenerateCharacterPortrait(selectedCharacter)}
          disabled={generatingPortraitMap[selectedCharacter.id]}
          className="px-4 py-2.5 text-xs font-bold bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-xl shadow-lg shadow-purple-600/30 transition flex items-center gap-2 shrink-0 disabled:opacity-50"
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
          <label className="block text-xs font-bold text-slate-300 mb-1">Role / Narrative Archetype</label>
          <input
            type="text"
            value={selectedCharacter.role}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, role: val } : c)));
            }}
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-bold text-slate-300">Actor Screen Reference &amp; Physical Appearance</label>
            <span className="text-[10px] font-medium text-purple-400">Gender, Age &amp; Build</span>
          </div>
          <textarea
            rows={2}
            value={selectedCharacter.actor_reference}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, actor_reference: val } : c)));
            }}
            placeholder="e.g. Early 30s woman, 5'7&quot; wiry athletic build, dark cropped hair, resolute bearing, intense gaze..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500 font-sans"
          />
          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Quick Traits:</span>
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
                className="px-2 py-0.5 text-[10px] font-semibold bg-slate-800 hover:bg-purple-900/60 hover:text-purple-200 text-slate-300 border border-slate-700 hover:border-purple-500/40 rounded-md transition"
              >
                + {tag}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 mt-1">Defines actor gender presentation (e.g. woman, man, non-binary), age, physique, build, hair, and baseline screen presence.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-300 mb-1">Costume, Wardrobe &amp; Props</label>
          <textarea
            rows={2}
            value={selectedCharacter.look_and_costume}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, look_and_costume: val } : c)));
            }}
            placeholder="e.g. Drenched dark linen shirt with rolled-up sleeves, charcoal wool vest, silver pocket watch..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500 font-sans"
          />
          <p className="text-[10px] text-slate-400 mt-1">Wardrobe textures, fabrics, tailoring, distress level, and accessories.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-300 mb-1">Facial Features &amp; Catchlights</label>
          <textarea
            rows={2}
            value={selectedCharacter.facial_features}
            onChange={e => {
              const val = e.target.value;
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, facial_features: val } : c)));
            }}
            placeholder="e.g. Sharp cheekbones, subtle 5 o'clock shadow, piercing hazel eyes filled with obsessive fervor..."
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500 font-sans"
          />
          <p className="text-[10px] text-slate-400 mt-1">Eyes, cheekbones, complexion, expressions, and key facial lighting marks.</p>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-300 mb-1">Personality Traits (Comma-separated)</label>
          <input
            type="text"
            value={selectedCharacter.personality_traits.join(', ')}
            onChange={e => {
              const traits = e.target.value.split(',').map(t => t.trim()).filter(Boolean);
              setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, personality_traits: traits } : c)));
            }}
            placeholder="e.g. Obsessive, Perfectionist, Haunted, Virtuoso"
            className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500"
          />
        </div>
      </div>

      {/* Character Relationship Network Section */}
      <div className="pt-6 border-t border-slate-800 space-y-3.5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Users className="w-4 h-4 text-purple-400" />
              Dramatic Relationships &amp; Co-Occurrences ({selectedCharacter.relationships?.length || 0})
            </h3>
            <p className="text-xs text-slate-400">
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
                  className="p-3.5 bg-slate-900/70 border border-slate-800 rounded-xl space-y-2 hover:border-purple-500/50 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-purple-950 border border-purple-500/40 flex items-center justify-center font-bold text-xs text-purple-200">
                        {rel.target_character.charAt(0)}
                      </div>
                      <h4 className="text-xs font-bold text-white">{rel.target_character}</h4>
                    </div>
                    {targetObj && (
                      <button
                        onClick={() => setSelectedCharId(targetObj.id)}
                        className="text-[10px] font-bold text-purple-400 hover:text-purple-300 transition"
                      >
                        Inspect →
                      </button>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1">
                    <span className="px-1.5 py-0.5 text-[9px] font-extrabold bg-purple-500/20 text-purple-300 rounded border border-purple-500/30">
                      {rel.relationship_type}
                    </span>
                    <span className="px-1.5 py-0.5 text-[9px] font-bold bg-slate-800 text-slate-300 rounded border border-slate-700">
                      {rel.shared_scenes.length > 0 ? `Scenes: ${rel.shared_scenes.join(', ')}` : 'Shared Scene'}
                    </span>
                    {rel.interaction_count > 0 && (
                      <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-500/20 text-emerald-300 rounded border border-emerald-500/30">
                        {rel.interaction_count} Dialogue Turns
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-slate-300 line-clamp-2 leading-relaxed">
                    {rel.dynamic_description}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl text-center text-xs text-slate-400">
            No direct multi-character interactions detected in script for {selectedCharacter.name}.
          </div>
        )}
      </div>
    </div>
  );
}
