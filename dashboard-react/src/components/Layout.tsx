import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Menu, RefreshCw } from 'lucide-react';
import Sidebar from './Sidebar';
import PeriodSelector from './PeriodSelector';

const noPeriodPaths = ['/config', '/knowledge', '/logs'];

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const showPeriod = !noPeriodPaths.some((p) => location.pathname.startsWith(p));

  return (
    <div className="min-h-screen bg-[#f8f9fc]">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="lg:ml-60">
        {/* Topbar */}
        <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-lg border-b border-gray-200/60">
          <div className="flex items-center justify-between px-4 sm:px-6 h-14">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-500"
            >
              <Menu size={20} />
            </button>

            <div className="flex items-center gap-3 ml-auto">
              {showPeriod && <PeriodSelector />}
              <button
                onClick={() => window.location.reload()}
                className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
                title="Refresh"
              >
                <RefreshCw size={16} />
              </button>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="p-4 sm:p-6 max-w-7xl mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
