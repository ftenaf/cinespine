import { ScriptSceneContext } from './types';

/**
 * Scene text split into the run before the highlight, the highlight, and the
 * run after it.
 *
 * The offsets come from the server, and rendering them raw would trust a
 * remote number with where a page is cut. Clamping keeps a stale or malformed
 * span from dropping text off the scene: the reader may lose the highlight,
 * but never the words.
 */
export function splitOnHighlight(scene: ScriptSceneContext): [string, string, string] {
  const body = scene.body ?? '';
  const highlight = scene.highlight;
  if (!highlight) return [body, '', ''];

  const start = Math.max(0, Math.min(highlight.start, body.length));
  const end = Math.max(start, Math.min(highlight.end, body.length));
  return [body.slice(0, start), body.slice(start, end), body.slice(end)];
}
