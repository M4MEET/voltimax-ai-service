import React, { useState, useCallback, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getApiKey } from './api';
import { PeriodProvider } from './hooks/usePeriod';
import Layout from './components/Layout';
import Login from './pages/Login';
import { CardSkeleton, ChartSkeleton } from './components/Skeleton';

const Overview = React.lazy(() => import('./pages/Overview'));
const Topics = React.lazy(() => import('./pages/Topics'));
const Conversations = React.lazy(() => import('./pages/Conversations'));
const Feedback = React.lazy(() => import('./pages/Feedback'));
const Costs = React.lazy(() => import('./pages/Costs'));
const Escalations = React.lazy(() => import('./pages/Escalations'));
const Performance = React.lazy(() => import('./pages/Performance'));
const Logs = React.lazy(() => import('./pages/Logs'));
const LlmConfig = React.lazy(() => import('./pages/LlmConfig'));
const AgentsConfig = React.lazy(() => import('./pages/AgentsConfig'));
const Knowledge = React.lazy(() => import('./pages/Knowledge'));
const Prompts = React.lazy(() => import('./pages/Prompts'));
const Tickets = React.lazy(() => import('./pages/Tickets'));
const MetricDetail = React.lazy(() => import('./pages/MetricDetail'));

function LoadingSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
      <ChartSkeleton />
    </div>
  );
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 max-w-md w-full text-center">
            <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
              <span className="text-red-500 text-xl">!</span>
            </div>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Something went wrong</h2>
            <p className="text-sm text-gray-500 mb-4">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 transition-all"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!getApiKey());

  const handleLogin = useCallback(() => {
    setAuthed(true);
  }, []);

  if (!authed) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <ErrorBoundary>
      <PeriodProvider>
        <BrowserRouter basename="/dashboard">
          <Suspense fallback={<LoadingSkeleton />}>
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
          </Suspense>
        </BrowserRouter>
      </PeriodProvider>
    </ErrorBoundary>
  );
}
