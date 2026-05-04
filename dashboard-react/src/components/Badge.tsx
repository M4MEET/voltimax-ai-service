import clsx from 'clsx';

const colorMap: Record<string, string> = {
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  blue: 'bg-indigo-50 text-indigo-700 ring-indigo-600/20',
  yellow: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  red: 'bg-red-50 text-red-700 ring-red-600/20',
  gray: 'bg-gray-50 text-gray-600 ring-gray-500/20',
  purple: 'bg-purple-50 text-purple-700 ring-purple-600/20',
  amber: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  darkred: 'bg-red-100 text-red-900 ring-red-700/30',
};

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  className?: string;
}

export default function Badge({ children, color = 'gray', className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        colorMap[color] || colorMap.gray,
        className
      )}
    >
      {children}
    </span>
  );
}
