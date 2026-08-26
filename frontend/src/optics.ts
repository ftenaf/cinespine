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
}

/**
 * Published open-gate active image areas. These drive every calculation in this
 * module, so verify against the current manufacturer spec sheet before relying
 * on the readouts for real production decisions.
 */
export const SENSOR_FORMATS: SensorFormat[] = [
  { id: 'Large Format 35mm (ARRI ALEXA 35)', label: 'ARRI ALEXA 35 (S35 open gate)', widthMm: 27.99, heightMm: 19.22 },
  { id: 'Full Frame 65mm (ARRI ALEXA 65)', label: 'ARRI ALEXA 65 (open gate)', widthMm: 54.12, heightMm: 25.58 },
  { id: 'Super 35mm (Panavision Panaflex Gold)', label: 'Panavision Panaflex Gold (4-perf S35)', widthMm: 24.89, heightMm: 18.66 },
  { id: 'RED V-Raptor 8K VV', label: 'RED V-Raptor 8K VV (open gate)', widthMm: 40.96, heightMm: 21.60 },
  { id: 'Large Format 35mm (ARRI ALEXA Mini LF)', label: 'ARRI ALEXA Mini LF (open gate)', widthMm: 36.70, heightMm: 25.54 },
];

export const DEFAULT_SENSOR_ID = SENSOR_FORMATS[0].id;

/** Full-frame stills reference, used only for the familiar "crop factor" figure. */
const FULL_FRAME_DIAGONAL_MM = Math.hypot(36, 24);

/** Reference focal length that maps to "no zoom" in the viewfinder. */
export const REFERENCE_FOCAL_MM = 35;

export function resolveSensor(id: string): SensorFormat {
  return SENSOR_FORMATS.find(s => s.id === id) ?? SENSOR_FORMATS[0];
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
  /** CSS transform scale for the plate inside the extraction window. */
  framingScale: number;
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

  return {
    sensor,
    frame,
    aspect,
    hfovDeg: angleOfView(frame.widthMm, focalLengthMm),
    vfovDeg: angleOfView(frame.heightMm, focalLengthMm),
    cropFactor: cropFactor(frame),
    framingScale: framingScale(frame.widthMm, focalLengthMm, referenceFocalMm),
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
