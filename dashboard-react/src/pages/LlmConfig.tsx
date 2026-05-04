import { useEffect, useState } from 'react';
import { Save, Check, AlertCircle } from 'lucide-react';
import { adminFetch } from '../api';
import type { LlmConfig, LlmProviderConfig } from '../types';
import { CardSkeleton } from '../components/Skeleton';
import clsx from 'clsx';

const PROVIDERS = ['openai', 'anthropic', 'google', 'mistral', 'custom'];

const defaultModels: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307'],
  google: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
  mistral: ['mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest'],
  custom: [],
};

function emptyProvider(): LlmProviderConfig {
  return { api_key: '', default_model: '', enabled: false };
}

export default function LlmConfig() {
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    setLoading(true);
    adminFetch<LlmConfig>('GET', '/api/admin/config/llm')
      .then(setConfig)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function updateProvider(provider: string, patch: Partial<LlmProviderConfig>) {
    if (!config) return;
    setConfig({
      ...config,
      [provider]: { ...(config[provider] || emptyProvider()), ...patch },
    });
    setSuccess(false);
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    setError('');
    setSuccess(false);
    try {
      await adminFetch('PUT', '/api/admin/config/llm', config);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 skeleton rounded" />
        {Array.from({ length: 4 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">LLM Configuration</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            success
              ? 'bg-emerald-500 text-white'
              : 'bg-indigo-500 text-white hover:bg-indigo-600 shadow-sm'
          )}
        >
          {saving ? (
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          ) : success ? (
            <Check size={16} />
          ) : (
            <Save size={16} />
          )}
          {success ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      <div className="space-y-4">
        {PROVIDERS.map((provider, i) => {
          const p = config?.[provider] || emptyProvider();
          return (
            <div
              key={provider}
              className={clsx(
                'bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop',
                `stagger-${Math.min(i + 1, 6)}`
              )}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold text-gray-900 capitalize">{provider}</h2>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={p.enabled}
                    onChange={(e) => updateProvider(provider, { enabled: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-indigo-500/30 rounded-full peer peer-checked:after:translate-x-5 peer-checked:bg-indigo-500 after:content-[''] after:absolute after:top-0.5 after:start-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">API Key</label>
                  <input
                    type="password"
                    value={p.api_key}
                    onChange={(e) => updateProvider(provider, { api_key: e.target.value })}
                    placeholder="sk-..."
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Default Model</label>
                  {defaultModels[provider]?.length ? (
                    <select
                      value={p.default_model}
                      onChange={(e) => updateProvider(provider, { default_model: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
                    >
                      <option value="">Select model...</option>
                      {defaultModels[provider].map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={p.default_model}
                      onChange={(e) => updateProvider(provider, { default_model: e.target.value })}
                      placeholder="model-name"
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
                    />
                  )}
                </div>
                {provider === 'custom' && (
                  <div className="md:col-span-2">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Base URL</label>
                    <input
                      type="text"
                      value={p.base_url || ''}
                      onChange={(e) => updateProvider(provider, { base_url: e.target.value })}
                      placeholder="https://api.example.com/v1"
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all"
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
