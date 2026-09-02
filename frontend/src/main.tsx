import React from 'react'
import ReactDOM from 'react-dom/client'
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
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
    ],
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

