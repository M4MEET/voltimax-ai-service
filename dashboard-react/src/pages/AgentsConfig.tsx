import { useEffect, useState } from 'react';
import { Search, AlertCircle, ChevronDown, ChevronUp, Send, FlaskConical } from 'lucide-react';
import { adminFetch } from '../api';
import { CardSkeleton } from '../components/Skeleton';
import clsx from 'clsx';

interface Agent {
  id: string;
  name: string;
  system_prefix: string;
  tier: number;
  greeting_hint: string;
}

interface TestResult {
  agent_id: string;
  response: string;
}

const TIER_CONFIG: Record<number, { label: string; color: string; border: string; bg: string }> = {
  0: { label: 'Open', color: 'text-emerald-700', border: 'border-l-emerald-500', bg: 'bg-emerald-50' },
  1: { label: 'Verified', color: 'text-blue-700', border: 'border-l-blue-500', bg: 'bg-blue-50' },
  2: { label: 'Order Required', color: 'text-amber-700', border: 'border-l-amber-500', bg: 'bg-amber-50' },
};

function TierBadge({ tier }: { tier: number }) {
  const cfg = TIER_CONFIG[tier] ?? TIER_CONFIG[0];
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold', cfg.bg, cfg.color)}>
      Tier {tier} &middot; {cfg.label}
    </span>
  );
}

function AgentCard({ agent, index }: { agent: Agent; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testInput, setTestInput] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testError, setTestError] = useState('');
  const [displayedText, setDisplayedText] = useState('');

  const tierCfg = TIER_CONFIG[agent.tier] ?? TIER_CONFIG[0];

  // Typing animation for test response
  useEffect(() => {
    if (!testResult) {
      setDisplayedText('');
      return;
    }
    let i = 0;
    setDisplayedText('');
    const interval = setInterval(() => {
      i++;
      setDisplayedText(testResult.slice(0, i));
      if (i >= testResult.length) clearInterval(interval);
    }, 12);
    return () => clearInterval(interval);
  }, [testResult]);

  async function handleTest() {
    if (!testInput.trim()) return;
    setTestLoading(true);
    setTestError('');
    setTestResult(null);
    try {
      const res = await adminFetch<TestResult>('POST', '/api/admin/test-agent', {
        agent_id: agent.id,
        message: testInput.trim(),
      });
      setTestResult(res.response);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTestLoading(false);
    }
  }

  return (
    <div
      className={clsx(
        'bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 animate-card-pop',
        tierCfg.border,
        `stagger-${Math.min(index + 1, 6)}`
      )}
    >
      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-gray-900 truncate">{agent.name}</h3>
            <span className="inline-block mt-1 px-2 py-0.5 rounded bg-gray-100 text-[11px] font-mono text-gray-500">
              {agent.id}
            </span>
          </div>
          <TierBadge tier={agent.tier} />
        </div>

        {/* System prefix */}
        <div className="mb-3">
          <p
            className={clsx(
              'text-sm text-gray-600 leading-relaxed transition-all duration-300',
              !expanded && 'line-clamp-2'
            )}
          >
            {agent.system_prefix}
          </p>
          {agent.system_prefix.length > 120 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 mt-1 text-xs text-indigo-500 hover:text-indigo-700 font-medium transition-colors"
            >
              {expanded ? (
                <>
                  <ChevronUp size={14} />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown size={14} />
                  Show more
                </>
              )}
            </button>
          )}
        </div>

        {/* Greeting hint */}
        {agent.greeting_hint && (
          <p className="text-xs italic text-gray-400 mb-3">{agent.greeting_hint}</p>
        )}

        {/* Test button */}
        <button
          onClick={() => {
            setTestOpen(!testOpen);
            if (testOpen) {
              setTestResult(null);
              setTestError('');
              setTestInput('');
            }
          }}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
            testOpen
              ? 'bg-indigo-100 text-indigo-700'
              : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
          )}
        >
          <FlaskConical size={14} />
          Test
        </button>
      </div>

      {/* Test area */}
      {testOpen && (
        <div className="border-t border-gray-100 p-5 bg-gray-50/50 rounded-b-xl animate-fade-in">
          <div className="flex gap-2">
            <input
              type="text"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleTest()}
              placeholder="Type a test message..."
              className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all bg-white"
            />
            <button
              onClick={handleTest}
              disabled={testLoading || !testInput.trim()}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
            >
              {testLoading ? (
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
              ) : (
                <Send size={14} />
              )}
              Send
            </button>
          </div>

          {testError && (
            <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-center gap-2">
              <AlertCircle size={14} />
              {testError}
            </div>
          )}

          {displayedText && (
            <div className="mt-3 bg-white border border-gray-200 rounded-lg p-3 text-sm text-gray-700 leading-relaxed">
              {displayedText}
              {displayedText.length < (testResult?.length ?? 0) && (
                <span className="inline-block w-1.5 h-4 bg-indigo-500 animate-pulse ml-0.5 align-text-bottom rounded-sm" />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentsConfig() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    adminFetch<Agent[]>('GET', '/api/admin/agents')
      .then(setAgents)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = agents?.filter((a) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return a.name.toLowerCase().includes(q) || a.id.toLowerCase().includes(q);
  });

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 skeleton rounded" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">AI Agents</h1>
        <p className="text-sm text-gray-500 mt-1">19 specialized agents auto-selected by intent</p>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter agents by name or ID..."
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* Agent cards grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {filtered?.map((agent, idx) => (
          <AgentCard key={agent.id} agent={agent} index={idx} />
        ))}
      </div>

      {filtered?.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <p>No agents match your search.</p>
        </div>
      )}
    </div>
  );
}
