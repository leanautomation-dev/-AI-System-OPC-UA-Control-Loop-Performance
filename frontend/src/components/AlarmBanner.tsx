import { clsx } from 'clsx';
import type { Alarm } from '../store/alarmStore';

interface Props { alarm: Alarm; }

const sevClass = (severity: number) => {
  if (severity >= 900) return 'text-alarm-critical';
  if (severity >= 500) return 'text-alarm-high';
  if (severity >= 200) return 'text-alarm-medium';
  return 'text-alarm-low';
};

const sevLabel = (severity: number) => {
  if (severity >= 900) return 'CRITICAL';
  if (severity >= 500) return 'HIGH';
  if (severity >= 200) return 'MED';
  return 'LOW';
};

export default function AlarmBanner({ alarm }: Props) {
  return (
    <div className="flex items-center gap-2 text-xs py-0.5">
      <span className={clsx('font-bold w-16 flex-shrink-0', sevClass(alarm.severity))}>
        [{sevLabel(alarm.severity)}]
      </span>
      <span className="text-industrial-400 flex-shrink-0">
        {new Date(alarm.time).toLocaleTimeString()}
      </span>
      <span className="text-industrial-200 truncate">{alarm.message}</span>
    </div>
  );
}
