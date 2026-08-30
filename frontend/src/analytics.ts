import posthog from 'posthog-js';

/**
 * Product analytics, sent to PostHog — self-hosted or their cloud.
 *
 * `VITE_POSTHOG_HOST` says which, and it is required rather than defaulted, so
 * the destination is always something somebody wrote down.
 *
 * Two rules, enforced here rather than assumed, and they hold for either
 * destination:
 *
 *   1. Nothing is captured, only emitted. Autocapture records the text of
 *      everything clicked; session replay records the screen. This interface
 *      renders unreleased footage and a previewer showing facing pages that
 *      carry crew phone numbers, so the screen is the material itself.
 *   2. Ids and actions. Properties are filtered at runtime, not just typed:
 *      a type stops nothing once a value is `any`, and the call sites are
 *      spread across the app.
 *
 * What leaves is the shape of the work — which production, which day, which
 * surface, and a role token for who. Not what any of it says.
 *
 * Unconfigured is the normal state in development, and every call below is
 * then a no-op.
 */

const KEY = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const HOST = import.meta.env.VITE_POSTHOG_HOST as string | undefined;

/**
 * Property names that carry what somebody typed, or what a document is called.
 * Stripped centrally so a new call site cannot add one by accident.
 */
export const FORBIDDEN_PROPERTIES = new Set([
  'title', 'description', 'note', 'resolution_note', 'comment',
  'filename', 'file_name', 'content', 'raw_content', 'message',
  'name', 'email', 'phone', 'target_label', 'prompt', 'body',
  'search', 'query', 'url', 'href', 'text',
]);

/** Ids and enumerations are short. Anything longer is prose. */
export const MAX_VALUE_LENGTH = 64;

export type SafeValue = string | number | boolean | null | undefined;

/**
 * The properties that may be sent.
 *
 * Mirrors the backend's filter deliberately: the two ends emit different
 * events and one central rule in each is what keeps them agreeing.
 */
export function safeProperties(properties: Record<string, unknown>): Record<string, SafeValue> {
  const clean: Record<string, SafeValue> = {};
  for (const [key, value] of Object.entries(properties ?? {})) {
    if (FORBIDDEN_PROPERTIES.has(key.toLowerCase())) continue;
    if (value === null || value === undefined) continue;
    if (typeof value === 'string') {
      if (value.length > MAX_VALUE_LENGTH) continue;
      clean[key] = value;
    } else if (typeof value === 'number' || typeof value === 'boolean') {
      clean[key] = value;
    }
    // Anything else — objects, arrays — is dropped rather than stringified.
    // Stringifying a payload is how content leaks: it arrives as one long value.
  }
  return clean;
}

/**
 * How PostHog is initialised. Exported so a test can assert the flags rather
 * than trusting that nobody flips one later.
 */
export const INIT_OPTIONS = {
  autocapture: false,
  disable_session_recording: true,
  capture_pageview: false,
  capture_pageleave: false,
  capture_performance: false,
  disable_surveys: true,
  person_profiles: 'identified_only',
  // No remote configuration. /decide is how PostHog can switch capture on from
  // the server; refusing to call it means the settings above are the only ones
  // that apply. It costs feature flags, which this app does not use.
  advanced_disable_decide: true,
} as const;

let started = false;

export function isConfigured(): boolean {
  return Boolean(KEY && HOST);
}

export function startAnalytics(): void {
  if (started) return;
  if (!isConfigured()) return;
  started = true;

  posthog.init(KEY!, {
    api_host: HOST!,
    ...INIT_OPTIONS,
    // The URL, referrer and pathname carry the production id from a shared
    // link, and tell us nothing we do not send deliberately.
    sanitize_properties: props => {
      const clean = { ...props };
      delete clean.$current_url;
      delete clean.$referrer;
      delete clean.$referring_domain;
      delete clean.$pathname;
      return clean;
    },
  });
}

/**
 * Who is acting. A role token like `@sound_supervisor`, which is what this
 * project uses in place of a crew member's name.
 */
export function identify(handle: string): void {
  if (!isConfigured() || !handle) return;
  posthog.identify(handle);
}

export function track(event: string, properties: Record<string, unknown> = {}): void {
  if (!isConfigured()) return;
  posthog.capture(event, safeProperties(properties));
}

/**
 * Which surface someone is working in. Named, not a URL: the pillars and tabs
 * are the vocabulary of the app, and a URL would carry the production id.
 */
export function trackView(surface: string, detail: Record<string, unknown> = {}): void {
  track('surface_viewed', { surface, ...detail });
}
