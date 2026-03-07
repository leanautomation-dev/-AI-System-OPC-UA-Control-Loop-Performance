import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine, Brush
} from 'recharts';
import { getControllerMetrics, getControllerLive } from '../api/client';
import { useTagStore } from '../store/tagStore';
import { useAIStore } from '../store/aiStore';
import { ArrowLeft, Activity, Zap } from 'lucide-react';
import { clsx } from 'clsx';
import { format } from 'date-fns';

const gradeColor: Record<string, string> = {
  Good: '#16a34a', Acceptable: '#ca8a04', Poor: '#ea580c', Bad: '#dc2626'
};

export default function ControllerDetail() {
  const { id } = useParams<{ id: string }>();
  const controllers = useTagStore((s) => s.controllers);
  const insights    = useAIStore((s) => s.insights);
  const ctrlList    = Object.keys(controllers);
  const selectedId  = id ?? ctrlList[0] ?? '';

  const { data: metricsData } = useQuery({
    queryKey: ['metrics', selectedId],
    queryFn: () => getControllerMetrics(selectedId),
    enabled: !!selectedId,
  });

  const liveCtrl  = controllers[selectedId];
  const insight   = insights[selectedId];
  const clpm      = insight?.clpm;
  const metrics   = metricsData?.metrics ?? [];

  const chartData = metrics.map((m: any) => ({
    time: format(new Date(m.time), 'MM/dd HH:mm'),
    pv_mean: m.pv_mean?.toFixed(3),
    sp_mean: m.sp_mean?.toFixed(3),
    co_mean: m.co_mean?.toFixed(1),
    pv_std: m.pv_std?.toFixed(4),
  }));

  return (
    <div className="p-4 space-y-4">
      {/* Back + controller selector */}
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-1 text-industrial-400 hover:text-industrial-100 text-sm">
          <ArrowLeft className="h-4 w-4" /> Back
        </Link>
        <select
          className="bg-industrial-800 border border-industrial-600 text-industrial-200 rounded-lg px-3 py-1.5 text-sm"
          value={selectedId}
          onChange={(e) => window.location.href = `/controllers/${e.target.value}`}
        >
          {ctrlList.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <span className="flex items-center gap-1 text-xs text-industrial-400">
          <Activity className="h-3 w-3 text-green-400 live-pulse" /> Live
        </span>
      </div>

      {/* Live values */}
      {liveCtrl && (
        <div className="grid grid-cols-3 gap-3">
          {(['PV', 'SP', 'CO'] as const).map((sig) => (
            <div key={sig} className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
              <p className="text-xs text-industrial-400">{sig} (Live)</p>
              <p className="text-3xl font-mono font-bold text-white mt-1">
                {liveCtrl[sig] != null ? liveCtrl[sig]!.toFixed(4) : '—'}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* AI CLPM metrics */}
      {clpm && (
        <div className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="h-4 w-4 text-industrial-300" />
            <h3 className="font-semibold text-industrial-100 text-sm">AI CLPM Analysis</h3>
            <span
              className="ml-auto px-2 py-0.5 rounded text-xs font-bold"
              style={{ color: gradeColor[clpm.grade], borderColor: gradeColor[clpm.grade], border: '1px solid' }}
            >
              {clpm.grade}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Score', value: `${((clpm.score ?? 0) * 100).toFixed(1)}%` },
              { label: 'IAE', value: clpm.iae.toFixed(2) },
              { label: 'AAE', value: clpm.aae.toFixed(4) },
              { label: 'PV StdDev', value: clpm.pv_std.toFixed(4) },
              { label: 'CO Travel', value: clpm.co_travel.toFixed(2) },
              { label: 'Oscillation Idx', value: clpm.oscillation_index },
              { label: 'Anomaly', value: insight.anomaly.anomaly ? '⚠ YES' : '✓ No' },
              { label: 'Pred. Alarm', value: insight.alarm_prediction.predicted_alarm ? '⚠ YES' : '✓ No' },
            ].map((kpi) => (
              <div key={kpi.label} className="bg-industrial-800 rounded-lg p-2">
                <p className="text-xs text-industrial-400">{kpi.label}</p>
                <p className="text-sm font-mono font-bold text-industrial-100 mt-0.5">{kpi.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* PV / SP trend chart */}
      <div className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
        <h3 className="font-semibold text-industrial-100 text-sm mb-3">PV vs SP Trend (Hourly)</h3>
        {chartData.length === 0 ? (
          <p className="text-industrial-500 text-sm text-center py-8">No historical data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#064e84" />
              <XAxis dataKey="time" tick={{ fill: '#7dc9fb', fontSize: 10 }} />
              <YAxis tick={{ fill: '#7dc9fb', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0b426d', border: '1px solid #38acf7', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#bae0fd' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#7dc9fb' }} />
              <Line type="monotone" dataKey="pv_mean" stroke="#38acf7" dot={false} name="PV Mean" strokeWidth={2} />
              <Line type="monotone" dataKey="sp_mean" stroke="#fbbf24" dot={false} name="SP Mean" strokeWidth={2} strokeDasharray="5 5" />
              <Brush dataKey="time" height={20} stroke="#064e84" fill="#0b426d" travellerWidth={8} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* CO / StdDev chart */}
      <div className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
        <h3 className="font-semibold text-industrial-100 text-sm mb-3">CO Output &amp; PV Variability</h3>
        {chartData.length === 0 ? (
          <p className="text-industrial-500 text-sm text-center py-8">No historical data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#064e84" />
              <XAxis dataKey="time" tick={{ fill: '#7dc9fb', fontSize: 10 }} />
              <YAxis yAxisId="co"   tick={{ fill: '#7dc9fb', fontSize: 10 }} />
              <YAxis yAxisId="std"  orientation="right" tick={{ fill: '#7dc9fb', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0b426d', border: '1px solid #38acf7', borderRadius: 8, fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#7dc9fb' }} />
              <Line yAxisId="co"  type="monotone" dataKey="co_mean" stroke="#a78bfa" dot={false} name="CO Mean" strokeWidth={2} />
              <Line yAxisId="std" type="monotone" dataKey="pv_std"  stroke="#fb923c" dot={false} name="PV StdDev" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
