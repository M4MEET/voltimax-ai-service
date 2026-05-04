import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getApiKey } from './api';
import { PeriodProvider } from './hooks/usePeriod';
import Layout from './components/Layout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import Topics from './pages/Topics';
import Conversations from './pages/Conversations';
import Feedback from './pages/Feedback';
import Costs from './pages/Costs';
import Escalations from './pages/Escalations';
import Performance from './pages/Performance';
import Logs from './pages/Logs';
import LlmConfig from './pages/LlmConfig';
import AgentsConfig from './pages/AgentsConfig';
import Knowledge from './pages/Knowledge';
import Prompts from './pages/Prompts';
import Tickets from './pages/Tickets';
import MetricDetail from './pages/MetricDetail';

export default function App() {
  const [authed, setAuthed] = useState(() => !!getApiKey());

  const handleLogin = useCallback(() => {
    setAuthed(true);
  }, []);

  if (!authed) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <PeriodProvider>
      <BrowserRouter basename="/dashboard">
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="topics" element={<Topics />} />
            <Route path="conversations" element={<Conversations />} />
            <Route path="feedback" element={<Feedback />} />
            <Route path="costs" element={<Costs />} />
            <Route path="escalations" element={<Escalations />} />
            <Route path="performance" element={<Performance />} />
            <Route path="logs" element={<Logs />} />
            <Route path="config/llm" element={<LlmConfig />} />
            <Route path="config/agents" element={<AgentsConfig />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="prompts" element={<Prompts />} />
            <Route path="tickets" element={<Tickets />} />
            <Route path="analytics/:metric" element={<MetricDetail />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </PeriodProvider>
  );
}
