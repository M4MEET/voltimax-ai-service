import { useEffect, useState } from 'react';
import { RefreshCw, ExternalLink, AlertCircle, Check } from 'lucide-react';
import { adminFetch } from '../api';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import Badge from '../components/Badge';
import { CardSkeleton, TableSkeleton } from '../components/Skeleton';

interface Prompt {
  name: string;
  type: string;
  used_by: string;
  cached: boolean;
  status: string;
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

  const cachedCount = data?.prompts.filter((p) => p.cached).length ?? 0;

  const columns: Column<Prompt>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (r) => <span className="font-semibold font-mono text-sm">{r.name}</span>,
    },
    {
      key: 'type',
      header: 'Type',
      render: (r) => (
        <Badge color={r.type === 'mustache' ? 'purple' : 'blue'}>{r.type}</Badge>
      ),
    },
    {
      key: 'used_by',
      header: 'Used By',
      render: (r) => <span className="text-gray-600">{r.used_by}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <Badge color={r.cached ? 'green' : 'blue'}>
          {r.cached ? 'cached' : 'available'}
        </Badge>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <TableSkeleton rows={7} />
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
      <h1 className="text-xl font-bold text-gray-900">LangSmith Prompts</h1>

      {message && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-sm text-indigo-700 flex items-center gap-2 animate-fade-in">
          {message.toLowerCase().includes('fail') ? <AlertCircle size={16} /> : <Check size={16} />}
          {message}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total Prompts" value={data?.prompts.length ?? 0} color="blue" index={0} />
        <KpiCard
          label="LangSmith Status"
          value={data?.enabled ? 'Enabled' : 'Disabled'}
          color={data?.enabled ? 'green' : 'red'}
          index={1}
        />
        <KpiCard
          label="Cache Status"
          value={`${cachedCount} / ${data?.prompts.length ?? 0}`}
          sub="prompts cached"
          color="purple"
          index={2}
        />
      </div>

      {/* Actions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center">
              <RefreshCw size={20} className="text-indigo-500" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Refresh Cache</h2>
              <p className="text-xs text-gray-400">Re-pull all prompts from LangSmith</p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 disabled:opacity-50 transition-all"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Cache'}
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
              <ExternalLink size={20} className="text-emerald-500" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Open LangSmith</h2>
              <p className="text-xs text-gray-400">View and edit prompts in LangSmith</p>
            </div>
          </div>
          <a
            href={data?.endpoint || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-500 text-white rounded-lg text-sm font-medium hover:bg-emerald-600 transition-all"
          >
            <ExternalLink size={16} />
            Open LangSmith
          </a>
        </div>
      </div>

      {/* Prompts table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-3">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Prompt Registry</h2>
        </div>
        <DataTable
          columns={columns}
          data={data?.prompts ?? []}
          keyExtractor={(r) => r.name}
          emptyMessage="No prompts configured"
        />
      </div>
    </div>
  );
}
