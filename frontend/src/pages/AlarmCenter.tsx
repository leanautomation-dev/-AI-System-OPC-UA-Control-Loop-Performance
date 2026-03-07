import { useState } from 'react';
import { clsx } from 'clsx';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CheckCircle, Bell, Filter } from 'lucide-react';
import { useAlarmStore, type Alarm } from '../store/alarmStore';
import { ackAlarm } from '../api/client';

const SEV_LABELS: Record<string, { label: string; cls: string }> = {
  critical: { label: 'CRITICAL', cls: 'bg-alarm-critical text-white' },
  high:     { label: 'HIGH',     cls: 'bg-alarm-high text-white' },
  medium:   { label: 'MED',      cls: 'bg-alarm-medium text-black' },
  low:      { label: 'LOW',      cls: 'bg-alarm-low text-white' },
};

function getSevKey(severity: number) {
  if (severity >= 900) return 'critical';
  if (severity >= 500) return 'high';
  if (severity >= 200) return 'medium';
  return 'low';
}

export default function AlarmCenter() {
  const alarms     = useAlarmStore((s) => s.alarms);
  const ackLocal   = useAlarmStore((s) => s.acknowledgeAlarm);
  const [filter, setFilter] = useState<'all' | 'active' | 'critical'>('active');

  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (id: number) => ackAlarm(id),
    onSuccess: (_data, id) => {
      ackLocal(id);
      toast.success('Alarm acknowledged');
    },
    onError: () => toast.error('Failed to acknowledge'),
  });

  const filtered = alarms.filter((a) => {
    if (filter === 'active')   return !a.acknowledged;
    if (filter === 'critical') return a.severity >= 900 && !a.acknowledged;
    return true;
  });

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-alarm-critical" />
          <h1 className="text-xl font-bold text-industrial-100">Alarm Center</h1>
          <span className="px-2 py-0.5 bg-alarm-critical text-white rounded text-xs font-bold">
            {alarms.filter((a) => !a.acknowledged).length} Active
          </span>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 bg-industrial-800 rounded-lg p-1">
          {(['all', 'active', 'critical'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={clsx(
                'px-3 py-1 rounded text-xs font-medium capitalize transition-colors',
                filter === f
                  ? 'bg-industrial-600 text-white'
                  : 'text-industrial-400 hover:text-industrial-200'
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Alarm table */}
      <div className="bg-industrial-900 border border-industrial-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-industrial-700 bg-industrial-800">
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Time</th>
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Severity</th>
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Source</th>
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Message</th>
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Status</th>
                <th className="px-4 py-2 text-left text-industrial-400 font-medium text-xs">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-industrial-500">
                    No alarms match the current filter.
                  </td>
                </tr>
              ) : (
                filtered.map((alarm) => (
                  <AlarmRow
                    key={alarm.id}
                    alarm={alarm}
                    onAck={() => mutation.mutate(alarm.id)}
                    acking={mutation.isPending}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AlarmRow({
  alarm,
  onAck,
  acking,
}: {
  alarm: Alarm;
  onAck: () => void;
  acking: boolean;
}) {
  const sevKey = getSevKey(alarm.severity);
  const { label, cls } = SEV_LABELS[sevKey];

  return (
    <tr
      className={clsx(
        'border-b border-industrial-800 transition-colors',
        !alarm.acknowledged && alarm.severity >= 900
          ? 'alarm-blink'
          : 'hover:bg-industrial-800/50'
      )}
    >
      <td className="px-4 py-2 text-industrial-400 font-mono text-xs whitespace-nowrap">
        {new Date(alarm.time).toLocaleString()}
      </td>
      <td className="px-4 py-2">
        <span className={clsx('px-2 py-0.5 rounded text-xs font-bold', cls)}>{label}</span>
      </td>
      <td className="px-4 py-2 text-industrial-300 text-xs">{alarm.source_name || '—'}</td>
      <td className="px-4 py-2 text-industrial-200 text-sm max-w-xs truncate">{alarm.message}</td>
      <td className="px-4 py-2">
        {alarm.acknowledged ? (
          <span className="flex items-center gap-1 text-xs text-grade-good">
            <CheckCircle className="h-3 w-3" /> Ack'd
          </span>
        ) : (
          <span className="text-xs text-alarm-high font-medium">Active</span>
        )}
      </td>
      <td className="px-4 py-2">
        {!alarm.acknowledged && (
          <button
            onClick={onAck}
            disabled={acking}
            className="px-2 py-1 bg-industrial-700 hover:bg-industrial-600 border border-industrial-500 rounded text-xs text-industrial-200 transition-colors disabled:opacity-50"
          >
            Acknowledge
          </button>
        )}
      </td>
    </tr>
  );
}
