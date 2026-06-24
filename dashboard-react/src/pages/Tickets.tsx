import { useEffect, useState } from 'react';
import { Ticket, Copy, ExternalLink, Download } from 'lucide-react';
import { apiFetch, downloadFile } from '../api';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import Badge from '../components/Badge';
import { CardSkeleton, TableSkeleton } from '../components/Skeleton';

interface TicketEntry {
  session_id: string;
  customer_name: string;
  customer_email: string;
  topic_id: string;
  order_number: string;
  ticket_id: string;
  created_at: string;
}

interface TicketsResponse {
  tickets: TicketEntry[];
  total: number;
}

const topicColors: Record<string, string> = {
  order: 'blue',
  return: 'yellow',
  shipping: 'purple',
  product: 'green',
  complaint: 'red',
  general: 'gray',
};

function getTopicColor(topic: string): string {
  const lower = topic.toLowerCase();
  for (const [key, color] of Object.entries(topicColors)) {
    if (lower.includes(key)) return color;
  }
  return 'gray';
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text);
}

export default function Tickets() {
  const [data, setData] = useState<TicketsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiFetch<TicketsResponse>('/api/admin/tickets?limit=50')
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

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
        <TableSkeleton />
      </div>
    );
  }

  const totalTickets = data.total;
  const withOrder = data.tickets.filter((t) => !!t.order_number).length;
  const latest = data.tickets.length > 0
    ? new Date(
        data.tickets.reduce((a, b) =>
          new Date(a.created_at) > new Date(b.created_at) ? a : b
        ).created_at
      ).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '—';

  const columns: Column<TicketEntry>[] = [
    {
      key: 'ticket_id',
      header: 'Ticket #',
      render: (r) => (
        <div className="flex items-center gap-1.5">
          <span className="font-bold text-gray-900">#{r.ticket_id}</span>
          <button
            onClick={() => copyToClipboard(r.ticket_id)}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            title="Copy ticket ID"
          >
            <Copy size={13} />
          </button>
        </div>
      ),
    },
    {
      key: 'customer',
      header: 'Customer',
      render: (r) => (
        <div>
          <p className="font-medium text-gray-900">{r.customer_name || 'Anonymous'}</p>
          {r.customer_email && <p className="text-xs text-gray-400">{r.customer_email}</p>}
        </div>
      ),
    },
    {
      key: 'topic',
      header: 'Topic',
      render: (r) => (
        <Badge color={getTopicColor(r.topic_id)}>{r.topic_id || '—'}</Badge>
      ),
    },
    {
      key: 'order_number',
      header: 'Order #',
      render: (r) => r.order_number ? (
        <span className="text-gray-700">{r.order_number}</span>
      ) : (
        <span className="text-gray-300">—</span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (r) =>
        new Date(r.created_at).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }),
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Tickets</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadFile('/api/admin/tickets/export-csv', 'tickets.csv').catch(() => {})}
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all shadow-sm"
          >
            <Download size={15} />
            Export CSV
          </button>
          <a
            href="https://battrongmbh.zendesk.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all shadow-sm"
          >
            <ExternalLink size={15} />
            Open Zendesk
          </a>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total Tickets" value={totalTickets} color="blue" index={0} />
        <KpiCard label="With Order" value={withOrder} color="green" index={1} />
        <KpiCard label="Latest" value={latest} color="purple" index={2} />
      </div>

      {/* Tickets table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-3">
        {data.tickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Ticket size={40} className="mb-3 text-gray-300" />
            <p className="text-sm">No tickets created yet</p>
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={data.tickets}
            keyExtractor={(r) => r.ticket_id || r.session_id}
          />
        )}
      </div>
    </div>
  );
}
