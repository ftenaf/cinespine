/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** PostHog project key. Absent means analytics are off, which is the default. */
  readonly VITE_POSTHOG_KEY?: string;
  /**
   * A self-hosted PostHog. Required alongside the key so a stray key cannot
   * send this production's telemetry to a cloud endpoint.
   */
  readonly VITE_POSTHOG_HOST?: string;
  /** Grafana Faro collector. Absent means no frontend telemetry. Build-time only. */
  readonly VITE_GRAFANA_FARO_URL?: string;
  /** The git sha the image was built from; Faro app.version. */
  readonly VITE_APP_VERSION?: string;
  /**
   * The same word as the backend's deployment.environment: "cloudrun" in the
   * Cloud Run image, "local" otherwise. Not Vite's MODE, which says
   * "production" for any optimised build wherever it runs.
   */
  readonly VITE_APP_ENVIRONMENT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
