import { useEffect, useState } from 'react';
import { ShoppingCart, Eye, TrendingUp, Package } from 'lucide-react';
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

interface RecommendationData {
  total_sessions_with_recommendations: number;
  total_product_impressions: number;
  total_alternatives_shown: number;
  top_recommended_products: ProductStat[];
  sessions_with_ticket_after_recommendation: number;
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

  const columns: Column<ProductStat>[] = [
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

  const stats = [
    {
      label: 'Sessions with Recommendations',
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
      label: 'Cheaper Alternatives Shown',
      value: data.total_alternatives_shown,
      icon: TrendingUp,
      color: 'text-green-600 bg-green-50',
    },
    {
      label: 'Led to Support Ticket',
      value: data.sessions_with_ticket_after_recommendation,
      icon: ShoppingCart,
      color: 'text-amber-600 bg-amber-50',
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Product Recommendations</h1>
        <p className="text-xs text-gray-400">Last {data.period_days} days</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <div key={s.label} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 animate-card-pop">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${s.color}`}>
                <s.icon size={18} />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{s.value}</p>
                <p className="text-[11px] text-gray-500">{s.label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* GA4 info banner */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-sm text-indigo-800">
        <strong>GA4 Tracking Active:</strong> Product impressions (<code className="text-xs bg-indigo-100 px-1 rounded">view_item_list</code>),
        clicks (<code className="text-xs bg-indigo-100 px-1 rounded">select_item</code>),
        and purchases (<code className="text-xs bg-indigo-100 px-1 rounded">groot_conversion</code>) are sent to Google Analytics.
        View conversion data in <strong>GA4 &rarr; Events &rarr; groot_conversion</strong>.
      </div>

      {/* Top recommended products table */}
      {data.top_recommended_products.length > 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop">
          <div className="p-6 pb-0">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Top Recommended Products</h2>
          </div>
          <DataTable
            columns={columns}
            data={data.top_recommended_products}
            keyExtractor={(r) => r.name}
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center text-gray-400">
          No product recommendations in the last {data.period_days} days
        </div>
      )}
    </div>
  );
}
