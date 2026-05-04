import { useEffect, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { EscalationStat } from '../types';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { ChartSkeleton, TableSkeleton } from '../components/Skeleton';

const chartColors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#f97316', '#ec4899'];

export default function Escalations() {
  const { days } = usePeriod();
  const [data, setData] = useState<EscalationStat[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<EscalationStat[]>(`/api/analytics/escalations?days=${days}`)
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
        <ChartSkeleton />
        <TableSkeleton />
      </div>
    );
  }

  const total = data.reduce((s, e) => s + e.count, 0);

  const columns: Column<EscalationStat>[] = [
    { key: 'reason', header: 'Reason', render: (r) => <span className="font-medium">{r._id || 'Unknown'}</span> },
    { key: 'count', header: 'Count', render: (r) => r.count },
    {
      key: 'pct',
      header: '% of Total',
      render: (r) => (
        <div className="flex items-center gap-2">
          <div className="w-20 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full"
              style={{ width: `${total > 0 ? (r.count / total) * 100 : 0}%` }}
            />
          </div>
          <span className="text-xs text-gray-500">
            {total > 0 ? ((r.count / total) * 100).toFixed(1) : 0}%
          </span>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Escalations</h1>
        <span className="text-sm text-gray-400">{total} total escalations</span>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Escalation Reasons</h2>
        <Bar
          data={{
            labels: data.map((d) => d._id || 'Unknown'),
            datasets: [
              {
                label: 'Escalations',
                data: data.map((d) => d.count),
                backgroundColor: data.map((_, i) => chartColors[i % chartColors.length]),
                borderRadius: 6,
                maxBarThickness: 56,
              },
            ],
          }}
          options={{
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: { beginAtZero: true, grid: { color: '#f3f4f6' } },
              y: { grid: { display: false } },
            },
          }}
        />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-2">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Breakdown</h2>
        </div>
        <DataTable columns={columns} data={data} keyExtractor={(r) => r._id} />
      </div>
    </div>
  );
}
