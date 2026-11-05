'use client';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

export default function HealthBanner() {
  const pipelines = useApi(() => api.getPipelineSummary(), [], 30000);
  const quality = useApi(() => api.getQualitySummary(), [], 30000);
  const health = useApi(() => api.getHealth(), [], 30000);

  const pData = pipelines.data;
  const qData = quality.data;
  const hData = health.data?.services || {};

  const pipelineOk = pData?.by_status?.success || 0;
  const pipelineFail = pData?.by_status?.failure || 0;
  const pipelineRunning = pData?.by_status?.running || 0;
  const qScore = qData?.health_score;
  const qTotal = qData?.total_tests || 0;
  const qFail = qData?.by_status?.fail || 0;
  const qWarn = qData?.by_status?.warn || 0;

  return (
    <div className="bg-white border-b border-surface-3 px-8 h-12 flex items-center shrink-0">
      <div className="flex items-center gap-6 text-sm flex-wrap">
        {/* Pipeline status */}
        <div className="flex items-center gap-2">
          <span className="text-ink-3 text-[11px] font-semibold uppercase tracking-wider">Pipelines</span>
          {pipelines.loading ? (
            <span className="text-ink-3 text-xs">loading...</span>
          ) : pipelines.error ? (
            <span className="health-pill text-ink-3 ring-1 ring-inset ring-surface-3">offline</span>
          ) : (
            <div className="flex items-center gap-2">
              {pipelineOk > 0 && (
                <span className="health-pill px-0 text-ink-2">
                  <Dot className="text-emerald-600" /> {pipelineOk} ok
                </span>
              )}
              {pipelineFail > 0 && (
                <span className="health-pill bg-red-50 text-red-700 ring-1 ring-inset ring-red-200">
                  <Dot /> {pipelineFail} failed
                </span>
              )}
              {pipelineRunning > 0 && (
                <span className="health-pill bg-datavloot-50 text-datavloot-700">
                  <Dot className="pulse-dot" /> {pipelineRunning} running
                </span>
              )}
              {pData?.total_runs === 0 && (
                <span className="text-ink-3 text-xs">no recent runs</span>
              )}
            </div>
          )}
        </div>

        <div className="w-px h-4 bg-surface-3" />

        {/* Quality status */}
        <div className="flex items-center gap-2">
          <span className="text-ink-3 text-[11px] font-semibold uppercase tracking-wider">Quality</span>
          {quality.loading ? (
            <span className="text-ink-3 text-xs">loading...</span>
          ) : quality.error ? (
            <span className="health-pill text-ink-3 ring-1 ring-inset ring-surface-3">offline</span>
          ) : (
            <div className="flex items-center gap-2">
              {qScore !== null && (
                <span className={`health-pill ${
                  qScore >= 95 ? 'px-0 text-ink-2' :
                  qScore >= 80 ? 'bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200' :
                  'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200'
                }`}>
                  {qScore >= 95 && <Dot className="text-emerald-600" />}{qScore}% healthy
                </span>
              )}
              {qTotal > 0 && (
                <span className="text-ink-3 text-xs">{qTotal} tests (7d)</span>
              )}
              {qFail > 0 && (
                <span className="health-pill bg-red-50 text-red-700 ring-1 ring-inset ring-red-200">{qFail} failing</span>
              )}
              {qWarn > 0 && (
                <span className="health-pill bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200">{qWarn} warnings</span>
              )}
            </div>
          )}
        </div>

        <div className="w-px h-4 bg-surface-3" />

        {/* Service status dots */}
        <div className="flex items-center gap-3">
          <span className="text-ink-3 text-[11px] font-semibold uppercase tracking-wider">Services</span>
          <ServiceDot label="Dagster" status={hData.dagster} />
          <ServiceDot label="DuckDB" status={hData.duckdb} />
          <ServiceDot label="Marimo" status={hData.marimo} />
        </div>
      </div>
    </div>
  );
}

function Dot({ className }) {
  return (
    <span className={`inline-block w-1.5 h-1.5 rounded-full bg-current ${className || ''}`} />
  );
}

function ServiceDot({ label, status }) {
  const color = status === 'ok' ? 'bg-emerald-500' : status === 'offline' ? 'bg-red-500' : 'bg-surface-3';
  return (
    <span className="flex items-center gap-1.5 text-xs text-ink-2" title={`${label}: ${status || 'unknown'}`}>
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
