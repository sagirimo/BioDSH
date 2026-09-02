import { useEffect } from 'react';
import { AppProvider, useApp } from './store';
import Sidebar from './components/Sidebar';
import ChatView from './views/ChatView';
import StoreView from './views/StoreView';
import DataView from './views/DataView';
import DatabaseView from './views/DatabaseView';
import EnvView from './views/EnvView';
import SettingsView from './views/SettingsView';
import Onboarding from './views/Onboarding';
import AskPopover from './components/AskPopover';
import AutoUpdate from './components/AutoUpdate';
import StarPrompt from './components/StarPrompt';
import { LangContext, resolveLang } from './i18n';

function useTheme() {
  const { settings, info } = useApp();
  useEffect(() => {
    const apply = (dark: boolean) => document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const sys = () => apply(mq.matches);
    if (!settings || settings.theme === 'system') { sys(); mq.addEventListener('change', sys); return () => mq.removeEventListener('change', sys); }
    apply(settings.theme === 'dark');
  }, [settings?.theme, info?.dark]);
}

function Shell() {
  useTheme();
  const { ready, settings, tab } = useApp();
  if (!ready || !settings) return <div className="h-full w-full drag" />;
  return (
    <LangContext.Provider value={resolveLang(settings.language)}>
    <div className="h-full w-full flex">
      <Sidebar />
      <main className="flex-1 min-w-0 h-full relative">
        {tab === 'chat' && <ChatView />}
        {tab === 'data' && <DataView />}
        {tab === 'db' && <DatabaseView />}
        {tab === 'store' && <StoreView />}
        {tab === 'env' && <EnvView />}
        {tab === 'settings' && <SettingsView />}
      </main>
      {!settings.onboarded && <Onboarding />}
      <AskPopover />
      <AutoUpdate />
      <StarPrompt />
    </div>
    </LangContext.Provider>
  );
}

export default function App() {
  return <AppProvider><Shell /></AppProvider>;
}
