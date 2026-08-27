import { describe, it, expect, beforeEach } from 'vitest';
import {
  DEFAULT_DOP_PRESETS,
  loadDeletedPresets,
  saveDeletedPresets,
  loadCustomPresets,
  saveCustomPresets,
  mergeActivePresets,
  DopMasterPreset
} from './presets';

describe('DoP Presets Deletion and Persistence', () => {
  let store: Record<string, string> = {};

  beforeEach(() => {
    store = {};
    const mockStorage = {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = String(value);
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      clear: () => {
        store = {};
      },
      key: (index: number) => Object.keys(store)[index] || null,
      get length() {
        return Object.keys(store).length;
      }
    };
    (globalThis as any).localStorage = mockStorage;
  });

  it('merges default presets when no custom or deleted presets exist', () => {
    const active = mergeActivePresets({}, {}, []);
    expect(Object.keys(active).length).toBe(Object.keys(DEFAULT_DOP_PRESETS).length);
    expect(active['Roger Deakins']).toBeDefined();
  });

  it('filters out deleted presets from the active preset dictionary', () => {
    const active = mergeActivePresets({}, {}, ['Roger Deakins', 'Gordon Willis']);
    expect(active['Roger Deakins']).toBeUndefined();
    expect(active['Gordon Willis']).toBeUndefined();
    expect(active['David Fincher']).toBeDefined();
  });

  it('includes custom presets and distinguishes them', () => {
    const custom: Record<string, DopMasterPreset> = {
      'My Custom Look': {
        name: 'My Custom Look',
        tagline: 'Deep Shadows and Contrast',
        description: 'Test description',
        focal_length: 50,
        lens_type: 'Spherical Prime',
        aperture: 'T2.0',
        sensor_format: 'Large Format 35mm (ARRI ALEXA Mini LF)',
        camera_body: 'ARRI ALEXA Mini LF',
        lighting_style: 'Low-Key',
        lighting_ratio: '8:1',
        color_temperature_k: 4500,
        color_palette: 'Teal & Orange',
        lut_emulation: 'Kodak 5219 Vision3',
        prompt_style_tag: 'cinematic style',
        is_custom: true
      }
    };

    const active = mergeActivePresets({}, custom, []);
    expect(active['My Custom Look']).toBeDefined();
    expect(active['My Custom Look'].is_custom).toBe(true);

    const afterDelete = mergeActivePresets({}, custom, ['My Custom Look']);
    expect(afterDelete['My Custom Look']).toBeUndefined();
  });

  it('persists and retrieves deleted presets to and from localStorage', () => {
    expect(loadDeletedPresets()).toEqual([]);

    saveDeletedPresets(['Wes Anderson', 'Stanley Kubrick']);
    expect(loadDeletedPresets()).toEqual(['Wes Anderson', 'Stanley Kubrick']);

    saveDeletedPresets([]);
    expect(loadDeletedPresets()).toEqual([]);
  });

  it('persists and retrieves custom presets to and from localStorage', () => {
    expect(loadCustomPresets()).toEqual({});

    const custom: Record<string, DopMasterPreset> = {
      'Indie Preset': {
        name: 'Indie Preset',
        tagline: 'Handheld gritty style',
        description: 'Raw indie aesthetics',
        focal_length: 28,
        lens_type: 'Vintage Glass',
        aperture: 'T1.8',
        sensor_format: 'Super 35',
        camera_body: 'Arriflex 416',
        lighting_style: 'Available light',
        lighting_ratio: '3:1',
        color_temperature_k: 5600,
        color_palette: 'Muted natural tones',
        lut_emulation: 'Kodak 5219',
        prompt_style_tag: 'indie style',
        is_custom: true
      }
    };

    saveCustomPresets(custom);
    const loaded = loadCustomPresets();
    expect(loaded['Indie Preset']).toBeDefined();
    expect(loaded['Indie Preset'].name).toBe('Indie Preset');
  });
});
