import { describe, it, expect } from 'vitest';
import { splitOnHighlight } from './scriptHighlight';
import { ScriptSceneContext } from './types';

function scene(over: Partial<ScriptSceneContext> = {}): ScriptSceneContext {
  return {
    scene_number: '119',
    heading: 'INT. GREAT HALL - DAY',
    body: 'LEAD sits.\nHe strikes a chord.\nSUPPORT enters.\n',
    highlight: null,
    highlight_basis: 'none',
    note: null,
    ...over,
  };
}

const whole = (s: ScriptSceneContext) => splitOnHighlight(s).join('');

describe('splitOnHighlight', () => {
  it('leaves an unhighlighted scene whole', () => {
    const [before, inside, after] = splitOnHighlight(scene());
    expect(before).toBe(scene().body);
    expect(inside).toBe('');
    expect(after).toBe('');
  });

  it('cuts the scene at the highlighted span', () => {
    const s = scene({ highlight: { start: 11, end: 32, terms: ['chord'], score: 1 } });
    const [, inside] = splitOnHighlight(s);
    expect(inside).toContain('chord');
  });

  it('never loses text, whatever the span says', () => {
    const spans = [
      { start: 0, end: 0 },
      { start: 5, end: 5 },
      { start: 0, end: 9999 },
      { start: -20, end: 12 },
      // Backwards: end before start. Slicing this raw would silently drop the
      // rest of the scene.
      { start: 30, end: 4 },
    ];
    for (const span of spans) {
      const s = scene({ highlight: { ...span, terms: [], score: 1 } });
      expect(whole(s)).toBe(scene().body);
    }
  });

  it('highlights nothing rather than something wrong when the span is backwards', () => {
    const s = scene({ highlight: { start: 30, end: 4, terms: [], score: 1 } });
    expect(splitOnHighlight(s)[1]).toBe('');
  });

  it('handles an empty scene body', () => {
    const s = scene({ body: '', highlight: { start: 0, end: 40, terms: [], score: 1 } });
    expect(splitOnHighlight(s)).toEqual(['', '', '']);
  });
});
