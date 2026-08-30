import { describe, it, expect } from 'vitest';
import { AXES, scoredAxes, polygonPoints } from './PersonalityPolygon';
import type { PersonalityAxes } from '../types';

/**
 * The one thing this chart must not get wrong.
 *
 * An axis the script could not support comes back null, and null is a real
 * answer. Drawn as zero it puts a vertex at the centre, which reads as "none
 * of this trait" — a claim nobody made. A character with four lines does not
 * contain five readings, and the chart has to show that as a gap.
 */

const full: PersonalityAxes = {
  openness: { score: 85, evidence: 'dedicates himself to counterpoint' },
  conscientiousness: { score: 40, evidence: 'hands falter under pressure' },
  extraversion: { score: 15, evidence: 'whispers to himself' },
  agreeableness: { score: 20, evidence: 'leaves without answering' },
  emotional_volatility: { score: 90, evidence: 'haggard, sweating' },
};

describe('the axes are fixed', () => {
  it('has five, in a stable order', () => {
    expect(AXES).toHaveLength(5);
    expect(AXES.map(a => a.key)).toEqual([
      'openness', 'conscientiousness', 'extraversion',
      'agreeableness', 'emotional_volatility',
    ]);
  });

  it('gives every axis a short label that fits and a full one that reads', () => {
    for (const axis of AXES) {
      expect(axis.short.length).toBeLessThanOrEqual(11);
      expect(axis.label.length).toBeGreaterThan(0);
      expect(axis.blurb.length).toBeGreaterThan(20);
    }
  });
});

describe('an unscored axis is a gap, not a zero', () => {
  it('counts a null score as unscored', () => {
    const axes: PersonalityAxes = { ...full, agreeableness: { score: null, evidence: null } };
    expect(scoredAxes(axes).map(a => a.key)).not.toContain('agreeableness');
    expect(scoredAxes(axes)).toHaveLength(4);
  });

  it('counts a zero score as scored, because somebody asserted it', () => {
    const axes: PersonalityAxes = { ...full, agreeableness: { score: 0, evidence: 'refuses everyone' } };
    expect(scoredAxes(axes).map(a => a.key)).toContain('agreeableness');
  });

  it('draws no vertex for an axis that was not scored', () => {
    const one: PersonalityAxes = { openness: { score: 85, evidence: 'x' } };
    expect(polygonPoints(one).split(' ')).toHaveLength(1);
  });

  it('draws a vertex for every axis that was', () => {
    expect(polygonPoints(full).split(' ')).toHaveLength(5);
  });

  it('puts a null axis nowhere rather than at the centre', () => {
    const withNull: PersonalityAxes = { ...full, extraversion: { score: null, evidence: null } };
    const zeroed: PersonalityAxes = { ...full, extraversion: { score: 0, evidence: 'x' } };
    expect(polygonPoints(withNull).split(' ')).toHaveLength(4);
    expect(polygonPoints(zeroed).split(' ')).toHaveLength(5);
    expect(polygonPoints(withNull)).not.toEqual(polygonPoints(zeroed));
  });
});

describe('nothing to draw', () => {
  it('treats missing axes as nothing scored', () => {
    expect(scoredAxes(undefined)).toHaveLength(0);
    expect(scoredAxes(null)).toHaveLength(0);
    expect(scoredAxes({})).toHaveLength(0);
    expect(polygonPoints(undefined)).toBe('');
  });

  it('treats an all-null reading as nothing scored', () => {
    const empty = Object.fromEntries(
      AXES.map(a => [a.key, { score: null, evidence: null }]),
    ) as PersonalityAxes;
    expect(scoredAxes(empty)).toHaveLength(0);
  });
});

describe('the shape reflects the scores', () => {
  it('places a higher score further from the centre', () => {
    const near: PersonalityAxes = { openness: { score: 10, evidence: 'x' } };
    const far: PersonalityAxes = { openness: { score: 90, evidence: 'x' } };
    const [, nearY] = polygonPoints(near).split(',').map(Number);
    const [, farY] = polygonPoints(far).split(',').map(Number);
    // The first axis points straight up, so further out is a smaller y.
    expect(farY).toBeLessThan(nearY);
  });
});
