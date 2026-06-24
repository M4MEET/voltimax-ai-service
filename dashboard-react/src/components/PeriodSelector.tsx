import { useState } from 'react';
import clsx from 'clsx';
import { usePeriod } from '../hooks/usePeriod';

const periods = [7, 14, 30, 90] as const;

export default function PeriodSelector() {
  const { days, setDays } = usePeriod();
  const isPreset = (periods as readonly number[]).includes(days);
  const [customOpen, setCustomOpen] = useState(false);
  const [customValue, setCustomValue] = useState(String(days));

  function applyCustom() {
    const n = Math.max(1, Math.min(365, parseInt(customValue, 10) || 0));
    if (n > 0) setDays(n);
    setCustomOpen(false);
  }

  return (
    <div className="flex items-center gap-2">
      <div className="flex bg-gray-100 rounded-lg p-0.5">
        {periods.map((p) => (
          <button
            key={p}
            onClick={() => { setDays(p); setCustomOpen(false); }}
            className={clsx(
              'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
              days === p
                ? 'bg-white text-indigo-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            {p}d
          </button>
        ))}
        <button
          onClick={() => { setCustomOpen((v) => !v); setCustomValue(String(days)); }}
          className={clsx(
            'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
            !isPreset
              ? 'bg-white text-indigo-600 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          )}
        >
          {!isPreset ? `${days}d` : 'Custom'}
        </button>
      </div>
      {customOpen && (
        <div className="flex items-center gap-1 animate-fade-in">
          <input
            type="number"
            min={1}
            max={365}
            value={customValue}
            autoFocus
            onChange={(e) => setCustomValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') applyCustom(); }}
            className="w-16 px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
          />
          <span className="text-xs text-gray-400">days</span>
          <button
            onClick={applyCustom}
            className="px-2.5 py-1.5 text-xs font-medium text-white bg-indigo-500 rounded-lg hover:bg-indigo-600 transition-colors"
          >
            Apply
          </button>
        </div>
      )}
    </div>
  );
}
