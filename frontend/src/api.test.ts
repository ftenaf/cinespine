import { afterEach, describe, expect, it, vi } from 'vitest';
import { runWrapRescueAgent } from './api';

describe('runWrapRescueAgent', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts the production, day and actor to the Wrap Rescue endpoint', async () => {
    const response = {
      production_id: 'DEMO_PRODUCTION',
      shoot_day: '31',
      actor: '@editor',
      mcp_status: {
        configured: true,
        available: true,
        transport: 'http',
        package_installed: true,
      },
      gemini_status: {
        configured: false,
        genai_available: false,
        adk_available: false,
        model: 'deterministic fallback',
        provider: 'Google GenAI SDK',
      },
      steps: [],
      tool_calls: [],
      blockers: [],
      requirement_actions: [],
      final_memo: 'Wrap Rescue handoff',
      generated_at: new Date(0).toISOString(),
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => response,
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await runWrapRescueAgent({
      production_id: 'DEMO_PRODUCTION',
      shoot_day: '31',
      actor: '@editor',
      max_blockers: 5,
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/agents/wrap-rescue/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        production_id: 'DEMO_PRODUCTION',
        shoot_day: '31',
        actor: '@editor',
        max_blockers: 5,
      }),
    });
    expect(result.final_memo).toBe('Wrap Rescue handoff');
  });
});
