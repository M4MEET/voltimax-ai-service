import { useEffect, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { PerformanceData } from '../types';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { CardSkeleton, ChartSkeleton, TableSkeleton } from '../components/Skeleton';

export default function Performance() {
  const { days } = usePeriod();
  const [data, setData] = useState<PerformanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<PerformanceData>(`/api/analytics/performance?days=${days}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [days]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load data: {error}
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <ChartSkeleton />
        <TableSkeleton />
      </div>
    );
  }

  const columns: Column<(typeof data.by_provider)[number]>[] = [
    { key: 'provider', header: 'Provider', render: (r) => <span className="font-medium capitalize">{r.provider}</span> },
    { key: 'response', header: 'Avg Response', render: (r) => `${r.avg_response_ms.toFixed(0)} ms` },
    { key: 'llm', header: 'Avg LLM Latency', render: (r) => `${r.avg_llm_ms.toFixed(0)} ms` },
    { key: 'messages', header: 'Messages', render: (r) => r.message_count.toLocaleString() },
  ];

  function formatDuration(seconds: number): string {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Performance</h1>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Avg Response Time" value={`${data?.avg_response_ms?.toFixed(0) ?? '0'} ms`} color="blue" index={0} />
        <KpiCard label="Avg LLM Latency" value={`${data?.avg_llm_ms?.toFixed(0) ?? '0'} ms`} color="purple" index={1} />
        <KpiCard label="Avg Chat Duration" value={formatDuration(data?.avg_chat_duration_s ?? 0)} color="green" index={2} />
      </div>

      {data.by_provider.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Latency by Provider</h2>
          <Bar
            data={{
              labels: data.by_provider.map((p) => p.provider),
              datasets: [
                {
                  label: 'Response (ms)',
                  data: data.by_provider.map((p) => p.avg_response_ms),
                  backgroundColor: '#6366f1',
                  borderRadius: 6,
                  maxBarThickness: 40,
                },
                {
                  label: 'LLM (ms)',
                  data: data.by_provider.map((p) => p.avg_llm_ms),
                  backgroundColor: '#8b5cf6',
                  borderRadius: 6,
                  maxBarThickness: 40,
                },
              ],
            }}
            options={{
              responsive: true,
              plugins: { legend: { position: 'top', align: 'end' } },
              scales: {
                y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
                x: { grid: { display: false } },
              },
            }}
          />
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-2">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Provider Performance</h2>
        </div>
        <DataTable columns={columns} data={data.by_provider} keyExtractor={(r) => r.provider} />
      </div>
    </div>
  );
}
