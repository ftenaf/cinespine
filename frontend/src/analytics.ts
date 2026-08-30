import posthog from 'posthog-js';

/**
 * Product analytics, sent to a self-hosted PostHog.
 *
 * What is deliberately switched off, and why it matters more here than in most
 * apps: this interface renders unreleased footage, crew names, and a document
 * previewer showing facing pages that carry phone numbers and email addresses.
 *
 *   autocapture          off — it records the text of everything clicked
 *   session_recording    off — it records the screen, which is the footage
 *   capture_pageview     off — we emit our own view events, without URLs
 *   person_profiles      identified_only — no profile for an anonymous visitor
 *
 * Events carry ids and enumerations. Never a title, a note, a filename or a
 * search query: those are what somebody typed, and a filename carries the
 * production's name.
 *
 * Unconfigured is the normal state in development. Every call below is a no-op
 * until both the key and a self-hosted host are set, and the host is required
 * so a stray key cannot send this production's telemetry to a cloud endpoint.
 */

const KEY = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const HOST = import.meta.env.VITE_POSTHOG_HOST as string | undefined;

let started = false;

export function isConfigured(): boolean {
  return Boolean(KEY && HOST);
}

export function startAnalytics(): void {
  if (started || !isConfigured()) return;
  started = true;

  posthog.init(KEY!, {
    api_host: HOST!,
    autocapture: false,
    disable_session_recording: true,
    capture_pageview: false,
    capture_pageleave: false,
    person_profiles: 'identified_only',
    // The referrer and the full URL can carry a production id from a shared
    // link; neither tells us anything we do not send deliberately.
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

/** Property values that are safe to send: ids, counts, enumerations. */
type SafeValue = string | number | boolean | null | undefined;

export function track(event: string, properties: Record<string, SafeValue> = {}): void {
  if (!isConfigured()) return;
  posthog.capture(event, properties);
}

/**
 * Which surface someone is working in. Named, not a URL: the pillars and tabs
 * are the vocabulary of the app, and a URL would carry the production id.
 */
export function trackView(surface: string, detail: Record<string, SafeValue> = {}): void {
  track('surface_viewed', { surface, ...detail });
}
