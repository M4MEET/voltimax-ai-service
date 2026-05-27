import { useEffect, useState } from 'react';
import { ShoppingCart, Eye, TrendingUp, Package, DollarSign, ArrowRight } from 'lucide-react';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import Badge from '../components/Badge';
import { TableSkeleton } from '../components/Skeleton';

interface ProductStat {
  name: string;
  count: number;
}

interface Conversion {
  order_number: string;
  order_total: number;
  currency: string;
  groot_session: string;
  created_at: string;
}

interface RecommendationData {
  total_sessions_with_recommendations: number;
  total_product_impressions: number;
  total_alternatives_shown: number;
  top_recommended_products: ProductStat[];
  sessions_with_ticket_after_recommendation: number;
  total_conversions: number;
  total_revenue: number;
  recent_conversions: Conversion[];
  period_days: number;
}

export default function ProductRecommendations() {
  const { days } = usePeriod();
  const [data, setData] = useState<RecommendationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<RecommendationData>(`/api/analytics/product-recommendations?days=${days}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [days]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load: {error}
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="space-y-6">
        <TableSkeleton />
      </div>
    );
  }

  const productColumns: Column<ProductStat>[] = [
    {
      key: 'rank',
      header: '#',
      render: (_, i) => <span className="text-gray-400 text-xs">{(i ?? 0) + 1}</span>,
      className: 'w-10',
    },
    {
      key: 'name',
      header: 'Product',
      render: (r) => <span className="font-medium text-gray-900 text-sm">{r.name}</span>,
    },
    {
      key: 'count',
      header: 'Times Shown',
      render: (r) => (
        <Badge color="blue" className="text-xs">{r.count}</Badge>
      ),
    },
  ];

  const conversionColumns: Column<Conversion>[] = [
    {
      key: 'order',
      header: 'Order',
      render: (r) => <span className="font-mono text-xs text-indigo-600">#{r.order_number}</span>,
    },
    {
      key: 'total',
      header: 'Total',
      render: (r) => <span className="font-semibold text-gray-900">{r.currency === 'EUR' ? '€' : r.currency}{r.order_total.toFixed(2)}</span>,
    },
    {
      key: 'session',
      header: 'Chat Session',
      render: (r) => r.groot_session ? (
        <span className="font-mono text-[10px] text-gray-500">{r.groot_session}</span>
      ) : <span className="text-gray-300">—</span>,
    },
    {
      key: 'date',
      header: 'Date',
      render: (r) => <span className="text-xs text-gray-500">{new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>,
    },
  ];

  const stats = [
    {
      label: 'Conversions',
      value: data.total_conversions,
      icon: ShoppingCart,
      color: 'text-green-600 bg-green-50',
      highlight: true,
    },
    {
      label: 'Revenue from Chat',
      value: `€${data.total_revenue.toFixed(0)}`,
      icon: DollarSign,
      color: 'text-emerald-600 bg-emerald-50',
      highlight: true,
    },
    {
      label: 'Recommendations Shown',
      value: data.total_sessions_with_recommendations,
      icon: Eye,
      color: 'text-indigo-600 bg-indigo-50',
    },
    {
      label: 'Product Impressions',
      value: data.total_product_impressions,
      icon: Package,
      color: 'text-blue-600 bg-blue-50',
    },
    {
      label: 'Cheaper Alternatives',
      value: data.total_alternatives_shown,
      icon: TrendingUp,
      color: 'text-amber-600 bg-amber-50',
    },
  ];

  const conversionRate = data.total_sessions_with_recommendations > 0
    ? ((data.total_conversions / data.total_sessions_with_recommendations) * 100).toFixed(1)
    : '0';

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Product Recommendations</h1>
        <p className="text-xs text-gray-400">Last {data.period_days} days</p>
      </div>

      {/* Conversion funnel banner */}
      {data.total_conversions > 0 && (
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-5">
          <div className="flex items-center gap-6 flex-wrap">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{data.total_sessions_with_recommendations}</p>
              <p className="text-[10px] text-gray-500 uppercase">Shown</p>
            </div>
            <ArrowRight size={16} className="text-gray-300" />
            <div className="text-center">
              <p className="text-2xl font-bold text-green-700">{data.total_conversions}</p>
              <p className="text-[10px] text-gray-500 uppercase">Purchased</p>
            </div>
            <ArrowRight size={16} className="text-gray-300" />
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-700">€{data.total_revenue.toFixed(2)}</p>
              <p className="text-[10px] text-gray-500 uppercase">Revenue</p>
            </div>
            <div className="ml-auto text-right">
              <p className="text-lg font-bold text-green-700">{conversionRate}%</p>
              <p className="text-[10px] text-gray-500 uppercase">Conversion Rate</p>
            </div>
          </div>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {stats.map((s) => (
          <div key={s.label} className={`bg-white rounded-xl shadow-sm border ${s.highlight ? 'border-green-200' : 'border-gray-100'} p-4 animate-card-pop`}>
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${s.color}`}>
                <s.icon size={18} />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{s.value}</p>
                <p className="text-[10px] text-gray-500">{s.label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Recent conversions table */}
      {data.recent_conversions.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-green-100 overflow-hidden animate-card-pop">
          <div className="p-6 pb-0">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Recent Purchases from Chat</h2>
          </div>
          <DataTable
            columns={conversionColumns}
            data={data.recent_conversions}
            keyExtractor={(r) => r.order_number}
          />
        </div>
      )}

      {/* Top recommended products table */}
      {data.top_recommended_products.length > 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop">
          <div className="p-6 pb-0">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Top Recommended Products</h2>
          </div>
          <DataTable
            columns={productColumns}
            data={data.top_recommended_products}
            keyExtractor={(r) => r.name}
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center text-gray-400">
          No product recommendations in the last {data.period_days} days
        </div>
      )}

      {/* GA4 info */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs text-gray-500">
        <strong>Tracking:</strong> Purchase attribution via <code className="bg-gray-100 px-1 rounded">groot_attribution</code> cookie (30min window).
        Also available in GA4 → Events → <code className="bg-gray-100 px-1 rounded">groot_conversion</code>.
      </div>
    </div>
  );
}
