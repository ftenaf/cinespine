import React from 'react'
import ReactDOM from 'react-dom/client'
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';
import App from './App.tsx'
import './index.css'

// Array.prototype.at is what web-vitals (bundled by Faro) calls on every
// layout-shift entry. One visitor's engine lacked it, so Faro's own vitals
// reporting threw four bursts of TypeErrors into Loki. Imports are hoisted,
// but Faro runs at initializeFaro below, so this lands in time.
if (!(Array.prototype as { at?: unknown }).at) {
  Object.defineProperty(Array.prototype, 'at', {
    value: function at(this: unknown[], index: number) {
      const i = Math.trunc(index) || 0;
      const k = i < 0 ? this.length + i : i;
      return k < 0 || k >= this.length ? undefined : this[k];
    },
    writable: true,
    configurable: true,
  });
}

const faroUrl = import.meta.env.VITE_GRAFANA_FARO_URL;

if (faroUrl) {
  initializeFaro({
    url: faroUrl,
    app: {
      name: 'cinespine-frontend',
      version: import.meta.env.VITE_APP_VERSION || 'dev',
      // The same word the backend puts in deployment.environment ("cloudrun"
      // on Cloud Run, "local" elsewhere), so one label selects both halves of
      // a request in Grafana. Vite's MODE said "production" for any optimised
      // build, including one running on a laptop.
      environment: import.meta.env.VITE_APP_ENVIRONMENT || 'local',
    },
    instrumentations: [
      ...getWebInstrumentations(),
      // Every fetch to /api carries a traceparent header, so the backend's
      // spans (cinespine.ingest, cinespine.reconcile, the agents) hang under
      // the browser's. Same origin in both the Vite proxy and the Cloud Run
      // build, so no CORS allow-list is needed for propagation.
      new TracingInstrumentation(),
    ],
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

