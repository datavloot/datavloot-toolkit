'use client';
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

export default function NotebooksPanel() {
  const { data: healthData, reload: reloadHealth } = useApi(() => api.getHealth(), [], 10000);
  const services = useApi(() => api.getServices(), []);
  const notebooks = useApi(() => api.getNotebooks(), []);

  const [launching, setLaunching] = useState(null);
  const [launchError, setLaunchError] = useState(null);

  const marimoStatus = healthData?.services?.marimo;
  const marimoUrl = services.data?.marimo_url || 'http://localhost:2718';

  // While the iframe is visible, poll health every 3s so we detect disconnect quickly.
  useEffect(() => {
    if (marimoStatus !== 'ok') return;
    const id = setInterval(reloadHealth, 3000);
    return () => clearInterval(id);
  }, [marimoStatus]);

  const handleLaunch = async (name) => {
    setLaunching(name);
    setLaunchError(null);
    try {
      await api.launchNotebook(name);
      const delays = [2000, 3000, 3000, 4000, 4000, 5000, 5000, 5000];
      for (const delay of delays) {
        await new Promise((r) => setTimeout(r, delay));
        try {
          const health = await api.getHealth();
          if (health?.services?.marimo === 'ok') break;
        } catch {
          // keep polling
        }
      }
    } catch (err) {
      setLaunchError(err.message);
    } finally {
      setLaunching(null);
      reloadHealth();
    }
  };

  const handleClose = async () => {
    try {
      await api.stopNotebook();
    } catch {
      // process may already be dead
    }
    reloadHealth();
  };

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

      {marimoStatus === 'ok' ? (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-surface-3 bg-surface-1">
            <span className="text-xs text-ink-3 font-mono">{marimoUrl}</span>
            <button
              onClick={handleClose}
              className="text-xs text-ink-2 hover:text-ink-0 transition-colors flex items-center gap-1.5 px-2 py-1 rounded hover:bg-surface-2"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
              Close notebook
            </button>
          </div>
          <iframe
            src={marimoUrl}
            className="w-full border-0"
            style={{ height: 'calc(100vh - 230px)', minHeight: '560px' }}
            title="Marimo notebooks"
          />
        </div>
      ) : launching ? (
        <LaunchingState name={launching} />
      ) : (
        <NotRunning
          marimoUrl={marimoUrl}
          notebooks={notebooks.data?.notebooks || []}
          notebooksAvailable={notebooks.data?.available}
          notebooksLoading={notebooks.loading}
          launchError={launchError}
          onLaunch={handleLaunch}
        />
      )}
    </div>
  );
}

function LaunchingState({ name }) {
  return (
    <div className="card px-6 py-12 text-center space-y-3">
      <div className="inline-block w-6 h-6 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
      <p className="text-sm font-medium text-ink-1">Starting Marimo…</p>
      <p className="text-xs text-ink-3">
        Launching <code className="font-mono bg-surface-2 px-1 rounded">{name}</code> — this may take a few seconds.
      </p>
    </div>
  );
}

function NotRunning({ marimoUrl, notebooks, notebooksAvailable, notebooksLoading, launchError, onLaunch }) {
  return (
    <div className="space-y-4">
      {launchError && (
        <div className="card border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{launchError}</p>
        </div>
      )}

      <div className="card px-6 py-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-surface-2 flex items-center justify-center shrink-0">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6b8f7d" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <path d="M8 21h8M12 17v4" />
              <path d="M9 8l2 2-2 2" />
              <path d="M13 12h3" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-ink-1">Marimo is not running</p>
            <p className="text-xs text-ink-3 mt-0.5">
              Expected at <code className="font-mono bg-surface-2 px-1 rounded">{marimoUrl}</code>
            </p>
          </div>
        </div>

        {notebooksLoading ? (
          <div className="text-xs text-ink-3">Looking for notebooks…</div>
        ) : notebooksAvailable && notebooks.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-ink-3 uppercase tracking-wider">Launch a notebook</p>
            {notebooks.map((nb) => (
              <div
                key={nb.name}
                className="flex items-center justify-between px-3 py-2.5 bg-surface-1 rounded-lg border border-surface-3"
              >
                <span className="text-sm font-mono text-ink-1">{nb.name}</span>
                <button
                  onClick={() => onLaunch(nb.name)}
                  className="text-xs px-3 py-1.5 bg-datavloot-600 text-white rounded-lg hover:bg-datavloot-700 transition-colors"
                >
                  Launch
                </button>
              </div>
            ))}
            <p className="text-xs text-ink-3 pt-1">
              Or run manually:{' '}
              <code className="font-mono bg-surface-2 px-1 rounded">
                marimo edit notebooks/{notebooks[0]?.name}
              </code>
            </p>
          </div>
        ) : (
          <div className="bg-surface-1 rounded-lg border border-surface-3 px-5 py-4 space-y-2">
            <p className="text-xs text-ink-3 font-medium uppercase tracking-wider">
              {notebooksAvailable === false ? 'No notebooks/ folder found' : 'No notebooks found'}
            </p>
            <p className="text-xs text-ink-3">
              Add <code className="font-mono bg-surface-2 px-1 rounded">.py</code> Marimo notebooks to the{' '}
              <code className="font-mono bg-surface-2 px-1 rounded">notebooks/</code> folder in your project, then launch them here.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
