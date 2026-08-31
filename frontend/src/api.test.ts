import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchProductionCrew,
  runAssistantEditorQueue,
  runWrapRescueAgent,
  upsertProductionCrewMember,
} from './api';

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

describe('assistant editorial API', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads production crew with encoded production ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal('fetch', fetchMock);

    await fetchProductionCrew('Night Watch', true);

    expect(fetchMock).toHaveBeenCalledWith('/api/productions/Night%20Watch/crew?active_only=true');
  });

  it('saves a crew member to the production roster', async () => {
    const member = {
      production_id: 'DEMO_PRODUCTION',
      handle: '@night_ae',
      name: 'Night AE',
      email: '',
      role: 'Assistant Editor',
      department: 'editorial',
      active: true,
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => member,
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await upsertProductionCrewMember('DEMO_PRODUCTION', {
      handle: '@night_ae',
      name: 'Night AE',
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/productions/DEMO_PRODUCTION/crew', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        handle: '@night_ae',
        name: 'Night AE',
      }),
    });
    expect(result.handle).toBe('@night_ae');
  });

  it('posts the logged editor to the assistant queue endpoint', async () => {
    const response = {
      production_id: 'DEMO_PRODUCTION',
      shoot_day: '31',
      actor: '@night_ae',
      assigned_to: '@night_ae',
      production_status: 'In Production',
      scenes: [],
      requirement_actions: [],
      summary: 'No clean scenes.',
      generated_at: new Date(0).toISOString(),
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => response,
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await runAssistantEditorQueue({
      production_id: 'DEMO_PRODUCTION',
      shoot_day: '31',
      actor: '@night_ae',
      assignee: '@night_ae',
      max_scenes: 6,
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/agents/assistant-editor-queue/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        production_id: 'DEMO_PRODUCTION',
        shoot_day: '31',
        actor: '@night_ae',
        assignee: '@night_ae',
        max_scenes: 6,
      }),
    });
    expect(result.assigned_to).toBe('@night_ae');
  });
});
