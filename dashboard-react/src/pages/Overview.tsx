import { useEffect, useState, useRef } from 'react';
import { Bar, Line } from 'react-chartjs-2';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { OverviewData, EscalationStat, RatingsData, ActiveConnectionsData, KnowledgeStatus } from '../types';
import KpiCard from '../components/KpiCard';
import { CardSkeleton, ChartSkeleton } from '../components/Skeleton';

interface CombinedTimeseries {
  days: number;
  group: string;
  metrics: Record<string, Array<{ date: string; value: number }>>;
}

const chartColors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#f97316', '#ec4899'];

const METRIC_CONFIG: Record<string, { label: string; color: string; bgColor: string }> = {
  chats: { label: 'Chats', color: '#6366f1', bgColor: 'rgba(99,102,241,0.08)' },
  escalations: { label: 'Escalations', color: '#f59e0b', bgColor: 'rgba(245,158,11,0.08)' },
  tickets: { label: 'Tickets', color: '#ef4444', bgColor: 'rgba(239,68,68,0.08)' },
  tokens: { label: 'Token Usage', color: '#8b5cf6', bgColor: 'rgba(139,92,246,0.08)' },
  resolution: { label: 'AI Resolution %', color: '#10b981', bgColor: 'rgba(16,185,129,0.08)' },
  response_time: { label: 'Response Time (ms)', color: '#06b6d4', bgColor: 'rgba(6,182,212,0.08)' },
};

function CombinedChart({ metrics, days }: { metrics: Record<string, Array<{ date: string; value: number }>>; days: number }) {
  const [visible, setVisible] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    Object.keys(METRIC_CONFIG).forEach((k) => { init[k] = k === 'chats' || k === 'escalations' || k === 'tickets'; });
    return init;
  });

  const toggle = (key: string) => setVisible((prev) => ({ ...prev, [key]: !prev[key] }));

  const firstKey = Object.keys(metrics).find((k) => visible[k] && metrics[k]?.length) || 'chats';
  const labels = (metrics[firstKey] || []).map((d) => {
    const date = new Date(d.date);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  const datasets = Object.entries(METRIC_CONFIG)
    .filter(([key]) => visible[key] && metrics[key])
    .map(([key, cfg]) => ({
      label: cfg.label,
      data: (metrics[key] || []).map((d) => d.value),
      borderColor: cfg.color,
      backgroundColor: cfg.bgColor,
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
      borderWidth: 2,
    }));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Activity Overview</h2>
          <p className="text-xs text-gray-400">Last {days} days &middot; Click metrics to toggle</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(METRIC_CONFIG).map(([key, cfg]) => (
            <button
              key={key}
              onClick={() => toggle(key)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-200"
              style={{
                backgroundColor: visible[key] ? cfg.color + '18' : '#f3f4f6',
                color: visible[key] ? cfg.color : '#9ca3af',
                border: `1px solid ${visible[key] ? cfg.color + '40' : '#e5e7eb'}`,
              }}
            >
              <span
                className="w-2 h-2 rounded-full transition-opacity"
                style={{ backgroundColor: cfg.color, opacity: visible[key] ? 1 : 0.3 }}
              />
              {cfg.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ height: 320 }}>
        {datasets.length > 0 ? (
          <Line
            data={{ labels, datasets }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: '#1e293b', padding: 10, cornerRadius: 8 },
              },
              scales: {
                x: { grid: { color: 'rgba(0,0,0,0.04)', lineWidth: 1 }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } },
                y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)', lineWidth: 1 }, ticks: { font: { size: 10 } } },
              },
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">
            Select at least one metric above
          </div>
        )}
      </div>
    </div>
  );
}

export default function Overview() {
  const { days } = usePeriod();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [escalations, setEscalations] = useState<EscalationStat[] | null>(null);
  const [ratings, setRatings] = useState<RatingsData | null>(null);
  const [activeNow, setActiveNow] = useState<number>(0);
  const [knowledgeVectors, setKnowledgeVectors] = useState<number>(0);
  const [combined, setCombined] = useState<CombinedTimeseries | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch active connections and auto-refresh every 10s
  useEffect(() => {
    const fetchActive = () => {
      apiFetch<ActiveConnectionsData>('/api/admin/active-connections')
        .then((data) => setActiveNow(data.active))
        .catch(() => {/* silent — non-critical */});
    };

    fetchActive();
    intervalRef.current = setInterval(fetchActive, 10_000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Fetch main dashboard data + knowledge status
  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<OverviewData>(`/api/analytics/overview?days=${days}`),
      apiFetch<EscalationStat[]>(`/api/analytics/escalations?days=${days}`),
      apiFetch<RatingsData>(`/api/analytics/ratings?days=${days}`),
      apiFetch<KnowledgeStatus>('/api/knowledge/status'),
      apiFetch<CombinedTimeseries>(`/api/analytics/timeseries/combined?days=${days}&group=daily`),
    ])
      .then(([o, e, r, k, c]) => {
        setOverview(o);
        setEscalations(e);
        setRatings(r);
        setKnowledgeVectors(k.total_vectors);
        setCombined(c);
      })
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

  if (loading || !overview) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 9 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
      </div>
    );
  }

  const t = overview.trends;
  const kpis = [
    { label: 'Total Chats', value: (overview?.total_chats ?? 0).toLocaleString(), color: 'blue', sub: `Last ${days}d`, delta: t?.total_chats, deltaGoodWhen: 'up' as const, to: '/analytics/chats' },
    { label: 'Active Now', value: activeNow, color: 'green', sub: 'Live', trend: 'neutral' as const, greenLeftBorder: activeNow > 0, pulsingDot: true },
    { label: 'Escalation Rate', value: `${overview.escalation_rate.toFixed(1)}%`, color: 'yellow', sub: 'Handoffs to human', delta: t?.escalation_rate, deltaGoodWhen: 'down' as const, to: '/analytics/escalations' },
    { label: 'AI Resolution', value: `${overview.ai_resolution_rate.toFixed(1)}%`, color: 'green', sub: 'Resolved by AI', delta: t?.ai_resolution_rate, deltaGoodWhen: 'up' as const, to: '/analytics/resolution' },
    { label: 'Tickets Created', value: overview.tickets_created.toLocaleString(), color: 'red', sub: 'Support tickets', delta: t?.tickets_created, deltaGoodWhen: 'down' as const, to: '/analytics/tickets' },
    { label: 'Token Usage', value: overview.token_usage.toLocaleString(), color: 'purple', sub: 'LLM tokens used', delta: t?.token_usage, deltaGoodWhen: 'down' as const, to: '/analytics/tokens' },
  ];

  const cacheStats = overview.semantic_cache || {};
  const closeReasons = overview.close_reasons || {};
  const cacheLookups = (cacheStats.hits ?? 0) + (cacheStats.misses ?? 0);

  const secondaryKpis = [
    { label: 'Avg Response Time', value: overview.avg_response_ms > 0 ? `${overview.avg_response_ms}ms` : '—', color: 'cyan', sub: 'End-to-end latency', delta: t?.avg_response_ms, deltaGoodWhen: 'down' as const, to: '/analytics/response_time' },
    { label: 'Knowledge Base', value: knowledgeVectors.toLocaleString(), color: 'blue', sub: 'Total vectors', to: '/knowledge' },
    { label: 'Cache Hit Rate', value: cacheLookups > 0 ? `${cacheStats.hit_rate ?? 0}%` : '—', color: 'green', sub: cacheLookups > 0 ? `${cacheStats.hits} hits / ${cacheLookups} lookups (since restart)` : 'No lookups yet' },
  ];

  const ratingLabels = ['1', '2', '3', '4', '5'];
  const ratingData = ratingLabels.map((k) => ratings?.distribution?.[k] ?? 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Dashboard Overview</h1>

      {/* Primary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {kpis.map((kpi, i) => (
          <KpiCard key={kpi.label} {...kpi} index={i} />
        ))}
      </div>

      {/* Secondary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {secondaryKpis.map((kpi, i) => (
          <KpiCard key={kpi.label} {...kpi} index={i + 6} />
        ))}
      </div>

      {/* Combined Activity Chart with toggleable metrics */}
      {combined && combined.metrics && (
        <CombinedChart metrics={combined.metrics} days={days} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Escalation Reasons */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Escalation Reasons</h2>
          {escalations && escalations.length > 0 ? (
            <ul className="space-y-3">
              {escalations.slice(0, 8).map((e, i) => (
                <li key={e._id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: chartColors[i % chartColors.length] }}
                    />
                    <span className="text-sm text-gray-700">{e._id || 'Unknown'}</span>
                  </div>
                  <span className="text-sm font-semibold text-gray-900">{e.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No escalation data available</p>
          )}
        </div>

        {/* Star Ratings Chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Star Ratings</h2>
          {ratings && (
            <p className="text-xs text-gray-400 mb-4">
              Average: {ratings?.avg_rating?.toFixed(1) ?? '0.0'} / 5 ({ratings?.total ?? 0} total)
            </p>
          )}
          <Bar
            data={{
              labels: ratingLabels.map((l) => `${l} Star`),
              datasets: [
                {
                  label: 'Ratings',
                  data: ratingData,
                  backgroundColor: ['#ef4444', '#f97316', '#f59e0b', '#10b981', '#6366f1'],
                  borderRadius: 6,
                  maxBarThickness: 48,
                },
              ],
            }}
            options={{
              responsive: true,
              plugins: { legend: { display: false } },
              scales: {
                y: { beginAtZero: true, grid: { color: '#f3f4f6' }, ticks: { stepSize: 1 } },
                x: { grid: { display: false } },
              },
            }}
          />
        </div>
      </div>

      {/* Session Close Reasons */}
      {Object.keys(closeReasons).length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Session Close Reasons</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {Object.entries(closeReasons).map(([reason, count]) => {
              const icons: Record<string, string> = {
                completed: '✅', idle_timeout: '⏱️', disconnected: '🔌', error: '❌', escalated: '🎫',
              };
              const labels: Record<string, string> = {
                completed: 'Completed', idle_timeout: 'Idle Timeout', disconnected: 'Disconnected', error: 'Error', escalated: 'Escalated',
              };
              return (
                <div key={reason} className="flex items-center gap-3 p-3 rounded-lg bg-gray-50">
                  <span className="text-xl">{icons[reason] || '❓'}</span>
                  <div>
                    <div className="text-lg font-bold text-gray-900">{count as number}</div>
                    <div className="text-xs text-gray-500">{labels[reason] || reason}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
