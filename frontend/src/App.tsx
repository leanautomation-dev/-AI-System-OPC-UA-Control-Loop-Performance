import { Routes, Route, NavLink } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  Activity, Bell, BarChart3, Cpu, Settings, Radio, ExternalLink
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import AlarmCenter from './pages/AlarmCenter';
import ControllerDetail from './pages/ControllerDetail';
import Analytics from './pages/Analytics';
import { useOPCUAConnection } from './hooks/useOPCUAConnection';
import { useAlarmStore } from './store/alarmStore';

const nav = [
  { to: '/',            icon: Activity,  label: 'Dashboard'   },
  { to: '/alarms',      icon: Bell,      label: 'Alarms'      },
  { to: '/analytics',   icon: BarChart3, label: 'Analytics'   },
  { to: '/controllers', icon: Cpu,       label: 'Controllers' },
];

export default function App() {
  const { connected } = useOPCUAConnection();
  const unackCount = useAlarmStore((s) => s.unacknowledgedCount);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 bg-industrial-900 border-r border-industrial-700 flex flex-col">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-industrial-700">
          <Radio className="h-6 w-6 text-industrial-300 flex-shrink-0" />
          <span className="hidden lg:block ml-2 font-bold text-industrial-100 text-sm tracking-wide">
            CLPM OPC-UA
          </span>
        </div>

        {/* OPC-UA status */}
        <div className="px-3 py-2 border-b border-industrial-700">
          <div className="flex items-center gap-2">
            <span
              className={clsx(
                'h-2 w-2 rounded-full flex-shrink-0',
                connected ? 'bg-green-400 live-pulse' : 'bg-red-500'
              )}
            />
            <span className="hidden lg:block text-xs text-industrial-300">
              {connected ? 'OPC-UA Live' : 'Disconnected'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 space-y-1 px-2">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-2 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-industrial-600 text-white'
                    : 'text-industrial-400 hover:bg-industrial-800 hover:text-industrial-100'
                )
              }
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
              {label === 'Alarms' && unackCount > 0 && (
                <span className="hidden lg:flex ml-auto items-center justify-center h-5 w-5 rounded-full bg-red-600 text-white text-xs font-bold">
                  {unackCount > 99 ? '99+' : unackCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Superset link */}
        <div className="p-2 border-t border-industrial-700">
          <a
            href={`${import.meta.env.VITE_SUPERSET_URL || 'http://localhost:8088'}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-2 py-2 rounded-lg text-industrial-400 hover:text-industrial-100 hover:bg-industrial-800 text-sm transition-colors"
          >
            <BarChart3 className="h-5 w-5 flex-shrink-0" />
            <span className="hidden lg:block">Superset</span>
            <ExternalLink className="hidden lg:block h-3 w-3 ml-auto" />
          </a>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-industrial-950">
        <Routes>
          <Route path="/"             element={<Dashboard />} />
          <Route path="/alarms"       element={<AlarmCenter />} />
          <Route path="/analytics"    element={<Analytics />} />
          <Route path="/controllers"  element={<ControllerDetail />} />
          <Route path="/controllers/:id" element={<ControllerDetail />} />
        </Routes>
      </main>
    </div>
  );
}
