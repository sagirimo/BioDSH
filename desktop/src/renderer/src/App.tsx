import { useEffect } from 'react';
import { AppProvider, useApp } from './store';
import Sidebar from './components/Sidebar';
import { Rail } from './components/Chrome';
import ChatView from './views/ChatView';
import SkillsView from './views/SkillsView';
import PipelinesView from './views/PipelinesView';
import DatabaseView from './views/DatabaseView';
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
    <div className="h-full w-full flex" style={{ background: 'var(--bg)' }}>
      <Rail />
      {tab === 'chat' && <Sidebar />}
      <main className="flex-1 min-w-0 h-full relative">
        {tab === 'chat' && <ChatView />}
        {tab === 'skills' && <SkillsView />}
        {tab === 'pipes' && <PipelinesView />}
        {tab === 'db' && <DatabaseView />}
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
