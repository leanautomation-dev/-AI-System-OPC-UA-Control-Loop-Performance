import { clsx } from 'clsx';
import { Link } from 'react-router-dom';
import { AlertTriangle, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ControllerState } from '../store/tagStore';
import type { AIInsight } from '../store/aiStore';

interface Props {
  controller: ControllerState;
  insight?: AIInsight;
}

const gradeClass: Record<string, string> = {
  Good: 'grade-good',
  Acceptable: 'grade-acceptable',
  Poor: 'grade-poor',
  Bad: 'grade-bad',
};

function scoreBar(score: number | null | undefined) {
  const pct = Math.round((score ?? 0) * 100);
  const color =
    pct >= 85 ? 'bg-grade-good'
    : pct >= 70 ? 'bg-grade-acceptable'
    : pct >= 40 ? 'bg-grade-poor'
    : 'bg-alarm-critical';
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-industrial-700 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-500', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-industrial-300 w-8 text-right">{pct}%</span>
    </div>
  );
}

function GaugeMini({ pv, sp }: { pv?: number; sp?: number }) {
  if (pv == null || sp == null) return null;
  const dev = ((pv - sp) / Math.max(Math.abs(sp), 0.001)) * 100;
  const Icon = Math.abs(dev) < 5 ? Minus : dev > 0 ? TrendingUp : TrendingDown;
  return (
    <div className={clsx('flex items-center gap-1 text-xs', Math.abs(dev) > 20 ? 'text-alarm-critical' : 'text-industrial-300')}>
      <Icon className="h-3 w-3" />
      <span>{dev > 0 ? '+' : ''}{dev.toFixed(1)}%</span>
    </div>
  );
}

export default function ControlLoopCard({ controller, insight }: Props) {
  const clpm  = insight?.clpm;
  const anom  = insight?.anomaly;
  const pred  = insight?.alarm_prediction;
  const grade = clpm?.grade ?? 'Unknown';

  return (
    <Link to={`/controllers/${controller.controller}`} className="block">
      <div
        className={clsx(
          'bg-industrial-900 border rounded-xl p-4 hover:border-industrial-400 transition-all cursor-pointer',
          anom?.anomaly
            ? 'border-alarm-high alarm-blink'
            : pred?.predicted_alarm
            ? 'border-alarm-medium'
            : 'border-industrial-700'
        )}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="font-semibold text-white text-sm">{controller.controller}</p>
            <p className="text-xs text-industrial-400 mt-0.5">
              {insight?.clpm ? `${insight.clpm.oscillation_index} osc/hr` : 'Awaiting AI…'}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            {grade !== 'Unknown' && (
              <span className={clsx('px-2 py-0.5 rounded text-xs font-semibold border', gradeClass[grade])}>
                {grade}
              </span>
            )}
            {anom?.anomaly && (
              <span className="flex items-center gap-1 text-xs text-alarm-high">
                <AlertTriangle className="h-3 w-3" /> Anomaly
              </span>
            )}
          </div>
        </div>

        {/* PV / SP / CO */}
        <div className="grid grid-cols-3 gap-1 mb-3">
          {(['PV', 'SP', 'CO'] as const).map((sig) => (
            <div key={sig} className="bg-industrial-800 rounded-lg p-2">
              <p className="text-xs text-industrial-400 mb-0.5">{sig}</p>
              <p className="font-mono text-sm text-white font-semibold">
                {controller[sig] != null ? controller[sig]!.toFixed(3) : '—'}
              </p>
            </div>
          ))}
        </div>

        {/* CLPM score bar */}
        {clpm && (
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-industrial-400">CLPM Score</span>
              <GaugeMini pv={insight?.pv} sp={insight?.sp} />
            </div>
            {scoreBar(clpm.score)}
          </div>
        )}

        {/* Predicted alarm */}
        {pred?.predicted_alarm && (
          <div className="mt-2 flex items-center gap-1 text-xs text-alarm-medium bg-alarm-medium/10 border border-alarm-medium/30 rounded px-2 py-1">
            <AlertTriangle className="h-3 w-3 flex-shrink-0" />
            Alarm predicted in ~{pred.minutes_ahead}min ({Math.round((pred.confidence ?? 0) * 100)}%)
          </div>
        )}

        {/* KPIs */}
        {clpm && (
          <div className="mt-2 grid grid-cols-2 gap-1">
            <div className="text-xs text-industrial-500">
              IAE: <span className="text-industrial-200 font-mono">{clpm.iae.toFixed(1)}</span>
            </div>
            <div className="text-xs text-industrial-500">
              AAE: <span className="text-industrial-200 font-mono">{clpm.aae.toFixed(4)}</span>
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}
