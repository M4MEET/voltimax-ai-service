import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  BarChart3,
  MessageSquare,
  ThumbsUp,
  DollarSign,
  AlertTriangle,
  Activity,
  FileText,
  Radio,
  Bot,
  BookOpen,
  LogOut,
  X,
  Zap,
  ScrollText,
  Ticket,
} from 'lucide-react';
import clsx from 'clsx';
import { clearApiKey } from '../api';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const analyticsNav = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/topics', icon: BarChart3, label: 'Topics' },
  { to: '/conversations', icon: MessageSquare, label: 'Conversations' },
  { to: '/feedback', icon: ThumbsUp, label: 'Feedback' },
  { to: '/costs', icon: DollarSign, label: 'Costs' },
  { to: '/escalations', icon: AlertTriangle, label: 'Escalations' },
  { to: '/performance', icon: Activity, label: 'Performance' },
  { to: '/logs', icon: FileText, label: 'Logs' },
];

const configNav = [
  { to: '/config/llm', icon: Radio, label: 'LLM Config' },
  { to: '/config/agents', icon: Bot, label: 'Agents' },
  { to: '/knowledge', icon: BookOpen, label: 'Knowledge' },
  { to: '/prompts', icon: ScrollText, label: 'Prompts' },
  { to: '/tickets', icon: Ticket, label: 'Tickets' },
];

function handleSignOut() {
  clearApiKey();
  window.location.reload();
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={clsx(
          'fixed left-0 top-0 bottom-0 w-60 bg-gradient-to-b from-slate-900 to-indigo-950 text-white z-50 flex flex-col transition-transform duration-300 lg:translate-x-0',
          isOpen ? 'translate-x-0 animate-slide-in' : '-translate-x-full'
        )}
      >
        {/* Brand */}
        <div className="flex items-center justify-between px-5 py-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center">
              <Zap size={16} className="text-white" />
            </div>
            <span className="font-bold text-sm tracking-wide">VoltimaxChat</span>
          </div>
          <button onClick={onClose} className="lg:hidden p-1 rounded hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {analyticsNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                  isActive
                    ? 'bg-indigo-500/20 text-white border-l-2 border-indigo-400 ml-0 pl-2.5'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                )
              }
            >
              <item.icon size={17} />
              {item.label}
            </NavLink>
          ))}

          <div className="pt-4 pb-2 px-3">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
              Config
            </p>
          </div>

          {configNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                  isActive
                    ? 'bg-indigo-500/20 text-white border-l-2 border-indigo-400 ml-0 pl-2.5'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                )
              }
            >
              <item.icon size={17} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Sign out */}
        <div className="px-3 py-4 border-t border-white/10">
          <button
            onClick={handleSignOut}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 transition-all w-full"
          >
            <LogOut size={17} />
            Sign Out
          </button>
        </div>
      </aside>
    </>
  );
}
