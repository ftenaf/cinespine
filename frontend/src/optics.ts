/**
 * Cinema optics geometry for the DoP Studio viewfinder.
 *
 * Everything here is deterministic geometry derived from real sensor dimensions.
 * It models FRAMING only (angle of view and the extracted frame within the
 * sensor's open gate). It deliberately does NOT claim to model perspective
 * compression: that is a function of camera-to-subject distance and cannot be
 * recovered from an already-rendered flat still. Re-render through the AI image
 * service when true optical character is required.
 */

export interface SensorFormat {
  /** Value used by the Camera Body / Sensor Format <select>. */
  id: string;
  label: string;
  /** Open gate active image area, in millimetres. */
  widthMm: number;
  heightMm: number;
  /**
   * Open gate photosite count. Null for photochemical formats, where there is
   * no pixel grid and delivered resolution is a property of the scan.
   */
  photositesW: number | null;
  photositesH: number | null;
}

/**
 * Published open-gate active image areas. These drive every calculation in this
 * module, so verify against the current manufacturer spec sheet before relying
 * on the readouts for real production decisions.
 */
export const SENSOR_FORMATS: SensorFormat[] = [
  { id: 'Large Format 35mm (ARRI ALEXA 35)', label: 'ARRI ALEXA 35 (S35 open gate)', widthMm: 27.99, heightMm: 19.22, photositesW: 4608, photositesH: 3164 },
  { id: 'Large Format 35mm (ARRI ALEXA Mini LF)', label: 'ARRI ALEXA Mini LF (open gate)', widthMm: 36.70, heightMm: 25.54, photositesW: 4448, photositesH: 3096 },
  { id: 'Full Frame 65mm (ARRI ALEXA 65)', label: 'ARRI ALEXA 65 (open gate)', widthMm: 54.12, heightMm: 25.58, photositesW: 6560, photositesH: 3100 },
  { id: 'IMAX 70mm 15-Perf (IMAX MKIV)', label: 'IMAX 15-Perf 70mm (horizontal gate)', widthMm: 70.41, heightMm: 52.63, photositesW: null, photositesH: null },
  { id: 'Super 35mm (Panavision Panaflex Gold)', label: 'Panavision Panaflex Gold (4-perf S35)', widthMm: 24.89, heightMm: 18.66, photositesW: null, photositesH: null },
  { id: 'Super 35 3-Perf (Arricam ST)', label: 'Arricam ST (3-perf S35)', widthMm: 24.89, heightMm: 13.87, photositesW: null, photositesH: null },
  { id: 'RED V-Raptor 8K VV', label: 'RED V-Raptor 8K VV (open gate)', widthMm: 40.96, heightMm: 21.60, photositesW: 8192, photositesH: 4320 },
];

export const DEFAULT_SENSOR_ID = SENSOR_FORMATS[0].id;

/** Full-frame stills reference, used only for the familiar "crop factor" figure. */
const FULL_FRAME_DIAGONAL_MM = Math.hypot(36, 24);

/** Reference focal length that maps to "no zoom" in the viewfinder. */
export const REFERENCE_FOCAL_MM = 35;

/**
 * Short names the backend and older saved presets use for a sensor, mapped to
 * the exact id they mean. Spelled out rather than matched by substring: several
 * ids share the "Large Format 35mm" prefix, so a substring match resolves by
 * array position and silently picks a different camera the moment SENSOR_FORMATS
 * is reordered.
 */
const SENSOR_ALIASES: Record<string, string> = {
  'large format 35mm': 'Large Format 35mm (ARRI ALEXA 35)',
  'super 35': 'Super 35mm (Panavision Panaflex Gold)',
  'super 35mm': 'Super 35mm (Panavision Panaflex Gold)',
  'full frame 35mm': 'Large Format 35mm (ARRI ALEXA Mini LF)',
  'large format 65mm': 'Full Frame 65mm (ARRI ALEXA 65)',
  'full frame 65mm': 'Full Frame 65mm (ARRI ALEXA 65)',
  'imax 70mm': 'IMAX 70mm 15-Perf (IMAX MKIV)',
};

export function resolveSensor(id: string): SensorFormat {
  if (!id) return SENSOR_FORMATS[0];

  const exact = SENSOR_FORMATS.find(s => s.id === id);
  if (exact) return exact;

  const key = id.trim().toLowerCase();
  const aliased = SENSOR_ALIASES[key];
  if (aliased) {
    const match = SENSOR_FORMATS.find(s => s.id === aliased);
    if (match) return match;
  }

  // Last resort: match on the human label, which is unique per sensor.
  const byLabel = SENSOR_FORMATS.find(s => s.label.toLowerCase() === key);
  return byLabel ?? SENSOR_FORMATS[0];
}

/** Parses "2.39:1", "16:9", "4:3" into a numeric width/height ratio. */
export function parseAspectRatio(ar: string): number {
  const [w, h] = ar.split(':').map(Number);
  if (!w || !h || !isFinite(w / h)) return 2.39;
  return w / h;
}

export interface ExtractedFrame {
  /** Extracted (recorded) frame within the open gate, in millimetres. */
  widthMm: number;
  heightMm: number;
  /** Fraction of the open-gate area actually used by this extraction, 0..1. */
  sensorAreaUsed: number;
  /** Whether the extraction is limited by sensor width or sensor height. */
  limitedBy: 'width' | 'height';
}

/**
 * Largest frame of the requested aspect ratio that fits inside the open gate.
 * A wide ratio on a boxy sensor is width-limited and loses height; a narrow
 * ratio on a wide sensor is height-limited and loses width.
 */
export function extractFrame(sensor: SensorFormat, aspect: number): ExtractedFrame {
  const gateAspect = sensor.widthMm / sensor.heightMm;
  let widthMm: number;
  let heightMm: number;
  let limitedBy: 'width' | 'height';

  if (aspect >= gateAspect) {
    widthMm = sensor.widthMm;
    heightMm = sensor.widthMm / aspect;
    limitedBy = 'width';
  } else {
    heightMm = sensor.heightMm;
    widthMm = sensor.heightMm * aspect;
    limitedBy = 'height';
  }

  const sensorAreaUsed = (widthMm * heightMm) / (sensor.widthMm * sensor.heightMm);
  return { widthMm, heightMm, sensorAreaUsed, limitedBy };
}

/** Angle of view in degrees across a given frame dimension, for a rectilinear lens. */
export function angleOfView(dimensionMm: number, focalLengthMm: number): number {
  if (focalLengthMm <= 0) return 0;
  return (2 * Math.atan(dimensionMm / (2 * focalLengthMm)) * 180) / Math.PI;
}

/** Crop factor of the extracted frame relative to full-frame stills. */
export function cropFactor(frame: ExtractedFrame): number {
  return FULL_FRAME_DIAGONAL_MM / Math.hypot(frame.widthMm, frame.heightMm);
}

/**
 * Scale to apply to a plate that was framed at `referenceFocalMm` so it matches
 * the angle of view of `focalLengthMm`. Longer lens -> scale > 1 (punch in).
 *
 * This is the magnification component of a focal length change only. It does
 * not reproduce perspective compression.
 */
export function framingScale(
  frameWidthMm: number,
  focalLengthMm: number,
  referenceFocalMm: number = REFERENCE_FOCAL_MM,
): number {
  const refHalf = Math.atan(frameWidthMm / (2 * referenceFocalMm));
  const curHalf = Math.atan(frameWidthMm / (2 * focalLengthMm));
  if (curHalf <= 0) return 1;
  return Math.tan(refHalf) / Math.tan(curHalf);
}

export interface ViewfinderGeometry {
  sensor: SensorFormat;
  frame: ExtractedFrame;
  aspect: number;
  /** Horizontal angle of view of the extracted frame, in degrees. */
  hfovDeg: number;
  /** Vertical angle of view of the extracted frame, in degrees. */
  vfovDeg: number;
  cropFactor: number;
  /**
   * True angle-of-view ratio against the reference focal length. Below 1 for
   * lenses wider than the plate was framed at.
   */
  framingScale: number;
  /**
   * Scale actually applied to the plate, clamped at 1. A crop cannot synthesise
   * field of view the plate does not contain, so going wider than the reference
   * is not simulatable — only a re-render can show it.
   */
  appliedScale: number;
  /** True when the requested focal length is wider than the plate can show. */
  plateLimited: boolean;
  /**
   * Scale for the dimmed surround view: how much larger the open gate is than
   * the extraction along each axis.
   */
  surroundScaleX: number;
  surroundScaleY: number;
}

export function computeViewfinderGeometry(
  sensorId: string,
  aspectRatio: string,
  focalLengthMm: number,
  referenceFocalMm: number = REFERENCE_FOCAL_MM,
): ViewfinderGeometry {
  const sensor = resolveSensor(sensorId);
  const aspect = parseAspectRatio(aspectRatio);
  const frame = extractFrame(sensor, aspect);
  const scale = framingScale(frame.widthMm, focalLengthMm, referenceFocalMm);

  return {
    sensor,
    frame,
    aspect,
    hfovDeg: angleOfView(frame.widthMm, focalLengthMm),
    vfovDeg: angleOfView(frame.heightMm, focalLengthMm),
    cropFactor: cropFactor(frame),
    framingScale: scale,
    appliedScale: scale,
    plateLimited: scale < 0.999,
    surroundScaleX: sensor.widthMm / frame.widthMm,
    surroundScaleY: sensor.heightMm / frame.heightMm,
  };
}

/** Common protect/shoot-and-protect ratios offered as frame lines. */
export const PROTECT_RATIOS = ['2.39:1', '1.85:1', '16:9', '4:3'] as const;

/**
 * Size of a protect frame as a percentage of the *extraction* box, for drawing
 * frame lines. Returns null when the protect ratio is the delivery ratio.
 */
export function protectFrameInset(deliveryAspect: number, protectAspect: number): { widthPct: number; heightPct: number } | null {
  if (Math.abs(deliveryAspect - protectAspect) < 0.001) return null;
  if (protectAspect > deliveryAspect) {
    // Wider than delivery: full width, shorter height.
    return { widthPct: 100, heightPct: (deliveryAspect / protectAspect) * 100 };
  }
  // Narrower than delivery: full height, narrower width.
  return { widthPct: (protectAspect / deliveryAspect) * 100, heightPct: 100 };
}

/* ------------------------------------------------------------------------- *
 * Depth of field
 *
 * Real geometric depth of field, computed from the extracted frame's circle of
 * confusion, the lens f-number, and the focus distance. These are the same
 * formulas a pCAM/Artemis-class calculator uses, so the numbers are checkable
 * against the tools an AC already carries.
 * ------------------------------------------------------------------------- */

/**
 * Circle of confusion divisor applied to the extracted frame diagonal.
 * 1500 puts Super 35 at roughly 0.020mm, the value commonly used for cinema
 * acquisition (stills calculators typically use a looser 1442-1730).
 */
export const COC_DIVISOR = 1500;

/**
 * Typical cine prime transmission efficiency. A T-stop is the measured
 * transmission stop; the geometric f-number that governs depth of field is
 * N = T * sqrt(transmission).
 */
export const LENS_TRANSMISSION = 0.8;

/** Parses "T2.8" (or "f/2.8", or "2.8") into its numeric stop. */
export function parseStop(stop: string): number {
  const n = parseFloat(String(stop).replace(/[^0-9.]/g, ''));
  return isFinite(n) && n > 0 ? n : 2.8;
}

/** Geometric f-number behind a marked T-stop. */
export function fNumberFromTStop(tStop: number): number {
  return tStop * Math.sqrt(LENS_TRANSMISSION);
}

/** Circle of confusion in millimetres for a given extracted frame. */
export function circleOfConfusion(frame: ExtractedFrame): number {
  return Math.hypot(frame.widthMm, frame.heightMm) / COC_DIVISOR;
}

export interface DepthOfField {
  /** Hyperfocal distance, metres. */
  hyperfocalM: number;
  /** Near limit of acceptable sharpness, metres. */
  nearM: number;
  /** Far limit, metres. Infinity once focus reaches the hyperfocal distance. */
  farM: number;
  /** Total depth, metres. Infinity when the far limit is unbounded. */
  totalM: number;
  /** Depth in front of the focus plane, metres. */
  inFrontM: number;
  /** Depth behind the focus plane, metres. Infinity when unbounded. */
  behindM: number;
  /** Circle of confusion used, millimetres. */
  cocMm: number;
  /** Geometric f-number derived from the marked T-stop. */
  fNumber: number;
  /** True once the far limit runs to infinity. */
  atInfinity: boolean;
}

/**
 * Depth of field for a focus distance in metres.
 *
 * H  = f^2 / (N * c) + f
 * Dn = s (H - f) / (H + s - 2f)
 * Df = s (H - f) / (H - s)      -> infinity once s >= H
 */
export function depthOfField(
  frame: ExtractedFrame,
  focalLengthMm: number,
  tStop: string | number,
  focusDistanceM: number,
): DepthOfField {
  const c = circleOfConfusion(frame);
  const f = focalLengthMm;
  const N = fNumberFromTStop(typeof tStop === 'number' ? tStop : parseStop(tStop));
  const s = Math.max(focusDistanceM, 0.01) * 1000; // mm

  const H = (f * f) / (N * c) + f;

  // Focusing closer than the focal length is not physically meaningful.
  if (s <= f) {
    return {
      hyperfocalM: H / 1000, nearM: 0, farM: 0, totalM: 0,
      inFrontM: 0, behindM: 0, cocMm: c, fNumber: N, atInfinity: false,
    };
  }

  const nearMm = (s * (H - f)) / (H + s - 2 * f);
  const atInfinity = s >= H;
  const farMm = atInfinity ? Infinity : (s * (H - f)) / (H - s);

  const nearM = nearMm / 1000;
  const farM = atInfinity ? Infinity : farMm / 1000;
  const focusM = s / 1000;

  return {
    hyperfocalM: H / 1000,
    nearM,
    farM,
    totalM: atInfinity ? Infinity : farM - nearM,
    inFrontM: focusM - nearM,
    behindM: atInfinity ? Infinity : farM - focusM,
    cocMm: c,
    fNumber: N,
    atInfinity,
  };
}

/** Widest blur a browser composites smoothly; beyond this, growth is compressed. */
const BLUR_SOFT_LIMIT_PX = 24;

/** Hard ceiling, to keep an extreme setting from stalling the compositor. */
const BLUR_HARD_LIMIT_PX = 64;

/**
 * Apparent blur radius, in CSS pixels, of a background object at infinity.
 * Drives the real-time visual depth of field simulator.
 *
 * The blur circle is computed on the sensor and then scaled by how many pixels
 * the frame is actually drawn across, so the same lens reads the same whatever
 * size the viewfinder happens to be. Pass the *extraction* width rather than the
 * full gate width: on a height-limited ratio the frame is narrower than the gate,
 * and the sensor's own dimension would understate the blur by around 9%.
 */
export function backgroundBlurRadius(
  focalLengthMm: number,
  fNumber: number,
  focusDistanceM: number,
  frameWidthMm: number,
  renderedWidthPx: number = 1000,
): number {
  if (!(focalLengthMm > 0) || !(fNumber > 0) || !(frameWidthMm > 0) || !(renderedWidthPx > 0)) {
    return 0;
  }

  // Focus distance in mm, floored just past the focal length so the thin-lens
  // denominator cannot reach zero.
  const s = Math.max(focusDistanceM * 1000, focalLengthMm + 1);

  // Blur circle diameter on the sensor, in mm, for a subject at infinity.
  // Exact thin-lens form; the f² / (N·s) approximation understates by ~2%.
  const cBg = (focalLengthMm * focalLengthMm) / (fNumber * (s - focalLengthMm));

  // As a fraction of frame width, then across the pixels the frame is drawn on.
  const blurRadiusPx = (cBg / frameWidthMm) * renderedWidthPx * 0.5;

  return softLimitBlur(blurRadiusPx);
}

/**
 * Keeps very shallow settings distinguishable from one another.
 *
 * A flat clamp made every long lens look identical past the limit — a 135mm and
 * a 250mm both pinned to the same value. Past the soft limit this compresses
 * logarithmically instead, so more blur still reads as more blur, while the
 * absolute ceiling protects the compositor.
 */
export function softLimitBlur(radiusPx: number): number {
  if (radiusPx <= BLUR_SOFT_LIMIT_PX) return radiusPx;
  const excess = radiusPx - BLUR_SOFT_LIMIT_PX;
  const headroom = BLUR_HARD_LIMIT_PX - BLUR_SOFT_LIMIT_PX;
  return BLUR_SOFT_LIMIT_PX + headroom * (1 - Math.exp(-excess / headroom));
}

/** Formats a distance in metres for a viewfinder readout. */
export function formatDistance(m: number): string {
  if (!isFinite(m)) return '∞';
  if (m < 1) return `${(m * 100).toFixed(0)}cm`;
  if (m < 10) return `${m.toFixed(2)}m`;
  return `${m.toFixed(1)}m`;
}

/* ------------------------------------------------------------------------- *
 * Colour temperature
 *
 * The image only shifts when the camera's white balance disagrees with the key
 * light. Matching WB to source is neutral by definition; balancing cooler than
 * the source warms the image, and balancing warmer cools it.
 * ------------------------------------------------------------------------- */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/**
 * Approximate sRGB rendering of a Planckian (blackbody) radiator, after the
 * Tanner Helland approximation. Valid roughly 1000K-40000K. Channels 0..1.
 */
export function colorTemperatureToRgb(kelvin: number): Rgb {
  const t = Math.min(Math.max(kelvin, 1000), 40000) / 100;
  const clamp = (v: number) => Math.min(Math.max(v, 0), 255) / 255;

  let r: number;
  let g: number;
  let b: number;

  if (t <= 66) {
    r = 255;
    g = 99.4708025861 * Math.log(t) - 161.1195681661;
  } else {
    r = 329.698727446 * Math.pow(t - 60, -0.1332047592);
    g = 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  }

  if (t >= 66) {
    b = 255;
  } else if (t <= 19) {
    b = 0;
  } else {
    b = 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  }

  return { r: clamp(r), g: clamp(g), b: clamp(b) };
}

/**
 * Multiplicative tint produced by shooting a `sourceK` key light while the
 * camera is balanced for `whiteBalanceK`. Normalised so the strongest channel
 * is 1, which makes it safe to apply as a multiply blend: matching values give
 * white (no shift), a mismatch darkens the opposing channels.
 */
export function whiteBalanceTint(sourceK: number, whiteBalanceK: number): Rgb {
  const src = colorTemperatureToRgb(sourceK);
  const wb = colorTemperatureToRgb(whiteBalanceK);

  const ratio = {
    r: src.r / Math.max(wb.r, 0.0001),
    g: src.g / Math.max(wb.g, 0.0001),
    b: src.b / Math.max(wb.b, 0.0001),
  };

  const peak = Math.max(ratio.r, ratio.g, ratio.b, 0.0001);
  return { r: ratio.r / peak, g: ratio.g / peak, b: ratio.b / peak };
}

/** Mired shift between source and white balance — how many CC units off it is. */
export function miredShift(sourceK: number, whiteBalanceK: number): number {
  return 1e6 / whiteBalanceK - 1e6 / sourceK;
}

export function rgbToCss({ r, g, b }: Rgb): string {
  return `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
}

/* ------------------------------------------------------------------------- *
 * Delivered resolution
 *
 * What the chosen extraction actually yields in pixels, and whether that still
 * clears the common mastering targets. Replaces the decorative "REC / RAW"
 * chrome with something a DoP or DIT can act on.
 * ------------------------------------------------------------------------- */

export interface ExtractedResolution {
  widthPx: number;
  heightPx: number;
  /** Photosite pitch in micrometres. */
  pixelPitchUm: number;
  /** Highest mastering target the extraction width clears. */
  masteringTarget: string;
  /** False once the extraction drops below HD width. */
  meetsHd: boolean;
}

const MASTERING_TARGETS: { minWidth: number; label: string }[] = [
  { minWidth: 7680, label: '8K UHD' },
  { minWidth: 6144, label: '6K' },
  { minWidth: 4096, label: 'DCI 4K' },
  { minWidth: 3840, label: 'UHD 4K' },
  { minWidth: 2048, label: 'DCI 2K' },
  { minWidth: 1920, label: 'HD' },
];

/**
 * Pixel dimensions of the extracted frame. Returns null for photochemical
 * formats, where resolution is a property of the scan rather than the camera.
 */
export function extractedResolution(
  sensor: SensorFormat,
  frame: ExtractedFrame,
): ExtractedResolution | null {
  if (sensor.photositesW === null || sensor.photositesH === null) return null;

  const widthPx = Math.round(sensor.photositesW * (frame.widthMm / sensor.widthMm));
  const heightPx = Math.round(sensor.photositesH * (frame.heightMm / sensor.heightMm));
  const pixelPitchUm = (sensor.widthMm / sensor.photositesW) * 1000;
  const target = MASTERING_TARGETS.find(t => widthPx >= t.minWidth);

  return {
    widthPx,
    heightPx,
    pixelPitchUm,
    masteringTarget: target ? target.label : 'sub-HD',
    meetsHd: widthPx >= 1920,
  };
}
