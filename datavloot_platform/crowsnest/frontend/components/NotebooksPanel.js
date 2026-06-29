'use client';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

export default function NotebooksPanel() {
  const health = useApi(() => api.getHealth(), [], 10000);
  const services = useApi(() => api.getServices(), []);

  const marimoStatus = health.data?.services?.marimo;
  const marimoUrl = services.data?.marimo_url || 'http://localhost:2718';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink-0 tracking-tight">Marimo notebooks</h2>
        {marimoStatus === 'ok' && (
          <a
            href={marimoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-datavloot-700 hover:text-datavloot-800 px-3 py-1.5 rounded-lg hover:bg-datavloot-50 transition-colors border border-datavloot-200"
          >
            Open in new tab ↗
          </a>
        )}
      </div>

      {health.loading ? (
        <div className="card px-4 py-16 text-center">
          <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
          <p className="mt-3 text-sm text-ink-3">Checking Marimo status...</p>
        </div>
      ) : marimoStatus === 'ok' ? (
        <div className="card overflow-hidden">
          <iframe
            src={marimoUrl}
            className="w-full border-0"
            style={{ height: 'calc(100vh - 200px)', minHeight: '600px' }}
            title="Marimo notebooks"
          />
        </div>
      ) : (
        <NotRunning marimoUrl={marimoUrl} />
      )}
    </div>
  );
}

function NotRunning({ marimoUrl }) {
  return (
    <div className="card px-6 py-12 text-center space-y-4">
      <div className="w-12 h-12 rounded-full bg-surface-2 flex items-center justify-center mx-auto">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b8f7d" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
          <path d="M9 8l2 2-2 2" />
          <path d="M13 12h3" />
        </svg>
      </div>
      <div>
        <p className="text-sm font-medium text-ink-1">Marimo is not running</p>
        <p className="text-xs text-ink-3 mt-1">
          Expected at <code className="font-mono bg-surface-2 px-1 rounded">{marimoUrl}</code>
        </p>
      </div>
      <div className="bg-surface-1 rounded-lg border border-surface-3 px-5 py-4 text-left inline-block mx-auto">
        <p className="text-xs text-ink-3 font-medium uppercase tracking-wider mb-2">Start Marimo</p>
        <code className="text-sm font-mono text-ink-1 block">marimo edit explore.py</code>
        <p className="text-xs text-ink-3 mt-2">
          Run this in your project directory to start the notebook server.
        </p>
      </div>
      <p className="text-xs text-ink-3">
        Once running, this panel will automatically show the notebook interface.
      </p>
    </div>
  );
}
