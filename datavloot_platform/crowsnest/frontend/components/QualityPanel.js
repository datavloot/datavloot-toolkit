'use client';
import { useState } from 'react';
import { api } from '../lib/api';
import { useApi, formatTimestamp } from '../lib/hooks';

export default function QualityPanel() {
  const [view, setView] = useState('by-model');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink-0 tracking-tight">Data quality</h2>
        <div className="flex bg-surface-2 rounded-lg p-0.5">
          {[
            { id: 'by-model', label: 'By model' },
            { id: 'all-tests', label: 'All tests' },
            { id: 'anomalies', label: 'Anomalies' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setView(tab.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                view === tab.id
                  ? 'bg-white text-ink-0 shadow-sm'
                  : 'text-ink-3 hover:text-ink-1'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {view === 'by-model' && <ByModelView />}
      {view === 'all-tests' && <AllTestsView />}
      {view === 'anomalies' && <AnomaliesView />}
    </div>
  );
}

function ByModelView() {
  const { data, loading, error } = useApi(() => api.getQualityByModel(), [], 30000);

  if (loading) return <Loading />;
  if (error) return <Error message={error} />;

  const models = data?.models || [];

  return (
    <div className="card overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="bg-surface-1">
            <th className="table-header">Model</th>
            <th className="table-header text-center">Pass</th>
            <th className="table-header text-center">Fail</th>
            <th className="table-header text-center">Warn</th>
            <th className="table-header">Health</th>
          </tr>
        </thead>
        <tbody>
          {models.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-12 text-center text-ink-3 text-sm">
                No test results found. Have you run dbt test with Elementary?
              </td>
            </tr>
          )}
          {models.map((m) => {
            const total = m.pass + m.fail + m.warn + m.error;
            const pct = total > 0 ? Math.round((m.pass / total) * 100) : null;
            return (
              <tr key={m.model} className="table-row">
                <td className="table-cell font-medium font-mono text-xs">{m.model}</td>
                <td className="table-cell text-center">
                  {m.pass > 0 ? <span className="text-emerald-600 font-medium">{m.pass}</span> : <span className="text-ink-3">—</span>}
                </td>
                <td className="table-cell text-center">
                  {m.fail > 0 ? <span className="text-red-600 font-medium">{m.fail}</span> : <span className="text-ink-3">—</span>}
                </td>
                <td className="table-cell text-center">
                  {m.warn > 0 ? <span className="text-amber-600 font-medium">{m.warn}</span> : <span className="text-ink-3">—</span>}
                </td>
                <td className="table-cell">
                  {pct !== null && <HealthBar pct={pct} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AllTestsView() {
  const { data, loading, error } = useApi(() => api.getTestResults(100), [], 30000);

  if (loading) return <Loading />;
  if (error) return <Error message={error} />;

  const tests = data?.test_results || [];

  return (
    <div className="card overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="bg-surface-1">
            <th className="table-header">Status</th>
            <th className="table-header">Test</th>
            <th className="table-header">Model</th>
            <th className="table-header">Column</th>
            <th className="table-header">Time</th>
          </tr>
        </thead>
        <tbody>
          {tests.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-12 text-center text-ink-3 text-sm">
                No test results found.
              </td>
            </tr>
          )}
          {tests.map((t, i) => (
            <tr key={`${t.test_unique_id}-${i}`} className="table-row">
              <td className="table-cell">
                <span className={`status-badge status-${t.status?.toLowerCase()}`}>{t.status}</span>
              </td>
              <td className="table-cell text-xs font-mono">{t.test_name}</td>
              <td className="table-cell text-xs font-mono">{t.table_name}</td>
              <td className="table-cell text-xs text-ink-2">{t.column_name || '—'}</td>
              <td className="table-cell text-xs text-ink-3">{formatTimestamp(t.test_timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnomaliesView() {
  const { data, loading, error } = useApi(() => api.getAnomalies(), [], 30000);

  if (loading) return <Loading />;
  if (error) return <Error message={error} />;

  const anomalies = data?.anomalies || [];

  return (
    <div className="card overflow-hidden">
      {anomalies.length === 0 ? (
        <div className="px-4 py-12 text-center">
          <div className="text-emerald-400 text-2xl mb-2">&#10003;</div>
          <p className="text-sm text-ink-2">No anomalies detected</p>
          <p className="text-xs text-ink-3 mt-1">Elementary anomaly detection tests are all passing.</p>
        </div>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="bg-surface-1">
              <th className="table-header">Status</th>
              <th className="table-header">Test</th>
              <th className="table-header">Table</th>
              <th className="table-header">Column</th>
              <th className="table-header">Detected</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map((a, i) => (
              <tr key={`${a.test_unique_id}-${i}`} className="table-row">
                <td className="table-cell">
                  <span className={`status-badge status-${a.status?.toLowerCase()}`}>{a.status}</span>
                </td>
                <td className="table-cell text-xs font-mono">{a.test_name}</td>
                <td className="table-cell text-xs font-mono">{a.table_name}</td>
                <td className="table-cell text-xs text-ink-2">{a.column_name || '—'}</td>
                <td className="table-cell text-xs text-ink-3">{formatTimestamp(a.test_timestamp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function HealthBar({ pct }) {
  const color = pct >= 95 ? 'bg-emerald-400' : pct >= 80 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-surface-2 rounded-full overflow-hidden max-w-[80px]">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ink-3 font-mono w-8 text-right">{pct}%</span>
    </div>
  );
}

function Loading() {
  return (
    <div className="card px-4 py-16 text-center">
      <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
      <p className="mt-3 text-sm text-ink-3">Loading quality data...</p>
    </div>
  );
}

function Error({ message }) {
  return (
    <div className="card px-4 py-12 text-center">
      <p className="text-sm text-ink-2">{message}</p>
    </div>
  );
}
