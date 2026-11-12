'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

// Above every panel while a pipeline runs or waits to: which one, for how long
// so far, and that it is still going. Dagster does not say how long a run will
// take, so the bar moves without filling. Nothing when no run is under way.
export default function RunBanner({ activeTab, onNavigate }) {
  // Every 5 seconds while a run is under way, so the banner goes when it ends;
  // otherwise every 10, so a run started elsewhere (Dagster) shows soon.
  const [every, setEvery] = useState(10000);
  const summary = useApi(() => api.getPipelineSummary(), [], every);
  const running = summary.data?.running || 0;
  useEffect(() => {
    setEvery(running > 0 ? 5000 : 10000);
  }, [running]);

  const latest = summary.data?.latest_run;
  const underway = latest && ['running', 'queued'].includes(latest.status) ? latest : null;

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!underway) return undefined;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [underway]);

  if (!running || !underway) return null;

  const started = toMillis(underway.started_at);
  const queued = underway.status === 'queued';
  const others = running - 1;

  return (
    <div role="status" className="bg-datavloot-50 border-b border-datavloot-200 px-8 py-3 shrink-0">
      <div className="flex items-baseline gap-x-4 gap-y-1 flex-wrap">
        <span className="text-sm font-semibold text-ink-0">
          {queued ? 'A pipeline run is waiting to start' : 'A pipeline is running'}:{' '}
          <span className="font-mono">{underway.job}</span>
        </span>
        {others > 0 && (
          <span className="text-sm text-ink-2">and {others} more</span>
        )}
        <span className="text-sm text-ink-2 ml-auto tabular-nums">
          {started && !queued && (
            <>Running for <span className="font-mono">{clock((now - started) / 1000)}</span></>
          )}
          {activeTab !== 'pipelines' && (
            <button onClick={() => onNavigate('pipelines')} className="ml-4 font-semibold text-datavloot-600 hover:underline">
              See the runs →
            </button>
          )}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white mt-2 overflow-hidden" aria-hidden="true">
        <div className="h-full w-full progress-stripe" />
      </div>
    </div>
  );
}

// Dagster's times come as seconds since 1970, or as an ISO string.
function toMillis(ts) {
  if (!ts) return null;
  const ms = typeof ts === 'number' ? ts * 1000 : Date.parse(ts);
  return Number.isNaN(ms) ? null : ms;
}

// 0:45, 1:05, 12:30
function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
