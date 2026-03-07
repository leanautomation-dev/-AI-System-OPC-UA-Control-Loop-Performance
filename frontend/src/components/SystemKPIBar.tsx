import { useTagStore } from '../store/tagStore';
import { useAIStore } from '../store/aiStore';
import { useAlarmStore } from '../store/alarmStore';

export default function SystemKPIBar() {
  const controllers = useTagStore((s) => s.controllers);
  const insights    = useAIStore((s) => s.insights);
  const alarms      = useAlarmStore((s) => s.alarms);

  const ctrlList = Object.values(controllers);
  const total    = ctrlList.length;

  const insightsList = Object.values(insights);
  const goodCount    = insightsList.filter((i) => i.clpm.grade === 'Good').length;
  const anomCount    = insightsList.filter((i) => i.anomaly.anomaly).length;
  const predAlarm    = insightsList.filter((i) => i.alarm_prediction.predicted_alarm).length;
  const activeAlarms = alarms.filter((a) => !a.acknowledged).length;
  const avgScore     = insightsList.length
    ? (insightsList.reduce((s, i) => s + (i.clpm.score ?? 0), 0) / insightsList.length * 100).toFixed(1)
    : '—';

  const kpis = [
    { label: 'Controllers',      value: total,        detail: 'Online', color: 'text-industrial-300' },
    { label: 'Avg CLPM Score',   value: `${avgScore}%`, detail: 'Fleet', color: 'text-industrial-300' },
    { label: 'Good Performance', value: goodCount,    detail: `of ${total}`, color: 'text-grade-good' },
    { label: 'Anomalies',        value: anomCount,    detail: 'Active', color: anomCount > 0 ? 'text-alarm-high' : 'text-industrial-400' },
    { label: 'Predicted Alarms', value: predAlarm,    detail: 'Next 15min', color: predAlarm > 0 ? 'text-alarm-medium' : 'text-industrial-400' },
    { label: 'Active Alarms',    value: activeAlarms, detail: 'Unack', color: activeAlarms > 0 ? 'text-alarm-critical' : 'text-industrial-400' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
      {kpis.map((kpi) => (
        <div
          key={kpi.label}
          className="bg-industrial-900 border border-industrial-700 rounded-xl px-3 py-2"
        >
          <p className="text-xs text-industrial-400 truncate">{kpi.label}</p>
          <p className={`text-xl font-bold font-mono mt-0.5 ${kpi.color}`}>{kpi.value}</p>
          <p className="text-xs text-industrial-500">{kpi.detail}</p>
        </div>
      ))}
    </div>
  );
}
