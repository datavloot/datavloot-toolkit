'use client';
import { api } from '../lib/api';
import { useApi, formatDuration, formatTimestamp } from '../lib/hooks';

export default function PipelinesPanel() {
  const { data, loading, error, reload } = useApi(
    () => api.getPipelineRuns(30),
    [],
    15000
  );
  const services = useApi(() => api.getServices(), []);
  const dagsterUrl = services.data?.dagster_url || 'http://localhost:3000';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink-0 tracking-tight">Pipeline runs</h2>
        <div className="flex items-center gap-2">
          <a
            href={dagsterUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-datavloot-700 hover:text-datavloot-800 px-3 py-1.5 rounded-lg hover:bg-datavloot-50 transition-colors border border-datavloot-200"
          >
            Open Dagster ↗
          </a>
          <button
            onClick={reload}
            className="text-xs text-ink-3 hover:text-ink-1 px-3 py-1.5 rounded-lg hover:bg-surface-2 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="card overflow-hidden">
        {loading && !data ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} dagsterUrl={dagsterUrl} />
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-surface-1">
                <th className="table-header">Status</th>
                <th className="table-header">Job</th>
                <th className="table-header">Run ID</th>
                <th className="table-header">Started</th>
                <th className="table-header text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {data?.runs?.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-ink-3 text-sm">
                    No pipeline runs yet.{' '}
                    <a
                      href={dagsterUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-datavloot-600 hover:underline"
                    >
                      Open Dagster
                    </a>
                    {' '}to start your first run.
                  </td>
                </tr>
              )}
              {data?.runs?.map((run) => (
                <tr key={run.id} className="table-row">
                  <td className="table-cell">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="table-cell font-medium">{run.job}</td>
                  <td className="table-cell">
                    <a
                      href={`${dagsterUrl}/runs/${run.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-datavloot-600 hover:underline font-mono bg-surface-2 px-1.5 py-0.5 rounded"
                    >
                      {run.id.slice(0, 8)}
                    </a>
                  </td>
                  <td className="table-cell text-ink-2">{formatTimestamp(run.started_at)}</td>
                  <td className="table-cell text-right text-ink-2 font-mono text-xs">
                    {formatDuration(run.duration_seconds)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-${status}`}>
      {status === 'running' && <span className="w-1.5 h-1.5 rounded-full bg-current pulse-dot" />}
      {status}
    </span>
  );
}

function LoadingState() {
  return (
    <div className="px-4 py-16 text-center">
      <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
      <p className="mt-3 text-sm text-ink-3">Loading pipeline runs...</p>
    </div>
  );
}

function ErrorState({ message, dagsterUrl }) {
  return (
    <div className="px-4 py-12 text-center">
      <div className="text-red-400 text-2xl mb-2">!</div>
      <p className="text-sm text-ink-2">{message}</p>
      <p className="text-xs text-ink-3 mt-1">
        Make sure Dagster is running:{' '}
        <code className="font-mono bg-surface-2 px-1 rounded">dagster dev</code>
        {' '}or{' '}
        <a href={dagsterUrl} target="_blank" rel="noopener noreferrer" className="text-datavloot-600 hover:underline">
          open Dagster
        </a>
      </p>
    </div>
  );
}
