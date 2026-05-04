import { useEffect, useState } from 'react';
import { Bar, Doughnut } from 'react-chartjs-2';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { CostsData } from '../types';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { CardSkeleton, ChartSkeleton, TableSkeleton } from '../components/Skeleton';

const chartColors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#f97316', '#ec4899'];

export default function Costs() {
  const { days } = usePeriod();
  const [data, setData] = useState<CostsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<CostsData>(`/api/analytics/costs?days=${days}`)
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
        <TableSkeleton />
      </div>
    );
  }

  const totalTokens = data.providers.reduce((s, p) => s + p.total_tokens, 0);
  const totalCost = data.providers.reduce((s, p) => s + p.estimated_cost, 0);
  const totalSessions = data.providers.reduce((s, p) => s + p.session_count, 0);

  const columns: Column<(typeof data.providers)[number]>[] = [
    { key: 'provider', header: 'Provider', render: (r) => <span className="font-medium capitalize">{r.provider}</span> },
    { key: 'tokens', header: 'Tokens', render: (r) => r.total_tokens.toLocaleString() },
    { key: 'sessions', header: 'Sessions', render: (r) => r.session_count.toLocaleString() },
    { key: 'cost', header: 'Est. Cost', render: (r) => `$${r.estimated_cost.toFixed(4)}` },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Cost Analysis</h1>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total Tokens" value={totalTokens.toLocaleString()} color="blue" index={0} sub={`Last ${days}d`} />
        <KpiCard label="Estimated Cost" value={`$${totalCost.toFixed(2)}`} color="yellow" index={1} />
        <KpiCard label="Total Sessions" value={totalSessions.toLocaleString()} color="green" index={2} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Tokens by Provider</h2>
          <Bar
            data={{
              labels: data.providers.map((p) => p.provider),
              datasets: [
                {
                  label: 'Tokens',
                  data: data.providers.map((p) => p.total_tokens),
                  backgroundColor: data.providers.map((_, i) => chartColors[i % chartColors.length]),
                  borderRadius: 6,
                  maxBarThickness: 56,
                },
              ],
            }}
            options={{
              responsive: true,
              plugins: { legend: { display: false } },
              scales: {
                y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
                x: { grid: { display: false } },
              },
            }}
          />
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Cost Distribution</h2>
          <Doughnut
            data={{
              labels: data.providers.map((p) => p.provider),
              datasets: [
                {
                  data: data.providers.map((p) => p.estimated_cost),
                  backgroundColor: data.providers.map((_, i) => chartColors[i % chartColors.length]),
                  borderWidth: 0,
                  spacing: 4,
                  borderRadius: 4,
                },
              ],
            }}
            options={{
              responsive: true,
              cutout: '65%',
              plugins: { legend: { position: 'bottom', labels: { padding: 16 } } },
            }}
          />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-3">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Provider Details</h2>
        </div>
        <DataTable columns={columns} data={data.providers} keyExtractor={(r) => r.provider} />
      </div>
    </div>
  );
}
