import React, { useState, useEffect, useRef, useMemo } from 'react';
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
  Save,
  Sun,
  Aperture,
  Crosshair,
  Terminal,
  Palette,
  Plus,
  Trash2,
  X
} from 'lucide-react';
import {
  SENSOR_FORMATS,
  DEFAULT_SENSOR_ID,
  PROTECT_RATIOS,
  REFERENCE_FOCAL_MM,
  computeViewfinderGeometry,
  parseAspectRatio,
  protectFrameInset
} from '../optics';

export interface DialogueLine {
  character: string;
  parenthetical?: string;
  line: string;
}

export interface CharacterRelationship {
  target_character: string;
  relationship_type: string;
  dynamic_description: string;
  shared_scenes: string[];
  interaction_count: number;
}

export interface CharacterProfile {
  id: string;
  name: string;
  role: string;
  actor_reference: string;
  look_and_costume: string;
  facial_features: string;
  personality_traits: string[];
  relationships?: CharacterRelationship[];
  dialogue_count: number;
  scenes_present: string[];
  avatar_url?: string;
  portrait_prompt?: string;
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
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [activeCamLetter, setActiveCamLetter] = useState<string>('A');

  // DoP Cinematography Controls & Real-Time Preview
  const [dopMode, setDopMode] = useState<'preset' | 'matrix' | 'prompt'>('preset');
  const [selectedPreset, setSelectedPreset] = useState<string>('Roger Deakins');
  const [aspectRatio, setAspectRatio] = useState<string>('2.39:1');
  const [customFocalLength, setCustomFocalLength] = useState<number>(35);
  const [customAperture, setCustomAperture] = useState<string>('T2.8');
  const [customColorTemp, setCustomColorTemp] = useState<number>(5600);
  const [customLightingRatio, setCustomLightingRatio] = useState<string>('4:1');
  const [customSensorFormat, setCustomSensorFormat] = useState<string>(DEFAULT_SENSOR_ID);
  const [customLutEmulation, setCustomLutEmulation] = useState<string>('Kodak 5219 Vision3');
  const [customMoodPrompt, setCustomMoodPrompt] = useState<string>('');
  const [dopTestRenderUrl, setDopTestRenderUrl] = useState<string | null>(null);
  const [isTestRenderingDoP, setIsTestRenderingDoP] = useState<boolean>(false);
  const [showViewfinderGrid, setShowViewfinderGrid] = useState<boolean>(true);
  const [showSurround, setShowSurround] = useState<boolean>(true);
  const [protectRatio, setProtectRatio] = useState<string>('16:9');

  // Presets Dictionary
  const [presetsDict, setPresetsDict] = useState<Record<string, any>>({});
  const [enlargedImage, setEnlargedImage] = useState<{ url: string; prompt: string; title: string } | null>(null);
  const [generatingCamMap, setGeneratingCamMap] = useState<Record<string, boolean>>({});

  // Real-Time Viewfinder Geometry (sensor extraction, angle of view, framing scale)
  const geometry = useMemo(
    () => computeViewfinderGeometry(customSensorFormat, aspectRatio, customFocalLength),
    [customSensorFormat, aspectRatio, customFocalLength]
  );

  // Protect frame lines drawn inside the delivery extraction
  const protectInset = useMemo(
    () => protectFrameInset(geometry.aspect, parseAspectRatio(protectRatio)),
    [geometry.aspect, protectRatio]
  );

  // Dynamic Real-Time DoP Prompt Compiler
  const compileDoPPromptPreview = (): string => {
    if (dopMode === 'prompt' && customMoodPrompt.trim()) {
      return `Cinematic master film still, ${customMoodPrompt.trim()}, ${customFocalLength}mm lens at ${customAperture}, ${customColorTemp}K color temperature, ${customLightingRatio} lighting ratio, ${customLutEmulation} LUT, 8k resolution, authentic 35mm grain`;
    }
    if (dopMode === 'matrix') {
      return `Cinematic master film still, captured on ${customSensorFormat}, ${customFocalLength}mm prime lens at ${customAperture} aperture, ${customColorTemp}K color temperature, ${customLightingRatio} key-to-fill lighting ratio, ${customLutEmulation} film stock emulsion grade, 8k resolution, photorealistic master cinema frame`;
    }
    const preset = presetsDict[selectedPreset];
    return preset?.prompt_style_tag || `Cinematic master film still in the style of ${selectedPreset}, natural lighting, master prime clarity, 8k photorealistic film still`;
  };

  // Execute DoP Live Frame Test Render
  const handleExecuteDoPTestRender = async () => {
    setIsTestRenderingDoP(true);
    const activePrompt = compileDoPPromptPreview();
    try {
      const res = await fetch('/api/script/generate-storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shot_id: 'DOP_TEST',
          camera_letter: 'A',
          prompt: activePrompt,
          scene_number: 'DOP_CALIB',
          shot_number: '1',
          shot_size: 'WS',
          focal_length: customFocalLength,
          aperture: customAperture,
          dop_preset: selectedPreset,
          lighting_ratio: customLightingRatio,
          color_temp_k: customColorTemp,
          lut_emulation: customLutEmulation,
          aspect_ratio: aspectRatio,
          character_details: characters.length > 0 ? `${characters[0].name} (${characters[0].actor_reference})` : undefined
        })
      });
      if (res.ok) {
        const data = await res.json();
        setDopTestRenderUrl(data.image_url);
      }
    } catch (err) {
      console.error('Failed to run DoP test render:', err);
    } finally {
      setIsTestRenderingDoP(false);
    }
  };

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

  // Per-Scene Breakdown Loading Map
  const [breakingDownSceneMap, setBreakingDownSceneMap] = useState<Record<string, boolean>>({});

  // Run AI Multi-Camera Breakdown for a Specific Scene
  const handleBreakdownScene = async (sceneToBreakdown: ScreenplayScene, sceneIdx?: number) => {
    if (!sceneToBreakdown) return;
    const scNum = sceneToBreakdown.scene_number;
    setBreakingDownSceneMap(prev => ({ ...prev, [scNum]: true }));
    if (typeof sceneIdx === 'number') {
      setSelectedSceneIndex(sceneIdx);
    }

    try {
      const overrides: Record<string, any> = {};
      if (dopMode === 'matrix') {
        overrides.focal_length = customFocalLength;
        overrides.aperture = customAperture;
        overrides.color_temperature_k = customColorTemp;
        overrides.lighting_ratio = customLightingRatio;
        overrides.sensor_format = customSensorFormat;
        overrides.lut_emulation = customLutEmulation;
      }

      const res = await fetch('/api/script/breakdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scene: sceneToBreakdown,
          dop_preset: selectedPreset,
          dop_overrides: Object.keys(overrides).length > 0 ? overrides : null,
          custom_prompt: dopMode === 'prompt' ? customMoodPrompt : null,
          aspect_ratio: aspectRatio,
          character_profiles: characters
        })
      });

      if (res.ok) {
        const data = await res.json();
        const shots: ShotProposal[] = data.shots || [];
        setShotsMap(prev => ({
          ...prev,
          [scNum]: shots
        }));
        if (shots.length > 0) {
          setSelectedShotId(shots[0].id);
          setActiveCamLetter('A');
        }
      } else {
        const err = await res.json().catch(() => ({}));
        console.error('Breakdown API error:', err);
      }
    } catch (err) {
      console.error('Failed to generate shot breakdown:', err);
    } finally {
      setBreakingDownSceneMap(prev => ({ ...prev, [scNum]: false }));
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
          dop_preset: shot.dop_spec?.dop_preset || selectedPreset,
          lighting_ratio: shot.dop_spec?.lighting_ratio || customLightingRatio,
          color_temp_k: shot.dop_spec?.color_temperature_k || customColorTemp,
          lut_emulation: shot.dop_spec?.lut_emulation || customLutEmulation,
          aspect_ratio: aspectRatio,
          character_details: charDetails
        })
      });

      if (res.ok) {
        const data = await res.json();
        setShotsMap(prev => {
          const sceneShots = prev[shot.scene_number] || [];
          const updatedShots = sceneShots.map(s => {
            if (s.id === shot.id) {
              const updatedCameras = (s.cameras || []).map(c => {
                if (c.camera_letter === cam.camera_letter) {
                  return { ...c, image_url: data.image_url, status: 'generated' as const };
                }
                return c;
              });

              const activeCameraObj = updatedCameras.find(c => c.camera_letter === s.active_camera) || updatedCameras[0];

              return {
                ...s,
                cameras: updatedCameras,
                storyboard: {
                  ...s.storyboard,
                  image_url: activeCameraObj?.image_url || data.image_url,
                  prompt: activeCameraObj?.prompt || cam.prompt,
                  status: 'generated' as const
                }
              };
            }
            return s;
          });

          return {
            ...prev,
            [shot.scene_number]: updatedShots
          };
        });
      }
    } catch (err) {
      console.error('Failed to regenerate camera frame:', err);
    } finally {
      setGeneratingCamMap(prev => ({ ...prev, [genKey]: false }));
    }
  };

  // Helper to compute next camera letter (e.g. A -> B -> C -> D -> E -> F -> G...)
  const getNextCameraLetter = (existingLetters: string[]): string => {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    for (const char of alphabet) {
      if (!existingLetters.includes(char)) {
        return char;
      }
    }
    return `C${existingLetters.length + 1}`;
  };

  // Add a New Camera Angle to a Specific Shot Setup
  const handleAddCameraToShot = (shot: ShotProposal) => {
    if (!shot) return;
    const existingLetters = (shot.cameras || []).map(c => c.camera_letter);
    const nextLetter = getNextCameraLetter(existingLetters);

    // Preset configurations for typical multi-camera extensions
    let defaultRole = `Camera ${nextLetter} (Supplementary Coverage)`;
    let defaultFocal = 50;
    let defaultAperture = 'T2.8';
    let defaultSize = 'MCU';
    let defaultAngle = 'EYE_LEVEL';

    if (nextLetter === 'D') {
      defaultRole = 'Camera D (High Angle Crane / Wide POV)';
      defaultFocal = 24;
      defaultSize = 'WS';
      defaultAngle = 'HIGH_ANGLE';
    } else if (nextLetter === 'E') {
      defaultRole = 'Camera E (Extreme Close-Up Macro / Detail)';
      defaultFocal = 135;
      defaultSize = 'ECU';
      defaultAngle = 'EYE_LEVEL';
    } else if (nextLetter === 'F') {
      defaultRole = 'Camera F (Dynamic Steadicam / Low Dutch Angle)';
      defaultFocal = 35;
      defaultSize = 'MS';
      defaultAngle = 'LOW_ANGLE';
    }

    const charDetails = getActiveCharacterDetails(shot.characters);
    const prompt = `Cinematic 35mm film still, Camera ${nextLetter} (${defaultRole}), ${defaultSize} shot, ${defaultFocal}mm lens at ${defaultAperture}, ${defaultAngle.toLowerCase().replace('_', ' ')}, ${shot.dop_spec?.dop_preset || selectedPreset} lighting (${shot.dop_spec?.lighting_ratio || customLightingRatio}), ${shot.subject_description}${charDetails ? `, featuring ${charDetails}` : ''}, authentic film grain, anamorphic optical characteristics, 8k masterpiece.`;

    const newCam: CameraAngleProposal = {
      id: `CAM-${Date.now().toString(36).toUpperCase()}-${nextLetter}`,
      camera_letter: nextLetter,
      camera_role: defaultRole,
      shot_size: defaultSize,
      focal_length: defaultFocal,
      aperture: defaultAperture,
      camera_angle: defaultAngle,
      camera_movement: 'STATIC',
      coverage_description: defaultRole,
      prompt: prompt,
      status: 'pending'
    };

    setShotsMap(prev => {
      const sceneShots = prev[shot.scene_number] || [];
      return {
        ...prev,
        [shot.scene_number]: sceneShots.map(s => {
          if (s.id === shot.id) {
            return {
              ...s,
              cameras: [...s.cameras, newCam]
            };
          }
          return s;
        })
      };
    });

    setSelectedShotId(shot.id);
    setActiveCamLetter(nextLetter);
  };

  // Remove Camera Angle from a Shot Setup
  const handleRemoveCameraFromShot = (shot: ShotProposal, camLetter: string) => {
    if (!shot || shot.cameras.length <= 1) return;

    setShotsMap(prev => {
      const sceneShots = prev[shot.scene_number] || [];
      return {
        ...prev,
        [shot.scene_number]: sceneShots.map(s => {
          if (s.id === shot.id) {
            const filteredCameras = s.cameras.filter(c => c.camera_letter !== camLetter);
            const nextActive = filteredCameras[0]?.camera_letter || 'A';
            if (activeCamLetter === camLetter) {
              setActiveCamLetter(nextActive);
            }
            return {
              ...s,
              cameras: filteredCameras,
              active_camera: s.active_camera === camLetter ? nextActive : s.active_camera
            };
          }
          return s;
        })
      };
    });
  };

  // Update Specific Camera Properties (Focal Length, Aperture, Role, Angle, Size)
  const handleUpdateCameraProperty = (shot: ShotProposal, camLetter: string, patch: Partial<CameraAngleProposal>) => {
    setShotsMap(prev => {
      const sceneShots = prev[shot.scene_number] || [];
      return {
        ...prev,
        [shot.scene_number]: sceneShots.map(s => {
          if (s.id === shot.id) {
            const updatedCameras = (s.cameras || []).map(c => {
              if (c.camera_letter === camLetter) {
                return { ...c, ...patch };
              }
              return c;
            });
            return { ...s, cameras: updatedCameras };
          }
          return s;
        })
      };
    });
  };

  // Batch Render All Cameras for a Shot
  const handleRenderAllCamerasForShot = async (shot: ShotProposal) => {
    if (!shot || !shot.cameras) return;
    for (const cam of shot.cameras) {
      await handleRegenerateCameraFrame(shot, cam);
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

  // Generate Photorealistic 35mm Character Portrait
  const [generatingPortraitMap, setGeneratingPortraitMap] = useState<Record<string, boolean>>({});

  const handleGenerateCharacterPortrait = async (char: CharacterProfile) => {
    setGeneratingPortraitMap(prev => ({ ...prev, [char.id]: true }));
    try {
      const res = await fetch('/api/script/characters/generate-portrait', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_id: char.id,
          character_name: char.name,
          actor_reference: char.actor_reference,
          look_and_costume: char.look_and_costume,
          facial_features: char.facial_features,
          role: char.role,
          dop_preset: selectedPreset
        })
      });
      if (res.ok) {
        const data = await res.json();
        const updatedChar = { ...char, avatar_url: data.image_url, portrait_prompt: data.compiled_prompt };
        setCharacters(prev => prev.map(c => (c.id === char.id ? updatedChar : c)));
        setCharSaveSuccess(char.id);
        setTimeout(() => setCharSaveSuccess(null), 3000);
      }
    } catch (err) {
      console.error('Failed to generate portrait:', err);
    } finally {
      setGeneratingPortraitMap(prev => ({ ...prev, [char.id]: false }));
    }
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

  // Geometry for the selected shot camera, which carries its own focal length
  const selectedCamGeometry = computeViewfinderGeometry(
    customSensorFormat,
    aspectRatio,
    selectedCam?.focal_length ?? customFocalLength
  );

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
            className="px-3.5 py-1.5 text-xs font-semibold bg-purple-950/60 hover:bg-purple-900/80 text-purple-200 rounded-md border border-purple-500/40 transition flex items-center gap-1.5 shadow-sm"
          >
            <Upload className={`w-3.5 h-3.5 text-purple-400 ${isUploading ? 'animate-bounce' : ''}`} />
            {isUploading ? 'Uploading & Parsing...' : 'Upload Script (.fountain / .md / .txt / .pdf)'}
          </button>

          <button
            onClick={() => {
              setUploadedFileName(null);
              handleParseScript(DEMO_FOUNTAIN_SCRIPT);
            }}
            className="px-3.5 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-md border border-slate-700 transition flex items-center gap-1.5"
          >
            <FileText className="w-3.5 h-3.5 text-slate-400" />
            Load Demo Script
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
                    <label className="block text-xs font-bold text-slate-300 mb-1">Actor Screen Reference &amp; Physical Appearance</label>
                    <textarea
                      rows={2}
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

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {parsedScenes.map((sc, idx) => {
                const isSelected = selectedSceneIndex === idx;
                const isBreakingDownThisScene = breakingDownSceneMap[sc.scene_number];
                const sceneShots = shotsMap[sc.scene_number];
                const hasShots = sceneShots && sceneShots.length > 0;

                return (
                  <div
                    key={idx}
                    onClick={() => setSelectedSceneIndex(idx)}
                    className={`p-3.5 rounded-xl border transition cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? 'bg-purple-950/50 border-purple-500 text-white shadow-lg shadow-purple-500/10'
                        : 'bg-slate-900/40 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-900/80'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[10px] font-bold px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded font-mono">
                          SCENE {sc.scene_number}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {hasShots && (
                            <span className="text-[9px] font-extrabold px-1.5 py-0.2 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded font-mono">
                              {sceneShots.length} Setups
                            </span>
                          )}
                          <span className="text-[10px] font-semibold text-slate-400">{sc.time_of_day}</span>
                        </div>
                      </div>
                      <h4 className="text-xs font-bold truncate text-slate-100">{sc.heading}</h4>
                      <p className="text-[11px] text-slate-400 line-clamp-2 mt-1 leading-relaxed">
                        {sc.action_blocks[0] || 'No action description'}
                      </p>
                      {sc.characters && sc.characters.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {sc.characters.map((cName, cIdx) => (
                            <span key={cIdx} className="px-1.5 py-0.2 text-[9px] font-semibold bg-slate-800 text-purple-300 rounded border border-purple-500/20">
                              {cName}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Dedicated Scene Card Breakdown Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBreakdownScene(sc, idx);
                      }}
                      disabled={isBreakingDownThisScene}
                      className={`w-full mt-3 py-1.5 px-3 text-[11px] font-bold rounded-lg transition flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50 ${
                        hasShots
                          ? 'bg-purple-950/70 hover:bg-purple-900/90 text-purple-200 border border-purple-500/40'
                          : 'bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white shadow-lg shadow-purple-600/20'
                      }`}
                      title={`Run 3-Camera breakdown for Scene ${sc.scene_number}`}
                    >
                      {isBreakingDownThisScene ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 animate-spin text-purple-300" />
                          Breaking Down Scene {sc.scene_number}...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                          {hasShots ? `⚡ Re-Run AI 3-Cam Breakdown` : `⚡ Run AI 3-Cam Breakdown`}
                        </>
                      )}
                    </button>
                  </div>
                );
              })}
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
                <div className="flex flex-col items-center justify-center h-full text-center p-6 text-slate-400 space-y-3">
                  <Camera className="w-10 h-10 text-slate-600" />
                  <div>
                    <p className="text-xs font-bold text-slate-200">No Shot Setups Generated Yet</p>
                    <p className="text-[11px] text-slate-500 mt-1 max-w-xs">
                      Click <strong className="text-purple-400">"⚡ Run AI 3-Cam Breakdown"</strong> on any scene card on the left to generate 3 synchronized camera angles.
                    </p>
                  </div>
                  {currentScene && (
                    <button
                      onClick={() => handleBreakdownScene(currentScene, selectedSceneIndex)}
                      disabled={breakingDownSceneMap[currentScene.scene_number]}
                      className="px-4 py-2 text-xs font-bold bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-lg shadow-lg shadow-purple-600/30 transition flex items-center gap-1.5"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                      Breakdown Scene {currentScene.scene_number} Now
                    </button>
                  )}
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

                    {/* Camera Switcher & Multi-Angle Manager */}
                    <div className="flex items-center justify-between gap-1.5 mt-2.5 pt-2 border-t border-slate-800/80">
                      <div className="flex items-center gap-1 flex-wrap">
                        {shot.cameras.map(cam => (
                          <div key={cam.camera_letter} className="relative group/cam flex items-center">
                            <button
                              onClick={e => {
                                e.stopPropagation();
                                setSelectedShotId(shot.id);
                                setActiveCamLetter(cam.camera_letter);
                              }}
                              className={`px-2 py-1 text-[10px] font-bold rounded flex items-center gap-1 transition ${
                                selectedShot?.id === shot.id && activeCamLetter === cam.camera_letter
                                  ? 'bg-purple-600 text-white shadow-sm'
                                  : 'bg-slate-800/80 text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              <Camera className="w-2.5 h-2.5" />
                              Cam {cam.camera_letter}
                            </button>
                            {shot.cameras.length > 1 && (
                              <button
                                onClick={e => {
                                  e.stopPropagation();
                                  handleRemoveCameraFromShot(shot, cam.camera_letter);
                                }}
                                className="opacity-0 group-hover/cam:opacity-100 ml-0.5 p-0.5 text-slate-500 hover:text-rose-400 transition"
                                title={`Remove Camera ${cam.camera_letter}`}
                              >
                                <X className="w-2.5 h-2.5" />
                              </button>
                            )}
                          </div>
                        ))}

                        {/* Add Camera Angle Button */}
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            handleAddCameraToShot(shot);
                          }}
                          className="px-1.5 py-1 text-[10px] font-bold text-purple-300 hover:text-white bg-purple-950/40 hover:bg-purple-900/60 border border-purple-500/30 rounded flex items-center gap-0.5 transition"
                          title="Add an additional camera angle to this setup"
                        >
                          <Plus className="w-2.5 h-2.5" />
                          Cam
                        </button>
                      </div>

                      {/* 1-Click Render All Cams for this Setup */}
                      <button
                        onClick={e => {
                          e.stopPropagation();
                          handleRenderAllCamerasForShot(shot);
                        }}
                        className="px-2 py-1 text-[10px] font-bold text-amber-300 hover:text-white bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded flex items-center gap-1 transition shrink-0"
                        title={`Batch Render AI Concepts for all ${shot.cameras.length} Cameras`}
                      >
                        <Sparkles className="w-2.5 h-2.5" />
                        Render {shot.cameras.length} Cams
                      </button>
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
                {/* Multi-Camera Angle Selector Bar & Add/Remove Controls */}
                <div className="flex items-center justify-between pb-2 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {selectedShot.cameras.map(cam => (
                      <button
                        key={cam.camera_letter}
                        onClick={() => setActiveCamLetter(cam.camera_letter)}
                        className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                          activeCamLetter === cam.camera_letter
                            ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                            : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <Camera className="w-3 h-3" />
                        Cam {cam.camera_letter} ({cam.focal_length}mm)
                      </button>
                    ))}

                    <button
                      onClick={() => handleAddCameraToShot(selectedShot)}
                      className="px-2.5 py-1 text-xs font-bold text-purple-300 hover:text-white bg-purple-950/60 hover:bg-purple-900 border border-purple-500/40 rounded-lg flex items-center gap-1 transition"
                      title="Add New Camera Angle (e.g. Cam D, E, F)"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Cam
                    </button>
                  </div>

                  {selectedShot.cameras.length > 1 && (
                    <button
                      onClick={() => handleRemoveCameraFromShot(selectedShot, activeCamLetter)}
                      className="px-2.5 py-1 text-xs font-semibold text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 border border-rose-500/30 rounded-lg flex items-center gap-1 transition shrink-0"
                      title={`Delete Camera ${activeCamLetter} from this setup`}
                    >
                      <Trash2 className="w-3 h-3" />
                      Delete Cam {activeCamLetter}
                    </button>
                  )}
                </div>

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
                <div
                  className="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950 shadow-2xl group"
                  style={{ aspectRatio: `${selectedCamGeometry.aspect}` }}
                >
                  {selectedCam.image_url ? (
                    <img
                      src={selectedCam.image_url}
                      alt={selectedCam.prompt}
                      className="w-full h-full object-cover origin-center transition-transform duration-200"
                      style={{ transform: `scale(${selectedCamGeometry.framingScale.toFixed(4)})` }}
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500 text-xs">
                      <Camera className="w-8 h-8 mb-2 text-slate-600" />
                      Rendering Previz Frame...
                    </div>
                  )}

                  {/* Overlay Badge */}
                  <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/70 backdrop-blur text-[10px] font-mono font-bold text-purple-300 rounded border border-purple-500/30">
                    35mm Previz • {selectedShot.dop_spec?.dop_preset || selectedPreset}
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

                {/* Quick Optics Tuners (Focal Length, Aperture, Shot Size) */}
                <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                      <Sliders className="w-3 h-3 text-purple-400" />
                      Camera {activeCamLetter} Optics &amp; Framing:
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {selectedCam.shot_size} • {selectedCam.focal_length}mm • {selectedCam.aperture}
                    </span>
                  </div>

                  {/* Focal Length Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-slate-400 mr-1">Lens:</span>
                    {[18, 24, 35, 50, 85, 135].map(fl => (
                      <button
                        key={fl}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { focal_length: fl })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.focal_length === fl
                            ? 'bg-purple-600 text-white'
                            : 'bg-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {fl}mm
                      </button>
                    ))}
                  </div>

                  {/* Aperture Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-slate-400 mr-1">Iris:</span>
                    {['T1.4', 'T2.0', 'T2.8', 'T4.0', 'T5.6', 'T8.0'].map(ap => (
                      <button
                        key={ap}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { aperture: ap })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.aperture === ap
                            ? 'bg-purple-600 text-white'
                            : 'bg-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {ap}
                      </button>
                    ))}
                  </div>

                  {/* Shot Size Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-slate-400 mr-1">Framing:</span>
                    {['EWS', 'WS', 'MS', 'MCU', 'CU', 'ECU', 'OTS', 'POV'].map(sz => (
                      <button
                        key={sz}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { shot_size: sz })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.shot_size === sz
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {sz}
                      </button>
                    ))}
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
      {/* VIEW 3: DOP CINEMATOGRAPHY MATRIX & REAL-TIME OPTICAL VIEWFINDER          */}
      {/* ========================================================================= */}
      {studioSubTab === 'dop' && (
        <div className="flex-1 grid grid-cols-12 gap-0 overflow-hidden">
          {/* Left Column: DoP Mode Controls & Parameters */}
          <div className="col-span-6 bg-[#0F172A]/80 border-r border-slate-800 flex flex-col overflow-y-auto p-6 space-y-6">
            <div>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-purple-400" />
                    Director of Photography (DoP) Studio
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Define cinematography via Master Presets, Manual Optics Matrix, or Natural Language.
                  </p>
                </div>

                {/* DoP Aspect Ratio Framing Selector */}
                <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider px-1.5">Ratio:</span>
                  {['2.39:1', '1.85:1', '16:9', '4:3'].map(ar => (
                    <button
                      key={ar}
                      onClick={() => setAspectRatio(ar)}
                      className={`px-2.5 py-1 text-xs font-mono font-bold rounded-lg transition ${
                        aspectRatio === ar
                          ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                          : 'text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      {ar}
                    </button>
                  ))}
                </div>
              </div>

              {/* Mode Switcher Tabs */}
              <div className="grid grid-cols-3 gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800 mt-4">
                <button
                  onClick={() => setDopMode('preset')}
                  className={`py-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 ${
                    dopMode === 'preset'
                      ? 'bg-purple-600 text-white shadow-md'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Palette className="w-3.5 h-3.5" />
                  Master Presets
                </button>
                <button
                  onClick={() => setDopMode('matrix')}
                  className={`py-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 ${
                    dopMode === 'matrix'
                      ? 'bg-purple-600 text-white shadow-md'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Aperture className="w-3.5 h-3.5" />
                  Manual Matrix
                </button>
                <button
                  onClick={() => setDopMode('prompt')}
                  className={`py-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 ${
                    dopMode === 'prompt'
                      ? 'bg-purple-600 text-white shadow-md'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Terminal className="w-3.5 h-3.5" />
                  Natural Language
                </button>
              </div>
            </div>

            {/* MODE 1: MASTER PRESETS */}
            {dopMode === 'preset' && (
              <div className="space-y-3">
                <h3 className="text-xs font-extrabold uppercase text-slate-400 tracking-wider">
                  Curated Cinematographer Masters
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(presetsDict).map(([presetName, presetData]: [string, any]) => (
                    <div
                      key={presetName}
                      onClick={() => {
                        setSelectedPreset(presetName);
                        if (presetData.focal_length) setCustomFocalLength(presetData.focal_length);
                        if (presetData.aperture) setCustomAperture(presetData.aperture);
                        if (presetData.color_temperature_k) setCustomColorTemp(presetData.color_temperature_k);
                        if (presetData.lighting_ratio) setCustomLightingRatio(presetData.lighting_ratio);
                        if (presetData.lut_emulation) setCustomLutEmulation(presetData.lut_emulation);
                      }}
                      className={`p-3.5 rounded-xl border transition cursor-pointer ${
                        selectedPreset === presetName
                          ? 'bg-purple-950/60 border-purple-500 shadow-lg shadow-purple-500/20'
                          : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <h4 className="text-xs font-bold text-white">{presetData.name || presetName}</h4>
                      <p className="text-[10px] text-purple-300 mt-0.5">{presetData.tagline}</p>
                      <p className="text-[11px] text-slate-400 line-clamp-2 mt-1.5 leading-relaxed">{presetData.description}</p>
                      <div className="flex flex-wrap gap-1 mt-2.5">
                        <span className="px-1.5 py-0.5 text-[9px] bg-slate-800 text-slate-300 rounded">
                          {presetData.focal_length || 35}mm
                        </span>
                        <span className="px-1.5 py-0.5 text-[9px] bg-slate-800 text-slate-300 rounded">
                          {presetData.aperture || 'T2.8'}
                        </span>
                        <span className="px-1.5 py-0.5 text-[9px] bg-slate-800 text-slate-300 rounded">
                          {presetData.color_temperature_k || 5600}K
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* MODE 2: MANUAL OPTICS & LIGHTING MATRIX */}
            {dopMode === 'matrix' && (
              <div className="space-y-5">
                {/* Focal Length Selector */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                      <Camera className="w-3.5 h-3.5 text-purple-400" />
                      Lens Focal Length
                    </label>
                    <span className="text-xs font-mono font-bold text-purple-300">{customFocalLength}mm</span>
                  </div>
                  <div className="grid grid-cols-6 gap-1.5">
                    {[18, 24, 35, 50, 85, 135].map(fl => (
                      <button
                        key={fl}
                        onClick={() => setCustomFocalLength(fl)}
                        className={`py-1.5 text-xs font-bold rounded-lg border transition ${
                          customFocalLength === fl
                            ? 'bg-purple-600 border-purple-500 text-white'
                            : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {fl}mm
                      </button>
                    ))}
                  </div>
                </div>

                {/* Aperture Selector */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                      <Aperture className="w-3.5 h-3.5 text-purple-400" />
                      Lens Aperture &amp; Depth of Field
                    </label>
                    <span className="text-xs font-mono font-bold text-purple-300">{customAperture}</span>
                  </div>
                  <div className="grid grid-cols-6 gap-1.5">
                    {['T1.3', 'T1.4', 'T2.0', 'T2.8', 'T4.0', 'T5.6', 'T8.0', 'T11'].map(ap => (
                      <button
                        key={ap}
                        onClick={() => setCustomAperture(ap)}
                        className={`py-1.5 text-xs font-bold rounded-lg border transition ${
                          customAperture === ap
                            ? 'bg-purple-600 border-purple-500 text-white'
                            : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {ap}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Color Temperature Kelvin Slider */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                      <Sun className="w-3.5 h-3.5 text-amber-400" />
                      Color Temperature (Kelvin)
                    </label>
                    <span className="text-xs font-mono font-bold text-amber-300">{customColorTemp}K</span>
                  </div>
                  <input
                    type="range"
                    min="2800"
                    max="7500"
                    step="100"
                    value={customColorTemp}
                    onChange={e => setCustomColorTemp(Number(e.target.value))}
                    className="w-full h-2 bg-gradient-to-r from-amber-500 via-slate-200 to-cyan-500 rounded-lg appearance-none cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                    <span>2800K (Warm Tungsten)</span>
                    <span>5600K (Daylight)</span>
                    <span>7500K (Cool Blue Hour)</span>
                  </div>
                </div>

                {/* Lighting Ratio Selector */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-300">
                      Key-to-Fill Lighting Contrast Ratio
                    </label>
                    <span className="text-xs font-mono font-bold text-purple-300">{customLightingRatio}</span>
                  </div>
                  <div className="grid grid-cols-5 gap-1.5">
                    {[
                      { label: '1:1 (Flat)', val: '1:1' },
                      { label: '2:1 (Soft)', val: '2:1' },
                      { label: '4:1 (Dramatic)', val: '4:1' },
                      { label: '8:1 (Noir)', val: '8:1' },
                      { label: '16:1 (Silhouette)', val: '16:1' }
                    ].map(r => (
                      <button
                        key={r.val}
                        onClick={() => setCustomLightingRatio(r.val)}
                        className={`py-1.5 px-2 text-[11px] font-bold rounded-lg border transition ${
                          customLightingRatio === r.val
                            ? 'bg-purple-600 border-purple-500 text-white'
                            : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Sensor & Camera Body */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-300 mb-1">Camera Body / Sensor Format</label>
                    <select
                      value={customSensorFormat}
                      onChange={e => setCustomSensorFormat(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500"
                    >
                      {SENSOR_FORMATS.map(sf => (
                        <option key={sf.id} value={sf.id}>
                          {sf.label} — {sf.widthMm}×{sf.heightMm}mm
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-300 mb-1">Film Stock / LUT Emulation</label>
                    <select
                      value={customLutEmulation}
                      onChange={e => setCustomLutEmulation(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500"
                    >
                      <option value="Kodak 5219 Vision3 500T">Kodak 5219 Vision3 500T</option>
                      <option value="Kodak 5207 Vision3 250D">Kodak 5207 Vision3 250D</option>
                      <option value="Fujifilm Eterna 500">Fujifilm Eterna 500</option>
                      <option value="Bleach Bypass Custom LUT">Bleach Bypass Custom LUT</option>
                      <option value="Film Print Kodak 2383">Film Print Kodak 2383</option>
                      <option value="Technicolor 3-Strip Vintage">Technicolor 3-Strip Vintage</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* MODE 3: NATURAL LANGUAGE PROMPT DIRECTOR */}
            {dopMode === 'prompt' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1">
                    Natural Language Cinematography Instructions
                  </label>
                  <textarea
                    rows={4}
                    value={customMoodPrompt}
                    onChange={e => setCustomMoodPrompt(e.target.value)}
                    placeholder="e.g. Rain-slicked gothic great_hall square, pierced by harsh halogen searchlights, deep amber sodium vapor streetlamps, heavy volumetric water droplets, anamorphic horizontal streak flares, high-contrast dark copper shadows..."
                    className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500 font-sans leading-relaxed"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    Describe atmospheric textures, weather, motivated lighting directions, and palette nuances in plain English.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1.5">
                    Quick Cinematography Modifiers
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      '+ Volumetric Haze',
                      '+ Anamorphic Oval Bokeh',
                      '+ Chiaroscuro Rim Light',
                      '+ Eye Catchlights Glow',
                      '+ Bleach Bypass Contrast',
                      '+ Kodak 5219 Grain',
                      '+ Symmetrical 1-Point Framing',
                      '+ Rain Reflections on Cobblestones'
                    ].map(mod => (
                      <button
                        key={mod}
                        onClick={() => {
                          const cur = customMoodPrompt.trim();
                          setCustomMoodPrompt(cur ? `${cur}, ${mod}` : mod);
                        }}
                        className="px-2.5 py-1 text-[10px] font-semibold bg-slate-900 hover:bg-purple-950 text-slate-300 hover:text-purple-200 border border-slate-800 hover:border-purple-500/40 rounded-lg transition"
                      >
                        {mod}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Real-Time Optical Viewfinder & HUD Preview Canvas */}
          <div className="col-span-6 bg-[#090D16] flex flex-col overflow-y-auto p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-purple-400" />
                <h3 className="text-sm font-bold text-white">Real-Time Optical Viewfinder Simulation</h3>
              </div>
              <button
                onClick={() => setShowViewfinderGrid(!showViewfinderGrid)}
                className={`px-2.5 py-1 text-[11px] font-bold rounded border transition ${
                  showViewfinderGrid
                    ? 'bg-purple-600 text-white border-purple-500'
                    : 'bg-slate-900 text-slate-400 border-slate-800'
                }`}
              >
                Grid &amp; Crosshairs: {showViewfinderGrid ? 'ON' : 'OFF'}
              </button>
            </div>

            {/* Optical Viewfinder Canvas — open gate with delivery extraction */}
            <div
              className="relative rounded-2xl overflow-hidden border-2 border-slate-700 bg-black shadow-2xl group flex items-center justify-center"
              style={{
                // Open gate when the surround view is on, delivery ratio when off.
                aspectRatio: showSurround
                  ? `${geometry.sensor.widthMm} / ${geometry.sensor.heightMm}`
                  : `${geometry.aspect}`
              }}
            >
              {/* Underlying Master Still or Rendered Test.
                  Scaled by the angle-of-view ratio so focal length changes actually
                  reframe the plate. Magnification only — not perspective compression. */}
              <img
                src={dopTestRenderUrl || '/previz/interior_cam_a.jpg'}
                alt="DoP Optical Simulation"
                className="absolute inset-0 w-full h-full object-cover origin-center transition-transform duration-200"
                style={{
                  transform: `scale(${geometry.framingScale.toFixed(4)})`,
                  filter: `contrast(${
                    customLightingRatio === '16:1' ? 145 : customLightingRatio === '8:1' ? 125 : customLightingRatio === '4:1' ? 110 : 100
                  }%) brightness(${
                    customLightingRatio === '16:1' ? 85 : customLightingRatio === '8:1' ? 92 : 100
                  }%)`
                }}
              />

              {/* Dynamic Kelvin Color Tint Layer */}
              <div
                className="absolute inset-0 pointer-events-none transition-colors duration-300"
                style={{
                  backgroundColor:
                    customColorTemp <= 3400
                      ? 'rgba(245, 158, 11, 0.22)' // Warm Amber
                      : customColorTemp <= 4500
                      ? 'rgba(251, 191, 36, 0.12)' // Mild Golden
                      : customColorTemp <= 5800
                      ? 'rgba(255, 255, 255, 0.02)' // Neutral
                      : 'rgba(6, 182, 212, 0.22)', // Cold Cyan
                  mixBlendMode: 'color'
                }}
              />

              {/* Shallow Depth of Field Blur Simulation (for wide apertures T1.3/T1.4/T2.0) */}
              {['T1.3', 'T1.4', 'T1.8', 'T2.0'].includes(customAperture) && (
                <div className="absolute inset-0 pointer-events-none border-[16px] border-black/30 backdrop-blur-[2px] rounded-2xl" />
              )}

              {/* Delivery Extraction Window.
                  When the surround is on, the container is the full open gate and this
                  box is the recorded frame: everything outside it is dimmed, the way a
                  director's viewfinder shows what is available outside the delivery ratio. */}
              <div
                className="absolute pointer-events-none"
                style={{
                  width: `${(geometry.frame.widthMm / geometry.sensor.widthMm) * 100}%`,
                  height: `${(geometry.frame.heightMm / geometry.sensor.heightMm) * 100}%`,
                  left: '50%',
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                  boxShadow: showSurround ? '0 0 0 9999px rgba(2, 6, 23, 0.74)' : 'none',
                  border: showSurround ? '1px solid rgba(168, 85, 247, 0.9)' : 'none',
                  transition: 'width 200ms ease, height 200ms ease'
                }}
              >
                {/* Protect / shoot-and-protect frame lines inside the delivery frame */}
                {showViewfinderGrid && protectInset && (
                  <div
                    className="absolute border border-dashed border-amber-300/70"
                    style={{
                      width: `${protectInset.widthPct}%`,
                      height: `${protectInset.heightPct}%`,
                      left: '50%',
                      top: '50%',
                      transform: 'translate(-50%, -50%)'
                    }}
                  >
                    <span className="absolute -top-4 left-0 text-[9px] font-mono font-bold text-amber-300/90">
                      PROTECT {protectRatio}
                    </span>
                  </div>
                )}

                {/* Rule of Thirds Lines */}
                {showViewfinderGrid && (
                  <div className="absolute inset-0 grid grid-cols-3 grid-rows-3 pointer-events-none opacity-25">
                    <div className="border-r border-b border-white" />
                    <div className="border-r border-b border-white" />
                    <div className="border-b border-white" />
                    <div className="border-r border-b border-white" />
                    <div className="border-r border-b border-white" />
                    <div className="border-b border-white" />
                    <div className="border-r border-white" />
                    <div className="border-r border-white" />
                    <div />
                  </div>
                )}

                {/* Center Crosshairs */}
                {showViewfinderGrid && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-40">
                    <div className="w-8 h-8 border border-white/60 rounded-full flex items-center justify-center">
                      <div className="w-2 h-2 bg-purple-400 rounded-full" />
                    </div>
                  </div>
                )}
              </div>

              {/* On-Screen Display (OSD HUD) */}
              <div className="absolute inset-0 p-3 flex flex-col justify-between pointer-events-none font-mono text-[10px] text-emerald-400 select-none">
                <div className="flex items-center justify-between bg-black/50 backdrop-blur-sm px-2 py-1 rounded">
                  <div className="flex items-center gap-2">
                    <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="font-bold text-white">REC 24.0 FPS</span>
                    <span className="text-slate-400">• ARRI RAW</span>
                  </div>
                  <div className="text-purple-300 font-bold">
                    {aspectRatio} • {geometry.sensor.label}
                  </div>
                </div>

                <div className="flex items-center justify-between bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded">
                  <div className="flex items-center gap-3">
                    <span>
                      LENS: <strong className="text-white">{customFocalLength}mm</strong>
                    </span>
                    <span>
                      IRIS: <strong className="text-white">{customAperture}</strong>
                    </span>
                    <span>
                      CCT: <strong className="text-amber-300">{customColorTemp}K</strong>
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span>
                      HFOV: <strong className="text-purple-300">{geometry.hfovDeg.toFixed(1)}°</strong>
                    </span>
                    <span>
                      RATIO: <strong className="text-purple-300">{customLightingRatio}</strong>
                    </span>
                    <span className="text-slate-300">
                      LUT: <strong className="text-white">{customLutEmulation}</strong>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Viewfinder Controls & Computed Geometry Readout */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-300">Surround (open gate)</span>
                  <button
                    onClick={() => setShowSurround(!showSurround)}
                    className={`px-2.5 py-1 text-[11px] font-bold rounded border transition ${
                      showSurround
                        ? 'bg-purple-600 text-white border-purple-500'
                        : 'bg-slate-900 text-slate-400 border-slate-800'
                    }`}
                  >
                    {showSurround ? 'ON' : 'OFF'}
                  </button>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Protect:</span>
                  {PROTECT_RATIOS.map(pr => (
                    <button
                      key={pr}
                      onClick={() => setProtectRatio(pr)}
                      className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                        protectRatio === pr
                          ? 'bg-amber-500/90 text-slate-950'
                          : 'text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      {pr}
                    </button>
                  ))}
                </div>
              </div>

              <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3 font-mono text-[10px] text-slate-300 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500">EXTRACTION</span>
                  <strong className="text-white">
                    {geometry.frame.widthMm.toFixed(2)} × {geometry.frame.heightMm.toFixed(2)} mm
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">GATE USED</span>
                  <strong className="text-white">
                    {(geometry.frame.sensorAreaUsed * 100).toFixed(1)}% ({geometry.frame.limitedBy}-limited)
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">ANGLE OF VIEW</span>
                  <strong className="text-white">
                    {geometry.hfovDeg.toFixed(1)}° H × {geometry.vfovDeg.toFixed(1)}° V
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">CROP FACTOR</span>
                  <strong className="text-white">{geometry.cropFactor.toFixed(2)}× vs FF</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">PLATE SCALE</span>
                  <strong className="text-white">
                    {geometry.framingScale.toFixed(2)}× vs {REFERENCE_FOCAL_MM}mm
                  </strong>
                </div>
              </div>
            </div>

            <p className="text-[10px] text-slate-500 leading-relaxed">
              Framing is geometrically exact: angle of view and sensor extraction are computed from
              the selected format's open-gate dimensions. The plate is magnified to match the chosen
              focal length, but perspective compression cannot be recovered from a flat still — run a
              test render to see true optical character.
            </p>

            {/* Live Synthesized Generative Prompt */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  Live Compiled AI Generative Prompt
                </label>
              </div>
              <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl text-xs font-mono text-purple-200 leading-relaxed max-h-28 overflow-y-auto">
                {compileDoPPromptPreview()}
              </div>
            </div>

            {/* Test Render Button */}
            <button
              onClick={handleExecuteDoPTestRender}
              disabled={isTestRenderingDoP}
              className="w-full py-3 text-xs font-bold bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-xl shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isTestRenderingDoP ? (
                <>
                  <RotateCw className="w-4 h-4 animate-spin" />
                  Rendering Live DoP Optical Frame...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  ⚡ Test Render Live DoP Optical Frame
                </>
              )}
            </button>
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
