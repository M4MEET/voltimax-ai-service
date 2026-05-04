import clsx from 'clsx';
import { usePeriod } from '../hooks/usePeriod';

const periods = [7, 14, 30, 90] as const;

export default function PeriodSelector() {
  const { days, setDays } = usePeriod();

  return (
    <div className="flex bg-gray-100 rounded-lg p-0.5">
      {periods.map((p) => (
        <button
          key={p}
          onClick={() => setDays(p)}
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
    </div>
  );
}
