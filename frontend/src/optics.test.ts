import { describe, it, expect } from 'vitest';
import {
  SENSOR_FORMATS,
  DEFAULT_SENSOR_ID,
  REFERENCE_FOCAL_MM,
  resolveSensor,
  parseAspectRatio,
  extractFrame,
  angleOfView,
  cropFactor,
  framingScale,
  computeViewfinderGeometry,
  parseStop,
  fNumberFromTStop,
  circleOfConfusion,
  depthOfField,
  backgroundBlurRadius,
  softLimitBlur,
  extractedResolution,
  formatDistance,
  colorTemperatureToRgb,
  whiteBalanceTint,
  miredShift,
  rgbToCss,
} from './optics';

const ALEXA_35 = 'Large Format 35mm (ARRI ALEXA 35)';
const MINI_LF = 'Large Format 35mm (ARRI ALEXA Mini LF)';

/* ------------------------------------------------------------------ *
 * Sensor resolution
 * ------------------------------------------------------------------ */

describe('resolveSensor', () => {
  it('returns the exact sensor for a known id', () => {
    expect(resolveSensor(MINI_LF).widthMm).toBeCloseTo(36.7, 2);
  });

  it('resolves a legacy short name to one specific sensor', () => {
    // Both ALEXA 35 and Mini LF ids begin "Large Format 35mm". A substring
    // match would resolve by array position; this must not.
    expect(resolveSensor('Large Format 35mm').id).toBe(ALEXA_35);
  });

  it('does not change answer when SENSOR_FORMATS is reordered', () => {
    const before = resolveSensor('Large Format 35mm').id;
    const reversed = [...SENSOR_FORMATS].reverse();
    // The alias table is keyed on id, not order, so the reversed copy still
    // contains exactly one sensor with that id.
    expect(reversed.filter(s => s.id === before)).toHaveLength(1);
    expect(resolveSensor('Large Format 35mm').id).toBe(before);
  });

  it('falls back to the default for an unknown id', () => {
    expect(resolveSensor('Nonexistent Camera 9000').id).toBe(DEFAULT_SENSOR_ID);
    expect(resolveSensor('').id).toBe(DEFAULT_SENSOR_ID);
  });

  it('every sensor id is unique', () => {
    const ids = SENSOR_FORMATS.map(s => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

/* ------------------------------------------------------------------ *
 * Frame extraction
 * ------------------------------------------------------------------ */

describe('extractFrame', () => {
  const sensor = resolveSensor(ALEXA_35);

  it('is width-limited on a wide delivery ratio', () => {
    const frame = extractFrame(sensor, 2.39);
    expect(frame.limitedBy).toBe('width');
    expect(frame.widthMm).toBeCloseTo(sensor.widthMm, 5);
    expect(frame.heightMm).toBeCloseTo(sensor.widthMm / 2.39, 5);
  });

  it('is height-limited on 4:3, so the frame is narrower than the gate', () => {
    const frame = extractFrame(sensor, 4 / 3);
    expect(frame.limitedBy).toBe('height');
    expect(frame.widthMm).toBeLessThan(sensor.widthMm);
    expect(frame.heightMm).toBeCloseTo(sensor.heightMm, 5);
  });

  it('never extracts outside the gate', () => {
    for (const s of SENSOR_FORMATS) {
      for (const ratio of [2.39, 1.85, 16 / 9, 4 / 3, 1]) {
        const frame = extractFrame(s, ratio);
        expect(frame.widthMm).toBeLessThanOrEqual(s.widthMm + 1e-9);
        expect(frame.heightMm).toBeLessThanOrEqual(s.heightMm + 1e-9);
        expect(frame.sensorAreaUsed).toBeGreaterThan(0);
        expect(frame.sensorAreaUsed).toBeLessThanOrEqual(1 + 1e-9);
      }
    }
  });
});

describe('parseAspectRatio', () => {
  it('parses the notations the UI offers', () => {
    expect(parseAspectRatio('2.39:1')).toBeCloseTo(2.39, 5);
    expect(parseAspectRatio('16:9')).toBeCloseTo(16 / 9, 5);
    expect(parseAspectRatio('4:3')).toBeCloseTo(4 / 3, 5);
  });

  it('returns a usable ratio for junk rather than NaN', () => {
    expect(parseAspectRatio('not a ratio')).toBeGreaterThan(0);
    expect(Number.isFinite(parseAspectRatio(''))).toBe(true);
  });
});

/* ------------------------------------------------------------------ *
 * Angle of view and framing
 * ------------------------------------------------------------------ */

describe('angleOfView', () => {
  it('matches the closed form 2·atan(w/2f)', () => {
    const expected = 2 * Math.atan(36 / (2 * 50)) * (180 / Math.PI);
    expect(angleOfView(36, 50)).toBeCloseTo(expected, 6);
  });

  it('a wider lens sees more', () => {
    expect(angleOfView(27.99, 18)).toBeGreaterThan(angleOfView(27.99, 35));
    expect(angleOfView(27.99, 35)).toBeGreaterThan(angleOfView(27.99, 135));
  });

  it('a larger frame sees more at the same focal length', () => {
    expect(angleOfView(54.12, 50)).toBeGreaterThan(angleOfView(24.89, 50));
  });
});

describe('cropFactor', () => {
  it('is 1.0 on a full-frame-sized extraction', () => {
    expect(cropFactor({ widthMm: 36, heightMm: 24, sensorAreaUsed: 1, limitedBy: 'width' }))
      .toBeCloseTo(1, 5);
  });

  it('is above 1 on Super 35', () => {
    expect(cropFactor(extractFrame(resolveSensor('Super 35mm (Panavision Panaflex Gold)'), 2.39)))
      .toBeGreaterThan(1);
  });
});

describe('framingScale', () => {
  it('is exactly 1 at the reference focal length', () => {
    expect(framingScale(27.99, REFERENCE_FOCAL_MM, REFERENCE_FOCAL_MM)).toBeCloseTo(1, 6);
  });

  it('is below 1 wider than reference and above 1 longer', () => {
    expect(framingScale(27.99, 18, REFERENCE_FOCAL_MM)).toBeLessThan(1);
    expect(framingScale(27.99, 85, REFERENCE_FOCAL_MM)).toBeGreaterThan(1);
  });
});

describe('computeViewfinderGeometry', () => {
  it('reports the surround as the gate-to-frame ratio', () => {
    const g = computeViewfinderGeometry(ALEXA_35, '4:3', 35);
    expect(g.surroundScaleX).toBeCloseTo(g.sensor.widthMm / g.frame.widthMm, 6);
    expect(g.surroundScaleX).toBeGreaterThan(1);
  });

  it('is stable across every sensor and ratio the UI exposes', () => {
    for (const s of SENSOR_FORMATS) {
      for (const ratio of ['2.39:1', '1.85:1', '16:9', '4:3']) {
        const g = computeViewfinderGeometry(s.id, ratio, 35);
        expect(Number.isFinite(g.hfovDeg)).toBe(true);
        expect(g.hfovDeg).toBeGreaterThan(0);
        expect(g.hfovDeg).toBeLessThan(180);
        expect(Number.isFinite(g.appliedScale)).toBe(true);
        expect(g.appliedScale).toBeGreaterThan(0);
      }
    }
  });
});

/* ------------------------------------------------------------------ *
 * Exposure and depth of field
 * ------------------------------------------------------------------ */

describe('parseStop / fNumberFromTStop', () => {
  it('reads the T-stop notation the UI uses', () => {
    expect(parseStop('T2.8')).toBeCloseTo(2.8, 5);
    expect(parseStop('T1.4')).toBeCloseTo(1.4, 5);
  });

  it('converts a T-stop to a smaller f-number, since glass loses light', () => {
    expect(fNumberFromTStop(2.8)).toBeLessThan(2.8);
    expect(fNumberFromTStop(2.8)).toBeCloseTo(2.8 * Math.sqrt(0.8), 5);
  });
});

describe('circleOfConfusion', () => {
  it('scales with frame diagonal', () => {
    const small = circleOfConfusion(extractFrame(resolveSensor('Super 35mm (Panavision Panaflex Gold)'), 2.39));
    const large = circleOfConfusion(extractFrame(resolveSensor('Full Frame 65mm (ARRI ALEXA 65)'), 2.39));
    expect(large).toBeGreaterThan(small);
  });
});

describe('depthOfField', () => {
  const frame = extractFrame(resolveSensor(ALEXA_35), 2.39);

  it('brackets the focus distance', () => {
    const dof = depthOfField(frame, 50, 'T2.8', 3);
    expect(dof.nearM).toBeLessThan(3);
    expect(dof.farM).toBeGreaterThan(3);
    expect(dof.inFrontM).toBeGreaterThan(0);
    expect(dof.behindM).toBeGreaterThan(0);
  });

  it('puts more depth behind the subject than in front', () => {
    const dof = depthOfField(frame, 50, 'T2.8', 3);
    expect(dof.behindM).toBeGreaterThan(dof.inFrontM);
  });

  it('gets shallower as the lens gets longer', () => {
    const wide = depthOfField(frame, 24, 'T2.8', 3);
    const long = depthOfField(frame, 135, 'T2.8', 3);
    expect(long.totalM).toBeLessThan(wide.totalM);
  });

  it('gets shallower as the aperture opens', () => {
    const stopped = depthOfField(frame, 50, 'T8', 3);
    const open = depthOfField(frame, 50, 'T1.4', 3);
    expect(open.totalM).toBeLessThan(stopped.totalM);
  });

  it('reaches infinity at the hyperfocal distance', () => {
    const near = depthOfField(frame, 50, 'T2.8', 3);
    const atHyperfocal = depthOfField(frame, 50, 'T2.8', near.hyperfocalM + 0.5);
    expect(atHyperfocal.atInfinity).toBe(true);
    expect(atHyperfocal.farM).toBe(Infinity);
    expect(atHyperfocal.totalM).toBe(Infinity);
  });
});

/* ------------------------------------------------------------------ *
 * Visual blur simulator
 * ------------------------------------------------------------------ */

describe('backgroundBlurRadius', () => {
  const FRAME_W = extractFrame(resolveSensor(ALEXA_35), 2.39).widthMm;

  it('grows with focal length', () => {
    const at35 = backgroundBlurRadius(35, 2.5, 3, FRAME_W, 600);
    const at85 = backgroundBlurRadius(85, 2.5, 3, FRAME_W, 600);
    expect(at85).toBeGreaterThan(at35);
  });

  it('grows as the aperture opens', () => {
    const stopped = backgroundBlurRadius(50, 8, 3, FRAME_W, 600);
    const open = backgroundBlurRadius(50, 1.4, 3, FRAME_W, 600);
    expect(open).toBeGreaterThan(stopped);
  });

  it('shrinks as focus moves further away', () => {
    const near = backgroundBlurRadius(50, 2.5, 1.5, FRAME_W, 600);
    const far = backgroundBlurRadius(50, 2.5, 30, FRAME_W, 600);
    expect(far).toBeLessThan(near);
  });

  it('scales with the pixels the frame is drawn across', () => {
    const small = backgroundBlurRadius(35, 2.5, 3, FRAME_W, 300);
    const large = backgroundBlurRadius(35, 2.5, 3, FRAME_W, 600);
    // Below the soft limit the relationship is linear.
    expect(large).toBeCloseTo(small * 2, 4);
  });

  it('keeps long lenses distinguishable instead of flattening them', () => {
    // A flat clamp made these identical, so 135mm and 250mm looked the same.
    const at135 = backgroundBlurRadius(135, 2.5, 3, FRAME_W, 600);
    const at250 = backgroundBlurRadius(250, 2.5, 3, FRAME_W, 600);
    expect(at250).toBeGreaterThan(at135);
  });

  it('keeps wide-open stops distinguishable', () => {
    const t14 = backgroundBlurRadius(85, 1.4, 3, FRAME_W, 600);
    const t10 = backgroundBlurRadius(85, 1.0, 3, FRAME_W, 600);
    expect(t10).toBeGreaterThan(t14);
  });

  it('never exceeds the compositor ceiling', () => {
    for (const f of [12, 35, 85, 135, 250, 1000]) {
      for (const n of [0.7, 1.4, 2.8, 22]) {
        const r = backgroundBlurRadius(f, n, 0.3, FRAME_W, 4000);
        expect(Number.isFinite(r)).toBe(true);
        expect(r).toBeLessThanOrEqual(64);
        expect(r).toBeGreaterThanOrEqual(0);
      }
    }
  });

  it('returns zero rather than NaN or Infinity on degenerate input', () => {
    expect(backgroundBlurRadius(0, 2.8, 3, FRAME_W, 600)).toBe(0);
    expect(backgroundBlurRadius(50, 0, 3, FRAME_W, 600)).toBe(0);
    expect(backgroundBlurRadius(50, 2.8, 3, 0, 600)).toBe(0);
    expect(backgroundBlurRadius(50, 2.8, 3, FRAME_W, 0)).toBe(0);
  });

  it('does not blow up when focus is at or inside the focal length', () => {
    const r = backgroundBlurRadius(50, 2.8, 0.01, FRAME_W, 600);
    expect(Number.isFinite(r)).toBe(true);
  });

  it('reports more blur on a height-limited extraction than on the full gate', () => {
    const sensor = resolveSensor(ALEXA_35);
    const frame43 = extractFrame(sensor, 4 / 3);
    const onExtraction = backgroundBlurRadius(50, 2.5, 3, frame43.widthMm, 600);
    const onGate = backgroundBlurRadius(50, 2.5, 3, sensor.widthMm, 600);
    expect(onExtraction).toBeGreaterThan(onGate);
  });
});

describe('softLimitBlur', () => {
  it('is the identity below the soft limit', () => {
    expect(softLimitBlur(0)).toBeCloseTo(0, 6);
    expect(softLimitBlur(10)).toBeCloseTo(10, 6);
    expect(softLimitBlur(24)).toBeCloseTo(24, 6);
  });

  it('is strictly increasing above it', () => {
    let previous = softLimitBlur(24);
    for (const v of [30, 40, 80, 160, 320, 5000]) {
      const current = softLimitBlur(v);
      expect(current).toBeGreaterThan(previous);
      previous = current;
    }
  });

  it('is asymptotic to the hard ceiling', () => {
    expect(softLimitBlur(1e6)).toBeLessThanOrEqual(64);
    expect(softLimitBlur(1e6)).toBeGreaterThan(63);
  });
});

/* ------------------------------------------------------------------ *
 * Delivery and colour
 * ------------------------------------------------------------------ */

describe('extractedResolution', () => {
  it('is null on a photochemical format with no photosites', () => {
    const sensor = resolveSensor('Super 35mm (Panavision Panaflex Gold)');
    expect(extractedResolution(sensor, extractFrame(sensor, 2.39))).toBeNull();
  });

  it('never claims more pixels than the sensor has', () => {
    const sensor = resolveSensor(ALEXA_35);
    const res = extractedResolution(sensor, extractFrame(sensor, 2.39));
    expect(res).not.toBeNull();
    expect(res!.widthPx).toBeLessThanOrEqual(sensor.photositesW!);
    expect(res!.heightPx).toBeLessThanOrEqual(sensor.photositesH!);
  });
});

describe('formatDistance', () => {
  it('renders infinity as the lens-barrel symbol', () => {
    expect(formatDistance(Infinity)).toBe('∞');
  });

  it('switches to centimetres under a metre', () => {
    expect(formatDistance(0.45)).toBe('45cm');
  });

  it('drops precision at longer distances', () => {
    expect(formatDistance(2.5)).toBe('2.50m');
    expect(formatDistance(42)).toBe('42.0m');
  });
});

describe('colour temperature', () => {
  it('renders neutral when white balance matches the key light', () => {
    // Channels are normalised 0..1 and multiplied over the plate, so neutral
    // is 1,1,1 — white, which shifts nothing.
    const tint = whiteBalanceTint(5600, 5600);
    expect(tint.r).toBeCloseTo(1, 4);
    expect(tint.g).toBeCloseTo(1, 4);
    expect(tint.b).toBeCloseTo(1, 4);
    expect(rgbToCss(tint)).toBe('rgb(255, 255, 255)');
  });

  it('goes warm when balanced cooler than the key, and cool the other way', () => {
    const warm = whiteBalanceTint(3200, 5600);
    const cool = whiteBalanceTint(7500, 5600);
    expect(warm.r).toBeGreaterThan(warm.b);
    expect(cool.b).toBeGreaterThan(cool.r);
  });

  it('produces a warmer rgb at lower kelvin', () => {
    const tungsten = colorTemperatureToRgb(3200);
    const daylight = colorTemperatureToRgb(6500);
    expect(tungsten.b).toBeLessThan(daylight.b);
  });

  it('mired shift is zero when the two agree and signed otherwise', () => {
    expect(miredShift(5600, 5600)).toBeCloseTo(0, 6);
    expect(miredShift(3200, 5600)).not.toBeCloseTo(0, 6);
    expect(Math.sign(miredShift(3200, 5600))).toBe(-Math.sign(miredShift(7500, 5600)));
  });
});
