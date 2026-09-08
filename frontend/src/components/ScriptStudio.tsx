import React, { useState, useEffect, useRef, useMemo } from 'react';
import { fetchDemoScript, fetchScreenplay, pushEvent } from '../api';
import { Film, Camera, Sparkles, Sliders, RotateCw, Maximize2, FileText, Upload, CheckCircle2, Users, ShieldCheck, Loader2, Aperture, Crosshair, Plus, Pencil, Trash2, Link2, Check, X } from 'lucide-react';
import { CharacterProfileCard } from './CharacterProfileCard';
// Every screenplay type now lives in types.ts and is re-exported here, because
// this module used to declare its own copies and other files import some of
// them from this path.
export type {
  DialogueLine, CharacterRelationship, CharacterProfile, ScreenplayScene,
  DoPSpecification, CameraAngleProposal, StoryboardFrame, ShotProposal,
} from '../types';
import type {
  CharacterProfile, ScreenplayScene,
  DoPSpecification, CameraAngleProposal, ShotProposal,
} from '../types';
import {
  
  DEFAULT_SENSOR_ID,
  PROTECT_RATIOS,
  REFERENCE_FOCAL_MM,
  computeViewfinderGeometry,
  parseAspectRatio,
  protectFrameInset,
  depthOfField,
  formatDistance,
  whiteBalanceTint,
  miredShift,
  rgbToCss,
  extractedResolution,
  
  backgroundBlurRadius
} from '../optics';
import { DopControls, DopSettings } from './DopControls';
import {
  loadCustomPresets,
  saveCustomPresets,
  loadDeletedPresets,
  saveDeletedPresets,
  mergeActivePresets
} from '../presets';
import { useWebMCP } from '../hooks/useWebMCP';


/**
 * Tracks an element's rendered width in CSS pixels.
 *
 * The depth of field simulator converts a blur circle on the sensor into screen
 * pixels, so it needs to know how many pixels the frame is actually drawn
 * across. Assuming a fixed width overstates the blur on any smaller viewfinder.
 */
function useMeasuredWidth<T extends HTMLElement>(): [React.RefCallback<T>, number] {
  // The node is held in state, not a ref, so attaching it re-runs the effect
  // below. A ref plus a mount-effect looks equivalent but silently breaks under
  // StrictMode: setup/cleanup/setup leaves the observer disconnected, because
  // the node has not changed and the ref callback therefore never re-runs.
  const [node, setNode] = useState<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!node) return;

    // Runs after paint, so a panel that was still laying out when its tab
    // opened reports its real width rather than zero.
    const measure = () => setWidth(node.getBoundingClientRect().width);
    measure();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }

    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);

  return [setNode as React.RefCallback<T>, width];
}

/** Where the studio remembers which screenplay it had open. */
const STUDIO_SCRIPT_KEY = 'cinespine.studio.scriptId';

export const ScriptStudio: React.FC<{ productionId?: string }> = ({ productionId }) => {
  // Screenplay Editor State
  const [scriptTitle, setScriptTitle] = useState<string>('Demo Production');
  const [parsedScenes, setParsedScenes] = useState<ScreenplayScene[]>([]);
  const [characters, setCharacters] = useState<CharacterProfile[]>([]);
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);
  const [selectedSceneIndex, setSelectedSceneIndex] = useState<number>(0);
  const [studioSubTab, setStudioSubTab] = useState<'previz' | 'cast' | 'dop'>('previz');
  const [savingCharId, setSavingCharId] = useState<string | null>(null);
  const [charSaveSuccess, setCharSaveSuccess] = useState<string | null>(null);
  const [economyMode, setEconomyMode] = useState<boolean>(false);

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
  // Identity of the loaded screenplay; character edits are stored against it.
  const [scriptId, setScriptId] = useState<string | null>(null);
  // Which production is shooting this script. Attaching it is what lets an
  // editor working the reconciliation side open the scene behind a slate.
  const [productions, setProductions] = useState<Array<{ production_id: string; name: string }>>([]);
  const [attachedProductionId, setAttachedProductionId] = useState<string>('');
  const [attachError, setAttachError] = useState<string | null>(null);
  const [isAttaching, setIsAttaching] = useState<boolean>(false);
  const [charSaveError, setCharSaveError] = useState<string | null>(null);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [showSurround, setShowSurround] = useState<boolean>(true);
  const [protectRatio, setProtectRatio] = useState<string>('16:9');
  const [focusDistanceM, setFocusDistanceM] = useState<number>(3);
  const [whiteBalanceK, setWhiteBalanceK] = useState<number>(5600);
  const [customPresets, setCustomPresets] = useState<Record<string, any>>(() => loadCustomPresets());
  const [deletedPresets, setDeletedPresets] = useState<string[]>(() => loadDeletedPresets());
  const [backendPresets, setBackendPresets] = useState<Record<string, any>>({});
  const [presetsDict, setPresetsDict] = useState<Record<string, any>>(() =>
    mergeActivePresets({}, loadCustomPresets(), loadDeletedPresets())
  );
  const [enlargedImage, setEnlargedImage] = useState<{ url: string; prompt: string; title: string } | null>(null);
  const [generatingCamMap, setGeneratingCamMap] = useState<Record<string, boolean>>({});
  const [showCamSettings, setShowCamSettings] = useState<boolean>(false);
  const [showShotScript, setShowShotScript] = useState<boolean>(false);
  const [popupCharacter, setPopupCharacter] = useState<CharacterProfile | null>(null);

  useWebMCP([
    {
      name: 'set_dop_settings',
      description: 'Configure the Director of Photography settings in the studio.',
      inputSchema: {
        type: 'object',
        properties: {
          preset: { type: 'string', description: 'Name of the DoP preset (e.g. "Roger Deakins")' },
          focal_length: { type: 'number', description: 'Lens focal length in mm' },
          aperture: { type: 'string', description: 'Lens aperture (e.g. "T2.8")' },
          color_temp: { type: 'number', description: 'Color temperature in Kelvin' },
          lighting_ratio: { type: 'string', description: 'Lighting ratio (e.g. "4:1")' },
          sensor_format: { type: 'string', description: 'Sensor format ID (e.g. "super35", "fullframe")' },
          focus_distance: { type: 'number', description: 'Focus distance in meters' }
        }
      },
      execute: (inputs: any) => {
        // The two modes are exclusive: a preset ignores the matrix fields and
        // the matrix ignores the preset. An agent that sends both would get
        // the preset and silently lose its overrides, so the request is
        // refused rather than half-applied.
        const overrides = ['focal_length', 'aperture', 'color_temp', 'lighting_ratio', 'sensor_format', 'focus_distance']
          .filter(k => inputs[k] !== undefined && inputs[k] !== null && inputs[k] !== '');
        if (inputs.preset && overrides.length > 0) {
          return { error: `Send either preset or the matrix fields (${overrides.join(', ')}), not both: a preset ignores them.` };
        }
        if (inputs.preset) {
          if (!presetsDict[inputs.preset]) {
            return { error: `Unknown preset "${inputs.preset}". Known: ${Object.keys(presetsDict).join(', ')}.` };
          }
          setDopMode('preset');
          setSelectedPreset(inputs.preset);
          return { success: true, message: `DoP preset set to ${inputs.preset}.` };
        }
        if (overrides.length === 0) {
          return { error: 'Nothing to set: give a preset or at least one matrix field.' };
        }
        setDopMode('matrix');
        if (inputs.focal_length) setCustomFocalLength(inputs.focal_length);
        if (inputs.aperture) setCustomAperture(inputs.aperture);
        if (inputs.color_temp) setCustomColorTemp(inputs.color_temp);
        if (inputs.lighting_ratio) setCustomLightingRatio(inputs.lighting_ratio);
        if (inputs.sensor_format) setCustomSensorFormat(inputs.sensor_format);
        if (inputs.focus_distance) setFocusDistanceM(inputs.focus_distance);
        return { success: true, message: `DoP matrix updated: ${overrides.join(', ')}.` };
      }
    },
    {
      name: 'generate_dop_test_render',
      description: 'Trigger the AI to generate a storyboard test render with the current DoP settings.',
      inputSchema: { type: 'object', properties: {} },
      execute: async () => {
        await handleExecuteDoPTestRender();
        return { success: true, message: 'Test render generated.' };
      }
    },
    {
      name: 'select_character',
      description: 'Select a character from the loaded screenplay to view their profile.',
      inputSchema: {
        type: 'object',
        properties: {
          character_id: { type: 'string', description: 'The ID of the character to select' }
        },
        required: ['character_id']
      },
      execute: (inputs: any) => {
        setSelectedCharId(inputs.character_id);
        return { success: true, message: `Character ${inputs.character_id} selected.` };
      }
    }
  ]);

  // Re-compute active presets dictionary whenever backend, custom, or deleted presets change
  useEffect(() => {
    setPresetsDict(mergeActivePresets(backendPresets, customPresets, deletedPresets));
  }, [backendPresets, customPresets, deletedPresets]);

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

  // Geometric depth of field for the current lens, stop and focus distance
  const dof = useMemo(
    () => depthOfField(geometry.frame, customFocalLength, customAperture, focusDistanceM),
    [geometry.frame, customFocalLength, customAperture, focusDistanceM]
  );

  // CSS pixel blur simulation for the visual DoF engine. Measured against the
  // viewfinder's real width so the same lens reads the same at any panel size,
  // and against the extraction rather than the gate so a height-limited ratio
  // is not understated.
  const [viewfinderRef, viewfinderWidthPx] = useMeasuredWidth<HTMLDivElement>();
  const visualBlurRadius = useMemo(
    () => backgroundBlurRadius(
      customFocalLength, dof.fNumber, focusDistanceM, geometry.frame.widthMm, viewfinderWidthPx || 1000
    ),
    [customFocalLength, dof.fNumber, focusDistanceM, geometry.frame.widthMm, viewfinderWidthPx]
  );

  // Pixel dimensions the current extraction actually delivers
  const resolution = useMemo(
    () => extractedResolution(geometry.sensor, geometry.frame),
    [geometry.sensor, geometry.frame]
  );

  // Image only shifts colour when white balance disagrees with the key light
  const wbTint = useMemo(
    () => whiteBalanceTint(customColorTemp, whiteBalanceK),
    [customColorTemp, whiteBalanceK]
  );
  const wbMired = miredShift(customColorTemp, whiteBalanceK);

  // Log-scaled position (0-100%) of a distance on the focus scale bar
  const DEPTH_SCALE_MIN_M = 0.3;
  const DEPTH_SCALE_MAX_M = 100;
  const depthScalePos = (m: number): number => {
    if (!isFinite(m)) return 100;
    const v = Math.min(Math.max(m, DEPTH_SCALE_MIN_M), DEPTH_SCALE_MAX_M);
    return (Math.log(v / DEPTH_SCALE_MIN_M) / Math.log(DEPTH_SCALE_MAX_M / DEPTH_SCALE_MIN_M)) * 100;
  };

  // Dynamic Real-Time DoP Prompt Compiler
  const compileDoPPromptPreview = (): string => {
    if (dopMode === 'prompt' && customMoodPrompt.trim()) {
      return `Cinematic master film still, ${customMoodPrompt.trim()}, ${customFocalLength}mm lens at ${customAperture}, ${customColorTemp}K color temperature, ${customLightingRatio} lighting ratio, ${customLutEmulation} LUT, 8k resolution, authentic 35mm grain`;
    }
    if (dopMode === 'matrix') {
      const focusPhrase = `focused at ${formatDistance(focusDistanceM)} with ${
        dof.atInfinity ? 'deep focus to infinity' : `${formatDistance(dof.totalM)} of depth of field`
      }`;
      const wbPhrase =
        Math.abs(wbMired) < 1
          ? `${customColorTemp}K key light, neutrally balanced`
          : `${customColorTemp}K key light balanced at ${whiteBalanceK}K for a ${
              wbMired > 0 ? 'cool blue' : 'warm amber'
            } cast`;
      return `Cinematic master film still, captured on ${customSensorFormat}, ${customFocalLength}mm prime lens at ${customAperture} aperture, ${focusPhrase}, ${wbPhrase}, ${customLightingRatio} key-to-fill lighting ratio, ${customLutEmulation} film stock emulsion grade, 8k resolution, photorealistic master cinema frame`;
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
          economy_mode: economyMode,
          // Use the characters actually present in the selected scene, not the
          // first in the cast list.
          character_details: getActiveCharacterDetails() || undefined
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
        if (data.presets) {
          setBackendPresets(data.presets);
        }
      })
      .catch(err => {
        console.warn('Using built-in Master DoP catalog (backend offline or loading):', err);
      });

    fetch('/api/productions')
      .then(res => res.json())
      .then(data => { if (Array.isArray(data)) setProductions(data); })
      .catch(() => {
        // The studio works without a production list; only the attach control
        // needs it, and it says so itself when there is nothing to attach to.
      });
  }, []);

  /**
   * The loaded script survives a refresh.
   *
   * The backend stored it at parse time and restores breakdowns and profiles
   * per script, but the script itself lived only in this tab's memory, so a
   * reload emptied the studio. The id is remembered here; on mount it is
   * asked for whole, and forgotten if the server no longer has it.
   */
  useEffect(() => {
    if (typeof localStorage === 'undefined') return;
    const remembered = localStorage.getItem(STUDIO_SCRIPT_KEY);
    if (!remembered) return;
    let live = true;
    fetchScreenplay(remembered)
      .then(data => {
        if (!live) return;
        if (data.title) setScriptTitle(data.title);
        setScriptId(data.script_id || remembered);
        setParseWarnings([]);
        setParsedScenes(data.scenes || []);
        setCharacters(data.characters || []);
        if (data.characters && data.characters.length > 0) {
          setSelectedCharId(data.characters[0].id);
        }
        setSelectedSceneIndex(0);
      })
      .catch(() => {
        if (live) localStorage.removeItem(STUDIO_SCRIPT_KEY);
      });
    return () => { live = false; };
  }, []);

  /**
   * The production's linked screenplay loads when the production changes,
   * and only then.
   *
   * This used to re-run on every scriptId change too. Uploading a new script
   * set the new id, the effect fired, found the production still linked to
   * the previous script, and put the previous script back: a fresh upload
   * looked like it had not happened. The current id is read through a ref so
   * the comparison stays correct without making it a dependency.
   */
  const scriptIdRef = useRef<string | null>(null);
  scriptIdRef.current = scriptId;

  useEffect(() => {
    if (!productionId) return;
    let live = true;
    fetch(`/api/script/link?production_id=${encodeURIComponent(productionId)}`)
      .then(res => res.json())
      .then(data => {
        if (!live) return;
        if (data && data.script_id && data.script_id !== scriptIdRef.current) {
          fetchScreenplay(data.script_id)
            .then(scriptData => {
              if (!live) return;
              if (scriptData.title) setScriptTitle(scriptData.title);
              setScriptId(data.script_id);
              setParseWarnings([]);
              setParsedScenes(scriptData.scenes || []);
              setCharacters(scriptData.characters || []);
              if (scriptData.characters && scriptData.characters.length > 0) {
                setSelectedCharId(scriptData.characters[0].id);
              }
              setSelectedSceneIndex(0);
              setShotsMap(scriptData.shots || {});
              setAttachedProductionId(productionId);
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
    return () => { live = false; };
  }, [productionId]);

  useEffect(() => {
    if (typeof localStorage === 'undefined' || !scriptId) return;
    localStorage.setItem(STUDIO_SCRIPT_KEY, scriptId);
  }, [scriptId]);


  const globalDopSettings: DopSettings = {
    dopMode, aspectRatio, selectedPreset, customFocalLength, customAperture,
    focusDistanceM, customColorTemp, whiteBalanceK, customLightingRatio,
    customSensorFormat, customLutEmulation, customMoodPrompt
  };

  const handleGlobalDopChange = (updates: Partial<DopSettings>) => {
    if (updates.dopMode !== undefined) setDopMode(updates.dopMode);
    if (updates.aspectRatio !== undefined) setAspectRatio(updates.aspectRatio);
    if (updates.selectedPreset !== undefined) setSelectedPreset(updates.selectedPreset);
    if (updates.customFocalLength !== undefined) setCustomFocalLength(updates.customFocalLength);
    if (updates.customAperture !== undefined) setCustomAperture(updates.customAperture);
    if (updates.focusDistanceM !== undefined) setFocusDistanceM(updates.focusDistanceM);
    if (updates.customColorTemp !== undefined) setCustomColorTemp(updates.customColorTemp);
    if (updates.whiteBalanceK !== undefined) setWhiteBalanceK(updates.whiteBalanceK);
    if (updates.customLightingRatio !== undefined) setCustomLightingRatio(updates.customLightingRatio);
    if (updates.customSensorFormat !== undefined) setCustomSensorFormat(updates.customSensorFormat);
    if (updates.customLutEmulation !== undefined) setCustomLutEmulation(updates.customLutEmulation);
    if (updates.customMoodPrompt !== undefined) setCustomMoodPrompt(updates.customMoodPrompt);
  };

  const handleSavePreset = (name: string, tagline: string, description: string, basePresetOverrides?: Partial<DopSettings>) => {
    const newPreset = {
      name,
      tagline,
      description,
      focal_length: basePresetOverrides?.customFocalLength || customFocalLength,
      aperture: basePresetOverrides?.customAperture || customAperture,
      color_temperature_k: basePresetOverrides?.customColorTemp || customColorTemp,
      lighting_ratio: basePresetOverrides?.customLightingRatio || customLightingRatio,
      lut_emulation: basePresetOverrides?.customLutEmulation || customLutEmulation,
      prompt_style_tag: basePresetOverrides?.customMoodPrompt || customMoodPrompt,
      is_custom: true
    };
    
    // If it was previously in deletedPresets, un-delete it
    if (deletedPresets.includes(name)) {
      const nextDeleted = deletedPresets.filter(n => n !== name);
      setDeletedPresets(nextDeleted);
      saveDeletedPresets(nextDeleted);
    }

    setCustomPresets(prev => {
      const next = { ...prev, [name]: newPreset };
      saveCustomPresets(next);
      return next;
    });
    
    // Automatically select it globally
    setSelectedPreset(name);
    setDopMode('preset');
  };

  const handleDeletePreset = (name: string) => {
    // 1. If it's a custom preset, remove from customPresets
    if (customPresets[name]) {
      setCustomPresets(prev => {
        const next = { ...prev };
        delete next[name];
        saveCustomPresets(next);
        return next;
      });
    }

    // 2. Mark as deleted so built-in / backend presets are also suppressed
    const nextDeleted = Array.from(new Set([...deletedPresets, name]));
    setDeletedPresets(nextDeleted);
    saveDeletedPresets(nextDeleted);

    // 3. If currently selected, fallback to the first available active preset
    if (selectedPreset === name) {
      const remainingKeys = Object.keys(presetsDict).filter(k => k !== name);
      if (remainingKeys.length > 0) {
        setSelectedPreset(remainingKeys[0]);
      }
    }
  };

  const handleResetPresets = () => {
    setDeletedPresets([]);
    saveDeletedPresets([]);
  };

  const handleCamDopChange = (shot: ShotProposal, camLetter: string, updates: Partial<DopSettings>) => {
    setShotsMap(prev => {
      const sceneShots = prev[shot.scene_number] || [];
      const updatedShots = sceneShots.map(s => {
        if (s.id === shot.id) {
          const updatedCameras = (s.cameras || []).map(c => {
            if (c.camera_letter === camLetter) {
              const currentSpec = c.dop_spec || {};
              const nextSpec = { ...currentSpec };
              
              if (updates.dopMode !== undefined) nextSpec.dopMode = updates.dopMode;
              if (updates.customColorTemp !== undefined) nextSpec.color_temp_k = updates.customColorTemp;
              if (updates.whiteBalanceK !== undefined) nextSpec.whiteBalanceK = updates.whiteBalanceK;
              if (updates.customLightingRatio !== undefined) nextSpec.lighting_ratio = updates.customLightingRatio;
              if (updates.customLutEmulation !== undefined) nextSpec.lut_emulation = updates.customLutEmulation;
              if (updates.selectedPreset !== undefined) nextSpec.dop_preset = updates.selectedPreset;
              if (updates.customMoodPrompt !== undefined) nextSpec.prompt_style_tag = updates.customMoodPrompt;
              
              return { 
                ...c, 
                dop_spec: nextSpec,
                focal_length: updates.customFocalLength !== undefined ? updates.customFocalLength : c.focal_length,
                aperture: updates.customAperture !== undefined ? updates.customAperture : c.aperture
              };
            }
            return c;
          });
          return { ...s, cameras: updatedCameras };
        }
        return s;
      });
      return { ...prev, [shot.scene_number]: updatedShots };
    });
  };

  const [isParsingDemo, setIsParsingDemo] = useState<boolean>(false);
  const [uploadStage, setUploadStage] = useState<string>('Ingesting screenplay file...');
  const [uploadProgress, setUploadProgress] = useState<number>(0);

  // Parse Script Handler
  /**
   * The demo script comes from the server (data/examples/demo_script.fountain)
   * rather than a string in this bundle, so the studio and the demo paperwork
   * describe the same screenplay and editing one file changes both.
   */
  const handleLoadDemo = async () => {
    setUploadedFileName(null);
    setIsParsingDemo(true);
    try {
      const demo = await fetchDemoScript();
      setUploadedFileName(demo.filename);
      await handleParseScript(demo.script_text);
    } catch (err) {
      console.error('Failed to load the demo screenplay:', err);
      setIsParsingDemo(false);
    }
  };

  const handleParseScript = async (textToParse: string, title?: string) => {
    setIsParsingDemo(true);
    try {
      const activeTitle = title || scriptTitle;
      const res = await fetch('/api/script/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: textToParse, title: activeTitle })
      });
      if (res.ok) {
        const data = await res.json();
        pushEvent('cinespine.parse', {
          script_id: data.script_id, scenes: data.scenes?.length,
          characters: data.characters?.length, warnings: data.parse_warnings?.length,
        });
        if (data.title) setScriptTitle(data.title);
        setScriptId(data.script_id || null);
        setParseWarnings(data.parse_warnings || []);
        setParsedScenes(data.scenes || []);
        setCharacters(data.characters || []);
        if (data.characters && data.characters.length > 0) {
          setSelectedCharId(data.characters[0].id);
        }
        setSelectedSceneIndex(0);
      }
    } catch (err) {
      console.error('Failed to parse screenplay:', err);
    } finally {
      setIsParsingDemo(false);
    }
  };

  // What has already been written for each scene, so the save-on-change effect
  // below can tell a real edit from the assignment that restored it.
  const savedBreakdowns = useRef<Record<string, string>>({});
  const [isRestoringBreakdowns, setIsRestoringBreakdowns] = useState(false);

  /**
   * Brings back the breakdowns already worked out for this screenplay.
   *
   * The coverage is generated once and then edited -- a focal length nudged, a
   * prompt rewritten and re-rendered -- and all of it used to live in this
   * tab's memory, so a reload threw away the work and the generations it cost.
   */
  useEffect(() => {
    if (!scriptId) return;
    let live = true;
    setIsRestoringBreakdowns(true);
    fetch(`/api/script/${encodeURIComponent(scriptId)}/breakdowns`)
      .then(res => res.json())
      .then(data => {
        if (!live) return;
        const restored: Record<string, ShotProposal[]> = data?.breakdowns || {};
        // Seeded before the state lands, so restoring does not read as an edit
        // and immediately write back what it just read.
        savedBreakdowns.current = Object.fromEntries(
          Object.entries(restored).map(([scene, shots]) => [scene, JSON.stringify(shots)])
        );
        if (Object.keys(restored).length > 0) setShotsMap(restored);
      })
      .catch(() => {
        // The studio works without them; only the restore is lost.
      })
      .finally(() => { if (live) setIsRestoringBreakdowns(false); });
    return () => { live = false; };
  }, [scriptId]);

  /**
   * Keeps every change to a breakdown, whatever made it.
   *
   * Watching the map rather than calling a save from each of the six places
   * that edit it: adding a camera, changing a focal length, rewriting a
   * prompt, re-rendering a frame. Debounced, because a slider drag is one
   * edit to a person and thirty to React.
   */
  useEffect(() => {
    if (!scriptId || isRestoringBreakdowns) return;

    const timer = setTimeout(() => {
      for (const [sceneNumber, shots] of Object.entries(shotsMap)) {
        const serialized = JSON.stringify(shots);
        if (savedBreakdowns.current[sceneNumber] === serialized) continue;
        savedBreakdowns.current[sceneNumber] = serialized;
        fetch(`/api/script/${encodeURIComponent(scriptId)}/breakdowns/${encodeURIComponent(sceneNumber)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ shots })
        }).catch(() => {
          // Let the next edit try again rather than claiming this one stuck.
          delete savedBreakdowns.current[sceneNumber];
        });
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [shotsMap, scriptId, isRestoringBreakdowns]);

  /**
   * Shows the production this script is already attached to, if any.
   *
   * The link is stored against the production, so without asking the other way
   * round the control would offer to attach a script that is attached already,
   * and a reload would make an existing link look absent.
   */
  useEffect(() => {
    if (!scriptId) { setAttachedProductionId(''); return; }
    let live = true;
    fetch(`/api/script/link?script_id=${encodeURIComponent(scriptId)}`)
      .then(res => res.json())
      .then(data => {
        if (live) setAttachedProductionId(data?.production_ids?.[0] ?? '');
      })
      .catch(() => {
        // Leave the control offering to attach; the attempt itself will say
        // if the server is unreachable.
      });
    return () => { live = false; };
  }, [scriptId]);

  /**
   * Attaches the loaded screenplay to a production.
   *
   * One script per production: a production with two scripts has no answer to
   * "what is scene 119", so attaching a second one replaces the first.
   */
  const handleAttachToProduction = async (productionId: string) => {
    setAttachedProductionId(productionId);
    setAttachError(null);
    if (!productionId || !scriptId) return;
    setIsAttaching(true);
    try {
      const res = await fetch('/api/script/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ production_id: productionId, script_id: scriptId })
      });
      if (!res.ok) {
        setAttachedProductionId('');
        setAttachError('Could not attach this script. Try loading it again.');
      }
    } catch {
      setAttachedProductionId('');
      setAttachError('Could not reach the server to attach this script.');
    } finally {
      setIsAttaching(false);
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
          character_profiles: characters,
          script_id: scriptId
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
          dop_preset: cam.dop_spec?.dop_preset || selectedPreset,
          lighting_ratio: cam.dop_spec?.lighting_ratio || customLightingRatio,
          color_temp_k: cam.dop_spec?.color_temp_k || customColorTemp,
          lut_emulation: cam.dop_spec?.lut_emulation || customLutEmulation,
          aspect_ratio: aspectRatio,
          character_details: charDetails,
          economy_mode: economyMode
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
  // ------------------------------------------------------------------ //
  // Setups: adding, editing and removing a shot
  //
  // The breakdown is a proposal, not a schedule. A DoP reads it and wants a
  // setup the model did not think of, or wants one gone, or wants the framing
  // called something else -- and until now the only way to change any of that
  // was to re-run the whole scene and lose every camera and frame with it.
  // ------------------------------------------------------------------ //

  /** What a setup may be, so the list stays countable and sortable. */
  const SHOT_SIZES = ['EWS', 'WS', 'MWS', 'MS', 'MCU', 'CU', 'ECU', 'OTS', 'POV', 'INSERT'];
  const CAMERA_ANGLES = ['EYE_LEVEL', 'LOW_ANGLE', 'HIGH_ANGLE', 'DUTCH_ANGLE', 'OVERHEAD', 'WORM_EYE'];
  const CAMERA_MOVEMENTS = ['STATIC', 'PAN_TILT', 'DOLLY_IN', 'DOLLY_OUT', 'SLIDER', 'HANDHELD', 'STEADICAM', 'CRANE'];

  // Which setup is open for editing, by id. One at a time: two open forms in a
  // narrow column is a column nobody can read.
  const [editingShotId, setEditingShotId] = useState<string | null>(null);

  const handleAddShotToScene = (scene: ScreenplayScene) => {
    if (!scene) return;
    const sceneShots = shotsMap[scene.scene_number] || [];
    const shotNumber = String(sceneShots.length + 1);
    const shotId = `SHOT-${scene.scene_number}-${Date.now().toString(36).toUpperCase()}`;

    const newShot: ShotProposal = {
      id: shotId,
      scene_number: scene.scene_number,
      shot_number: shotNumber,
      shot_name: `SCENE ${scene.scene_number} - SHOT ${shotNumber}`,
      shot_size: 'MS',
      camera_angle: 'EYE_LEVEL',
      camera_movement: 'STATIC',
      dramatic_beat: '',
      subject_description: '',
      characters: scene.characters || [],
      // The scene's own optics, so a hand-added setup matches the ones around
      // it rather than resetting to a different look.
      dop_spec: sceneShots[0]?.dop_spec || {
        dop_preset: selectedPreset,
        focal_length: customFocalLength,
        aperture: customAperture,
        color_temperature_k: customColorTemp,
        lighting_ratio: customLightingRatio,
        sensor_format: customSensorFormat,
        lut_emulation: customLutEmulation,
        lighting_style: '',
        mood_notes: customMoodPrompt
      } as DoPSpecification,
      cameras: [{
        id: `CAM-${shotId}-A`,
        camera_letter: 'A',
        camera_role: 'Primary Setup',
        shot_size: 'MS',
        focal_length: 50,
        aperture: 'T2.8',
        camera_angle: 'EYE_LEVEL',
        camera_movement: 'STATIC',
        coverage_description: 'Primary coverage.',
        prompt: '',
        status: 'pending'
      }],
      active_camera: 'A',
      storyboard: { image_url: undefined, prompt: '', aspect_ratio: aspectRatio, status: 'pending' }
    };

    setShotsMap(prev => ({
      ...prev,
      [scene.scene_number]: [...sceneShots, newShot]
    }));
    setSelectedShotId(shotId);
    setActiveCamLetter('A');
    setEditingShotId(shotId);
  };

  const handleUpdateShotProperty = (shot: ShotProposal, patch: Partial<ShotProposal>) => {
    setShotsMap(prev => {
      const sceneShots = prev[shot.scene_number] || [];
      return {
        ...prev,
        [shot.scene_number]: sceneShots.map(s => (s.id === shot.id ? { ...s, ...patch } : s))
      };
    });
  };

  const handleRemoveShotFromScene = (shot: ShotProposal) => {
    setShotsMap(prev => {
      const remaining = (prev[shot.scene_number] || []).filter(s => s.id !== shot.id);
      // Move the selection off the setup that is going, rather than leaving
      // the canvas pointed at something that no longer exists.
      if (selectedShotId === shot.id) {
        setSelectedShotId(remaining[0]?.id || null);
        setActiveCamLetter(remaining[0]?.active_camera || 'A');
      }
      return { ...prev, [shot.scene_number]: remaining };
    });
    setEditingShotId(current => (current === shot.id ? null : current));
  };

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
          dop_preset: selectedPreset,
          economy_mode: economyMode,
          // Named so the server can keep the portrait against the character
          // rather than handing it back to be lost on the next reload.
          script_id: scriptId
        })
      });
      if (res.ok) {
        const data = await res.json();
        const updatedChar = { ...char, avatar_url: data.image_url, portrait_prompt: data.compiled_prompt };
        setCharacters(prev => prev.map(c => (c.id === char.id ? updatedChar : c)));
        // Only claim it was saved when it was. The portrait appearing is its
        // own confirmation that it generated.
        if (data.saved) {
          setCharSaveSuccess(char.id);
          setTimeout(() => setCharSaveSuccess(null), 3000);
        }
      }
    } catch (err) {
      console.error('Failed to generate portrait:', err);
    } finally {
      setGeneratingPortraitMap(prev => ({ ...prev, [char.id]: false }));
    }
  };

  // Update Character Profile Handler
  const handleUpdateCharacter = async (char: CharacterProfile) => {
    if (!scriptId) {
      setCharSaveError('Upload or parse a screenplay before saving character edits.');
      return;
    }
    setSavingCharId(char.id);
    setCharSaveError(null);
    try {
      const res = await fetch('/api/script/characters/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...char, script_id: scriptId })
      });
      if (res.ok) {
        const data = await res.json();
        // Trust the stored record so the UI reflects what was actually saved.
        setCharacters(prev => prev.map(c => (c.id === char.id ? { ...c, ...data.character } : c)));
        setCharSaveSuccess(char.id);
        setTimeout(() => setCharSaveSuccess(null), 3000);
      } else {
        const detail = await res.json().catch(() => null);
        setCharSaveError(detail?.detail || `Save failed (HTTP ${res.status}).`);
      }
    } catch (err) {
      console.error('Failed to update character profile:', err);
      setCharSaveError('Save failed: could not reach the server.');
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
  const selectedCamFocalLength = selectedCam?.focal_length ?? customFocalLength;
  const selectedCamGeometry = useMemo(
    () => computeViewfinderGeometry(customSensorFormat, aspectRatio, selectedCamFocalLength),
    [customSensorFormat, aspectRatio, selectedCamFocalLength]
  );
  const selectedCamDof = useMemo(
    () => depthOfField(selectedCamGeometry.frame, selectedCamFocalLength, customAperture, focusDistanceM),
    [selectedCamGeometry.frame, selectedCamFocalLength, customAperture, focusDistanceM]
  );
  const [previzFrameRef, previzFrameWidthPx] = useMeasuredWidth<HTMLDivElement>();
  const selectedCamBlurRadius = useMemo(
    () => backgroundBlurRadius(
      selectedCamFocalLength, selectedCamDof.fNumber, focusDistanceM,
      selectedCamGeometry.frame.widthMm, previzFrameWidthPx || 1000
    ),
    [selectedCamFocalLength, selectedCamDof.fNumber, focusDistanceM, selectedCamGeometry.frame.widthMm, previzFrameWidthPx]
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
    setUploadStage('Ingesting file & normalizing screenplay text...');
    setUploadProgress(15);

    const timer1 = setTimeout(() => {
      setUploadStage('Extracting scene headers, action blocks & dialogue...');
      setUploadProgress(38);
    }, 1200);

    const timer2 = setTimeout(() => {
      setUploadStage('Running Gemini AI character inference & cast profiling...');
      setUploadProgress(68);
    }, 3800);

    const timer3 = setTimeout(() => {
      setUploadStage('Compiling multi-camera setups (Cam A, B, C) & optical matrix...');
      setUploadProgress(88);
    }, 8000);

    const timer4 = setTimeout(() => {
      setUploadStage('Finalizing persistent character profiles & studio scenes...');
      setUploadProgress(95);
    }, 14000);

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
        setScriptId(data.script_id || null);
        setParseWarnings(data.parse_warnings || []);
        setParsedScenes(data.scenes || []);
        setCharacters(data.characters || []);
        if (data.characters && data.characters.length > 0) {
          setSelectedCharId(data.characters[0].id);
        }
        setSelectedSceneIndex(0);
        // Only when this is a different screenplay. Re-uploading the same file
        // resolves to the same script id and its breakdowns are still that
        // script's, so clearing them would hide work the server still holds.
        if (data.script_id !== scriptId) {
          setShotsMap({});
          setSelectedShotId(null);
        }
      } else {
        const text = await file.text();
        await handleParseScript(text, file.name.replace(/\.[^/.]+$/, ''));
      }
    } catch (err) {
      console.error('Screenplay upload failed, parsing locally:', err);
      try {
        const text = await file.text();
        await handleParseScript(text, file.name.replace(/\.[^/.]+$/, ''));
      } catch (readErr) {
        console.error('Local text read failed:', readErr);
      }
    } finally {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
      setUploadProgress(100);
      setTimeout(() => {
        setIsUploading(false);
      }, 400);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#090D16] text-slate-100 font-sans relative">
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
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr bg-spine-800 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/20">
            <Film className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-white tracking-wide">Screenplay &amp; Visual Director Studio</h1>
              <span className="px-2 py-0.5 text-[10px] font-extrabold uppercase bg-spine-accent/20 text-spine-accent border border-spine-accent/30 rounded-full">
                Multi-Camera (A, B, C) Previz
              </span>
              {uploadedFileName && (
                <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-spine-success/20 text-spine-success border border-spine-success/30 rounded-md">
                  <CheckCircle2 className="w-3 h-3 text-spine-success" />
                  {uploadedFileName}
                </span>
              )}
            </div>
            {parseWarnings.length > 0 && (
              <div className="mt-2 p-3 bg-spine-warning/50 border border-spine-warning/40 rounded-lg text-[11px] text-spine-warning space-y-1">
                <div className="font-bold">Parsed with warnings:</div>
                {parseWarnings.map((w, i) => (
                  <div key={i}>• {w}</div>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-300">
              Multi-Format Screenplay Ingestion (.fountain / .md / .txt / .pdf) • Cast Character Profiler • Tri-Modal DoP Previz
            </p>
          </div>
        </div>

        {/* Action Controls Top Bar */}
        <div className="flex items-center gap-2.5">
          {/* Attach this script to a production, so an editor working a slate
              on the reconciliation side can open the scene behind it. */}
          <div className="flex items-center gap-1.5">
            <Link2 className={`w-3.5 h-3.5 ${attachedProductionId ? 'text-spine-success' : 'text-gray-500'}`} />
            <select
              value={attachedProductionId}
              onChange={e => handleAttachToProduction(e.target.value)}
              disabled={!scriptId || isAttaching || productions.length === 0}
              title="The production shooting this script"
              className="bg-slate-800 border border-slate-700 text-gray-200 text-xs rounded-md px-2 py-1.5 disabled:opacity-50"
            >
              <option value="">
                {productions.length === 0 ? 'No productions yet' : 'Attach to production...'}
              </option>
              {productions.map(p => (
                <option key={p.production_id} value={p.production_id}>{p.name}</option>
              ))}
            </select>
            {attachedProductionId && !isAttaching && !attachError && (
              <Check className="w-3.5 h-3.5 text-spine-success" />
            )}
            {attachError && (
              <span className="text-[10px] text-red-400 max-w-[10rem]">{attachError}</span>
            )}
          </div>

          {/* Upload Script File Button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className={`px-3.5 py-1.5 text-xs font-semibold rounded-md border transition flex items-center gap-1.5 shadow-sm ${
              isUploading
                ? 'bg-spine-900/80 text-spine-accent border-spine-accent animate-pulse cursor-wait'
                : 'bg-spine-900/60 hover:bg-spine-900/80 text-spine-accent border-spine-accent/40'
            }`}
          >
            {isUploading ? (
              <Loader2 className="w-3.5 h-3.5 text-spine-accent animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5 text-spine-accent" />
            )}
            {isUploading ? 'Ingesting Screenplay...' : 'Upload Script (.fountain / .md / .txt / .pdf)'}
          </button>

          <button
            onClick={handleLoadDemo}
            disabled={isUploading || isParsingDemo}
            className="px-3.5 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-gray-200 rounded-md border border-slate-700 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            {isParsingDemo ? (
              <Loader2 className="w-3.5 h-3.5 text-gray-300 animate-spin" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-gray-300" />
            )}
            {isParsingDemo ? 'Loading Demo...' : 'Load Demo Script'}
          </button>

          {/* Economy Mode Toggle */}
          <button
            onClick={() => setEconomyMode(!economyMode)}
            className={`px-3.5 py-1.5 text-xs font-semibold rounded-md border transition flex items-center gap-1.5 shadow-sm ${
              economyMode
                ? 'bg-spine-success/60 hover:bg-emerald-900/80 text-spine-success border-spine-success/40'
                : 'bg-slate-800 hover:bg-slate-700 text-gray-300 border-slate-700'
            }`}
            title="Economy Mode uses free APIs and caches to save AI credits"
          >
            <ShieldCheck className={`w-3.5 h-3.5 ${economyMode ? 'text-spine-success' : 'text-gray-400'}`} />
            Economy Mode {economyMode ? 'ON' : 'OFF'}
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
                ? 'bg-spine-accent text-white shadow-md shadow-purple-600/20'
                : 'text-gray-300 hover:text-gray-100 hover:bg-slate-800/60'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            3-Camera Previz &amp; Breakdown
          </button>

          <button
            onClick={() => setStudioSubTab('cast')}
            className={`px-4 py-1.5 text-xs font-bold rounded-md flex items-center gap-2 transition ${
              studioSubTab === 'cast'
                ? 'bg-spine-accent text-white shadow-md shadow-purple-600/20'
                : 'text-gray-300 hover:text-gray-100 hover:bg-slate-800/60'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            Cast &amp; Character Profiles
            <span className="px-1.5 py-0.2 text-[10px] font-extrabold bg-spine-900 text-spine-accent rounded-full border border-spine-accent/40">
              {characters.length}
            </span>
          </button>

          <button
            onClick={() => setStudioSubTab('dop')}
            className={`px-4 py-1.5 text-xs font-bold rounded-md flex items-center gap-2 transition ${
              studioSubTab === 'dop'
                ? 'bg-spine-accent text-white shadow-md shadow-purple-600/20'
                : 'text-gray-300 hover:text-gray-100 hover:bg-slate-800/60'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            DoP Optics &amp; Master Styles
          </button>
        </div>

        {/* Character Consistency Indicator */}
        <div className="flex items-center gap-2 px-3 py-1 bg-spine-900/40 border border-spine-accent/30 rounded-md">
          <ShieldCheck className="w-3.5 h-3.5 text-spine-success" />
          <span className="text-[11px] font-semibold text-spine-accent">
            Character Visual Consistency: <strong className="text-spine-success font-bold">{characters.length} Profiles Active</strong>
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
                  <Users className="w-4 h-4 text-spine-accent" />
                  Detected Cast ({characters.length})
                </h3>
                <p className="text-[11px] text-gray-300">Click a character to polish physical look, wardrobe, and facial traits.</p>
              </div>
            </div>

            <div className="space-y-2.5">
              {characters.map(char => (
                <div
                  key={char.id}
                  onClick={() => setSelectedCharId(char.id)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer flex items-start gap-3.5 ${
                    selectedCharacter?.id === char.id
                      ? 'bg-spine-900/60 border-spine-accent shadow-lg shadow-purple-500/10'
                      : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-spine-800 flex items-center justify-center font-black text-sm text-white shrink-0 shadow-md">
                    {char.name.charAt(0)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-black text-white tracking-wider">{char.name}</h4>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-800 text-spine-accent rounded border border-spine-accent/20">
                        {char.dialogue_count} cues
                      </span>
                    </div>
                    <p className="text-[11px] font-medium text-gray-200 truncate mt-0.5">{char.role}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {char.personality_traits.slice(0, 3).map((t, idx) => (
                        <span key={idx} className="px-1.5 py-0.5 text-[9px] bg-slate-800/80 text-gray-200 rounded border border-slate-700">
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
              <CharacterProfileCard
                selectedCharacter={selectedCharacter}
                characters={characters}
                setCharacters={setCharacters}
                savingCharId={savingCharId}
                charSaveSuccess={charSaveSuccess}
                charSaveError={charSaveError}
                handleUpdateCharacter={handleUpdateCharacter}
                generatingPortraitMap={generatingPortraitMap}
                handleGenerateCharacterPortrait={handleGenerateCharacterPortrait}
                setEnlargedImage={setEnlargedImage}
                setSelectedCharId={setSelectedCharId}
                scriptId={scriptId ?? undefined}
                onGoToScene={(sceneNumber: string) => {
                  const idx = parsedScenes.findIndex(
                    sc => String(sc.scene_number) === String(sceneNumber),
                  );
                  if (idx >= 0) setSelectedSceneIndex(idx);
                }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-300">
                <Users className="w-12 h-12 text-slate-600 mb-3" />
                <p className="text-sm font-semibold">No characters selected</p>
                <p className="text-xs text-gray-400">Upload a script or choose a demo to detect and profile characters.</p>
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
                <p className="text-[11px] text-gray-300">{parsedScenes.length} Scenes Extracted</p>
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
                        ? 'bg-spine-900/50 border-spine-accent text-white shadow-lg shadow-purple-500/10'
                        : 'bg-slate-900/40 border-slate-800 text-gray-200 hover:border-slate-700 hover:bg-slate-900/80'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[10px] font-bold px-1.5 py-0.5 bg-spine-accent/20 text-spine-accent rounded font-mono">
                          SCENE {sc.scene_number}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {hasShots && (
                            <span className="text-[9px] font-extrabold px-1.5 py-0.2 bg-spine-success/20 text-spine-success border border-spine-success/30 rounded font-mono">
                              {sceneShots.length} Setups
                            </span>
                          )}
                          <span className="text-[10px] font-semibold text-gray-300">{sc.time_of_day}</span>
                        </div>
                      </div>
                      <h4 className="text-xs font-bold truncate text-slate-100">{sc.heading}</h4>
                      <p className="text-[11px] text-gray-300 line-clamp-2 mt-1 leading-relaxed">
                        {sc.action_blocks?.[0] || 'No action description'}
                      </p>
                        {sc.characters && sc.characters.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {sc.characters.map((cName, cIdx) => (
                              <button key={cIdx} onClick={(e) => { e.stopPropagation(); setPopupCharacter(characters.find(c => c.name === cName) || null); }} className="px-1.5 py-0.2 text-[9px] font-semibold bg-slate-800 text-spine-accent rounded border border-spine-accent/20 hover:bg-slate-700 transition cursor-pointer">
                                {cName}
                              </button>
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
                          ? 'bg-spine-900/70 hover:bg-spine-900/90 text-spine-accent border border-spine-accent/40'
                          : 'bg-gradient-to-r bg-spine-800 via-indigo-600 to-pink-600 hover:bg-spine-800 hover:to-pink-500 text-white shadow-lg shadow-purple-600/20'
                      }`}
                      title={`Run 3-Camera breakdown for Scene ${sc.scene_number}`}
                    >
                      {isBreakingDownThisScene ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 animate-spin text-spine-accent" />
                          Breaking Down Scene {sc.scene_number}...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5 text-spine-warning" />
                          {hasShots ? `⚡ Re-Run AI-Cam Breakdown` : `⚡ Run AI-Cam Breakdown`}
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
                <p className="text-[11px] text-gray-300">
                  {currentShots.length > 0
                    ? `${currentShots.length} ${currentShots.length === 1 ? 'setup' : 'setups'}`
                    : 'No breakdown yet'}
                </p>
              </div>
              {/* The breakdown is a proposal. A DoP who wants a setup the model
                  did not think of should not have to re-run the scene and lose
                  every camera and frame with it. */}
              {currentScene && (
                <button
                  onClick={() => handleAddShotToScene(currentScene)}
                  title="Add a setup to this scene by hand"
                  className="px-2 py-1 text-[10px] font-bold text-spine-accent hover:text-white bg-spine-900/40 hover:bg-spine-900/60 border border-spine-accent/30 rounded-lg flex items-center gap-1 transition shrink-0"
                >
                  <Plus className="w-3 h-3" />
                  Add Setup
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {currentShots.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-6 text-gray-300 space-y-3">
                  <Camera className="w-10 h-10 text-slate-600" />
                  <div>
                    <p className="text-xs font-bold text-gray-100">No Shot Setups Generated Yet</p>
                    <p className="text-[11px] text-gray-400 mt-1 max-w-xs">
                      Click <strong className="text-spine-accent">"⚡ Run AI-Cam Breakdown"</strong> on any scene card on the left to generate synchronized camera angles.
                    </p>
                  </div>
                  {currentScene && (
                    <button
                      onClick={() => handleBreakdownScene(currentScene, selectedSceneIndex)}
                      disabled={breakingDownSceneMap[currentScene.scene_number]}
                      className="px-4 py-2 text-xs font-bold bg-gradient-to-r bg-spine-800 to-pink-600 hover:bg-spine-800 hover:to-pink-500 text-white rounded-lg shadow-lg shadow-purple-600/30 transition flex items-center gap-1.5"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-spine-warning" />
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
                        ? 'bg-spine-900/40 border-spine-accent shadow-md'
                        : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <span className="text-xs font-black text-white min-w-0 truncate">{shot.shot_name}</span>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[10px] font-bold px-1.5 py-0.5 bg-slate-800 text-gray-200 rounded border border-slate-700">
                          {shot.shot_size} • {shot.camera_angle}
                        </span>
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            setSelectedShotId(shot.id);
                            setEditingShotId(editingShotId === shot.id ? null : shot.id);
                          }}
                          title="Edit this setup"
                          className="p-0.5 text-gray-500 hover:text-white transition"
                        >
                          <Pencil className="w-2.5 h-2.5" />
                        </button>
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            handleRemoveShotFromScene(shot);
                          }}
                          title="Remove this setup"
                          className="p-0.5 text-gray-500 hover:text-rose-400 transition"
                        >
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    </div>

                    {editingShotId === shot.id ? (
                      <div className="space-y-1.5 pb-1" onClick={e => e.stopPropagation()}>
                        <input
                          value={shot.shot_name}
                          onChange={e => handleUpdateShotProperty(shot, { shot_name: e.target.value })}
                          placeholder="Setup name"
                          className="w-full bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-[11px] text-white"
                        />
                        <div className="grid grid-cols-3 gap-1">
                          <select
                            value={shot.shot_size}
                            onChange={e => handleUpdateShotProperty(shot, { shot_size: e.target.value })}
                            title="Shot size"
                            className="bg-slate-950 border border-slate-700 rounded px-1 py-1 text-[10px] text-gray-200"
                          >
                            {SHOT_SIZES.map(v => <option key={v} value={v}>{v}</option>)}
                          </select>
                          <select
                            value={shot.camera_angle}
                            onChange={e => handleUpdateShotProperty(shot, { camera_angle: e.target.value })}
                            title="Camera angle"
                            className="bg-slate-950 border border-slate-700 rounded px-1 py-1 text-[10px] text-gray-200"
                          >
                            {CAMERA_ANGLES.map(v => <option key={v} value={v}>{v.replace(/_/g, ' ')}</option>)}
                          </select>
                          <select
                            value={shot.camera_movement}
                            onChange={e => handleUpdateShotProperty(shot, { camera_movement: e.target.value })}
                            title="Camera movement"
                            className="bg-slate-950 border border-slate-700 rounded px-1 py-1 text-[10px] text-gray-200"
                          >
                            {CAMERA_MOVEMENTS.map(v => <option key={v} value={v}>{v.replace(/_/g, ' ')}</option>)}
                          </select>
                        </div>
                        <textarea
                          value={shot.subject_description}
                          onChange={e => handleUpdateShotProperty(shot, { subject_description: e.target.value })}
                          rows={2}
                          placeholder="What the camera is on"
                          className="w-full bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-[10px] text-gray-200"
                        />
                        <input
                          value={shot.dramatic_beat}
                          onChange={e => handleUpdateShotProperty(shot, { dramatic_beat: e.target.value })}
                          placeholder="Dramatic beat"
                          className="w-full bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-[10px] text-gray-200"
                        />
                        <button
                          onClick={() => setEditingShotId(null)}
                          className="text-[10px] text-spine-accent hover:text-white font-semibold"
                        >
                          Done
                        </button>
                      </div>
                    ) : (
                      <p className="text-[11px] text-gray-200 line-clamp-2">
                        {shot.subject_description || <span className="text-gray-500 italic">No description yet.</span>}
                      </p>
                    )}

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
                                  ? 'bg-spine-accent text-white shadow-sm'
                                  : 'bg-slate-800/80 text-gray-300 hover:text-gray-100'
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
                                className="ml-0.5 p-0.5 text-gray-600 hover:text-rose-400 transition"
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
                          className="px-1.5 py-1 text-[10px] font-bold text-spine-accent hover:text-white bg-spine-900/40 hover:bg-spine-900/60 border border-spine-accent/30 rounded flex items-center gap-0.5 transition"
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
                        className="px-2 py-1 text-[10px] font-bold text-spine-warning hover:text-white bg-spine-warning/10 hover:bg-spine-warning/20 border border-spine-warning/30 rounded flex items-center gap-1 transition shrink-0"
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
                            ? 'bg-spine-accent text-white shadow-md shadow-purple-600/30'
                            : 'bg-slate-900 border border-slate-800 text-gray-300 hover:text-gray-100'
                        }`}
                      >
                        <Camera className="w-3 h-3" />
                        Cam {cam.camera_letter} ({cam.focal_length}mm)
                      </button>
                    ))}

                    <button
                      onClick={() => handleAddCameraToShot(selectedShot)}
                      className="px-2.5 py-1 text-xs font-bold text-spine-accent hover:text-white bg-spine-900/60 hover:bg-spine-900 border border-spine-accent/40 rounded-lg flex items-center gap-1 transition"
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
                    <span className="px-2 py-0.5 text-xs font-black bg-spine-accent text-white rounded">
                      CAMERA {activeCamLetter}
                    </span>
                    <span className="text-xs font-bold text-white">{selectedCam.camera_role}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-spine-accent">
                      {selectedCam.focal_length}mm • {selectedCam.aperture} • {aspectRatio}
                    </span>
                    <button
                      onClick={() => {
                        setShowCamSettings(!showCamSettings);
                        if (!showCamSettings) setShowShotScript(false);
                      }}
                      className={`p-1.5 rounded-lg transition ${showCamSettings ? 'bg-spine-accent text-white shadow-md' : 'bg-slate-800 text-gray-300 hover:text-white'}`}
                      title="Camera DoP Overrides"
                    >
                      <Sliders className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        setShowShotScript(!showShotScript);
                        if (!showShotScript) setShowCamSettings(false);
                      }}
                      className={`p-1.5 rounded-lg transition ${showShotScript ? 'bg-spine-accent text-white shadow-md' : 'bg-slate-800 text-gray-300 hover:text-white'}`}
                      title="Shot Script & Scene Context"
                    >
                      <FileText className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Main Previz Frame Display */}
                <div
                  ref={previzFrameRef}
                  className="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950 shadow-2xl group"
                  style={{ aspectRatio: `${selectedCamGeometry.aspect}` }}
                >
                  {selectedCam.image_url ? (
                    <>
                      <img
                        src={selectedCam.image_url}
                        alt={selectedCam.prompt}
                        className="w-full h-full object-cover origin-center transition-transform duration-200"
                        style={{ transform: `scale(${selectedCamGeometry.appliedScale.toFixed(4)})` }}
                      />
                      {/* CSS Masked Blur DoF Simulator */}
                      <div
                        className="absolute inset-0 pointer-events-none transition-all duration-100 ease-out"
                        style={{
                          backdropFilter: `blur(${selectedCamBlurRadius}px)`,
                          WebkitBackdropFilter: `blur(${selectedCamBlurRadius}px)`,
                          maskImage: 'radial-gradient(circle at 50% 45%, transparent 25%, black 75%)',
                          WebkitMaskImage: 'radial-gradient(circle at 50% 45%, transparent 25%, black 75%)',
                        }}
                      />
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400 text-xs">
                      <Camera className="w-8 h-8 mb-2 text-slate-600" />
                      Rendering Previz Frame...
                    </div>
                  )}

                  {/* Overlay Badge */}
                  <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/70 backdrop-blur text-[10px] font-mono font-bold text-spine-accent rounded border border-spine-accent/30">
                    35mm Previz • {selectedShot.dop_spec?.dop_preset || selectedPreset}
                  </div>

                  {/* Character Lock Badge */}
                  <div className="absolute bottom-2 left-2 px-2 py-0.5 bg-black/80 backdrop-blur text-[10px] font-semibold text-spine-success rounded border border-spine-success/30 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-spine-success" />
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

                {showCamSettings && (
                  <div className="p-4 bg-slate-900/95 border border-spine-accent/50 rounded-xl shadow-lg shadow-purple-500/10 h-[500px] flex flex-col">
                    <div className="flex justify-between items-center mb-4">
                      <h4 className="text-sm font-bold text-white flex items-center gap-2">
                        <Sliders className="w-4 h-4 text-spine-accent" />
                        Camera {activeCamLetter} DoP Overrides
                      </h4>
                      <button onClick={() => setShowCamSettings(false)} className="text-gray-300 hover:text-white">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto pr-2">
                      <DopControls
                        settings={{
                          dopMode: selectedCam.dop_spec?.dopMode || dopMode,
                          aspectRatio: aspectRatio,
                          selectedPreset: selectedCam.dop_spec?.dop_preset || selectedPreset,
                          customFocalLength: selectedCam.focal_length,
                          customAperture: selectedCam.aperture,
                          focusDistanceM: selectedCam.dop_spec?.focusDistanceM || focusDistanceM,
                          customColorTemp: selectedCam.dop_spec?.color_temp_k || customColorTemp,
                          whiteBalanceK: selectedCam.dop_spec?.whiteBalanceK || whiteBalanceK,
                          customLightingRatio: selectedCam.dop_spec?.lighting_ratio || customLightingRatio,
                          customSensorFormat: selectedCam.dop_spec?.customSensorFormat || customSensorFormat,
                          customLutEmulation: selectedCam.dop_spec?.lut_emulation || customLutEmulation,
                          customMoodPrompt: selectedCam.dop_spec?.prompt_style_tag || customMoodPrompt,
                        }}
                        onChange={(updates) => handleCamDopChange(selectedShot, selectedCam.camera_letter, updates)}
                        presetsDict={presetsDict}
                        onSavePreset={handleSavePreset}
                        onDeletePreset={handleDeletePreset}
                        onResetPresets={handleResetPresets}
                        deletedPresetsCount={deletedPresets.length}
                        hideAspectRatio={true}
                      />
                    </div>
                  </div>
                )}

                {showShotScript && (() => {
                  const shotScene = parsedScenes.find(s => s.scene_number === selectedShot.scene_number);
                  if (!shotScene) return null;
                  const rawLines = (shotScene.raw_content || '').split('\n');
                  return (
                    <div className="p-5 bg-slate-900/95 border border-indigo-500/50 rounded-xl shadow-lg shadow-indigo-500/10 h-[500px] flex flex-col">
                      <div className="flex justify-between items-center mb-4 pb-3 border-b border-slate-800">
                        <div>
                          <h4 className="text-sm font-bold text-white flex items-center gap-2">
                            <FileText className="w-4 h-4 text-indigo-400" />
                            Script Context: Scene {selectedShot.scene_number} ({selectedShot.shot_name})
                          </h4>
                          <div className="flex flex-wrap gap-1 mt-2">
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mr-1">Cast in Shot:</span>
                            {selectedShot.characters && selectedShot.characters.length > 0 ? (
                              selectedShot.characters.map(c => (
                                <button key={c} onClick={() => setPopupCharacter(characters.find(char => char.name === c) || null)} className="px-1.5 py-0.5 text-[9px] font-bold bg-indigo-950/60 text-indigo-200 border border-indigo-500/30 rounded hover:bg-spine-900 transition cursor-pointer">
                                  {c}
                                </button>
                              ))
                            ) : (
                              <span className="text-[10px] text-gray-400 italic">None specified</span>
                            )}
                          </div>
                        </div>
                        <button onClick={() => setShowShotScript(false)} className="text-gray-300 hover:text-white self-start">
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="flex-1 overflow-y-auto pr-2 space-y-1.5 font-mono text-[11px] leading-relaxed custom-scrollbar">
                        <h4 className="text-xs font-black text-gray-100 mb-4">{shotScene.heading}</h4>
                        {(() => {
                          let insideCharBlock = false;
                          let currentSpeaker = "";
                          return rawLines.map((line, lIdx) => {
                            const trimmed = line.trim();
                            if (!trimmed) {
                              insideCharBlock = false;
                              currentSpeaker = "";
                              return <div key={lIdx} className="h-2" />;
                            }
                            
                            const isCharMatch = selectedShot.characters?.includes(trimmed);
                            if (isCharMatch) {
                              insideCharBlock = true;
                              currentSpeaker = trimmed;
                            }
                            
                            const isHighlighted = insideCharBlock && selectedShot.characters?.includes(currentSpeaker);
                            
                            return (
                              <div key={lIdx} className={`whitespace-pre-wrap ${isHighlighted ? 'bg-spine-900/50 text-indigo-100 border-l-[3px] border-indigo-500 pl-3 -ml-3 py-0.5 font-medium shadow-sm' : 'text-gray-300'}`}>
                                {line}
                              </div>
                            );
                          });
                        })()}
                      </div>
                    </div>
                  );
                })()}

                {/* Quick Optics Tuners (Focal Length, Aperture, Shot Size) */}
                <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-gray-200 flex items-center gap-1.5">
                      <Sliders className="w-3 h-3 text-spine-accent" />
                      Camera {activeCamLetter} Optics &amp; Framing:
                    </span>
                    <span className="text-[10px] font-mono text-gray-300">
                      {selectedCam.shot_size} • {selectedCam.focal_length}mm • {selectedCam.aperture}
                    </span>
                  </div>

                  {/* Focal Length Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-gray-300 mr-1">Lens:</span>
                    {[18, 24, 35, 50, 85, 135].map(fl => (
                      <button
                        key={fl}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { focal_length: fl })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.focal_length === fl
                            ? 'bg-spine-accent text-white'
                            : 'bg-slate-800 text-gray-300 hover:text-white'
                        }`}
                      >
                        {fl}mm
                      </button>
                    ))}
                  </div>

                  {/* Aperture Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-gray-300 mr-1">Iris:</span>
                    {['T1.4', 'T2.0', 'T2.8', 'T4.0', 'T5.6', 'T8.0'].map(ap => (
                      <button
                        key={ap}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { aperture: ap })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.aperture === ap
                            ? 'bg-spine-accent text-white'
                            : 'bg-slate-800 text-gray-300 hover:text-white'
                        }`}
                      >
                        {ap}
                      </button>
                    ))}
                  </div>

                  {/* Shot Size Pills */}
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] font-semibold text-gray-300 mr-1">Framing:</span>
                    {['EWS', 'WS', 'MS', 'MCU', 'CU', 'ECU', 'OTS', 'POV'].map(sz => (
                      <button
                        key={sz}
                        onClick={() => handleUpdateCameraProperty(selectedShot, activeCamLetter, { shot_size: sz })}
                        className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                          selectedCam.shot_size === sz
                            ? 'bg-spine-accent text-white'
                            : 'bg-slate-800 text-gray-300 hover:text-white'
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
                    <label className="text-[11px] font-bold text-gray-200 flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-spine-accent" />
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
                        className="px-2 py-1 text-[10px] font-semibold bg-slate-900 hover:bg-spine-900 text-gray-200 hover:text-spine-accent border border-slate-800 hover:border-spine-accent/40 rounded transition shadow-sm"
                      >
                        {mod}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Editable Generative Prompt Box */}
                <div>
                  <label className="block text-[11px] font-bold text-gray-200 mb-1">
                    Cinematography &amp; Character Prompt (Camera {activeCamLetter})
                  </label>
                  <textarea
                    rows={4}
                    value={selectedCam.prompt}
                    onChange={e => handleUpdateActivePrompt(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white font-mono focus:outline-none focus:border-spine-accent"
                  />
                </div>

                {/* Execute AI Render Button */}
                <button
                  onClick={() => handleRegenerateCameraFrame(selectedShot, selectedCam)}
                  disabled={generatingCamMap[`${selectedShot.id}_${selectedCam.camera_letter}`]}
                  className="w-full py-2.5 text-xs font-bold bg-gradient-to-r bg-spine-800 via-indigo-600 to-pink-600 hover:bg-spine-800 hover:to-pink-500 text-white rounded-lg shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
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
              <div className="flex flex-col items-center justify-center h-full text-gray-400 text-xs">
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
                    <Sliders className="w-4 h-4 text-spine-accent" />
                    Director of Photography (DoP) Studio
                  </h2>
                  <p className="text-xs text-gray-300 mt-0.5">
                    Define cinematography via Master Presets, Manual Optics Matrix, or Natural Language.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex-1 overflow-hidden flex flex-col">
                <DopControls
                  settings={globalDopSettings}
                  onChange={handleGlobalDopChange}
                  presetsDict={presetsDict}
                  onSavePreset={handleSavePreset}
                  onDeletePreset={handleDeletePreset}
                  onResetPresets={handleResetPresets}
                  deletedPresetsCount={deletedPresets.length}
                />
              </div>
            </div>
          </div>

          {/* Right Column: Real-Time Optical Viewfinder & HUD Preview Canvas */}
          <div className="col-span-6 bg-[#090D16] flex flex-col overflow-y-auto p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-spine-accent" />
                <h3 className="text-sm font-bold text-white">Real-Time Optical Viewfinder Simulation</h3>
              </div>
              <button
                onClick={() => setShowViewfinderGrid(!showViewfinderGrid)}
                className={`px-2.5 py-1 text-[11px] font-bold rounded border transition ${
                  showViewfinderGrid
                    ? 'bg-spine-accent text-white border-spine-accent'
                    : 'bg-slate-900 text-gray-300 border-slate-800'
                }`}
              >
                Grid &amp; Crosshairs: {showViewfinderGrid ? 'ON' : 'OFF'}
              </button>
            </div>

            {/* Optical Viewfinder Canvas — open gate with delivery extraction */}
            <div
              ref={viewfinderRef}
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
                  transform: `scale(${geometry.appliedScale.toFixed(4)})`,
                  filter: `contrast(${
                    customLightingRatio === '16:1' ? 145 : customLightingRatio === '8:1' ? 125 : customLightingRatio === '4:1' ? 110 : 100
                  }%) brightness(${
                    customLightingRatio === '16:1' ? 85 : customLightingRatio === '8:1' ? 92 : 100
                  }%)`
                }}
              />

              {/* CSS Masked Blur DoF Simulator */}
              <div
                className="absolute inset-0 pointer-events-none transition-all duration-100 ease-out"
                style={{
                  backdropFilter: `blur(${visualBlurRadius}px)`,
                  WebkitBackdropFilter: `blur(${visualBlurRadius}px)`,
                  maskImage: 'radial-gradient(circle at 50% 45%, transparent 25%, black 75%)',
                  WebkitMaskImage: 'radial-gradient(circle at 50% 45%, transparent 25%, black 75%)',
                }}
              />

              {/* Dynamic Kelvin Color Tint Layer */}
              <div
                className="absolute inset-0 pointer-events-none transition-colors duration-300"
                style={{
                  // Multiply by the source/white-balance ratio: matched values are
                  // neutral white and shift nothing.
                  backgroundColor: rgbToCss(wbTint),
                  mixBlendMode: 'multiply'
                }}
              />

              {/* Delivery Extraction Window.
                  When the surround is on, the container is the full open gate and this
                  box is the recorded frame: everything outside it is dimmed, the way a
                  director's viewfinder shows what is available outside the delivery ratio. */}
              <div
                className="absolute pointer-events-none"
                style={{
                  // With the surround off the container is already the delivery frame.
                  width: showSurround ? `${(geometry.frame.widthMm / geometry.sensor.widthMm) * 100}%` : '100%',
                  height: showSurround ? `${(geometry.frame.heightMm / geometry.sensor.heightMm) * 100}%` : '100%',
                  left: '50%',
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                  boxShadow: showSurround ? '0 0 0 9999px rgba(2, 6, 23, 0.74)' : 'none',
                  border: showSurround ? '1px solid rgba(168, 85, 247, 0.9)' : 'none',
                  transition: 'transform 200ms ease'
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
                    <span className="absolute top-0.5 left-1 text-[9px] font-mono font-bold text-spine-warning/90 drop-shadow">
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

              {/* Plate coverage warning — crop cannot synthesise a wider field of view */}
              {geometry.plateLimited && (
                <div className="absolute left-1/2 -translate-x-1/2 bottom-12 z-10 pointer-events-none">
                  <span className="block whitespace-nowrap px-2.5 py-1 rounded bg-spine-accent/90 text-white text-[9px] font-mono font-bold tracking-wide shadow-lg border border-spine-accent/40">
                    OPTICAL {customFocalLength}MM WIDE FOV ({geometry.hfovDeg.toFixed(1)}° HFOV) · TEST RENDER FOR 8K NATIVE COVERAGE
                  </span>
                </div>
              )}

              {/* On-Screen Display (OSD HUD) */}
              <div className="absolute inset-0 p-3 flex flex-col justify-between pointer-events-none font-mono text-[10px] text-spine-success select-none">
                <div className="flex items-center justify-between bg-black/50 backdrop-blur-sm px-2 py-1 rounded">
                  <div className="flex items-center gap-2">
                    {resolution ? (
                      <>
                        <span className="font-bold text-white">
                          {resolution.widthPx} × {resolution.heightPx}
                        </span>
                        <span
                          className={`px-1.5 py-px rounded text-[9px] font-bold ${
                            resolution.meetsHd
                              ? 'bg-spine-success/20 text-spine-success'
                              : 'bg-spine-critical/25 text-spine-critical'
                          }`}
                        >
                          {resolution.masteringTarget}
                        </span>
                        <span className="text-gray-300">
                          {resolution.pixelPitchUm.toFixed(2)}µm
                        </span>
                      </>
                    ) : (
                      <span className="text-gray-200">
                        PHOTOCHEMICAL · resolution set by scan
                      </span>
                    )}
                  </div>
                  <div className="text-spine-accent font-bold">
                    {aspectRatio} • {geometry.sensor.label}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-x-3 gap-y-1 flex-wrap bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded">
                  <div className="flex items-center gap-3 [&>span]:whitespace-nowrap">
                    <span>
                      LENS: <strong className="text-white">{customFocalLength}mm</strong>
                    </span>
                    <span>
                      IRIS: <strong className="text-white">{customAperture}</strong>
                    </span>
                    <span>
                      FOCUS: <strong className="text-white">{formatDistance(focusDistanceM)}</strong>
                    </span>
                    <span>
                      DOF:{' '}
                      <strong className="text-white">
                        {formatDistance(dof.nearM)}–{formatDistance(dof.farM)}
                      </strong>
                    </span>
                    <span>
                      WB: <strong className="text-spine-warning">{whiteBalanceK}K</strong>
                    </span>
                  </div>
                  <div className="flex items-center gap-3 [&>span]:whitespace-nowrap">
                    <span>
                      RATIO: <strong className="text-spine-accent">{customLightingRatio}</strong>
                    </span>
                    <span className="text-gray-200">
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
                  <span className="text-[11px] font-bold text-gray-200">Surround (open gate)</span>
                  <button
                    onClick={() => setShowSurround(!showSurround)}
                    className={`px-2.5 py-1 text-[11px] font-bold rounded border transition ${
                      showSurround
                        ? 'bg-spine-accent text-white border-spine-accent'
                        : 'bg-slate-900 text-gray-300 border-slate-800'
                    }`}
                  >
                    {showSurround ? 'ON' : 'OFF'}
                  </button>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] font-bold text-gray-400 uppercase">Protect:</span>
                  {PROTECT_RATIOS.map(pr => (
                    <button
                      key={pr}
                      onClick={() => setProtectRatio(pr)}
                      className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded transition ${
                        protectRatio === pr
                          ? 'bg-spine-warning/90 text-slate-950'
                          : 'text-gray-300 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      {pr}
                    </button>
                  ))}
                </div>
              </div>

              <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3 font-mono text-[10px] text-gray-200 space-y-1">
                <div className="flex justify-between">
                  <span className="text-gray-400">EXTRACTION</span>
                  <strong className="text-white">
                    {geometry.frame.widthMm.toFixed(2)} × {geometry.frame.heightMm.toFixed(2)} mm
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">GATE USED</span>
                  <strong className="text-white">
                    {(geometry.frame.sensorAreaUsed * 100).toFixed(1)}% ({geometry.frame.limitedBy}-limited)
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">ANGLE OF VIEW</span>
                  <strong className="text-white">
                    {geometry.hfovDeg.toFixed(1)}° H × {geometry.vfovDeg.toFixed(1)}° V
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">CROP FACTOR</span>
                  <strong className="text-white">{geometry.cropFactor.toFixed(2)}× vs FF</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">PLATE SCALE</span>
                  <strong className={geometry.plateLimited ? 'text-spine-warning' : 'text-white'}>
                    {geometry.framingScale.toFixed(2)}× vs {REFERENCE_FOCAL_MM}mm
                  </strong>
                </div>
                {geometry.plateLimited && (
                  <div className="text-[9px] text-spine-accent leading-snug pt-0.5 font-medium">
                    Wide-angle field of view ({geometry.framingScale.toFixed(2)}× optical scale). Run test render for full native {customFocalLength}mm sensor coverage.
                  </div>
                )}
              </div>
            </div>

            {/* Depth of Field — geometric, from CoC, f-number and focus distance */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Aperture className="w-3.5 h-3.5 text-spine-accent" />
                  <span className="text-[11px] font-bold text-gray-100">Depth of Field</span>
                </div>
                <span className="font-mono text-[9px] text-gray-400">
                  f/{dof.fNumber.toFixed(2)} from {customAperture} • CoC {dof.cocMm.toFixed(4)}mm
                </span>
              </div>

              {/* Focus scale — logarithmic, 0.3m to 100m */}
              <div className="pt-3 pb-1">
                <div className="relative h-1.5 bg-slate-800 rounded-full">
                  <div
                    className="absolute h-full bg-spine-success/70 rounded-full"
                    style={{
                      left: `${depthScalePos(dof.nearM)}%`,
                      width: `${Math.max(depthScalePos(dof.farM) - depthScalePos(dof.nearM), 0.8)}%`
                    }}
                  />
                  <div
                    className="absolute -top-1 w-0.5 h-3.5 bg-white rounded-full"
                    style={{ left: `${depthScalePos(focusDistanceM)}%` }}
                  />
                  {dof.hyperfocalM <= DEPTH_SCALE_MAX_M && (
                    <div
                      className="absolute -top-0.5 w-px h-2.5 bg-amber-400/80"
                      style={{ left: `${depthScalePos(dof.hyperfocalM)}%` }}
                      title="Hyperfocal"
                    />
                  )}
                </div>
                <div className="flex justify-between font-mono text-[8px] text-slate-600 pt-1">
                  <span>0.3m</span>
                  <span>1m</span>
                  <span>3m</span>
                  <span>10m</span>
                  <span>30m</span>
                  <span>∞</span>
                </div>
              </div>

              <div className="grid grid-cols-4 gap-2 font-mono text-[10px]">
                <div>
                  <div className="text-gray-400 text-[8px] uppercase tracking-wide">Near</div>
                  <strong className="text-spine-success">{formatDistance(dof.nearM)}</strong>
                </div>
                <div>
                  <div className="text-gray-400 text-[8px] uppercase tracking-wide">Far</div>
                  <strong className="text-spine-success">{formatDistance(dof.farM)}</strong>
                </div>
                <div>
                  <div className="text-gray-400 text-[8px] uppercase tracking-wide">Total</div>
                  <strong className="text-white">{formatDistance(dof.totalM)}</strong>
                </div>
                <div>
                  <div className="text-gray-400 text-[8px] uppercase tracking-wide">Hyperfocal</div>
                  <strong className="text-spine-warning">{formatDistance(dof.hyperfocalM)}</strong>
                </div>
              </div>

              <div className="font-mono text-[9px] text-gray-400">
                {formatDistance(dof.inFrontM)} in front • {formatDistance(dof.behindM)} behind
                {dof.atInfinity && ' — focused at or past hyperfocal, far limit is infinite'}
              </div>
            </div>

            <p className="text-[10px] text-gray-400 leading-relaxed">
              Framing is geometrically exact: angle of view and sensor extraction are computed from
              the selected format's open-gate dimensions. The plate is magnified to match the chosen
              focal length, but perspective compression cannot be recovered from a flat still — run a
              test render to see true optical character.
            </p>

            {/* Live Synthesized Generative Prompt */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-bold text-gray-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-spine-accent" />
                  Live Compiled AI Generative Prompt
                </label>
              </div>
              <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl text-xs font-mono text-spine-accent leading-relaxed max-h-28 overflow-y-auto">
                {compileDoPPromptPreview()}
              </div>
            </div>

            {/* Test Render Button */}
            <button
              onClick={handleExecuteDoPTestRender}
              disabled={isTestRenderingDoP}
              className="w-full py-3 text-xs font-bold bg-gradient-to-r bg-spine-800 via-indigo-600 to-pink-600 hover:bg-spine-800 hover:to-pink-500 text-white rounded-xl shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
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
                className="text-gray-300 hover:text-white text-sm font-bold"
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
            <div className="p-4 bg-slate-900/90 text-xs font-mono text-gray-200">
              {enlargedImage.prompt}
            </div>
          </div>
        </div>
      )}
    
      {popupCharacter && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setPopupCharacter(null)}>
          <div className="relative w-full max-w-4xl max-h-[90vh] bg-[#090D16] border border-slate-700 rounded-2xl shadow-2xl overflow-y-auto custom-scrollbar flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 right-0 p-4 flex justify-end z-10 bg-gradient-to-b from-[#090D16] to-transparent">
              <button onClick={() => setPopupCharacter(null)} className="p-2 bg-slate-800/80 hover:bg-slate-700 text-gray-200 hover:text-white rounded-full backdrop-blur transition shadow-lg">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="px-8 pb-8 -mt-6">
              <CharacterProfileCard
                selectedCharacter={popupCharacter}
                characters={characters}
                setCharacters={setCharacters}
                savingCharId={savingCharId}
                charSaveSuccess={charSaveSuccess}
                charSaveError={charSaveError}
                handleUpdateCharacter={handleUpdateCharacter}
                generatingPortraitMap={generatingPortraitMap}
                handleGenerateCharacterPortrait={handleGenerateCharacterPortrait}
                setEnlargedImage={setEnlargedImage}
                scriptId={scriptId ?? undefined}
                setSelectedCharId={(id: string) => {
                  setSelectedCharId(id);
                  setPopupCharacter(characters.find(c => c.id === id) || null);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Screenplay Ingestion & AI Parsing HUD Modal */}
      {isUploading && (
        <div className="fixed inset-0 z-[120] bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className="max-w-md w-full bg-[#0F172A] border border-spine-accent/50 rounded-2xl p-6 shadow-2xl shadow-purple-500/20 text-center flex flex-col items-center relative overflow-hidden">
            {/* Top Glowing Gradient Bar */}
            <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r bg-spine-800 via-pink-500 to-cyan-400 animate-pulse"></div>

            {/* Pulsing Film Clapper & Orbit Glow */}
            <div className="relative my-3">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr bg-spine-800 to-pink-600 flex items-center justify-center shadow-xl shadow-purple-600/40 animate-pulse">
                <Film className="w-8 h-8 text-white" />
              </div>
              <div className="absolute -inset-2 rounded-2xl border-2 border-spine-accent/30 animate-ping opacity-25 pointer-events-none"></div>
            </div>

            <h3 className="text-base font-bold text-white mb-1">
              Ingesting &amp; Parsing Screenplay
            </h3>
            <p className="text-xs font-mono font-semibold text-spine-accent mb-4 truncate max-w-full px-2">
              {uploadedFileName || 'Processing document...'}
            </p>

            {/* Smooth Dynamic Progress Bar */}
            <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800 mb-3 shadow-inner">
              <div
                className="h-full bg-gradient-to-r bg-spine-800 via-pink-500 to-cyan-400 rounded-full transition-all duration-700 ease-out shadow-sm"
                style={{ width: `${Math.max(10, uploadProgress)}%` }}
              ></div>
            </div>

            {/* Live Pipeline Action Indicator */}
            <div className="w-full flex items-center justify-center gap-2 text-xs font-bold text-gray-100 mb-4 bg-slate-950/80 py-2 px-3 rounded-xl border border-spine-accent/30 shadow-inner">
              <Loader2 className="w-4 h-4 text-spine-accent animate-spin shrink-0" />
              <span className="truncate">{uploadStage}</span>
            </div>

            {/* Step-by-Step Architecture Pipeline */}
            <div className="w-full space-y-2 text-left text-[11px] font-mono text-gray-300 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
              <div className={`flex items-center gap-2.5 transition-colors ${uploadProgress >= 20 ? 'text-spine-success font-bold' : 'text-gray-400'}`}>
                {uploadProgress >= 20 ? (
                  <CheckCircle2 className="w-4 h-4 text-spine-success shrink-0" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[9px] text-slate-600">1</div>
                )}
                <span>Multi-Format File Ingest &amp; Normalization</span>
              </div>

              <div className={`flex items-center gap-2.5 transition-colors ${uploadProgress >= 50 ? 'text-spine-success font-bold' : uploadProgress >= 20 ? 'text-spine-accent font-bold' : 'text-gray-400'}`}>
                {uploadProgress >= 50 ? (
                  <CheckCircle2 className="w-4 h-4 text-spine-success shrink-0" />
                ) : uploadProgress >= 20 ? (
                  <Loader2 className="w-4 h-4 text-spine-accent animate-spin shrink-0" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[9px] text-slate-600">2</div>
                )}
                <span>Scene Sluglines, Actions &amp; Dialogue Blocks</span>
              </div>

              <div className={`flex items-center gap-2.5 transition-colors ${uploadProgress >= 80 ? 'text-spine-success font-bold' : uploadProgress >= 50 ? 'text-spine-accent font-bold' : 'text-gray-400'}`}>
                {uploadProgress >= 80 ? (
                  <CheckCircle2 className="w-4 h-4 text-spine-success shrink-0" />
                ) : uploadProgress >= 50 ? (
                  <Loader2 className="w-4 h-4 text-spine-accent animate-spin shrink-0" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[9px] text-slate-600">3</div>
                )}
                <span>Gemini AI Cast Profiler &amp; Visual Traits</span>
              </div>

              <div className={`flex items-center gap-2.5 transition-colors ${uploadProgress >= 95 ? 'text-spine-success font-bold' : uploadProgress >= 80 ? 'text-spine-accent font-bold' : 'text-gray-400'}`}>
                {uploadProgress >= 95 ? (
                  <CheckCircle2 className="w-4 h-4 text-spine-success shrink-0" />
                ) : uploadProgress >= 80 ? (
                  <Loader2 className="w-4 h-4 text-spine-accent animate-spin shrink-0" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[9px] text-slate-600">4</div>
                )}
                <span>Multi-Camera (A, B, C) Previz Initialization</span>
              </div>
            </div>

            <p className="text-[10px] text-gray-400 mt-3 italic">
              AI evaluates character action and dialogue to ensure visual consistency across all camera angles.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
