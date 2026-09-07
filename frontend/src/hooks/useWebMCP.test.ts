import { describe, it, expect, vi } from 'vitest';
import { bindToLatest, getModelContext, WebMCPTool } from './useWebMCP';

function tool(name: string, execute: WebMCPTool['execute']): WebMCPTool {
  return { name, description: name, inputSchema: { type: 'object', properties: {} }, execute };
}

describe('getModelContext', () => {
  it('reads document.modelContext, the spec surface, not window.webmcp', () => {
    const registerTool = vi.fn();
    expect(getModelContext({ modelContext: { registerTool } } as any)).toEqual({ registerTool });
    expect(getModelContext({} as any)).toBeNull();
    expect(getModelContext(undefined)).toBeNull();
  });
});

describe('bindToLatest', () => {
  it('runs the newest execute for a name, not the one registered', async () => {
    const ref = { current: [tool('t', () => 'old')] };
    const bound = bindToLatest(ref.current, ref);
    ref.current = [tool('t', () => 'new')];
    expect(await bound[0].execute({})).toBe('new');
  });

  it('answers with an error object when the tool has left the page', async () => {
    const ref = { current: [tool('t', () => 'x')] };
    const bound = bindToLatest(ref.current, ref);
    ref.current = [];
    expect(await bound[0].execute({})).toEqual({ error: 'Tool t is no longer available on this page.' });
  });

  it('keeps the descriptor fields the browser reads', () => {
    const ref = { current: [{ ...tool('t', () => 1), annotations: { destructiveHint: true } }] };
    const [bound] = bindToLatest(ref.current, ref);
    expect(bound.name).toBe('t');
    expect(bound.inputSchema).toEqual({ type: 'object', properties: {} });
    expect(bound.annotations).toEqual({ destructiveHint: true });
  });
});
