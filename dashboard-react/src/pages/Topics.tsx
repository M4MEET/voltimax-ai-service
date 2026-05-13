import { useEffect, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { TopicStat } from '../types';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { TableSkeleton, ChartSkeleton } from '../components/Skeleton';

const chartColors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#f97316', '#ec4899'];

export default function Topics() {
  const { days } = usePeriod();
  const [data, setData] = useState<TopicStat[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<TopicStat[]>(`/api/analytics/topics?days=${days}`)
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

  const columns: Column<TopicStat>[] = [
    { key: 'topic', header: 'Topic', render: (r) => <span className="font-medium">{r._id || 'Unknown'}</span> },
    { key: 'count', header: 'Sessions', render: (r) => r.count },
    { key: 'escalated', header: 'Escalated', render: (r) => r.escalated },
    { key: 'avg_msg', header: 'Avg Messages', render: (r) => r.avg_messages?.toFixed(1) ?? '0' },
    {
      key: 'esc_rate',
      header: 'Esc. Rate',
      render: (r) => (
        <span className={r.count > 0 && r.escalated / r.count > 0.3 ? 'text-red-600 font-semibold' : ''}>
          {r.count > 0 ? `${((r.escalated / r.count) * 100).toFixed(1)}%` : '0%'}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Topic Analytics</h1>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">Sessions by Topic</h2>
        <Bar
          data={{
            labels: data.map((d) => d._id || 'Unknown'),
            datasets: [
              {
                label: 'Sessions',
                data: data.map((d) => d.count),
                backgroundColor: data.map((_, i) => chartColors[i % chartColors.length]),
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

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-2">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Topic Breakdown</h2>
        </div>
        <DataTable columns={columns} data={data} keyExtractor={(r) => r._id} />
      </div>
    </div>
  );
}
