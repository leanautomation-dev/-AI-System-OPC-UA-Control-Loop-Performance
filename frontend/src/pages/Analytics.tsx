import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ScatterChart, Scatter, ZAxis, Cell
} from 'recharts';
import { getMetrics } from '../api/client';
import { useAIStore } from '../store/aiStore';
import { BarChart3, ExternalLink } from 'lucide-react';

const SUPERSET_URL = import.meta.env.VITE_SUPERSET_URL ?? 'http://localhost:8088';

const gradeColor: Record<string, string> = {
  Good: '#16a34a', Acceptable: '#ca8a04', Poor: '#ea580c', Bad: '#dc2626'
};

export default function Analytics() {
  const [hours, setHours] = useState(24);
  const { data } = useQuery({
    queryKey: ['metrics-all', hours],
    queryFn: () => getMetrics(hours),
  });
  const insights = useAIStore((s) => s.insights);

  const metrics: any[] = data?.metrics ?? [];

  // Group by controller – last value per controller
  const byCtrl: Record<string, any> = {};
  for (const m of metrics) {
    byCtrl[m.controller] = m;
  }
  const ctrlMetrics = Object.values(byCtrl);

  // Grade distribution
  const insightsList = Object.values(insights);
  const gradeCounts = { Good: 0, Acceptable: 0, Poor: 0, Bad: 0 };
  for (const i of insightsList) {
    const g = i.clpm.grade as keyof typeof gradeCounts;
    if (g in gradeCounts) gradeCounts[g]++;
  }
  const gradeData = Object.entries(gradeCounts).map(([grade, count]) => ({ grade, count }));

  // Radar chart for fleet health
  const radarData = ctrlMetrics.map((m) => ({
    controller: m.controller,
    pv_std: m.pv_std ? Math.max(0, 1 - m.pv_std) : 0,
    co_stability: m.co_std ? Math.max(0, 1 - m.co_std / 10) : 0,
    in_auto: (m.bad_quality_pct ? 1 - m.bad_quality_pct : 1),
  }));

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-industrial-300" />
          <h1 className="text-xl font-bold text-industrial-100">Fleet Analytics</h1>
        </div>
        <div className="flex items-center gap-3">
          {/* Time range */}
          <select
            className="bg-industrial-800 border border-industrial-600 text-industrial-200 rounded-lg px-3 py-1.5 text-sm"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            <option value={1}>Last 1h</option>
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={168}>Last 7d</option>
          </select>
          {/* Superset link */}
          <a
            href={SUPERSET_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-industrial-700 hover:bg-industrial-600 rounded-lg text-sm text-industrial-200 transition-colors"
          >
            <BarChart3 className="h-4 w-4" />
            Open Superset
            <ExternalLink className="h-3 w-3 ml-0.5" />
          </a>
        </div>
      </div>

      {/* CLPM Grade Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-industrial-100 mb-3">
            Controller Grade Distribution (Live AI)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={gradeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#064e84" />
              <XAxis dataKey="grade" tick={{ fill: '#7dc9fb', fontSize: 12 }} />
              <YAxis tick={{ fill: '#7dc9fb', fontSize: 12 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#0b426d', border: '1px solid #38acf7', borderRadius: 8 }}
              />
              <Bar dataKey="count" name="Controllers" radius={[4, 4, 0, 0]}>
                {gradeData.map((entry) => (
                  <Cell key={entry.grade} fill={gradeColor[entry.grade] ?? '#38acf7'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* IAE comparison */}
        <div className="bg-industrial-900 border border-industrial-700 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-industrial-100 mb-3">
            IAE by Controller (Historical)
          </h3>
          {ctrlMetrics.length === 0 ? (
            <p className="text-industrial-500 text-sm text-center py-8">No data.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={ctrlMetrics} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#064e84" />
                <XAxis type="number" tick={{ fill: '#7dc9fb', fontSize: 11 }} />
                <YAxis dataKey="controller" type="category" tick={{ fill: '#7dc9fb', fontSize: 11 }} width={60} />
                <Tooltip
                  contentStyle={{ background: '#0b426d', border: '1px solid #38acf7', borderRadius: 8 }}
                />
                <Bar dataKey="pv_std" name="PV StdDev" fill="#38acf7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* AI insights summary table */}
      <div className="bg-industrial-900 border border-industrial-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-industrial-700">
          <h3 className="text-sm font-semibold text-industrial-100">Live AI CLPM Summary</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-industrial-800">
                {['Controller', 'Grade', 'Score', 'IAE', 'AAE', 'PV Std', 'Oscillations', 'Anomaly', 'Pred. Alarm'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-industrial-400 text-xs font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {insightsList.length === 0 ? (
                <tr><td colSpan={9} className="text-center py-8 text-industrial-500 text-sm">Waiting for AI insights…</td></tr>
              ) : (
                insightsList.map((i) => (
                  <tr key={i.controller} className="border-t border-industrial-800 hover:bg-industrial-800/50">
                    <td className="px-3 py-2 text-industrial-200 font-medium">{i.controller}</td>
                    <td className="px-3 py-2">
                      <span className="px-1.5 py-0.5 rounded text-xs font-bold" style={{ color: gradeColor[i.clpm.grade], border: `1px solid ${gradeColor[i.clpm.grade]}` }}>
                        {i.clpm.grade}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-industrial-200">{((i.clpm.score ?? 0) * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2 font-mono text-industrial-300">{i.clpm.iae.toFixed(1)}</td>
                    <td className="px-3 py-2 font-mono text-industrial-300">{i.clpm.aae.toFixed(4)}</td>
                    <td className="px-3 py-2 font-mono text-industrial-300">{i.clpm.pv_std.toFixed(4)}</td>
                    <td className="px-3 py-2 font-mono text-industrial-300">{i.clpm.oscillation_index}</td>
                    <td className="px-3 py-2">
                      {i.anomaly.anomaly
                        ? <span className="text-alarm-high text-xs font-bold">⚠ {i.anomaly.reason}</span>
                        : <span className="text-grade-good text-xs">✓</span>}
                    </td>
                    <td className="px-3 py-2">
                      {i.alarm_prediction.predicted_alarm
                        ? <span className="text-alarm-medium text-xs font-bold">⚠ ~{i.alarm_prediction.minutes_ahead}min</span>
                        : <span className="text-grade-good text-xs">✓</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Superset iFrame embed */}
      <div className="bg-industrial-900 border border-industrial-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-industrial-700 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-industrial-100">Superset CLPM Dashboard</h3>
          <a href={SUPERSET_URL} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-industrial-400 hover:text-industrial-100">
            Open full screen <ExternalLink className="h-3 w-3 ml-0.5" />
          </a>
        </div>
        <iframe
          src={`${SUPERSET_URL}/superset/dashboard/clpm-monitoring/`}
          className="w-full border-0"
          style={{ height: '600px', background: '#072a48' }}
          title="Superset CLPM Dashboard"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
        />
      </div>
    </div>
  );
}
