import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import { installTauriBridge } from './tauri-bridge';

if (import.meta.env.BIODSH_TAURI || '__TAURI_INTERNALS__' in window) installTauriBridge();

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
