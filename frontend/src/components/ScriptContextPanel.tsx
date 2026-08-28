import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, Loader2, X, AlertTriangle, Highlighter } from 'lucide-react';
import { ScriptContext, ScriptSceneContext, TagTargetType } from '../types';
import { fetchScriptContext } from '../api';
import { splitOnHighlight } from '../scriptHighlight';

/**
 * The scene behind a slate.
 *
 * An editor cutting 119/5 is looking at camera cards, timecodes and a take
 * number, none of which say what the scene is about. This opens the screenplay
 * at that scene.
 *
 * The highlight makes two different kinds of claim and the panel never lets
 * them look alike. A scene highlight is exact -- the scene is the scene. A shot
 * highlight is inferred by matching the script supervisor's description against
 * the text, so it is labelled as inferred and shows the words it matched on. A
 * confident-looking highlight over the wrong half of a page would send someone
 * to cut the wrong moment.
 */

function BasisLine({ scene }: { scene: ScriptSceneContext }) {
  if (scene.highlight_basis === 'scene') {
    return (
      <p className="text-[11px] text-gray-500">
        The whole scene is highlighted.
      </p>
    );
  }

  if (scene.highlight_basis === 'description' && scene.highlight) {
    return (
      <p className="text-[11px] text-amber-300/80 flex items-start gap-1.5">
        <Highlighter className="w-3 h-3 mt-0.5 shrink-0" aria-hidden />
        <span>
          Placed by matching the script supervisor&rsquo;s note on{' '}
          <span className="font-semibold">{scene.highlight.terms.join(', ')}</span>. This is
          inferred from the wording, not recorded anywhere &mdash; check it before you cut.
        </span>
      </p>
    );
  }

  return scene.note ? <p className="text-[11px] text-gray-500">{scene.note}</p> : null;
}

function SceneBlock({ scene }: { scene: ScriptSceneContext }) {
  const markRef = useRef<HTMLElement>(null);
  const [before, inside, after] = splitOnHighlight(scene);

  useEffect(() => {
    // A highlight below the fold is a highlight nobody sees.
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'auto' });
  }, [scene.scene_number, scene.highlight?.start]);

  return (
    <section className="space-y-2">
      <div className="flex items-baseline gap-2 sticky top-0 bg-slate-900 py-1">
        <span className="text-xs font-bold text-spine-accent">Scene {scene.scene_number}</span>
        <span className="text-[11px] text-gray-400 truncate">{scene.heading}</span>
      </div>
      <BasisLine scene={scene} />
      <pre className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-gray-300 bg-slate-950/60 border border-slate-800 rounded-lg p-3">
        {before}
        {inside && (
          <mark ref={markRef} className="bg-amber-400/25 text-amber-100 rounded-sm">
            {inside}
          </mark>
        )}
        {after}
      </pre>
    </section>
  );
}

function EmptyState({ context }: { context: ScriptContext }) {
  return (
    <div className="flex items-start gap-2 text-sm text-gray-300 bg-slate-950/60 border border-slate-800 rounded-lg p-4">
      <AlertTriangle className="w-4 h-4 mt-0.5 text-amber-400 shrink-0" aria-hidden />
      <p>{context.message ?? 'There is nothing to show for this target.'}</p>
    </div>
  );
}

interface PanelProps {
  productionId: string;
  targetType: TagTargetType;
  targetId: string;
  onClose: () => void;
}

export function ScriptContextPanel({ productionId, targetType, targetId, onClose }: PanelProps) {
  const [context, setContext] = useState<ScriptContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setIsLoading(true);
    setError(null);
    fetchScriptContext(productionId, targetType, targetId)
      .then(data => { if (live) setContext(data); })
      .catch(err => { if (live) setError(err?.message ?? 'Failed to open the script'); })
      .finally(() => { if (live) setIsLoading(false); });
    return () => { live = false; };
  }, [productionId, targetType, targetId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={`Script for ${targetType} ${targetId}`}
        className="w-full max-w-3xl max-h-[85vh] flex flex-col bg-slate-900 border border-slate-700 rounded-xl shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 px-4 py-3 border-b border-slate-800">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white">
              {targetType === 'shot' ? 'Shot' : 'Scene'} {targetId}
            </p>
            <p className="text-[11px] text-gray-400 truncate">
              {context?.script_title ?? 'Screenplay'}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close the script"
            className="text-gray-500 hover:text-white transition"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="overflow-y-auto px-4 py-3 space-y-4">
          {isLoading && (
            <p className="flex items-center gap-2 text-sm text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> Opening the script&hellip;
            </p>
          )}

          {!isLoading && error && (
            <div className="flex items-start gap-2 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg p-4">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
              <p>{error}</p>
            </div>
          )}

          {!isLoading && !error && context && (
            <>
              {context.scenes.length === 0 && <EmptyState context={context} />}
              {context.scenes.length > 0 && context.message && (
                <p className="text-[11px] text-amber-300/80">{context.message}</p>
              )}
              {context.scenes.map((scene, i) => (
                <SceneBlock key={`${scene.scene_number}-${i}`} scene={scene} />
              ))}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

interface ButtonProps {
  productionId: string;
  targetType: TagTargetType;
  targetId: string;
  /** Shown beside the icon. Omit for an icon-only button in tight rows. */
  label?: string;
  className?: string;
}

/**
 * The affordance that opens the script, for use anywhere a scene or a shot is
 * shown. It carries its own open state so a row only has to name its target.
 */
export function ScriptSceneButton({
  productionId,
  targetType,
  targetId,
  label = 'Script',
  className = '',
}: ButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const close = useCallback(() => setIsOpen(false), []);

  return (
    <>
      <button
        onClick={e => { e.stopPropagation(); setIsOpen(true); }}
        title={`Read scene ${targetId} in the script`}
        className={`flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-200 hover:bg-white/5 rounded-md px-1 -mx-1 py-0.5 transition shrink-0 ${className}`}
      >
        <BookOpen className="w-3 h-3 shrink-0" aria-hidden />
        {label && <span>{label}</span>}
      </button>
      {isOpen && (
        <ScriptContextPanel
          productionId={productionId}
          targetType={targetType}
          targetId={targetId}
          onClose={close}
        />
      )}
    </>
  );
}
