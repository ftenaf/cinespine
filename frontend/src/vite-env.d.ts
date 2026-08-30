/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** PostHog project key. Absent means analytics are off, which is the default. */
  readonly VITE_POSTHOG_KEY?: string;
  /**
   * A self-hosted PostHog. Required alongside the key so a stray key cannot
   * send this production's telemetry to a cloud endpoint.
   */
  readonly VITE_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
