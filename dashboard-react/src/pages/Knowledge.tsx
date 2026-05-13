import { useEffect, useState, useRef } from 'react';
import { Database, Upload, RefreshCw, Trash2, AlertCircle, Check, Plus, Brain } from 'lucide-react';
import { apiFetch, adminFetch } from '../api';
import type { KnowledgeStatus, KnowledgeSource, QaPair } from '../types';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import type { Column } from '../components/DataTable';
import { CardSkeleton, TableSkeleton } from '../components/Skeleton';

export default function Knowledge() {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [reembedding, setReembedding] = useState(false);
  const [reembedMessage, setReembedMessage] = useState('');
  const [message, setMessage] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // Q&A state
  const [qaPairs, setQaPairs] = useState<QaPair[]>([]);
  const [qaLoading, setQaLoading] = useState(false);
  const [qaQuestion, setQaQuestion] = useState('');
  const [qaAnswer, setQaAnswer] = useState('');
  const [qaAdding, setQaAdding] = useState(false);
  const [qaMessage, setQaMessage] = useState('');
  const [qaError, setQaError] = useState('');

  function fetchStatus() {
    setLoading(true);
    setError('');
    apiFetch<KnowledgeStatus>('/api/knowledge/status')
      .then(setStatus)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  function fetchQaPairs() {
    setQaLoading(true);
    setQaError('');
    apiFetch<QaPair[]>('/api/knowledge/qa-pairs')
      .then(setQaPairs)
      .catch((err) => setQaError(err instanceof Error ? err.message : 'Failed to load Q&A pairs'))
      .finally(() => setQaLoading(false));
  }

  useEffect(() => {
    fetchStatus();
    fetchQaPairs();
  }, []);

  async function handleSync() {
    setSyncing(true);
    setMessage('');
    try {
      const res = await adminFetch<{ synced: number }>('POST', '/api/knowledge/sync-cms');
      setMessage(`CMS sync complete: ${res.synced} items synced`);
      fetchStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMessage('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await apiFetch<{ chunks_indexed: number }>('/api/knowledge/upload', {
        method: 'POST',
        body: formData,
      });
      setMessage(`Uploaded: ${res.chunks_indexed} chunks indexed`);
      fetchStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDelete(sourceId: string) {
    if (!confirm('Delete this knowledge source?')) return;
    try {
      await adminFetch('DELETE', `/api/knowledge/${sourceId}`);
      setMessage('Source deleted');
      fetchStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  async function handleReembed() {
    setReembedding(true);
    setReembedMessage('Re-embedding all documents...');
    try {
      const res = await adminFetch<{ status: string; count: number; model: string }>('POST', '/api/admin/reembed');
      setReembedMessage(`${res.count} docs re-embedded with ${res.model}`);
    } catch (err) {
      setReembedMessage(err instanceof Error ? err.message : 'Re-embed failed');
    } finally {
      setReembedding(false);
    }
  }

  async function handleAddQa(e: React.FormEvent) {
    e.preventDefault();
    if (!qaQuestion.trim() || !qaAnswer.trim()) return;
    setQaAdding(true);
    setQaMessage('');
    try {
      const formData = new FormData();
      formData.append('question', qaQuestion.trim());
      formData.append('answer', qaAnswer.trim());
      await apiFetch('/api/knowledge/add-qa', { method: 'POST', body: formData });
      setQaQuestion('');
      setQaAnswer('');
      setQaMessage('Q&A pair added');
      fetchQaPairs();
      fetchStatus();
    } catch (err) {
      setQaMessage(err instanceof Error ? err.message : 'Failed to add Q&A pair');
    } finally {
      setQaAdding(false);
    }
  }

  async function handleDeleteQa(pairId: string) {
    if (!confirm('Delete this Q&A pair?')) return;
    try {
      await adminFetch('DELETE', `/api/knowledge/qa/${pairId}`);
      setQaMessage('Q&A pair deleted');
      fetchQaPairs();
      fetchStatus();
    } catch (err) {
      setQaMessage(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  const columns: Column<KnowledgeSource>[] = [
    { key: 'name', header: 'Name', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'type', header: 'Type', render: (r) => <span className="capitalize">{r.type}</span> },
    { key: 'chunks', header: 'Chunks', render: (r) => r.chunk_count },
    {
      key: 'created',
      header: 'Created',
      render: (r) => new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
    },
    {
      key: 'actions',
      header: '',
      render: (r) => (
        <button
          onClick={() => handleDelete(r.id)}
          className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
          title="Delete source"
        >
          <Trash2 size={16} />
        </button>
      ),
      className: 'w-12',
    },
  ];

  const qaColumns: Column<QaPair>[] = [
    {
      key: 'question',
      header: 'Question',
      render: (r) => <span className="font-medium">{r.question}</span>,
    },
    {
      key: 'answer',
      header: 'Answer',
      render: (r) => (
        <span className="text-gray-500" title={r.answer}>
          {r.answer.length > 120 ? r.answer.slice(0, 120) + '...' : r.answer}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      render: (r) => (
        <button
          onClick={() => handleDeleteQa(r._id)}
          className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
          title="Delete Q&A pair"
        >
          <Trash2 size={16} />
        </button>
      ),
      className: 'w-12',
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <TableSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load: {error}
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Knowledge Base</h1>

      {message && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-sm text-indigo-700 flex items-center gap-2 animate-fade-in">
          {message.toLowerCase().includes('fail') ? <AlertCircle size={16} /> : <Check size={16} />}
          {message}
        </div>
      )}

      {/* Status KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total Sources" value={status?.total_sources ?? 0} color="blue" index={0} />
        <KpiCard label="Total Vectors" value={(status?.total_vectors ?? 0).toLocaleString()} color="purple" index={1} />
        <KpiCard label="QA Pairs" value={status?.qa_pairs ?? 0} color="green" index={2} />
        <KpiCard label="Embedding Model" value="text-embedding-3-large" color="cyan" index={3} />
      </div>

      {/* Actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center">
              <Database size={20} className="text-indigo-500" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">CMS Sync</h2>
              <p className="text-xs text-gray-400">Sync content from your CMS</p>
            </div>
          </div>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 disabled:opacity-50 transition-all"
          >
            <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing...' : 'Sync CMS'}
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
              <Upload size={20} className="text-emerald-500" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Upload File</h2>
              <p className="text-xs text-gray-400">Add a knowledge source file</p>
            </div>
          </div>
          <label className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-500 text-white rounded-lg text-sm font-medium hover:bg-emerald-600 disabled:opacity-50 transition-all cursor-pointer">
            <Upload size={16} className={uploading ? 'animate-bounce' : ''} />
            {uploading ? 'Uploading...' : 'Choose File'}
            <input
              ref={fileRef}
              type="file"
              onChange={handleUpload}
              className="hidden"
              disabled={uploading}
            />
          </label>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-3">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <Brain size={20} className="text-amber-500" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Re-embed</h2>
              <p className="text-xs text-gray-400">Re-embed all vectors</p>
            </div>
          </div>
          <button
            onClick={handleReembed}
            disabled={reembedding}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600 disabled:opacity-50 transition-all"
          >
            <RefreshCw size={16} className={reembedding ? 'animate-spin' : ''} />
            {reembedding ? 'Re-embedding...' : 'Re-embed All'}
          </button>
          {reembedMessage && (
            <p className="mt-2 text-xs text-gray-500 text-center animate-fade-in">{reembedMessage}</p>
          )}
        </div>
      </div>

      {/* Sources table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-4">
        <div className="p-6 pb-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Knowledge Sources</h2>
        </div>
        <DataTable
          columns={columns}
          data={status?.sources ?? []}
          keyExtractor={(r) => r.id}
          emptyMessage="No knowledge sources yet"
        />
      </div>

      {/* Q&A Pairs section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden animate-card-pop stagger-5">
        <div className="p-6 pb-0">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-gray-900">Q&A Pairs</h2>
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-600">
              {qaPairs.length}
            </span>
          </div>

          {qaMessage && (
            <div className="mb-4 bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-sm text-indigo-700 flex items-center gap-2 animate-fade-in">
              {qaMessage.toLowerCase().includes('fail') ? <AlertCircle size={14} /> : <Check size={14} />}
              {qaMessage}
            </div>
          )}

          <form onSubmit={handleAddQa} className="flex flex-col sm:flex-row items-end gap-3 mb-4">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-500 mb-1">Question</label>
              <input
                type="text"
                value={qaQuestion}
                onChange={(e) => setQaQuestion(e.target.value)}
                placeholder="e.g. What is your return policy?"
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-all"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-500 mb-1">Answer</label>
              <input
                type="text"
                value={qaAnswer}
                onChange={(e) => setQaAnswer(e.target.value)}
                placeholder="e.g. You can return items within 30 days..."
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-all"
              />
            </div>
            <button
              type="submit"
              disabled={qaAdding || !qaQuestion.trim() || !qaAnswer.trim()}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-500 text-white rounded-lg text-sm font-medium hover:bg-indigo-600 disabled:opacity-50 transition-all whitespace-nowrap"
            >
              <Plus size={16} />
              {qaAdding ? 'Adding...' : 'Add'}
            </button>
          </form>
        </div>

        {qaError && (
          <div className="px-6">
            <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600 flex items-center gap-2 animate-fade-in">
              <AlertCircle size={14} />
              {qaError}
            </div>
          </div>
        )}
        {qaLoading ? (
          <div className="px-6 pb-6">
            <div className="h-24 bg-gray-50 rounded-lg animate-pulse" />
          </div>
        ) : (
          <DataTable
            columns={qaColumns}
            data={qaPairs}
            keyExtractor={(r) => r._id}
            emptyMessage="No Q&A pairs yet. Add your first one above."
          />
        )}
      </div>
    </div>
  );
}
