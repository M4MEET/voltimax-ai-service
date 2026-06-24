import clsx from 'clsx';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';

const borderColors: Record<string, string> = {
  blue: 'from-indigo-500 to-blue-500',
  green: 'from-emerald-500 to-teal-500',
  yellow: 'from-amber-400 to-orange-500',
  red: 'from-red-500 to-pink-500',
  purple: 'from-purple-500 to-indigo-500',
  cyan: 'from-cyan-500 to-blue-500',
};

type Trend = 'up' | 'down' | 'neutral';

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  index?: number;
  trend?: Trend;
  /** Real period-over-period % change. null = no prior baseline. */
  delta?: number | null;
  /** Which direction counts as "good" for coloring the delta. Default 'up'. */
  deltaGoodWhen?: 'up' | 'down';
  greenLeftBorder?: boolean;
  pulsingDot?: boolean;
  to?: string;
}

function TrendIcon({ trend }: { trend: Trend }) {
  if (trend === 'up') return <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />;
  if (trend === 'down') return <TrendingDown className="w-3.5 h-3.5 text-red-400" />;
  return <Minus className="w-3.5 h-3.5 text-gray-300" />;
}

/** Render a real % delta vs previous period, colored by whether the change is good or bad. */
function DeltaBadge({ delta, goodWhen }: { delta: number; goodWhen: 'up' | 'down' }) {
  const rising = delta > 0;
  const isGood = (rising && goodWhen === 'up') || (!rising && goodWhen === 'down');
  const color = delta === 0 ? 'text-gray-400' : isGood ? 'text-emerald-600' : 'text-red-500';
  const Icon = rising ? TrendingUp : TrendingDown;
  return (
    <span className={clsx('flex items-center gap-0.5 text-xs font-medium', color)} title="vs. previous period">
      {delta !== 0 && <Icon className="w-3 h-3" />}
      {delta > 0 ? '+' : ''}{delta}%
    </span>
  );
}

export default function KpiCard({
  label,
  value,
  sub,
  color = 'blue',
  index = 0,
  trend,
  delta,
  deltaGoodWhen = 'up',
  greenLeftBorder = false,
  pulsingDot = false,
  to,
}: KpiCardProps) {
  const navigate = useNavigate();
  return (
    <div
      onClick={to ? () => navigate(to) : undefined}
      className={clsx(
        'bg-white rounded-xl shadow-sm border border-gray-100 hover:shadow-md hover:scale-[1.02] transition-all duration-200 overflow-hidden animate-card-pop',
        `stagger-${Math.min(index + 1, 6)}`,
        greenLeftBorder && 'border-l-4 border-l-emerald-500',
        to && 'cursor-pointer group',
      )}
    >
      <div className={clsx('h-1 bg-gradient-to-r', borderColors[color] || borderColors.blue)} />
      <div className="p-5">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            {label}
          </p>
          <div className="flex items-center gap-1.5">
            {delta != null ? (
              <DeltaBadge delta={delta} goodWhen={deltaGoodWhen} />
            ) : trend ? (
              <TrendIcon trend={trend} />
            ) : null}
            {to && <ChevronRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-indigo-400 transition-colors" />}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {pulsingDot && (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
          )}
        </div>
        {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
      </div>
    </div>
  );
}
