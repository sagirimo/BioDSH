import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import '@fontsource/source-serif-4/600.css';
import '@fontsource/noto-serif-sc/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './styles.css';
import './shell.css';
import './assets/biodsh-ui/tokens.css';
import { installTauriBridge } from './tauri-bridge';

if (import.meta.env.BIODSH_TAURI || '__TAURI_INTERNALS__' in window) installTauriBridge();

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
