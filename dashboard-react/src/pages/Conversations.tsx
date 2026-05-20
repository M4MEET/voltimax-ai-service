import { useEffect, useState, useCallback } from 'react';
import { Search, Eye, ChevronLeft, ChevronRight, Package, ChevronDown, AlertTriangle } from 'lucide-react';
import { apiFetch } from '../api';
import type { ConversationsResponse, SessionSummary, ConversationDetail, SessionEvent } from '../types';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import Badge from '../components/Badge';
import Modal from '../components/Modal';
import { TableSkeleton } from '../components/Skeleton';
import clsx from 'clsx';

const PAGE_SIZE = 20;

const statusColor: Record<string, string> = {
  active: 'green',
  closed: 'gray',
  escalated: 'red',
  resolved: 'blue',
};

const tagColors = ['blue', 'purple', 'green', 'amber', 'red', 'gray'];
function tagColor(tag: string): string {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  return tagColors[Math.abs(hash) % tagColors.length];
}

const eventTypeColor: Record<string, string> = {
  card_action: 'blue',
  verification_success: 'green',
  verification_failed: 'red',
  ticket_created: 'purple',
  button_clicked: 'gray',
  topic_auto_switched: 'amber',
};

export default function Conversations() {
  const [data, setData] = useState<ConversationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [topic, setTopic] = useState('');
  const [page, setPage] = useState(0);
  const [modalData, setModalData] = useState<ConversationDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({
      skip: String(page * PAGE_SIZE),
      limit: String(PAGE_SIZE),
    });
    if (search) params.set('search', search);
    if (topic) params.set('topic', topic);

    apiFetch<ConversationsResponse>(`/api/analytics/conversations?${params}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, search, topic]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(0);
    fetchData();
  }

  async function viewConversation(id: string) {
    setModalLoading(true);
    setModalOpen(true);
    setEventsOpen(false);
    try {
      const detail = await apiFetch<ConversationDetail>(`/api/analytics/conversation/${id}`);
      setModalData(detail);
    } catch {
      setModalData(null);
    } finally {
      setModalLoading(false);
    }
  }

  const columns: Column<SessionSummary>[] = [
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
      key: 'chat_id',
      header: 'Session',
      render: (r) => r.chat_id ? (
        <span className="font-mono text-xs text-indigo-600">{r.chat_id}</span>
      ) : <span className="text-gray-300">—</span>,
    },
    { key: 'topic', header: 'Topic', render: (r) => r.topic_id || '-' },
    {
      key: 'tags',
      header: 'Tags',
      render: (r) =>
        r.topic_tags && r.topic_tags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {r.topic_tags.slice(0, 3).map((t) => (
              <Badge key={t} color={tagColor(t)} className="text-[10px] px-1.5 py-0">
                {t}
              </Badge>
            ))}
            {r.topic_tags.length > 3 && (
              <span className="text-[10px] text-gray-400">+{r.topic_tags.length - 3}</span>
            )}
          </div>
        ) : (
          <span className="text-gray-300">-</span>
        ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <div className="flex flex-col gap-0.5">
          <Badge color={statusColor[r.status] || 'gray'}>{r.status}</Badge>
          {r.close_reason && r.close_reason !== 'completed' && (
            <span className="text-[10px] text-gray-400">{r.close_reason}</span>
          )}
        </div>
      ),
    },
    { key: 'messages', header: 'Messages', render: (r) => r.message_count },
    {
      key: 'started',
      header: 'Started',
      render: (r) => new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
    },
    {
      key: 'action',
      header: '',
      render: (r) => (
        <button
          onClick={() => viewConversation(r.id)}
          className="p-1.5 rounded-lg hover:bg-indigo-50 text-indigo-500 hover:text-indigo-700 transition-colors"
          title="View transcript"
        >
          <Eye size={16} />
        </button>
      ),
      className: 'w-12',
    },
  ];

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Conversations</h1>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <form onSubmit={handleSearch} className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations..."
            className="w-full pl-9 pr-4 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
          />
        </form>
        <input
          type="text"
          value={topic}
          onChange={(e) => { setTopic(e.target.value); setPage(0); }}
          placeholder="Filter by topic..."
          className="sm:w-48 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
        />
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load: {error}
        </div>
      )}

      {loading ? (
        <TableSkeleton rows={8} />
      ) : data ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop">
          <DataTable columns={columns} data={data.sessions} keyExtractor={(r) => r.id} emptyMessage="No conversations found" />

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <p className="text-xs text-gray-400">
                Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, data.total)} of {data.total}
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-xs text-gray-600 px-2">
                  {page + 1} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* Transcript modal */}
      <Modal
        open={modalOpen}
        onClose={() => { setModalOpen(false); setModalData(null); }}
        title={modalData ? `${modalData.session.customer_name || 'Anonymous'} ${modalData.session.chat_id ? `— ${modalData.session.chat_id}` : ''}` : 'Loading...'}
      >
        {modalLoading ? (
          <div className="space-y-4 py-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className={clsx('flex', i % 2 === 0 ? 'justify-start' : 'justify-end')}>
                <div className="skeleton h-12 w-3/4 rounded-xl" />
              </div>
            ))}
          </div>
        ) : modalData ? (
          <div className="space-y-4 py-2">
            {/* Session Info Bar */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl bg-gray-50 px-4 py-3 border border-gray-100">
              <Badge color={statusColor[modalData.session.status] || 'gray'}>
                {modalData.session.status}
              </Badge>
              {modalData.session.topic_tags?.map((t) => (
                <Badge key={t} color={tagColor(t)} className="text-[10px]">
                  {t}
                </Badge>
              ))}
              {modalData.session.order_number && (
                <span className="inline-flex items-center gap-1 text-xs text-gray-600 bg-white rounded-full px-2.5 py-0.5 ring-1 ring-inset ring-gray-200">
                  <Package size={12} className="text-gray-400" />
                  {modalData.session.order_number}
                </span>
              )}
              {modalData.session.escalation_reason && (
                <Badge color="red" className="inline-flex items-center gap-1">
                  <AlertTriangle size={10} />
                  {modalData.session.escalation_reason}
                </Badge>
              )}
            </div>

            {/* Session Events Timeline */}
            {modalData.session.events && modalData.session.events.length > 0 && (
              <div className="rounded-xl border border-gray-100 overflow-hidden">
                <button
                  onClick={() => setEventsOpen((v) => !v)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <span>Show session activity ({modalData.session.events.length} events)</span>
                  <ChevronDown
                    size={14}
                    className={clsx('transition-transform duration-200', eventsOpen && 'rotate-180')}
                  />
                </button>
                <div
                  className={clsx(
                    'grid transition-[grid-template-rows] duration-200 ease-in-out',
                    eventsOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
                  )}
                >
                  <div className="overflow-hidden">
                    <div className="px-4 pb-3 pt-1 space-y-0">
                      {modalData.session.events.map((evt: SessionEvent, i: number) => (
                        <div key={i} className="relative flex gap-3 pb-3 last:pb-0">
                          {/* vertical line */}
                          {i < (modalData.session.events?.length ?? 0) - 1 && (
                            <div className="absolute left-[5px] top-3 bottom-0 w-px bg-gray-200" />
                          )}
                          {/* dot */}
                          <div className="relative mt-1.5 h-[11px] w-[11px] flex-shrink-0 rounded-full border-2 border-gray-300 bg-white" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge color={eventTypeColor[evt.type] || 'gray'} className="text-[10px] px-1.5 py-0">
                                {evt.type.replace(/_/g, ' ')}
                              </Badge>
                              <span className="text-[10px] text-gray-400">
                                {evt.ts}
                              </span>
                            </div>
                            <p className="text-xs text-gray-600 mt-0.5 break-words" style={{ overflowWrap: 'anywhere' }}>{evt.detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Chat transcript */}
            <div className="space-y-3">
              {modalData.messages.map((msg, i) => (
                <div key={i} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                  <div
                    className={clsx(
                      'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm overflow-hidden',
                      msg.role === 'user'
                        ? 'bg-indigo-500 text-white rounded-br-md'
                        : 'bg-gray-100 text-gray-800 rounded-bl-md'
                    )}
                  >
                    <p className="whitespace-pre-wrap break-words" style={{ overflowWrap: 'anywhere' }}>{msg.content}</p>
                    <p className={clsx('text-[10px] mt-1', msg.role === 'user' ? 'text-indigo-200' : 'text-gray-400')}>
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-gray-400 text-center py-8">Failed to load conversation</p>
        )}
      </Modal>
    </div>
  );
}
