import React, { useState, useEffect } from 'react';
import {
  Film,
  Camera,
  Sparkles,
  Layers,
  Sliders,
  RotateCw,
  Download,
  Maximize2,
  FileText
} from 'lucide-react';

export interface DialogueLine {
  character: string;
  parenthetical?: string;
  line: string;
}

export interface ScreenplayScene {
  scene_number: string;
  heading: string;
  environment: string;
  location: string;
  time_of_day: string;
  action_blocks: string[];
  dialogues: DialogueLine[];
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
  dop_spec: DoPSpecification;
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
  const [scriptText, setScriptText] = useState<string>(DEMO_FOUNTAIN_SCRIPT);
  const [scriptTitle, setScriptTitle] = useState<string>('La Cathédrale');
  const [parsedScenes, setParsedScenes] = useState<ScreenplayScene[]>([]);
  const [selectedSceneIndex, setSelectedSceneIndex] = useState<number>(0);
  const [isParsingScript, setIsParsingScript] = useState<boolean>(false);

  // Breakdown & Shots State
  const [shotsMap, setShotsMap] = useState<Record<string, ShotProposal[]>>({});
  const [isBreakingDown, setIsBreakingDown] = useState<boolean>(false);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);

  // DoP Cinematography Controls
  const [dopMode, setDopMode] = useState<'preset' | 'matrix' | 'prompt'>('preset');
  const [selectedPreset, setSelectedPreset] = useState<string>('Roger Deakins');
  const [aspectRatio, setAspectRatio] = useState<string>('2.39:1');
  const [customFocalLength, setCustomFocalLength] = useState<number>(35);
  const [customAperture, setCustomAperture] = useState<string>('T2.8');
  const [customColorTemp, setCustomColorTemp] = useState<number>(5600);
  const [customLightingRatio, setCustomLightingRatio] = useState<string>('4:1');
  const [customMoodPrompt, setCustomMoodPrompt] = useState<string>('');

  // Presets Dictionary
  const [presetsDict, setPresetsDict] = useState<Record<string, any>>({});
  const [enlargedImage, setEnlargedImage] = useState<{ url: string; prompt: string; title: string } | null>(null);

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
    setIsParsingScript(true);
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
        setSelectedSceneIndex(0);
      }
    } catch (err) {
      console.error('Failed to parse screenplay:', err);
    } finally {
      setIsParsingScript(false);
    }
  };

  // Run AI Breakdown on Current Scene
  const handleBreakdownCurrentScene = async () => {
    const currentScene = parsedScenes[selectedSceneIndex];
    if (!currentScene) return;

    setIsBreakingDown(true);
    try {
      const overrides: Record<string, any> = {};
      if (dopMode === 'matrix') {
        overrides.focal_length = customFocalLength;
        overrides.aperture = customAperture;
        overrides.color_temperature_k = customColorTemp;
        overrides.lighting_ratio = customLightingRatio;
      }

      const res = await fetch('/api/script/breakdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scene: currentScene,
          dop_preset: selectedPreset,
          dop_overrides: Object.keys(overrides).length > 0 ? overrides : null,
          custom_prompt: dopMode === 'prompt' ? customMoodPrompt : null,
          aspect_ratio: aspectRatio
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
        }
      }
    } catch (err) {
      console.error('Failed to generate shot breakdown:', err);
    } finally {
      setIsBreakingDown(false);
    }
  };

  // Regenerate Single Storyboard Frame
  const handleRegenerateFrame = async (shot: ShotProposal) => {
    try {
      const res = await fetch('/api/script/generate-storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shot_id: shot.id,
          prompt: shot.storyboard.prompt,
          scene_number: shot.scene_number,
          shot_number: shot.shot_number,
          shot_size: shot.shot_size,
          focal_length: shot.dop_spec.focal_length,
          aperture: shot.dop_spec.aperture,
          dop_preset: shot.dop_spec.dop_preset,
          aspect_ratio: aspectRatio
        })
      });

      if (res.ok) {
        const data = await res.json();
        const currentScene = parsedScenes[selectedSceneIndex];
        if (currentScene && shotsMap[currentScene.scene_number]) {
          const updatedShots = shotsMap[currentScene.scene_number].map(s => {
            if (s.id === shot.id) {
              return {
                ...s,
                storyboard: {
                  ...s.storyboard,
                  image_url: data.image_url,
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
      console.error('Failed to regenerate storyboard frame:', err);
    }
  };

  const currentScene = parsedScenes[selectedSceneIndex];
  const currentShots = currentScene ? shotsMap[currentScene.scene_number] || [] : [];
  const selectedShot = currentShots.find(s => s.id === selectedShotId) || currentShots[0];

  return (
    <div className="flex flex-col h-full bg-[#090D16] text-slate-100 font-sans">
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
                AI Breakdown &amp; Previz
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Fountain Screenplay Ingestion • AI Scene-to-Shot Breakdown • Tri-Modal DoP Cinematography • Generative Storyboard Previz
            </p>
          </div>
        </div>

        {/* Action Controls Top Bar */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => {
              setScriptText(DEMO_FOUNTAIN_SCRIPT);
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
                Analyzing Scene...
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                Propose Shot Breakdown
              </>
            )}
          </button>
        </div>
      </div>

      {/* 3-Column Studio Grid Layout */}
      <div className="flex-1 grid grid-cols-12 gap-0 overflow-hidden divide-x divide-slate-800">
        
        {/* ======================================================== */}
        {/* COLUMN 1: FOUNTAIN SCRIPT & SCENE NAVIGATOR (Width: 3/12) */}
        {/* ======================================================== */}
        <div className="col-span-3 flex flex-col h-full bg-[#0B0F19] overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 flex items-center justify-between shrink-0">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-purple-400" />
              1. Screenplay &amp; Scenes ({parsedScenes.length})
            </span>
            <button
              onClick={() => handleParseScript(scriptText)}
              disabled={isParsingScript}
              className="text-[11px] font-semibold text-purple-400 hover:text-purple-300 transition flex items-center gap-1"
            >
              <RotateCw className={`w-3 h-3 ${isParsingScript ? 'animate-spin' : ''}`} />
              Re-parse
            </button>
          </div>

          {/* Scene Headings Quick Selector */}
          <div className="p-3 border-b border-slate-800 bg-slate-950/40 space-y-1.5 shrink-0 max-h-48 overflow-y-auto">
            {parsedScenes.map((sc, idx) => {
              const isSelected = idx === selectedSceneIndex;
              const hasShots = !!shotsMap[sc.scene_number]?.length;
              return (
                <button
                  key={idx}
                  onClick={() => setSelectedSceneIndex(idx)}
                  className={`w-full text-left p-2 rounded-md border text-xs transition flex items-center justify-between ${
                    isSelected
                      ? 'bg-purple-950/40 border-purple-500/50 text-purple-100 shadow-sm'
                      : 'bg-slate-900/40 border-slate-800 text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                  }`}
                >
                  <div className="truncate pr-2">
                    <span className="font-mono font-bold text-amber-400 mr-1.5">SC {sc.scene_number}</span>
                    <span className="font-semibold text-slate-200">{sc.location}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`px-1.5 py-0.2 text-[9px] font-bold rounded ${
                      sc.environment === 'INT' ? 'bg-blue-500/20 text-blue-300' : 'bg-amber-500/20 text-amber-300'
                    }`}>
                      {sc.environment}
                    </span>
                    {hasShots && (
                      <span className="px-1.5 py-0.2 text-[9px] font-bold bg-emerald-500/20 text-emerald-300 rounded">
                        {shotsMap[sc.scene_number].length} shots
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Raw Fountain / Screenplay Text Editor */}
          <div className="flex-1 flex flex-col overflow-hidden p-3">
            <label className="text-[11px] font-semibold text-slate-400 mb-1.5 flex items-center justify-between">
              <span>Fountain Editor</span>
              <span className="text-[10px] text-slate-500">Live Auto-format</span>
            </label>
            <textarea
              value={scriptText}
              onChange={e => setScriptText(e.target.value)}
              className="flex-1 w-full bg-slate-950/80 border border-slate-800 rounded-md p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 resize-none leading-relaxed"
              placeholder="Type or paste screenplay in standard Fountain syntax..."
            />
          </div>
        </div>

        {/* ======================================================== */}
        {/* COLUMN 2: SHOT BREAKDOWN & TIMELINE MATRIX (Width: 4/12) */}
        {/* ======================================================== */}
        <div className="col-span-4 flex flex-col h-full bg-[#0C101B] overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 flex items-center justify-between shrink-0">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Camera className="w-3.5 h-3.5 text-indigo-400" />
              2. Proposed Shot List ({currentShots.length} Setups)
            </span>
            {currentScene && (
              <span className="text-[11px] font-mono text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                SCENE {currentScene.scene_number} • {currentScene.time_of_day}
              </span>
            )}
          </div>

          {/* Scene Action Synopsis Card */}
          {currentScene && (
            <div className="p-3.5 border-b border-slate-800/80 bg-slate-900/30 shrink-0">
              <div className="text-[11px] font-bold text-slate-300 mb-1">
                {currentScene.heading}
              </div>
              <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                {currentScene.action_blocks.join(' ') || 'No action description.'}
              </p>
              {currentScene.dialogues.length > 0 && (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-purple-400 font-medium">
                  <span>Characters:</span>
                  {Array.from(new Set(currentScene.dialogues.map(d => d.character))).map(c => (
                    <span key={c} className="px-1.5 py-0.5 bg-purple-500/10 border border-purple-500/20 rounded text-[10px]">
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Shot Cards List */}
          <div className="flex-1 p-3 overflow-y-auto space-y-2.5">
            {currentShots.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-slate-800 rounded-lg">
                <div className="w-12 h-12 rounded-full bg-indigo-950/40 border border-indigo-800/50 flex items-center justify-center mb-3">
                  <Sparkles className="w-6 h-6 text-indigo-400" />
                </div>
                <h4 className="text-xs font-bold text-slate-200 mb-1">No Shots Proposed Yet</h4>
                <p className="text-xs text-slate-500 mb-4 max-w-[240px]">
                  Click &quot;Propose Shot Breakdown&quot; to divide Scene {currentScene?.scene_number || '1'} into camera setups, dramatic beats, and technical specs.
                </p>
                <button
                  onClick={handleBreakdownCurrentScene}
                  disabled={isBreakingDown}
                  className="px-3.5 py-1.5 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition shadow-md flex items-center gap-1.5"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Generate Shot Breakdown
                </button>
              </div>
            ) : (
              currentShots.map(shot => {
                const isSelected = shot.id === selectedShotId;
                return (
                  <div
                    key={shot.id}
                    onClick={() => setSelectedShotId(shot.id)}
                    className={`p-3.5 rounded-lg border transition cursor-pointer relative overflow-hidden ${
                      isSelected
                        ? 'bg-gradient-to-r from-indigo-950/50 to-slate-900 border-indigo-500 shadow-md shadow-indigo-500/10 ring-1 ring-indigo-500/40'
                        : 'bg-slate-900/40 border-slate-800 hover:bg-slate-800/50 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 text-[11px] font-bold font-mono text-white flex items-center justify-center">
                          {shot.shot_number}
                        </span>
                        <h4 className="text-xs font-bold text-slate-100">{shot.shot_name}</h4>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="px-2 py-0.5 text-[10px] font-extrabold bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded">
                          {shot.shot_size}
                        </span>
                        <span className="px-2 py-0.5 text-[10px] font-semibold bg-slate-800 text-slate-300 rounded">
                          {shot.camera_movement}
                        </span>
                      </div>
                    </div>

                    <p className="text-xs text-slate-400 line-clamp-2 mb-2.5">
                      {shot.dramatic_beat || shot.subject_description}
                    </p>

                    {/* Technical Lens & Preset Badge */}
                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 bg-slate-950/60 px-2.5 py-1.5 rounded border border-slate-800/60">
                      <span className="text-purple-300">{shot.dop_spec.focal_length}mm • {shot.dop_spec.aperture}</span>
                      <span className="text-slate-400">{shot.dop_spec.dop_preset}</span>
                      <span className="text-emerald-400 font-bold">{shot.dop_spec.lighting_ratio}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ======================================================== */}
        {/* COLUMN 3: DoP STUDIO & STORYBOARD GALLERY (Width: 5/12)   */}
        {/* ======================================================== */}
        <div className="col-span-5 flex flex-col h-full bg-[#080C14] overflow-hidden">
          {/* DoP Configuration Header & Mode Switcher */}
          <div className="px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 flex items-center justify-between shrink-0">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-pink-400" />
              3. DoP Cinematography &amp; Storyboard Previz
            </span>

            {/* Tri-Modal Switcher */}
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-md p-0.5">
              <button
                onClick={() => setDopMode('preset')}
                className={`px-2.5 py-1 text-[11px] font-bold rounded transition ${
                  dopMode === 'preset' ? 'bg-pink-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Presets
              </button>
              <button
                onClick={() => setDopMode('matrix')}
                className={`px-2.5 py-1 text-[11px] font-bold rounded transition ${
                  dopMode === 'matrix' ? 'bg-pink-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Technical Matrix
              </button>
              <button
                onClick={() => setDopMode('prompt')}
                className={`px-2.5 py-1 text-[11px] font-bold rounded transition ${
                  dopMode === 'prompt' ? 'bg-pink-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Free-form
              </button>
            </div>
          </div>

          {/* DoP Style Selector Controls Area */}
          <div className="p-3.5 border-b border-slate-800 bg-slate-900/30 shrink-0">
            {dopMode === 'preset' && (
              <div className="grid grid-cols-3 gap-2">
                {Object.keys(presetsDict).map(pKey => {
                  const p = presetsDict[pKey];
                  const isChosen = selectedPreset === pKey;
                  return (
                    <button
                      key={pKey}
                      onClick={() => setSelectedPreset(pKey)}
                      className={`p-2 rounded-md border text-left transition flex flex-col justify-between ${
                        isChosen
                          ? 'bg-pink-950/40 border-pink-500 text-pink-100 shadow-md shadow-pink-500/10'
                          : 'bg-slate-900/50 border-slate-800 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      <div>
                        <div className="text-[11px] font-bold text-white truncate">{pKey}</div>
                        <div className="text-[9px] text-slate-400 line-clamp-1 mt-0.5">{p.tagline}</div>
                      </div>
                      <div className="mt-2 text-[9px] font-mono text-pink-400 font-semibold">
                        {p.focal_length}mm • {p.aperture}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {dopMode === 'matrix' && (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="text-[10px] font-bold uppercase text-slate-400 mb-1 block">
                    Focal Length ({customFocalLength}mm)
                  </label>
                  <input
                    type="range"
                    min="18"
                    max="135"
                    step="1"
                    value={customFocalLength}
                    onChange={e => setCustomFocalLength(Number(e.target.value))}
                    className="w-full accent-pink-500 cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                    <span>18mm (Wide)</span>
                    <span>50mm</span>
                    <span>135mm (Tele)</span>
                  </div>
                </div>

                <div>
                  <label className="text-[10px] font-bold uppercase text-slate-400 mb-1 block">
                    Aperture / T-Stop ({customAperture})
                  </label>
                  <select
                    value={customAperture}
                    onChange={e => setCustomAperture(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200 focus:outline-none focus:border-pink-500"
                  >
                    {['T1.3', 'T1.4', 'T2.0', 'T2.8', 'T4.0', 'T5.6', 'T8.0'].map(ap => (
                      <option key={ap} value={ap}>{ap}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] font-bold uppercase text-slate-400 mb-1 block">
                    Color Temp ({customColorTemp}K)
                  </label>
                  <input
                    type="range"
                    min="2800"
                    max="6500"
                    step="100"
                    value={customColorTemp}
                    onChange={e => setCustomColorTemp(Number(e.target.value))}
                    className="w-full accent-pink-500 cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                    <span>3200K (Warm)</span>
                    <span>5600K (Daylight)</span>
                  </div>
                </div>

                <div>
                  <label className="text-[10px] font-bold uppercase text-slate-400 mb-1 block">
                    Lighting Contrast Ratio
                  </label>
                  <select
                    value={customLightingRatio}
                    onChange={e => setCustomLightingRatio(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200 focus:outline-none focus:border-pink-500"
                  >
                    {['1:1 (Flat)', '2:1 (Gentle)', '4:1 (Dramatic)', '8:1 (Chiaroscuro)', '16:1 (Noir)'].map(r => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {dopMode === 'prompt' && (
              <div>
                <label className="text-[10px] font-bold uppercase text-slate-400 mb-1 block">
                  Natural Language Mood &amp; Lighting Prompt
                </label>
                <textarea
                  value={customMoodPrompt}
                  onChange={e => setCustomMoodPrompt(e.target.value)}
                  rows={2}
                  placeholder="e.g. Gothic great_hall gloom with shafts of golden light, heavy vignette, anamorphic flare..."
                  className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs text-slate-200 focus:outline-none focus:border-pink-500 resize-none font-sans"
                />
              </div>
            )}
          </div>

          {/* Active Storyboard Previz Preview */}
          <div className="flex-1 p-4 overflow-y-auto flex flex-col">
            {selectedShot ? (
              <div className="flex-1 flex flex-col bg-slate-950/80 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
                {/* Concept Frame Render Display */}
                <div className="relative w-full bg-black flex items-center justify-center p-3 group">
                  {selectedShot.storyboard.image_url ? (
                    <div className="relative w-full overflow-hidden rounded-lg border border-slate-800 shadow-inner">
                      <img
                        src={selectedShot.storyboard.image_url}
                        alt={selectedShot.shot_name}
                        className="w-full object-contain cursor-pointer transition transform group-hover:scale-[1.01]"
                        onClick={() => setEnlargedImage({
                          url: selectedShot.storyboard.image_url!,
                          prompt: selectedShot.storyboard.prompt,
                          title: `SC ${selectedShot.scene_number} / SHOT ${selectedShot.shot_number} - ${selectedShot.shot_name}`
                        })}
                      />
                      <button
                        onClick={() => setEnlargedImage({
                          url: selectedShot.storyboard.image_url!,
                          prompt: selectedShot.storyboard.prompt,
                          title: `SC ${selectedShot.scene_number} / SHOT ${selectedShot.shot_number} - ${selectedShot.shot_name}`
                        })}
                        className="absolute bottom-3 right-3 p-1.5 bg-black/70 hover:bg-black text-white rounded-md border border-slate-700 opacity-0 group-hover:opacity-100 transition shadow"
                      >
                        <Maximize2 className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="w-full aspect-[2.39/1] bg-slate-900 flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-lg">
                      <Film className="w-8 h-8 text-slate-600 mb-2" />
                      <span className="text-xs text-slate-500">No Previz Rendered</span>
                    </div>
                  )}
                </div>

                {/* Shot Metadata & Regenerate Controls */}
                <div className="p-4 bg-slate-900/50 border-t border-slate-800 flex-1 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                          SCENE {selectedShot.scene_number} • SHOT {selectedShot.shot_number}
                        </span>
                        <span className="text-xs font-bold text-white">{selectedShot.shot_name}</span>
                      </div>
                      <span className="px-2 py-0.5 text-[10px] font-extrabold bg-purple-500/20 text-purple-300 rounded border border-purple-500/30">
                        {aspectRatio} Scope
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 mb-3 text-[11px] font-mono">
                      <div className="p-2 bg-slate-950/60 rounded border border-slate-800">
                        <span className="text-slate-500 block text-[9px] uppercase font-sans">Optics</span>
                        <span className="text-slate-200 font-bold">{selectedShot.dop_spec.focal_length}mm {selectedShot.dop_spec.aperture}</span>
                      </div>
                      <div className="p-2 bg-slate-950/60 rounded border border-slate-800">
                        <span className="text-slate-500 block text-[9px] uppercase font-sans">Lighting &amp; Temp</span>
                        <span className="text-slate-200 font-bold">{selectedShot.dop_spec.color_temperature_k}K • {selectedShot.dop_spec.lighting_ratio}</span>
                      </div>
                      <div className="p-2 bg-slate-950/60 rounded border border-slate-800">
                        <span className="text-slate-500 block text-[9px] uppercase font-sans">Film Stock</span>
                        <span className="text-pink-300 font-bold">{selectedShot.dop_spec.lut_emulation}</span>
                      </div>
                    </div>

                    <div className="p-2.5 bg-slate-950/80 rounded border border-slate-800 mb-3">
                      <span className="text-[9px] font-bold uppercase text-slate-500 block mb-1">Synthesized Generative Image Prompt</span>
                      <p className="text-xs text-slate-300 font-mono leading-relaxed line-clamp-3">
                        {selectedShot.storyboard.prompt}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                    <button
                      onClick={() => handleRegenerateFrame(selectedShot)}
                      className="px-3.5 py-1.5 text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md border border-slate-700 transition flex items-center gap-1.5"
                    >
                      <RotateCw className="w-3.5 h-3.5 text-purple-400" />
                      Regenerate Concept Frame
                    </button>

                    <button
                      onClick={() => {
                        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentShots, null, 2));
                        const downloadAnchor = document.createElement('a');
                        downloadAnchor.setAttribute("href", dataStr);
                        downloadAnchor.setAttribute("download", `CineSpine_ShotList_Scene_${currentScene?.scene_number || '1'}.json`);
                        document.body.appendChild(downloadAnchor);
                        downloadAnchor.click();
                        downloadAnchor.remove();
                      }}
                      className="px-3.5 py-1.5 text-xs font-bold bg-purple-600 hover:bg-purple-500 text-white rounded-md transition shadow-md flex items-center gap-1.5"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Export Previz Shot Pack
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 border border-dashed border-slate-800 rounded-xl">
                <Film className="w-8 h-8 text-slate-600 mb-2" />
                <span className="text-xs text-slate-400 font-semibold">Select a shot from Column 2 to view its DoP parameters &amp; concept art frame.</span>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Lightbox Image Preview Modal */}
      {enlargedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-6"
          onClick={() => setEnlargedImage(null)}
        >
          <div
            className="max-w-5xl w-full bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
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
                alt="Enlarged concept frame"
                className="max-h-[70vh] w-auto object-contain rounded-lg border border-slate-800"
              />
            </div>
            <div className="p-4 bg-slate-900/80 border-t border-slate-800 text-xs text-slate-300 font-mono">
              <span className="text-purple-400 font-bold block mb-1">PROMPT:</span>
              {enlargedImage.prompt}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
