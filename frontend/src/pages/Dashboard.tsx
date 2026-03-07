import { useTagStore } from '../store/tagStore';
import { useAIStore } from '../store/aiStore';
import { useAlarmStore } from '../store/alarmStore';
import ControlLoopCard from '../components/ControlLoopCard';
import AlarmBanner from '../components/AlarmBanner';
import SystemKPIBar from '../components/SystemKPIBar';
import { Link } from 'react-router-dom';
import { AlertTriangle, TrendingUp } from 'lucide-react';

export default function Dashboard() {
  const controllers = useTagStore((s) => s.controllers);
  const insights    = useAIStore((s) => s.insights);
  const alarms      = useAlarmStore((s) => s.alarms);

  const controllerList = Object.values(controllers);
  const activeAlarms   = alarms.filter((a) => !a.acknowledged).slice(0, 5);

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-industrial-100">
            Control Loop Performance Monitor
          </h1>
          <p className="text-sm text-industrial-400">
            Real-time OPC-UA — AI-enhanced CLPM monitoring
          </p>
        </div>
        <Link
          to="/analytics"
          className="flex items-center gap-2 px-3 py-1.5 bg-industrial-700 hover:bg-industrial-600 rounded-lg text-sm text-industrial-200 transition-colors"
        >
          <TrendingUp className="h-4 w-4" />
          Analytics
        </Link>
      </div>

      {/* KPI summary bar */}
      <SystemKPIBar />

      {/* Active alarms banner */}
      {activeAlarms.length > 0 && (
        <div className="bg-alarm-critical/10 border border-alarm-critical/30 rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-4 w-4 text-alarm-critical" />
            <span className="text-sm font-semibold text-alarm-critical">
              {activeAlarms.length} Active Alarm{activeAlarms.length !== 1 ? 's' : ''}
            </span>
            <Link to="/alarms" className="ml-auto text-xs text-industrial-300 hover:text-white underline">
              View all
            </Link>
          </div>
          <div className="space-y-1">
            {activeAlarms.map((a) => (
              <AlarmBanner key={a.id} alarm={a} />
            ))}
          </div>
        </div>
      )}

      {/* Controller grid */}
      {controllerList.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
          {controllerList.map((ctrl) => (
            <ControlLoopCard
              key={ctrl.controller}
              controller={ctrl}
              insight={insights[ctrl.controller]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-industrial-500">
      <svg className="h-16 w-16 mb-4 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <p className="text-lg font-medium">No OPC-UA tags received yet</p>
      <p className="text-sm mt-1">Waiting for data from the OPC-UA server…</p>
    </div>
  );
}
