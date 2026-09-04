import React from 'react'
import ReactDOM from 'react-dom/client'
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';
import App from './App.tsx'
import './index.css'

const faroUrl = import.meta.env.VITE_GRAFANA_FARO_URL;

if (faroUrl) {
  initializeFaro({
    url: faroUrl,
    app: {
      name: 'cinespine-frontend',
      version: '0.1.0',
      environment: import.meta.env.MODE
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

