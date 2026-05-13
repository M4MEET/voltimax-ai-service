import { useEffect, useState, useCallback } from 'react';
import { Search, ChevronLeft, ChevronRight, ChevronDown, ChevronUp } from 'lucide-react';
import { apiFetch } from '../api';
import type { LogsResponse, LogEntry } from '../types';
import Badge from '../components/Badge';
import Modal from '../components/Modal';
import { TableSkeleton } from '../components/Skeleton';
import clsx from 'clsx';

const PAGE_SIZE = 50;

const levelColors: Record<string, string> = {
  DEBUG: 'gray',
  INFO: 'blue',
  WARNING: 'yellow',
  ERROR: 'red',
  CRITICAL: 'darkred',
};

export default function Logs() {
  const [data, setData] = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [level, setLevel] = useState('');
  const [hours, setHours] = useState('24');
  const [page, setPage] = useState(0);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({
      skip: String(page * PAGE_SIZE),
      limit: String(PAGE_SIZE),
      hours,
    });
    if (search) params.set('search', search);
    if (level) params.set('level', level);

    apiFetch<LogsResponse>(`/api/analytics/logs?${params}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, search, level, hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(0);
    fetchData();
  }

  function toggleRow(idx: number) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">System Logs</h1>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <form onSubmit={handleSearch} className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs..."
            className="w-full pl-9 pr-4 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
          />
        </form>
        <select
          value={level}
          onChange={(e) => { setLevel(e.target.value); setPage(0); }}
          className="sm:w-36 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
        >
          <option value="">All Levels</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <select
          value={hours}
          onChange={(e) => { setHours(e.target.value); setPage(0); }}
          className="sm:w-32 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
        >
          <option value="1">1 hour</option>
          <option value="6">6 hours</option>
          <option value="24">24 hours</option>
          <option value="72">3 days</option>
          <option value="168">7 days</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load: {error}
        </div>
      )}

      {loading ? (
        <TableSkeleton rows={10} />
      ) : data ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400 w-8" />
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Timestamp</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Level</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Logger</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Message</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-400 w-10" />
                </tr>
              </thead>
              <tbody>
                {data.logs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                      No logs found
                    </td>
                  </tr>
                ) : (
                  data.logs.map((log: LogEntry, i: number) => (
                    <LogRow
                      key={`${log.timestamp}-${i}`}
                      log={log}
                      index={i}
                      expanded={expandedRows.has(i)}
                      onToggle={() => toggleRow(i)}
                      onView={() => setSelectedLog(log)}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

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
                <span className="text-xs text-gray-600 px-2">{page + 1} / {totalPages}</span>
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

      <Modal
        open={selectedLog !== null}
        onClose={() => setSelectedLog(null)}
        title="Log Details"
      >
        {selectedLog && (
          <div className="space-y-4">
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <span className="font-medium text-gray-500">Timestamp</span>
              <span className="text-gray-900 font-mono">
                {new Date(selectedLog.timestamp).toLocaleString('en-US', {
                  weekday: 'short',
                  year: 'numeric',
                  month: 'short',
                  day: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>

              <span className="font-medium text-gray-500">Level</span>
              <span><Badge color={levelColors[selectedLog.level] || 'gray'}>{selectedLog.level}</Badge></span>

              <span className="font-medium text-gray-500">Logger</span>
              <span className="text-gray-900 font-mono text-xs">{selectedLog.logger}</span>

              <span className="font-medium text-gray-500">Module</span>
              <span className="text-gray-900 font-mono text-xs">{selectedLog.module}</span>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Message</h3>
              <p className="text-sm text-gray-800 whitespace-pre-wrap break-words bg-gray-50 rounded-lg p-3">
                {selectedLog.message}
              </p>
            </div>

            {selectedLog.traceback && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Traceback</h3>
                <pre className="bg-gray-900 text-gray-200 text-xs p-4 rounded-lg overflow-x-auto max-h-80 font-mono whitespace-pre-wrap">
                  {selectedLog.traceback}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

function EyeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function LogRow({ log, index, expanded, onToggle, onView }: { log: LogEntry; index: number; expanded: boolean; onToggle: () => void; onView: () => void }) {
  return (
    <>
      <tr className={clsx('border-b border-gray-50 hover:bg-indigo-50/30 transition-colors', index % 2 === 1 && 'bg-gray-50/50')}>
        <td className="px-4 py-2.5">
          {log.traceback && (
            <button onClick={onToggle} className="p-0.5 rounded hover:bg-gray-200 text-gray-400 transition-colors">
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </td>
        <td className="px-4 py-2.5 text-xs text-gray-500 whitespace-nowrap font-mono">
          {new Date(log.timestamp).toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </td>
        <td className="px-4 py-2.5">
          <Badge color={levelColors[log.level] || 'gray'}>{log.level}</Badge>
        </td>
        <td className="px-4 py-2.5 text-xs text-gray-500 font-mono">{log.logger}</td>
        <td className="px-4 py-2.5 text-gray-700 max-w-md truncate">{log.message}</td>
        <td className="px-4 py-2.5">
          <button
            onClick={onView}
            className="p-1 rounded-lg hover:bg-indigo-100 text-gray-400 hover:text-indigo-600 transition-colors"
            title="View full log"
          >
            <EyeIcon />
          </button>
        </td>
      </tr>
      {expanded && log.traceback && (
        <tr>
          <td colSpan={6} className="px-4 pb-3">
            <pre className="bg-gray-900 text-gray-200 text-xs p-4 rounded-lg overflow-x-auto max-h-64 font-mono">
              {log.traceback}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}
