import { useMemo, useState } from 'react';
import type { PersonalityAxes } from '../types';

/**
 * A character's personality, read from the script, drawn as a polygon.
 *
 * Five axes, always the same five and always in the same order, because the
 * point of the shape is comparison: two characters are only tellable apart at
 * a glance if their axes sit in the same places.
 *
 * The axes are the Big Five, named rather than invented — five dimensions made
 * up for this app would be pseudo-psychology with a chart around it, and
 * nobody could say what a score meant.
 *
 * # An unscored axis is a gap, not a zero
 *
 * A character with four lines does not contain five readings, and the
 * inference is allowed to return null for an axis the script will not support.
 * Null must not be drawn at the centre: a point at the centre reads as "none
 * of this trait", which is a claim nobody made. So the polygon is drawn only
 * across the axes that were scored, unscored spokes are dashed, and the count
 * is stated. A shape over three axes should not be mistaken for a shape over
 * five.
 */

// `short` is what fits around a 300px chart; `label` is what the caption says
// when an axis is hovered. Truncating the full names at draw time clipped them
// to "Conscie" and "vol... 90", which named nothing.
export const AXES: { key: keyof PersonalityAxes; label: string; short: string; blurb: string }[] = [
  { key: 'openness', label: 'Openness', short: 'Openness',
    blurb: 'Curiosity and imagination; appetite for the unfamiliar.' },
  { key: 'conscientiousness', label: 'Conscientiousness', short: 'Conscient.',
    blurb: 'Order, diligence, follow-through.' },
  { key: 'extraversion', label: 'Extraversion', short: 'Extravers.',
    blurb: 'Energy directed outward; how much they take up a room.' },
  { key: 'agreeableness', label: 'Agreeableness', short: 'Agreeable.',
    blurb: 'Warmth and accommodation towards others.' },
  { key: 'emotional_volatility', label: 'Emotional volatility', short: 'Volatility',
    blurb: 'How readily feeling breaks the surface and swings.' },
];

// Room for the labels outside the rings. The chart is small; the words are not.
const SIZE = 320;
const CENTRE = SIZE / 2;
const RADIUS = 88;

/** Where an axis sits, with the first spoke pointing straight up. */
function point(index: number, distance: number) {
  const angle = (Math.PI * 2 * index) / AXES.length - Math.PI / 2;
  return {
    x: CENTRE + Math.cos(angle) * distance,
    y: CENTRE + Math.sin(angle) * distance,
  };
}

/**
 * The axes that actually carry a score, in draw order.
 *
 * Exported and pure so the one invariant that matters can be tested without a
 * DOM: an axis scored 0 is scored, and an axis scored null is not. Those two
 * look identical on a chart if this function conflates them, and the whole
 * design rests on their staying apart.
 */
export function scoredAxes(axes?: PersonalityAxes | null) {
  if (!axes) return [];
  return AXES.filter(a => typeof axes[a.key]?.score === 'number');
}

/** Where the shape's vertices sit. Only across scored axes. */
export function polygonPoints(axes?: PersonalityAxes | null): string {
  return scoredAxes(axes)
    .map(a => {
      const i = AXES.findIndex(x => x.key === a.key);
      const p = point(i, (RADIUS * (axes![a.key]!.score as number)) / 100);
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    })
    .join(' ');
}

function ring(fraction: number) {
  return AXES.map((_, i) => {
    const p = point(i, RADIUS * fraction);
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(' ');
}

export function PersonalityPolygon({ axes, name }: { axes?: PersonalityAxes | null; name?: string }) {
  const [hovered, setHovered] = useState<string | null>(null);

  const scored = useMemo(() => scoredAxes(axes), [axes]);

  if (!axes || scored.length === 0) {
    // Said plainly rather than drawn as an empty pentagon. A collapsed shape
    // looks like a character with no personality instead of a script the
    // inference could not read.
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-xs text-gray-400">
        <div className="font-semibold text-gray-300 mb-1">Personality</div>
        No axes were scored from the script
        {name ? <> for <span className="text-gray-200">{name}</span></> : null}. This
        happens when a character speaks too little to read.
      </div>
    );
  }

  // Only across the axes that have a score. Closing the shape through an
  // unscored axis would invent a vertex.
  const shape = polygonPoints(axes);

  const active = hovered ? AXES.find(a => a.key === hovered) : null;
  const activeEntry = active ? axes[active.key] : null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-baseline justify-between mb-1">
        <div className="text-xs font-semibold text-gray-300">Personality, read from the script</div>
        <div className="text-[10px] text-gray-500">
          {scored.length} of {AXES.length} axes scored
        </div>
      </div>

      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[330px] mx-auto" role="img"
           aria-label={`Personality polygon${name ? ` for ${name}` : ''}, ${scored.length} of ${AXES.length} axes scored`}>
        {[0.25, 0.5, 0.75, 1].map(f => (
          <polygon key={f} points={ring(f)} fill="none" stroke="#1e293b" strokeWidth={1} />
        ))}

        {AXES.map((axis, i) => {
          const end = point(i, RADIUS);
          const isScored = typeof axes[axis.key]?.score === 'number';
          return (
            <line
              key={axis.key}
              x1={CENTRE} y1={CENTRE} x2={end.x} y2={end.y}
              stroke={isScored ? '#334155' : '#1e293b'}
              // Dashed where nothing was scored, so a short shape is visibly
              // short on evidence rather than low on the trait.
              strokeDasharray={isScored ? undefined : '3 3'}
              strokeWidth={1}
            />
          );
        })}

        {scored.length >= 3 ? (
          <polygon points={shape} fill="rgba(56,189,248,0.22)" stroke="#38bdf8" strokeWidth={2} />
        ) : (
          // Two points are a line and one is a dot; drawing either as a filled
          // polygon would suggest an area that was never measured.
          <polyline points={shape} fill="none" stroke="#38bdf8" strokeWidth={2} />
        )}

        {AXES.map((axis, i) => {
          const entry = axes[axis.key];
          if (typeof entry?.score !== 'number') return null;
          const p = point(i, (RADIUS * entry.score) / 100);
          return (
            <circle
              key={axis.key}
              cx={p.x} cy={p.y} r={hovered === axis.key ? 5 : 3.5}
              fill="#38bdf8"
              className="cursor-pointer"
              onMouseEnter={() => setHovered(axis.key)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}

        {AXES.map((axis, i) => {
          const p = point(i, RADIUS + 20);
          const entry = axes[axis.key];
          const score = typeof entry?.score === 'number' ? entry.score : null;
          return (
            <text
              key={axis.key}
              x={p.x} y={p.y}
              textAnchor={p.x > CENTRE + 4 ? 'start' : p.x < CENTRE - 4 ? 'end' : 'middle'}
              dominantBaseline="middle"
              className="cursor-pointer"
              fontSize={9.5}
              fill={score === null ? '#475569' : hovered === axis.key ? '#e2e8f0' : '#94a3b8'}
              onMouseEnter={() => setHovered(axis.key)}
              onMouseLeave={() => setHovered(null)}
            >
              {axis.short}
              {score === null ? ' —' : ` ${score}`}
            </text>
          );
        })}
      </svg>

      <div className="mt-2 min-h-[3.5rem] text-[11px] leading-snug">
        {active ? (
          <>
            <div className="text-gray-200 font-semibold">{active.label}</div>
            <div className="text-gray-500">{active.blurb}</div>
            {/* The evidence, not just the number. A score nobody can check
                against the script is an assertion with a chart around it. */}
            <div className="text-gray-400 mt-1">
              {activeEntry?.evidence
                ? `“${activeEntry.evidence}”`
                : 'Not scored — the script does not say enough.'}
            </div>
          </>
        ) : (
          <div className="text-gray-600">Hover an axis to see what in the script it rests on.</div>
        )}
      </div>
    </div>
  );
}
