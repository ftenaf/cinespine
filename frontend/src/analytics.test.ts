import { describe, it, expect } from 'vitest';
import {
  FORBIDDEN_PROPERTIES, INIT_OPTIONS, isSelfHosted, safeProperties,
} from './analytics';

/**
 * The three rules, as tests rather than comments.
 *
 * This interface renders unreleased footage and a document previewer showing
 * facing pages that carry crew phone numbers. What must never be sent matters
 * more than what is.
 */

describe('self-hosted only', () => {
  it('accepts a host on the deployer’s own domain', () => {
    expect(isSelfHosted('https://posthog.example.com')).toBe(true);
  });

  it('accepts localhost and a private address', () => {
    expect(isSelfHosted('http://localhost:8000')).toBe(true);
    expect(isSelfHosted('http://10.0.0.5:8000')).toBe(true);
  });

  it.each([
    'https://us.i.posthog.com',
    'https://eu.i.posthog.com',
    'https://app.posthog.com',
    'posthog.com',
    'https://POSTHOG.COM/ingest',
  ])('refuses PostHog’s own endpoint %s', host => {
    expect(isSelfHosted(host)).toBe(false);
  });

  it('matches the domain rather than a list of known endpoints', () => {
    // A region added tomorrow must be refused without anyone updating a list:
    // that is "the keyed list that rots".
    expect(isSelfHosted('https://ap-southeast-3.i.posthog.com')).toBe(false);
  });

  it('is not fooled by a lookalike domain', () => {
    expect(isSelfHosted('https://notposthog.com')).toBe(true);
    expect(isSelfHosted('https://posthog.com.example.org')).toBe(true);
  });

  it('treats a missing host as not configured', () => {
    expect(isSelfHosted(undefined)).toBe(false);
    expect(isSelfHosted('   ')).toBe(false);
  });
});

describe('nothing is captured, only emitted', () => {
  it('has autocapture off', () => {
    expect(INIT_OPTIONS.autocapture).toBe(false);
  });

  it('has session replay off', () => {
    // Session replay records the screen, and the screen is the footage.
    expect(INIT_OPTIONS.disable_session_recording).toBe(true);
  });

  it('does not send pageviews, which carry the production id in the URL', () => {
    expect(INIT_OPTIONS.capture_pageview).toBe(false);
    expect(INIT_OPTIONS.capture_pageleave).toBe(false);
  });

  it('cannot be switched on remotely', () => {
    // /decide is how PostHog turns capture on from the server. Refusing to
    // call it makes the flags above the only ones that apply.
    expect(INIT_OPTIONS.advanced_disable_decide).toBe(true);
  });
});

describe('ids and actions, never content', () => {
  it('sends ids, counts and enumerations', () => {
    expect(safeProperties({
      production_id: 'DEMO', shoot_day: '31', target_id: '27/7',
      priority: 'critical', handed_over: true, hours_owed: 4.5,
    })).toEqual({
      production_id: 'DEMO', shoot_day: '31', target_id: '27/7',
      priority: 'critical', handed_over: true, hours_owed: 4.5,
    });
  });

  it.each([...FORBIDDEN_PROPERTIES])('drops %s', field => {
    expect(safeProperties({ [field]: 'something real', slate: '27/7' })).toEqual({ slate: '27/7' });
  });

  it('does not depend on capitalisation', () => {
    expect(safeProperties({ Title: 'x', FILENAME: 'y', shoot_day: '31' })).toEqual({ shoot_day: '31' });
  });

  it('drops a long string even under a name the list did not anticipate', () => {
    expect(safeProperties({ summary: 'x'.repeat(200), slate: '27/7' })).toEqual({ slate: '27/7' });
  });

  it('drops an object rather than stringifying it', () => {
    // Stringifying a payload is how content leaks: it arrives as one long value.
    expect(safeProperties({ witnesses: [{ note: 'secret' }], slate: '27/7' })).toEqual({ slate: '27/7' });
  });

  it('leaves a missing value out rather than sending null', () => {
    expect(safeProperties({ assigned_to: null, other: undefined, slate: '27/7' })).toEqual({ slate: '27/7' });
  });

  it('filters at runtime, not only in the type system', () => {
    // The call sites are spread across the app and a value can arrive as any.
    const fromSomewhereElse = { note: 'typed by a person' } as Record<string, unknown>;
    expect(safeProperties(fromSomewhereElse)).toEqual({});
  });
});
