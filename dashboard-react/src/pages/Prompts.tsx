import { useEffect, useState } from 'react';
import { RefreshCw, ExternalLink, AlertCircle, Check, Eye, Code } from 'lucide-react';
import { adminFetch } from '../api';
import KpiCard from '../components/KpiCard';
import Badge from '../components/Badge';
import Modal from '../components/Modal';
import { CardSkeleton } from '../components/Skeleton';

interface Prompt {
  name: string;
  type: string;
  used_by: string;
  cached: boolean;
  status: string;
  active: boolean;
  description: string;
  char_count: number;
  preview: string;
  in_langsmith: boolean;
}

interface PromptsResponse {
  prompts: Prompt[];
  endpoint: string;
  enabled: boolean;
}

export default function Prompts() {
  const [data, setData] = useState<PromptsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState('');
  const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null);

  function fetchPrompts() {
    setLoading(true);
    setError('');
    adminFetch<PromptsResponse>('GET', '/api/admin/prompts')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchPrompts();
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    setMessage('');
    try {
      const res = await adminFetch<{ status: string; message: string }>(
        'POST',
        '/api/admin/prompts/refresh'
      );
      setMessage(res.message || 'Cache refreshed successfully');
      fetchPrompts();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Refresh failed');
    } finally {
      setRefreshing(false);
    }
  }

  const cachedCount = data?.prompts?.filter((p) => p.cached).length ?? 0;
  const activeCount = data?.prompts?.filter((p) => p.active).length ?? 0;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <div className="grid grid-cols-1 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 p-5 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-2/3" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load: {error}
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-gray-900">LangSmith Prompts</h1>
        <div className="flex gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 disabled:opacity-50 transition-all"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Cache'}
          </button>
          <a
            href={data?.endpoint || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm font-medium hover:bg-emerald-600 transition-all"
          >
            <ExternalLink size={14} />
            Open LangSmith
          </a>
        </div>
      </div>

      {message && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-sm text-indigo-700 flex items-center gap-2 animate-fade-in">
          {message.toLowerCase().includes('fail') ? <AlertCircle size={16} /> : <Check size={16} />}
          {message}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard label="Total Prompts" value={data?.prompts?.length ?? 0} color="blue" index={0} />
        <KpiCard label="Active" value={activeCount} color="green" index={1} />
        <KpiCard
          label="Cached"
          value={`${cachedCount} / ${data?.prompts?.length ?? 0}`}
          color="purple"
          index={2}
        />
        <KpiCard
          label="LangSmith"
          value={data?.enabled ? 'Connected' : 'Disconnected'}
          color={data?.enabled ? 'green' : 'red'}
          index={3}
        />
      </div>

      {/* Prompt Cards */}
      <div className="space-y-3">
        {(data?.prompts ?? []).map((prompt, i) => (
          <div
            key={prompt.name}
            className={`bg-white rounded-xl shadow-sm border border-gray-100 p-5 animate-card-pop transition-all hover:shadow-md ${
              !prompt.active ? 'opacity-60' : ''
            }`}
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-mono text-sm font-semibold text-gray-900">{prompt.name}</span>
                  <Badge color={prompt.type === 'mustache' ? 'purple' : 'blue'}>{prompt.type}</Badge>
                  <Badge color={prompt.active ? 'green' : 'gray'}>{prompt.active ? 'active' : 'legacy'}</Badge>
                  <Badge color={prompt.cached ? 'green' : 'yellow'}>{prompt.cached ? 'cached' : 'not cached'}</Badge>
                  {prompt.in_langsmith && <Badge color="blue">in LangSmith</Badge>}
                  {prompt.char_count > 0 && (
                    <span className="text-xs text-gray-400">{prompt.char_count.toLocaleString()} chars</span>
                  )}
                </div>
                <p className="text-sm text-gray-500 mb-1">{prompt.description}</p>
                <p className="text-xs text-gray-400">Used by: {prompt.used_by}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                {prompt.cached && prompt.preview && (
                  <button
                    onClick={() => setSelectedPrompt(prompt)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-all"
                  >
                    <Eye size={14} />
                    Preview
                  </button>
                )}
                <a
                  href={`${data?.endpoint || '#'}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-all"
                >
                  <Code size={14} />
                  Edit
                </a>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Prompt Preview Modal */}
      <Modal
        open={!!selectedPrompt}
        onClose={() => setSelectedPrompt(null)}
        title={selectedPrompt?.name ?? ''}
      >
        {selectedPrompt && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge color={selectedPrompt.type === 'mustache' ? 'purple' : 'blue'}>{selectedPrompt.type}</Badge>
              <Badge color={selectedPrompt.active ? 'green' : 'gray'}>{selectedPrompt.active ? 'active' : 'legacy'}</Badge>
              <span className="text-xs text-gray-400">{selectedPrompt.char_count.toLocaleString()} characters</span>
            </div>
            <p className="text-sm text-gray-600">{selectedPrompt.description}</p>
            <div className="bg-gray-900 text-gray-100 rounded-lg p-4 text-xs font-mono leading-relaxed max-h-96 overflow-y-auto whitespace-pre-wrap break-words">
              {selectedPrompt.preview}
            </div>
            <p className="text-xs text-gray-400">
              This is a cached preview (first 500 chars). Edit the full prompt in LangSmith.
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
