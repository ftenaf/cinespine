import React, { useState, useEffect, useRef } from 'react';
import {
  Film,
  Camera,
  Sparkles,
  Sliders,
  RotateCw,
  Maximize2,
  FileText,
  Upload,
  CheckCircle2,
  Users,
  ShieldCheck,
  Save
} from 'lucide-react';

export interface DialogueLine {
  character: string;
  parenthetical?: string;
  line: string;
}

export interface CharacterProfile {
  id: string;
  name: string;
  role: string;
  actor_reference: string;
  look_and_costume: string;
  facial_features: string;
  personality_traits: string[];
  dialogue_count: number;
  scenes_present: string[];
  avatar_url?: string;
}

export interface ScreenplayScene {
  scene_number: string;
  heading: string;
  environment: string;
  location: string;
  time_of_day: string;
  action_blocks: string[];
  dialogues: DialogueLine[];
  characters?: string[];
  raw_content?: string;
}

export interface DoPSpecification {
  dop_preset: string;
  focal_length: number;
  lens_type: string;
  aperture: string;
  sensor_format: string;
  camera_body: string;
  fps: number;
  lighting_style: string;
  lighting_ratio: string;
  color_temperature_k: number;
  color_palette: string;
  lut_emulation: string;
  mood_notes: string;
}

export interface CameraAngleProposal {
  id: string;
  camera_letter: string; // "A", "B", "C"
  camera_role: string;
  shot_size: string;
  focal_length: number;
  aperture: string;
  camera_angle: string;
  camera_movement: string;
  coverage_description: string;
  prompt: string;
  image_url?: string;
  status: 'pending' | 'generating' | 'generated' | 'failed';
}

export interface StoryboardFrame {
  image_url?: string;
  prompt: string;
  aspect_ratio: string;
  status: 'pending' | 'generating' | 'generated' | 'failed';
}

export interface ShotProposal {
  id: string;
  scene_number: string;
  shot_number: string;
  shot_name: string;
  shot_size: string;
  camera_angle: string;
  camera_movement: string;
  dramatic_beat: string;
  subject_description: string;
  characters?: string[];
  dop_spec: DoPSpecification;
  cameras: CameraAngleProposal[];
  active_camera: string;
  storyboard: StoryboardFrame;
}

const DEMO_FOUNTAIN_SCRIPT = `Title: LA CATHÉDRALE
Author: Francisco

INT. GREAT HALL - NAVE - DAY

Colossal gothic arches soar into the gloom. Beams of volumetric sunlight slice through high stained-glass windows, illuminating floating dust motes.

LEAD (30s), haggard and drenched in sweat, sits at the multi-tier pipe organ console. His hands hover over the stops in frantic hesitation.

LEAD
(whispering to himself)
If the cadence fails, the sanctuary falls with it.

He strikes a heavy, resounding C-minor chord that reverberates through the stone columns.

From the shadows of the narthex, SUPPORT (30s) emerges, clutching a leather dossier.

SUPPORT
LEAD! Stop! They've already breached the perimeter gates.

LEAD doesn't look back. His fingers dance across the keys in relentless counterpoint.

LEAD
Then let them hear what they came to destroy.

EXT. PLAZA - NIGHT

Rain lashes against ancient cobblestones. Black tactical sedans screech to a halt around the bronze great_hall doors.

COMMANDER VANCE steps out into the downpour, pointing a high-power spotlight at the stained-glass facade.
`;

export const ScriptStudio: React.FC = () => {
  // Screenplay Editor State
  const [scriptTitle, setScriptTitle] = useState<string>('La Cathédrale');
  const [parsedScenes, setParsedScenes] = useState<ScreenplayScene[]>([]);
  const [characters, setCharacters] = useState<CharacterProfile[]>([]);
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);
  const [selectedSceneIndex, setSelectedSceneIndex] = useState<number>(0);
  const [studioSubTab, setStudioSubTab] = useState<'previz' | 'cast' | 'dop'>('previz');
  const [savingCharId, setSavingCharId] = useState<string | null>(null);
  const [charSaveSuccess, setCharSaveSuccess] = useState<string | null>(null);

  // Breakdown & Multi-Cam Shots State
  const [shotsMap, setShotsMap] = useState<Record<string, ShotProposal[]>>({});
  const [isBreakingDown, setIsBreakingDown] = useState<boolean>(false);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [activeCamLetter, setActiveCamLetter] = useState<string>('A');

  // DoP Cinematography Controls
  const [selectedPreset, setSelectedPreset] = useState<string>('Roger Deakins');
  const [aspectRatio, setAspectRatio] = useState<string>('2.39:1');

  // Presets Dictionary
  const [presetsDict, setPresetsDict] = useState<Record<string, any>>({});
  const [enlargedImage, setEnlargedImage] = useState<{ url: string; prompt: string; title: string } | null>(null);
  const [generatingCamMap, setGeneratingCamMap] = useState<Record<string, boolean>>({});

  // Fetch presets on mount and parse default demo
  useEffect(() => {
    fetch('/api/script/presets')
      .then(res => res.json())
      .then(data => {
        if (data.presets) setPresetsDict(data.presets);
      })
      .catch(err => console.error('Failed to load DoP presets:', err));

    handleParseScript(DEMO_FOUNTAIN_SCRIPT);
  }, []);

  // Parse Script Handler
  const handleParseScript = async (textToParse: string, title?: string) => {
    try {
      const activeTitle = title || scriptTitle;
      const res = await fetch('/api/script/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: textToParse, title: activeTitle })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.title) setScriptTitle(data.title);
        setParsedScenes(data.scenes || []);
        setCharacters(data.characters || []);
        if (data.characters && data.characters.length > 0) {
          setSelectedCharId(data.characters[0].id);
        }
        setSelectedSceneIndex(0);
      }
    } catch (err) {
      console.error('Failed to parse screenplay:', err);
    }
  };

  // Run AI Multi-Camera Breakdown on Current Scene
  const handleBreakdownCurrentScene = async () => {
    const currentScene = parsedScenes[selectedSceneIndex];
    if (!currentScene) return;

    setIsBreakingDown(true);
    try {
      const res = await fetch('/api/script/breakdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scene: currentScene,
          dop_preset: selectedPreset,
          aspect_ratio: aspectRatio,
          character_profiles: characters
        })
      });

      if (res.ok) {
        const data = await res.json();
        const shots: ShotProposal[] = data.shots || [];
        setShotsMap(prev => ({
          ...prev,
          [currentScene.scene_number]: shots
        }));
        if (shots.length > 0) {
          setSelectedShotId(shots[0].id);
          setActiveCamLetter('A');
        }
      }
    } catch (err) {
      console.error('Failed to generate shot breakdown:', err);
    } finally {
      setIsBreakingDown(false);
    }
  };

  // Synthesize Character Visual Details String for Active Scene
  const getActiveCharacterDetails = (sceneChars?: string[]): string => {
    const targetNames = sceneChars || parsedScenes[selectedSceneIndex]?.characters || [];
    if (!targetNames.length) return '';
    return characters
      .filter(c => targetNames.includes(c.name))
      .map(c => `${c.name} (${c.actor_reference}, wearing ${c.look_and_costume}, facial features: ${c.facial_features})`)
      .join('; ');
  };

  // Regenerate Single Camera Frame
  const handleRegenerateCameraFrame = async (shot: ShotProposal, cam: CameraAngleProposal) => {
    const genKey = `${shot.id}_${cam.camera_letter}`;
    setGeneratingCamMap(prev => ({ ...prev, [genKey]: true }));

    const charDetails = getActiveCharacterDetails(shot.characters);

    try {
      const res = await fetch('/api/script/generate-storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shot_id: shot.id,
          camera_letter: cam.camera_letter,
          prompt: cam.prompt,
          scene_number: shot.scene_number,
          shot_number: shot.shot_number,
          shot_size: cam.shot_size,
          focal_length: cam.focal_length,
          aperture: cam.aperture,
          dop_preset: shot.dop_spec.dop_preset,
          lighting_ratio: shot.dop_spec.lighting_ratio,
          color_temp_k: shot.dop_spec.color_temperature_k,
          lut_emulation: shot.dop_spec.lut_emulation,
          aspect_ratio: aspectRatio,
          character_details: charDetails
        })
      });

      if (res.ok) {
        const data = await res.json();
        const currentScene = parsedScenes[selectedSceneIndex];
        if (currentScene && shotsMap[currentScene.scene_number]) {
          const updatedShots = shotsMap[currentScene.scene_number].map(s => {
            if (s.id === shot.id) {
              const updatedCameras = (s.cameras || []).map(c => {
                if (c.camera_letter === cam.camera_letter) {
                  return { ...c, image_url: data.image_url, status: 'generated' as const };
                }
                return c;
              });

              const primaryCam = updatedCameras.find(c => c.camera_letter === activeCamLetter) || updatedCameras[0];

              return {
                ...s,
                cameras: updatedCameras,
                storyboard: {
                  ...s.storyboard,
                  image_url: primaryCam?.image_url || data.image_url,
                  prompt: primaryCam?.prompt || cam.prompt,
                  status: 'generated' as const
                }
              };
            }
            return s;
          });

          setShotsMap(prev => ({
            ...prev,
            [currentScene.scene_number]: updatedShots
          }));
        }
      }
    } catch (err) {
      console.error('Failed to regenerate camera frame:', err);
    } finally {
      setGeneratingCamMap(prev => ({ ...prev, [genKey]: false }));
    }
  };

  // Update Active Camera Prompt in State
  const handleUpdateActivePrompt = (newPrompt: string) => {
    const currentScene = parsedScenes[selectedSceneIndex];
    if (!currentScene || !selectedShot) return;

    const updatedShots = (shotsMap[currentScene.scene_number] || []).map(s => {
      if (s.id === selectedShot.id) {
        const updatedCameras = (s.cameras || []).map(c => {
          if (c.camera_letter === activeCamLetter) {
            return { ...c, prompt: newPrompt };
          }
          return c;
        });

        return {
          ...s,
          cameras: updatedCameras,
          storyboard: s.active_camera === activeCamLetter ? { ...s.storyboard, prompt: newPrompt } : s.storyboard
        };
      }
      return s;
    });

    setShotsMap(prev => ({
      ...prev,
      [currentScene.scene_number]: updatedShots
    }));
  };

  // Append Quick Prompt Modifier Keyword
  const handleAppendPromptModifier = (modifier: string) => {
    if (!selectedCam) return;
    const current = selectedCam.prompt.trim();
    const updated = current ? `${current}, ${modifier}` : modifier;
    handleUpdateActivePrompt(updated);
  };

  // Update Character Profile Handler
  const handleUpdateCharacter = async (char: CharacterProfile) => {
    setSavingCharId(char.id);
    try {
      const res = await fetch('/api/script/characters/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(char)
      });
      if (res.ok) {
        setCharacters(prev => prev.map(c => (c.id === char.id ? char : c)));
        setCharSaveSuccess(char.id);
        setTimeout(() => setCharSaveSuccess(null), 3000);
      }
    } catch (err) {
      console.error('Failed to update character profile:', err);
    } finally {
      setSavingCharId(null);
    }
  };

  const currentScene = parsedScenes[selectedSceneIndex];
  const currentShots = currentScene ? shotsMap[currentScene.scene_number] || [] : [];
  const selectedShot = currentShots.find(s => s.id === selectedShotId) || currentShots[0];
  const selectedCam = selectedShot?.cameras?.find(c => c.camera_letter === activeCamLetter) || selectedShot?.cameras?.[0];
  const selectedCharacter = characters.find(c => c.id === selectedCharId) || characters[0];

  // Script Upload State
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);

  // File Upload Handler (.fountain, .txt, .md, .pdf, .fdx)
  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsUploading(true);
    setUploadedFileName(file.name);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/script/upload', {
        method: 'POST',
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        if (data.title) setScriptTitle(data.title);
        setParsedScenes(data.scenes || []);
        setCharacters(data.characters || []);
        if (data.characters && data.characters.length > 0) {
          setSelectedCharId(data.characters[0].id);
        }
        setSelectedSceneIndex(0);
        setShotsMap({});
        setSelectedShotId(null);
      } else {
        const text = await file.text();
        handleParseScript(text, file.name.replace(/\.[^/.]+$/, ''));
      }
    } catch (err) {
      console.error('Screenplay upload failed, parsing locally:', err);
      try {
        const text = await file.text();
        handleParseScript(text, file.name.replace(/\.[^/.]+$/, ''));
      } catch (readErr) {
        console.error('Local text read failed:', readErr);
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#090D16] text-slate-100 font-sans">
      {/* Hidden File Input for Screenplay Upload */}
      <input
        type="file"
        ref={fileInputRef}
        accept=".fountain,.txt,.md,.pdf,.fdx"
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) handleFileUpload(file);
        }}
        className="hidden"
      />

      {/* Studio Header Toolbar */}
      <div className="flex items-center justify-between px-6 py-3.5 bg-[#0F172A]/90 border-b border-slate-800 backdrop-blur shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-purple-600 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/20">
            <Film className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-white tracking-wide">Screenplay &amp; Visual Director Studio</h1>
              <span className="px-2 py-0.5 text-[10px] font-extrabold uppercase bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-full">
                Multi-Camera (A, B, C) Previz
              </span>
              {uploadedFileName && (
                <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-md">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                  {uploadedFileName}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400">
              Multi-Format Screenplay Ingestion (.fountain / .md / .txt / .pdf) • Cast Character Profiler • Tri-Modal DoP Previz
            </p>
          </div>
        </div>

        {/* Action Controls Top Bar */}
        <div className="flex items-center gap-2.5">
          {/* Upload Script File Button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-3 py-1.5 text-xs font-semibold bg-purple-950/60 hover:bg-purple-900/80 text-purple-200 rounded-md border border-purple-500/40 transition flex items-center gap-1.5 shadow-sm"
          >
            <Upload className={`w-3.5 h-3.5 text-purple-400 ${isUploading ? 'animate-bounce' : ''}`} />
            {isUploading ? 'Uploading & Parsing...' : 'Upload Script (.fountain / .md / .txt / .pdf)'}
          </button>

          <button
            onClick={() => {
              setUploadedFileName(null);
              handleParseScript(DEMO_FOUNTAIN_SCRIPT);
            }}
            className="px-3 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-md border border-slate-700 transition flex items-center gap-1.5"
          >
            <FileText className="w-3.5 h-3.5 text-slate-400" />
            Load Demo Script
          </button>

          {/* Aspect Ratio Selector */}
          <div className="flex items-center bg-slate-900 border border-slate-700 rounded-md p-0.5">
            {['2.39:1', '1.85:1', '16:9', '4:3'].map(ar => (
              <button
                key={ar}
                onClick={() => setAspectRatio(ar)}
                className={`px-2 py-1 text-[11px] font-semibold rounded transition ${
                  aspectRatio === ar
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {ar}
              </button>
            ))}
          </div>

          {/* AI Breakdown Button */}
          <button
            onClick={handleBreakdownCurrentScene}
            disabled={isBreakingDown || !currentScene}
            className="px-4 py-1.5 text-xs font-bold bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-md shadow-lg shadow-purple-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            {isBreakingDown ? (
              <>
                <RotateCw className="w-3.5 h-3.5 animate-spin" />
                Breaking Down Scene...
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                Run AI 3-Cam Breakdown
              </>
            )}
          </button>
        </div>
      </div>

      {/* Sub-Navigation Tabs Bar */}
      <div className="flex items-center justify-between px-6 py-2 bg-[#0B132B] border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setStudioSubTab('previz')}
            className={`px-4 py-1.5 text-xs font-bold rounded-md flex items-center gap-2 transition ${
              studioSubTab === 'previz'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            3-Camera Previz &amp; Breakdown
          </button>

          <button
            onClick={() => setStudioSubTab('cast')}
            className={`px-4 py-1.5 text-xs font-bold rounded-md flex items-center gap-2 transition ${
              studioSubTab === 'cast'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            Cast &amp; Character Profiles
            <span className="px-1.5 py-0.2 text-[10px] font-extrabold bg-purple-950 text-purple-300 rounded-full border border-purple-500/40">
              {characters.length}
            </span>
          </button>

          <button
            onClick={() => setStudioSubTab('dop')}
            className={`px-4 py-1.5 text-xs font-bold rounded-md flex items-center gap-2 transition ${
              studioSubTab === 'dop'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            DoP Optics &amp; Master Styles
          </button>
        </div>

        {/* Character Consistency Indicator */}
        <div className="flex items-center gap-2 px-3 py-1 bg-purple-950/40 border border-purple-500/30 rounded-md">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-[11px] font-semibold text-purple-200">
            Character Visual Consistency: <strong className="text-emerald-400 font-bold">{characters.length} Profiles Active</strong>
          </span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* VIEW 1: CAST & CHARACTER PROFILES STUDIO                                 */}
      {/* ========================================================================= */}
      {studioSubTab === 'cast' && (
        <div className="flex-1 grid grid-cols-12 gap-0 overflow-hidden">
          {/* Left Column: Character List */}
          <div className="col-span-4 bg-[#0F172A]/70 border-r border-slate-800 flex flex-col overflow-y-auto p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-purple-400" />
                  Detected Cast ({characters.length})
                </h3>
                <p className="text-[11px] text-slate-400">Click a character to polish physical look, wardrobe, and facial traits.</p>
              </div>
            </div>

            <div className="space-y-2.5">
              {characters.map(char => (
                <div
                  key={char.id}
                  onClick={() => setSelectedCharId(char.id)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer flex items-start gap-3.5 ${
                    selectedCharacter?.id === char.id
                      ? 'bg-purple-950/60 border-purple-500 shadow-lg shadow-purple-500/10'
                      : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-purple-700 to-indigo-500 flex items-center justify-center font-black text-sm text-white shrink-0 shadow-md">
                    {char.name.charAt(0)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-black text-white tracking-wider">{char.name}</h4>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-800 text-purple-300 rounded border border-purple-500/20">
                        {char.dialogue_count} cues
                      </span>
                    </div>
                    <p className="text-[11px] font-medium text-slate-300 truncate mt-0.5">{char.role}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {char.personality_traits.slice(0, 3).map((t, idx) => (
                        <span key={idx} className="px-1.5 py-0.5 text-[9px] bg-slate-800/80 text-slate-300 rounded border border-slate-700">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Character Visual Polish Console */}
          <div className="col-span-8 bg-[#090D16] flex flex-col overflow-y-auto p-6">
            {selectedCharacter ? (
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
                    Character visual profile locked. All future Gen-AI camera renders will strictly enforce this actor look.
                  </div>
                )}

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
                    <label className="block text-xs font-bold text-slate-300 mb-1">Actor Screen Reference &amp; Physical Appearance</label>
                    <textarea
                      rows={3}
                      value={selectedCharacter.actor_reference}
                      onChange={e => {
                        const val = e.target.value;
                        setCharacters(prev => prev.map(c => (c.id === selectedCharacter.id ? { ...c, actor_reference: val } : c)));
                      }}
                      placeholder="e.g. Late 30s man, intense sunken eyes, dark wavy hair, weathered features, rugged jawline..."
                      className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500 font-sans"
                    />
                    <p className="text-[10px] text-slate-400 mt-1">Defines actor age, physique, build, hair, and baseline screen presence.</p>
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
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-400">
                <Users className="w-12 h-12 text-slate-600 mb-3" />
                <p className="text-sm font-semibold">No characters selected</p>
                <p className="text-xs text-slate-500">Upload a script or choose a demo to detect and profile characters.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: 3-CAMERA PREVIZ & BREAKDOWN STUDIO                               */}
      {/* ========================================================================= */}
      {studioSubTab === 'previz' && (
        <div className="flex-1 grid grid-cols-12 gap-0 overflow-hidden">
          {/* Column 1: Scenes & Fountain Screenplay Ingestion */}
          <div className="col-span-3 bg-[#0F172A]/70 border-r border-slate-800 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">Screenplay Scenes</h3>
                <p className="text-[11px] text-slate-400">{parsedScenes.length} Scenes Extracted</p>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {parsedScenes.map((sc, idx) => (
                <div
                  key={idx}
                  onClick={() => setSelectedSceneIndex(idx)}
                  className={`p-3 rounded-lg border transition cursor-pointer ${
                    selectedSceneIndex === idx
                      ? 'bg-purple-950/40 border-purple-500 text-white shadow-md'
                      : 'bg-slate-900/40 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-900/80'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded">
                      SCENE {sc.scene_number}
                    </span>
                    <span className="text-[10px] font-semibold text-slate-400">{sc.time_of_day}</span>
                  </div>
                  <h4 className="text-xs font-bold truncate text-slate-100">{sc.heading}</h4>
                  <p className="text-[11px] text-slate-400 line-clamp-2 mt-1">
                    {sc.action_blocks[0] || 'No action description'}
                  </p>
                  {sc.characters && sc.characters.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {sc.characters.map((cName, cIdx) => (
                        <span key={cIdx} className="px-1 py-0.5 text-[9px] font-semibold bg-slate-800 text-purple-300 rounded border border-purple-500/20">
                          {cName}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Column 2: Shot List & Synchronized Camera Setups */}
          <div className="col-span-4 bg-[#0B1120] border-r border-slate-800 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">Multi-Cam Setups</h3>
                <p className="text-[11px] text-slate-400">
                  {currentShots.length > 0 ? `${currentShots.length} Setups (3 Cams / Setup)` : 'No breakdown yet'}
                </p>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {currentShots.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-400">
                  <Camera className="w-10 h-10 text-slate-600 mb-2" />
                  <p className="text-xs font-bold">No Shot Breakdown Generated</p>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Click "Run AI 3-Cam Breakdown" to generate synchronized setups.
                  </p>
                </div>
              ) : (
                currentShots.map(shot => (
                  <div
                    key={shot.id}
                    onClick={() => setSelectedShotId(shot.id)}
                    className={`p-3 rounded-xl border transition cursor-pointer ${
                      selectedShot?.id === shot.id
                        ? 'bg-purple-950/40 border-purple-500 shadow-md'
                        : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-black text-white">{shot.shot_name}</span>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded border border-slate-700">
                        {shot.shot_size} • {shot.camera_angle}
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300 line-clamp-2">{shot.subject_description}</p>

                    {/* Camera Switcher Pills */}
                    <div className="flex items-center gap-1.5 mt-2.5 pt-2 border-t border-slate-800/80">
                      {shot.cameras.map(cam => (
                        <button
                          key={cam.camera_letter}
                          onClick={e => {
                            e.stopPropagation();
                            setSelectedShotId(shot.id);
                            setActiveCamLetter(cam.camera_letter);
                          }}
                          className={`px-2 py-1 text-[10px] font-bold rounded flex items-center gap-1 transition ${
                            selectedShot?.id === shot.id && activeCamLetter === cam.camera_letter
                              ? 'bg-purple-600 text-white'
                              : 'bg-slate-800/80 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          <Camera className="w-2.5 h-2.5" />
                          Cam {cam.camera_letter} ({cam.focal_length}mm)
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Column 3: Active Previz Canvas & Generative Prompt Console */}
          <div className="col-span-5 bg-[#090D16] flex flex-col overflow-y-auto p-4 space-y-4">
            {selectedShot && selectedCam ? (
              <div className="space-y-4">
                {/* Visual Frame Canvas Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 text-xs font-black bg-purple-600 text-white rounded">
                      CAMERA {activeCamLetter}
                    </span>
                    <span className="text-xs font-bold text-white">{selectedCam.camera_role}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-purple-300">
                      {selectedCam.focal_length}mm • {selectedCam.aperture} • {aspectRatio}
                    </span>
                  </div>
                </div>

                {/* Main Previz Frame Display */}
                <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950 aspect-[2.39/1] shadow-2xl group">
                  {selectedCam.image_url ? (
                    <img
                      src={selectedCam.image_url}
                      alt={selectedCam.prompt}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500 text-xs">
                      <Camera className="w-8 h-8 mb-2 text-slate-600" />
                      Rendering Previz Frame...
                    </div>
                  )}

                  {/* Overlay Badge */}
                  <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/70 backdrop-blur text-[10px] font-mono font-bold text-purple-300 rounded border border-purple-500/30">
                    35mm Previz • {selectedShot.dop_spec.dop_preset}
                  </div>

                  {/* Character Lock Badge */}
                  <div className="absolute bottom-2 left-2 px-2 py-0.5 bg-black/80 backdrop-blur text-[10px] font-semibold text-emerald-300 rounded border border-emerald-500/30 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-emerald-400" />
                    Consistent Cast Applied
                  </div>

                  {/* Hover Actions */}
                  <div className="absolute top-2 right-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition">
                    {selectedCam.image_url && (
                      <button
                        onClick={() =>
                          setEnlargedImage({
                            url: selectedCam.image_url!,
                            prompt: selectedCam.prompt,
                            title: `${selectedShot.shot_name} - Camera ${activeCamLetter}`
                          })
                        }
                        className="p-1.5 bg-black/80 hover:bg-black text-white rounded-md border border-slate-700 transition"
                      >
                        <Maximize2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Prompt Modifier Chips */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-purple-400" />
                      Quick Cinematography Modifiers:
                    </label>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      '+ Volumetric Haze',
                      '+ Chiaroscuro Rim Light',
                      '+ Anamorphic Streak Flare',
                      '+ Close-Up Eye Catchlights',
                      '+ Rain Reflections',
                      '+ 35mm Authentic Grain'
                    ].map(mod => (
                      <button
                        key={mod}
                        onClick={() => handleAppendPromptModifier(mod)}
                        className="px-2 py-1 text-[10px] font-semibold bg-slate-900 hover:bg-purple-950 text-slate-300 hover:text-purple-200 border border-slate-800 hover:border-purple-500/40 rounded transition shadow-sm"
                      >
                        {mod}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Editable Generative Prompt Box */}
                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Cinematography &amp; Character Prompt (Camera {activeCamLetter})
                  </label>
                  <textarea
                    rows={4}
                    value={selectedCam.prompt}
                    onChange={e => handleUpdateActivePrompt(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white font-mono focus:outline-none focus:border-purple-500"
                  />
                </div>

                {/* Execute AI Render Button */}
                <button
                  onClick={() => handleRegenerateCameraFrame(selectedShot, selectedCam)}
                  disabled={generatingCamMap[`${selectedShot.id}_${selectedCam.camera_letter}`]}
                  className="w-full py-2.5 text-xs font-bold bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-lg shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {generatingCamMap[`${selectedShot.id}_${selectedCam.camera_letter}`] ? (
                    <>
                      <RotateCw className="w-4 h-4 animate-spin" />
                      Rendering Camera {activeCamLetter} AI Still...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Execute &amp; Render Camera {activeCamLetter} AI Concept
                    </>
                  )}
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 text-xs">
                <Camera className="w-10 h-10 mb-2 text-slate-600" />
                Select a shot setup to inspect camera perspectives.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 3: DOP CINEMATOGRAPHY MATRIX                                        */}
      {/* ========================================================================= */}
      {studioSubTab === 'dop' && (
        <div className="flex-1 overflow-y-auto p-6 bg-[#090D16]">
          <div className="max-w-4xl space-y-6">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Sliders className="w-4 h-4 text-purple-400" />
                Director of Photography Optical &amp; Lighting Matrix
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Configure master cinematographer presets, color temperature Kelvin, lighting contrast ratio, and film stock LUT emulation.
              </p>
            </div>

            {/* Presets Grid */}
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(presetsDict).map(([presetName, presetData]: [string, any]) => (
                <div
                  key={presetName}
                  onClick={() => setSelectedPreset(presetName)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer ${
                    selectedPreset === presetName
                      ? 'bg-purple-950/60 border-purple-500 shadow-lg shadow-purple-500/20'
                      : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <h4 className="text-xs font-bold text-white">{presetData.name || presetName}</h4>
                  <p className="text-[10px] text-purple-300 mt-0.5">{presetData.tagline}</p>
                  <p className="text-[11px] text-slate-400 line-clamp-3 mt-2">{presetData.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Lightbox Enlarged Image Modal */}
      {enlargedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col items-center justify-center p-6"
          onClick={() => setEnlargedImage(null)}
        >
          <div
            className="max-w-5xl w-full bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white">{enlargedImage.title}</h3>
              <button
                onClick={() => setEnlargedImage(null)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                ✕
              </button>
            </div>
            <div className="p-4 bg-black flex items-center justify-center">
              <img
                src={enlargedImage.url}
                alt={enlargedImage.prompt}
                className="max-h-[70vh] object-contain rounded-lg"
              />
            </div>
            <div className="p-4 bg-slate-900/90 text-xs font-mono text-slate-300">
              {enlargedImage.prompt}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
