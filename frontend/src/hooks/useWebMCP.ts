import { useEffect, useRef } from 'react';

/**
 * WebMCP: tools a browser agent can call on this page.
 *
 * The API is `document.modelContext` (W3C Web Machine Learning CG draft,
 * https://webmachinelearning.github.io/webmcp/). `registerTool` takes the
 * descriptor and an `AbortSignal`; there is no `unregisterTool`, a tool goes
 * away when its signal aborts. `window.webmcp` was never a thing, so the
 * earlier version of this hook registered nothing anywhere.
 *
 * Tools register once on mount and resolve their `execute` through a ref, so
 * an agent always runs the latest closure over React state without the hook
 * re-registering on every render.
 */

export interface WebMCPTool {
  name: string;
  description: string;
  /** JSON Schema for the tool's input object. */
  inputSchema: Record<string, unknown>;
  execute: (inputs: any) => unknown | Promise<unknown>;
  /** Hints for the agent; `destructiveHint: true` on anything that deletes. */
  annotations?: Record<string, unknown>;
}

export interface ModelContextLike {
  registerTool: (tool: WebMCPTool, options?: { signal?: AbortSignal }) => Promise<void> | void;
}

declare global {
  interface Document {
    modelContext?: ModelContextLike;
  }
}

/** Where the page's model context lives, or null in a browser without one. */
export function getModelContext(doc: Document | undefined = typeof document === 'undefined' ? undefined : document): ModelContextLike | null {
  return doc?.modelContext ?? null;
}

/**
 * Binds each tool's `execute` to the latest version in `ref` by name, so the
 * descriptor handed to the browser stays valid across re-renders. Exported
 * for tests; the hook is the only production caller.
 */
export function bindToLatest(tools: WebMCPTool[], ref: { current: WebMCPTool[] }): WebMCPTool[] {
  return tools.map(tool => ({
    ...tool,
    execute: async (inputs: unknown) => {
      const latest = ref.current.find(t => t.name === tool.name);
      if (!latest) {
        return { error: `Tool ${tool.name} is no longer available on this page.` };
      }
      return latest.execute(inputs);
    },
  }));
}

export function useWebMCP(tools: WebMCPTool[]) {
  const toolsRef = useRef(tools);
  toolsRef.current = tools;

  useEffect(() => {
    const context = getModelContext();
    if (!context) {
      console.debug('WebMCP: document.modelContext is absent; tools not registered.');
      return;
    }
    const controller = new AbortController();
    for (const tool of bindToLatest(toolsRef.current, toolsRef)) {
      Promise.resolve(context.registerTool(tool, { signal: controller.signal }))
        .catch(err => console.warn(`WebMCP: could not register ${tool.name}:`, err));
    }
    return () => controller.abort();
  }, []);
}
