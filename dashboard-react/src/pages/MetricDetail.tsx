import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Line, Bar } from 'react-chartjs-2';
import type { ChartData, ChartOptions } from 'chart.js';
import { ArrowLeft } from 'lucide-react';
import { apiFetch } from '../api';
import { CardSkeleton, ChartSkeleton } from '../components/Skeleton';

/* ------------------------------------------------------------------ */
/*  Metric config map                                                 */
/* ------------------------------------------------------------------ */
const METRIC_CONFIG: Record<string, { title: string; color: string; suffix: string; description: string }> = {
  chats:         { title: 'Total Chats',         color: '#6366f1', suffix: '',   description: 'Chat sessions started per day' },
  escalations:   { title: 'Escalation Rate',     color: '#f59e0b', suffix: '',   description: 'Sessions escalated to human support' },
  tickets:       { title: 'Tickets Created',     color: '#ef4444', suffix: '',   description: 'Zendesk support tickets created' },
  tokens:        { title: 'Token Usage',         color: '#8b5cf6', suffix: '',   description: 'LLM tokens consumed' },
  resolution:    { title: 'AI Resolution Rate',  color: '#10b981', suffix: '%',  description: 'Percentage of sessions resolved by AI' },
  response_time: { title: 'Avg Response Time',   color: '#06b6d4', suffix: 'ms', description: 'End-to-end response latency' },
};

type DaysOption = 7 | 30 | 90 | 365;
type GroupOption = 'daily' | 'monthly';

interface DataPoint {
  date: string;
  value: number;
}

interface TimeseriesResponse {
  metric: string;
  group: string;
  days: number;
  data: DataPoint[];
}

/* ------------------------------------------------------------------ */
/*  Helper: hex -> rgba                                               */
/* ------------------------------------------------------------------ */
function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */
export default function MetricDetail() {
  const { metric } = useParams<{ metric: string }>();
  const navigate = useNavigate();
  const lineRef = useRef<HTMLCanvasElement | null>(null);

  const [days, setDays] = useState<DaysOption>(30);
  const [group, setGroup] = useState<GroupOption>('daily');
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const config = METRIC_CONFIG[metric ?? ''] ?? METRIC_CONFIG.chats;

  /* Fetch time-series data */
  useEffect(() => {
    if (!metric) return;
    setLoading(true);
    setError('');
    apiFetch<TimeseriesResponse>(`/api/analytics/timeseries?metric=${metric}&days=${days}&group=${group}`)
      .then((res) => setData(res.data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [metric, days, group]);

  /* Summary stats */
  const values = data.map((d) => d.value);
  const total = values.reduce((a, b) => a + b, 0);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const avg = values.length ? total / values.length : 0;

  /* Chart data */
  const labels = data.map((d) => d.date);

  const lineData: ChartData<'line'> = {
    labels,
    datasets: [
      {
        label: config.title,
        data: values,
        borderColor: config.color,
        backgroundColor: (ctx) => {
          const chart = ctx.chart;
          const { ctx: canvasCtx, chartArea } = chart;
          if (!chartArea) return hexToRgba(config.color, 0.15);
          const gradient = canvasCtx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, hexToRgba(config.color, 0.25));
          gradient.addColorStop(1, hexToRgba(config.color, 0.02));
          return gradient;
        },
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: config.color,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
      },
    ],
  };

  const lineOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1f2937',
        titleColor: '#f3f4f6',
        bodyColor: '#f3f4f6',
        padding: 10,
        cornerRadius: 8,
        callbacks: {
          label: (ctx) => `${config.title}: ${(ctx.parsed.y ?? 0).toLocaleString()}${config.suffix}`,
        },
      },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: '#f3f4f6' }, ticks: { callback: (v) => `${v}${config.suffix}` } },
      x: { grid: { color: 'rgba(0,0,0,0.04)', lineWidth: 1 }, ticks: { maxTicksLimit: 12 } },
    },
  };

  const barData: ChartData<'bar'> = {
    labels,
    datasets: [
      {
        label: config.title,
        data: values,
        backgroundColor: hexToRgba(config.color, 0.6),
        hoverBackgroundColor: config.color,
        borderRadius: 4,
        maxBarThickness: 32,
      },
    ],
  };

  const barOptions: ChartOptions<'bar'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1f2937',
        titleColor: '#f3f4f6',
        bodyColor: '#f3f4f6',
        padding: 10,
        cornerRadius: 8,
        callbacks: {
          label: (ctx) => `${config.title}: ${(ctx.parsed.y ?? 0).toLocaleString()}${config.suffix}`,
        },
      },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: '#f3f4f6' }, ticks: { callback: (v) => `${v}${config.suffix}` } },
      x: { grid: { color: 'rgba(0,0,0,0.04)', lineWidth: 1 }, ticks: { maxTicksLimit: 12 } },
    },
  };

  /* Period / Group toggle button helper */
  const toggleBtn = (
    label: string,
    active: boolean,
    onClick: () => void,
  ) => (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-150 ${
        active
          ? 'bg-indigo-600 text-white shadow-sm'
          : 'bg-white text-gray-500 hover:text-gray-700 hover:bg-gray-50 border border-gray-200'
      }`}
    >
      {label}
    </button>
  );

  /* Stat card helper */
  const statCard = (label: string, value: string, idx: number) => (
    <div
      key={label}
      className={`bg-white rounded-xl shadow-sm border border-gray-100 p-5 animate-card-pop stagger-${Math.min(idx + 1, 6)}`}
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  );

  /* Error state */
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load data: {error}
      </div>
    );
  }

  /* Loading state */
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gray-100" />
          <div className="h-6 w-48 rounded bg-gray-100" />
        </div>
        <ChartSkeleton />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
        <ChartSkeleton />
      </div>
    );
  }

  const formatValue = (v: number) => `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}${config.suffix}`;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-indigo-600 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Overview
          </button>
          <div className="h-5 w-px bg-gray-200" />
          <h1 className="text-xl font-bold text-gray-900">{config.title}</h1>
        </div>
        <p className="text-sm text-gray-400">{config.description}</p>
      </div>

      {/* Toggles */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Period */}
        <div className="flex items-center gap-1.5">
          {([7, 30, 90, 365] as DaysOption[]).map((d) =>
            toggleBtn(`${d === 365 ? '365 Days' : `${d} Days`}`, days === d, () => setDays(d)),
          )}
        </div>

        <div className="h-5 w-px bg-gray-200 hidden sm:block" />

        {/* Group */}
        <div className="flex items-center gap-1.5">
          {toggleBtn('Daily', group === 'daily', () => setGroup('daily'))}
          {toggleBtn('Monthly', group === 'monthly', () => setGroup('monthly'))}
        </div>
      </div>

      {/* Line chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">{config.title} Over Time</h2>
        <div className="h-80">
          <Line ref={lineRef as never} data={lineData} options={lineOptions} />
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {statCard('Min', formatValue(min), 0)}
        {statCard('Max', formatValue(max), 1)}
        {statCard('Average', formatValue(Math.round(avg * 10) / 10), 2)}
        {statCard('Total', formatValue(total), 3)}
      </div>

      {/* Bar chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
        <h2 className="text-sm font-semibold text-gray-900 mb-4">{config.title} (Bar View)</h2>
        <div className="h-64">
          <Bar data={barData} options={barOptions} />
        </div>
      </div>
    </div>
  );
}
