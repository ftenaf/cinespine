import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchCharacterLines } from '../api';
import type { CharacterLines } from '../types';

/**
 * A character's lines, in script order, walkable one at a time.
 *
 * This is the other half of the personality polygon. A profile that says
 * "guarded, evasive" is unverifiable on its own — the director would have to
 * page through the whole screenplay to check it. Here the evidence is the
 * thing you navigate.
 *
 * Grouped by scene rather than run together, because a line means something
 * different in a nave at dawn than in a car at night, and the heading is the
 * cheapest way to carry that.
 */
export function CharacterLinesPanel({
  scriptId,
  characterName,
  onGoToScene,
}: {
  scriptId: string;
  characterName: string;
  /** Optional: lets the rest of the app follow along when a line is selected. */
  onGoToScene?: (sceneNumber: string) => void;
}) {
  const [data, setData] = useState<CharacterLines | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!scriptId || !characterName) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchCharacterLines(scriptId, characterName)
      .then(res => {
        if (cancelled) return;
        setData(res);
        setCursor(0);
      })
      .catch(e => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [scriptId, characterName]);

  const grouped = useMemo(() => {
    if (!data) return [];
    const out: { scene: string; heading: string; from: number; lines: typeof data.lines }[] = [];
    data.lines.forEach((line, i) => {
      const last = out[out.length - 1];
      if (last && last.scene === line.scene_number) last.lines.push(line);
      else out.push({ scene: line.scene_number, heading: line.heading, from: i, lines: [line] });
    });
    return out;
  }, [data]);

  // Keep the selected line in view when stepping with the buttons.
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-line="${cursor}"]`);
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [cursor]);

  const step = (delta: number) => {
    if (!data || data.lines.length === 0) return;
    const next = Math.min(Math.max(cursor + delta, 0), data.lines.length - 1);
    setCursor(next);
    onGoToScene?.(data.lines[next].scene_number);
  };

  if (loading) {
    return <div className="text-xs text-gray-500 p-4">Reading the script…</div>;
  }
  if (error) {
    return <div className="text-xs text-rose-300 p-4">{error}</div>;
  }
  if (!data) return null;

  // Three different facts, kept apart. An empty list could mean any of them,
  // and telling a director "no lines" about a character the script does not
  // contain would send them looking for the wrong thing.
  if (!data.known_character) {
    return (
      <div className="text-xs text-gray-400 p-4 rounded-lg border border-slate-800 bg-slate-900/60">
        <span className="text-gray-200">{characterName}</span> is not a character in this script.
      </div>
    );
  }
  if (data.line_count === 0) {
    return (
      <div className="text-xs text-gray-400 p-4 rounded-lg border border-slate-800 bg-slate-900/60">
        <span className="text-gray-200">{characterName}</span> appears in this script and never
        speaks. That is a fact about the part, not a gap in the reading
        {!data.has_profile && (
          <> — and it is why there is no profile: those are built from dialogue</>
        )}
        .
      </div>
    );
  }

  const current = data.lines[cursor];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
        <div className="text-xs font-semibold text-gray-300">
          {data.line_count} {data.line_count === 1 ? 'line' : 'lines'}
          <span className="text-gray-500 font-normal">
            {' '}across {data.scenes_present.length}{' '}
            {data.scenes_present.length === 1 ? 'scene' : 'scenes'}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500 tabular-nums">
            {cursor + 1}/{data.line_count}
          </span>
          <button
            onClick={() => step(-1)}
            disabled={cursor === 0}
            className="px-2 py-1 text-xs rounded bg-slate-800 text-gray-300 disabled:opacity-30 hover:bg-slate-700"
            aria-label="Previous line"
          >
            ↑
          </button>
          <button
            onClick={() => step(1)}
            disabled={cursor >= data.line_count - 1}
            className="px-2 py-1 text-xs rounded bg-slate-800 text-gray-300 disabled:opacity-30 hover:bg-slate-700"
            aria-label="Next line"
          >
            ↓
          </button>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-slate-800 bg-slate-950/40">
        <div className="text-[10px] uppercase tracking-wide text-spine-accent mb-1">
          Scene {current.scene_number} · {current.heading}
        </div>
        {current.parenthetical && (
          <div className="text-[11px] italic text-gray-500">({current.parenthetical})</div>
        )}
        <div className="text-sm text-gray-100 leading-relaxed">{current.line}</div>
      </div>

      <div ref={listRef} className="max-h-72 overflow-y-auto">
        {grouped.map(group => (
          <div key={`${group.scene}-${group.from}`}>
            <div className="sticky top-0 px-4 py-1.5 bg-slate-900 border-b border-slate-800 text-[10px] uppercase tracking-wide text-gray-500">
              Scene {group.scene} · {group.heading}
            </div>
            {group.lines.map((line, i) => {
              const index = group.from + i;
              return (
                <button
                  key={index}
                  data-line={index}
                  onClick={() => {
                    setCursor(index);
                    onGoToScene?.(line.scene_number);
                  }}
                  className={`block w-full text-left px-4 py-2 text-xs border-b border-slate-800/60 hover:bg-slate-800/50 ${
                    index === cursor ? 'bg-slate-800/70 text-gray-100' : 'text-gray-400'
                  }`}
                >
                  {line.parenthetical && (
                    <span className="italic text-gray-500">({line.parenthetical}) </span>
                  )}
                  {line.line}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
