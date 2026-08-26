import React, { useMemo, useState } from 'react';
import { Camera, Aperture, Crosshair, Sun, Palette, Terminal, Save } from 'lucide-react';
import { parseStop, SENSOR_FORMATS, formatDistance, depthOfField, computeViewfinderGeometry } from '../optics';

export interface DopSettings {
  dopMode: 'preset' | 'matrix' | 'prompt';
  aspectRatio: string;
  selectedPreset: string;
  customFocalLength: number;
  customAperture: string;
  focusDistanceM: number;
  customColorTemp: number;
  whiteBalanceK: number;
  customLightingRatio: string;
  customSensorFormat: string;
  customLutEmulation: string;
  customMoodPrompt: string;
}

export interface DopControlsProps {
  settings: DopSettings;
  onChange: (updates: Partial<DopSettings>) => void;
  presetsDict: Record<string, any>;
  onSavePreset: (presetName: string, tagline: string, description: string, basePresetOverrides?: Partial<DopSettings>) => void;
  hideAspectRatio?: boolean;
}

export const DopControls: React.FC<DopControlsProps> = ({ settings, onChange, presetsDict, onSavePreset, hideAspectRatio = false }) => {
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const [newPresetName, setNewPresetName] = useState('');
  const [newPresetTagline, setNewPresetTagline] = useState('');
  const [newPresetDesc, setNewPresetDesc] = useState('');

  const handleSaveClick = () => {
    if (!newPresetName) return;
    onSavePreset(newPresetName, newPresetTagline, newPresetDesc, settings);
    setIsSavingPreset(false);
    setNewPresetName('');
    setNewPresetTagline('');
    setNewPresetDesc('');
  };

  // Compute DoF for UI feedback
  const dof = useMemo(() => {
    const geometry = computeViewfinderGeometry(settings.customSensorFormat, settings.aspectRatio, settings.customFocalLength);
    return depthOfField(geometry.frame, settings.customFocalLength, settings.customAperture, settings.focusDistanceM);
  }, [settings.customSensorFormat, settings.aspectRatio, settings.customFocalLength, settings.customAperture, settings.focusDistanceM]);

  // Compute White Balance offset
  const wbMired = (1000000 / settings.whiteBalanceK) - (1000000 / settings.customColorTemp);

  return (
    <div className="flex flex-col h-full">
      {/* Header and Aspect Ratio */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-xl border border-slate-800 flex-1 mr-2">
          <button
            onClick={() => onChange({ dopMode: 'preset' })}
            className={`py-1.5 px-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 flex-1 ${
              settings.dopMode === 'preset' ? 'bg-purple-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Palette className="w-3 h-3" />
            Presets
          </button>
          <button
            onClick={() => onChange({ dopMode: 'matrix' })}
            className={`py-1.5 px-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 flex-1 ${
              settings.dopMode === 'matrix' ? 'bg-purple-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Aperture className="w-3 h-3" />
            Matrix
          </button>
          <button
            onClick={() => onChange({ dopMode: 'prompt' })}
            className={`py-1.5 px-2 text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 flex-1 ${
              settings.dopMode === 'prompt' ? 'bg-purple-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Terminal className="w-3 h-3" />
            Prompt
          </button>
        </div>

        {!hideAspectRatio && (
          <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
            <span className="text-[9px] font-extrabold text-slate-400 uppercase tracking-wider px-1">Ratio:</span>
            {['2.39:1', '1.85:1', '16:9', '4:3'].map(ar => (
              <button
                key={ar}
                onClick={() => onChange({ aspectRatio: ar })}
                className={`px-1.5 py-0.5 text-[10px] font-mono font-bold rounded-lg transition ${
                  settings.aspectRatio === ar ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30' : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {ar}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="overflow-y-auto pr-1 pb-4 flex-1 space-y-4 custom-scrollbar">
        {/* MODE 1: PRESETS */}
        {settings.dopMode === 'preset' && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(presetsDict).map(([presetName, presetData]: [string, any]) => (
                <div
                  key={presetName}
                  onClick={() => {
                    onChange({
                      selectedPreset: presetName,
                      customFocalLength: presetData.focal_length || settings.customFocalLength,
                      customAperture: presetData.aperture || settings.customAperture,
                      customColorTemp: presetData.color_temperature_k || settings.customColorTemp,
                      customLightingRatio: presetData.lighting_ratio || settings.customLightingRatio,
                      customLutEmulation: presetData.lut_emulation || settings.customLutEmulation,
                      customMoodPrompt: presetData.prompt_style_tag || settings.customMoodPrompt
                    });
                  }}
                  className={`p-2 rounded-xl border transition cursor-pointer ${
                    settings.selectedPreset === presetName
                      ? 'bg-purple-950/60 border-purple-500 shadow-lg shadow-purple-500/20'
                      : 'bg-slate-900/50 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <h4 className="text-xs font-bold text-white leading-tight">{presetData.name || presetName}</h4>
                  <p className="text-[9px] text-purple-300 mt-0.5 line-clamp-1">{presetData.tagline}</p>
                  <p className="text-[10px] text-slate-400 line-clamp-2 mt-1 leading-relaxed">{presetData.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* MODE 2: MATRIX */}
        {settings.dopMode === 'matrix' && (
          <div className="space-y-4">
            {/* Focal Length */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                  <Camera className="w-3 h-3 text-purple-400" />
                  Lens Focal Length
                </label>
                <span className="text-[11px] font-mono font-bold text-purple-300">{settings.customFocalLength}mm</span>
              </div>
              <input
                type="range"
                min={Math.log(12)}
                max={Math.log(250)}
                step="0.01"
                value={Math.log(settings.customFocalLength)}
                onChange={e => onChange({ customFocalLength: Math.round(Math.exp(Number(e.target.value))) })}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <div className="flex items-center gap-0.5 mt-1 flex-wrap">
                {[12, 18, 24, 35, 50, 85, 135].map(fl => (
                  <button
                    key={fl}
                    onClick={() => onChange({ customFocalLength: fl })}
                    className={`px-1 py-0.5 text-[9px] font-mono font-bold rounded transition ${
                      settings.customFocalLength === fl ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'
                    }`}
                  >
                    {fl}
                  </button>
                ))}
              </div>
            </div>

            {/* Aperture */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                  <Aperture className="w-3 h-3 text-blue-400" />
                  Aperture (Iris)
                </label>
                <span className="text-[11px] font-mono font-bold text-blue-300">
                  T{parseStop(settings.customAperture).toFixed(1).replace(/\.0$/, '')}
                </span>
              </div>
              <input
                type="range"
                min={Math.log2(1.0)}
                max={Math.log2(22.0)}
                step="0.01"
                value={Math.log2(parseStop(settings.customAperture))}
                onChange={e => {
                  const val = Math.pow(2, Number(e.target.value));
                  const valStr = val >= 10 ? Math.round(val).toString() : val.toFixed(1);
                  onChange({ customAperture: 'T' + valStr });
                }}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
            </div>

            {/* Focus Distance */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                  <Crosshair className="w-3 h-3 text-emerald-400" />
                  Focus Distance
                </label>
                <span className="text-[11px] font-mono font-bold text-emerald-300">{formatDistance(settings.focusDistanceM)}</span>
              </div>
              <input
                type="range"
                min={Math.log(0.3)}
                max={Math.log(100)}
                step="0.01"
                value={Math.log(settings.focusDistanceM)}
                onChange={e => onChange({ focusDistanceM: +Math.exp(Number(e.target.value)).toFixed(2) })}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex items-center gap-1 mt-1 flex-wrap">
                {[0.5, 1, 2, 3, 5, 10, 25].map(d => (
                  <button
                    key={d}
                    onClick={() => onChange({ focusDistanceM: d })}
                    className={`px-1 py-0.5 text-[9px] font-mono font-bold rounded transition ${
                      Math.abs(settings.focusDistanceM - d) < 0.01
                        ? 'bg-emerald-600 text-white'
                        : 'text-slate-400 hover:text-white hover:bg-slate-800'
                    }`}
                  >
                    {d < 1 ? `${d * 100}cm` : `${d}m`}
                  </button>
                ))}
                <button
                  onClick={() => onChange({ focusDistanceM: +dof.hyperfocalM.toFixed(2) })}
                  className="px-1 py-0.5 text-[9px] font-mono font-bold rounded text-amber-300 hover:bg-slate-800 transition"
                  title={`Hyperfocal: ${formatDistance(dof.hyperfocalM)}`}
                >
                  HYP
                </button>
              </div>
            </div>

            {/* Key Light */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                  <Sun className="w-3 h-3 text-amber-400" />
                  Key Light (Kelvin)
                </label>
                <span className="text-[11px] font-mono font-bold text-amber-300">{settings.customColorTemp}K</span>
              </div>
              <input
                type="range"
                min="2800" max="7500" step="100"
                value={settings.customColorTemp}
                onChange={e => onChange({ customColorTemp: Number(e.target.value) })}
                className="w-full h-1.5 bg-gradient-to-r from-amber-500 via-slate-200 to-cyan-500 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* White Balance */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                  <Palette className="w-3 h-3 text-cyan-400" />
                  Camera WB
                </label>
                <span className="text-[11px] font-mono font-bold text-cyan-300">{settings.whiteBalanceK}K</span>
              </div>
              <input
                type="range"
                min="2800" max="7500" step="100"
                value={settings.whiteBalanceK}
                onChange={e => onChange({ whiteBalanceK: Number(e.target.value) })}
                className="w-full h-1.5 bg-gradient-to-r from-cyan-500 via-slate-200 to-amber-500 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex items-center justify-between text-[9px] font-mono mt-1">
                <button
                  onClick={() => onChange({ whiteBalanceK: settings.customColorTemp })}
                  className="text-slate-400 hover:text-white underline decoration-dotted"
                >
                  Match to key ({settings.customColorTemp}K)
                </button>
                <span className={Math.abs(wbMired) < 1 ? 'text-slate-500' : 'text-amber-300'}>
                  {Math.abs(wbMired) < 1
                    ? 'Neutral'
                    : `${wbMired > 0 ? '+' : ''}${wbMired.toFixed(0)} mired ${wbMired > 0 ? '(cool)' : '(warm)'}`}
                </span>
              </div>
            </div>

            {/* Lighting Ratio & LUT */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-300 mb-1">Contrast Ratio</label>
                <select
                  value={settings.customLightingRatio}
                  onChange={e => onChange({ customLightingRatio: e.target.value })}
                  className="w-full px-2 py-1 bg-slate-900 border border-slate-700 rounded text-[10px] text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="1:1">1:1 (Flat)</option>
                  <option value="2:1">2:1 (Soft)</option>
                  <option value="4:1">4:1 (Dramatic)</option>
                  <option value="8:1">8:1 (Noir)</option>
                  <option value="16:1">16:1 (Silhouette)</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-300 mb-1">LUT Emulation</label>
                <select
                  value={settings.customLutEmulation}
                  onChange={e => onChange({ customLutEmulation: e.target.value })}
                  className="w-full px-2 py-1 bg-slate-900 border border-slate-700 rounded text-[10px] text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="Kodak 5219 Vision3 500T">Kodak 5219</option>
                  <option value="Kodak 5207 Vision3 250D">Kodak 5207</option>
                  <option value="Bleach Bypass Custom LUT">Bleach Bypass</option>
                  <option value="Film Print Kodak 2383">Print 2383</option>
                </select>
              </div>
            </div>
            
            <div>
                <label className="block text-[10px] font-bold text-slate-300 mb-1">Camera Sensor Format</label>
                <select
                  value={settings.customSensorFormat}
                  onChange={e => onChange({ customSensorFormat: e.target.value })}
                  className="w-full px-2 py-1 bg-slate-900 border border-slate-700 rounded text-[10px] text-white focus:outline-none focus:border-purple-500"
                >
                    {SENSOR_FORMATS.map(sf => (
                        <option key={sf.id} value={sf.id}>
                            {sf.label}
                        </option>
                    ))}
                </select>
            </div>

          </div>
        )}

        {/* MODE 3: PROMPT */}
        {settings.dopMode === 'prompt' && (
          <div className="space-y-2">
            <label className="block text-xs font-bold text-slate-300">Natural Language Prompt</label>
            <textarea
              rows={5}
              value={settings.customMoodPrompt}
              onChange={e => onChange({ customMoodPrompt: e.target.value })}
              placeholder="e.g. Rain-slicked gothic great_hall square, pierced by harsh halogen searchlights..."
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-purple-500 leading-relaxed custom-scrollbar"
            />
          </div>
        )}

        {/* SAVE PRESET */}
        {settings.dopMode !== 'preset' && (
          <div className="mt-6 border-t border-slate-800 pt-4">
            {isSavingPreset ? (
              <div className="space-y-2 bg-slate-900/50 p-2.5 rounded-xl border border-purple-500/30">
                <input
                  type="text"
                  placeholder="Preset Name (e.g. Dark Neon Alley)"
                  value={newPresetName}
                  onChange={e => setNewPresetName(e.target.value)}
                  className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs text-white"
                />
                <input
                  type="text"
                  placeholder="Tagline (e.g. High contrast, gritty textures)"
                  value={newPresetTagline}
                  onChange={e => setNewPresetTagline(e.target.value)}
                  className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs text-white"
                />
                <textarea
                  rows={2}
                  placeholder="Full description..."
                  value={newPresetDesc}
                  onChange={e => setNewPresetDesc(e.target.value)}
                  className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs text-white custom-scrollbar"
                />
                <div className="flex items-center gap-2 pt-1">
                  <button
                    onClick={handleSaveClick}
                    disabled={!newPresetName}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-bold rounded"
                  >
                    Save Preset
                  </button>
                  <button
                    onClick={() => setIsSavingPreset(false)}
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setIsSavingPreset(true)}
                className="w-full py-2 bg-slate-800/80 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-slate-300 text-[11px] font-bold rounded-lg transition flex items-center justify-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                Save as Custom Preset
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
