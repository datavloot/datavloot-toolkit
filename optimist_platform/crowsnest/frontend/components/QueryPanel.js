'use client';
import { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

const DEFAULT_SQL = `-- Write your SQL here
-- Tables are available from your DuckDB warehouse
SELECT 1 as hello;`;

export default function QueryPanel() {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const tables = useApi(() => api.getTables(), []);

  const executeQuery = useCallback(async () => {
    if (!sql.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.executeQuery(sql);
      setResult(res);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [sql]);

  const handleEditorMount = (editor, monaco) => {
    editor.addAction({
      id: 'execute-query',
      label: 'Execute Query',
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
      run: () => executeQuery(),
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink-0 tracking-tight">SQL editor</h2>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-ink-3">Ctrl+Enter to run</span>
          <button
            onClick={executeQuery}
            disabled={loading}
            className="px-4 py-2 bg-datavloot-600 text-white text-sm font-medium rounded-lg hover:bg-datavloot-700 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Running...' : 'Run query'}
          </button>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Table sidebar */}
        <div className="w-48 shrink-0">
          <div className="card p-3">
            <h3 className="text-xs font-medium text-ink-3 uppercase tracking-wider mb-2">Tables</h3>
            <div className="space-y-0.5 max-h-[400px] overflow-y-auto">
              {tables.loading ? (
                <p className="text-xs text-ink-3">Loading...</p>
              ) : (
                tables.data?.tables?.map((t) => (
                  <button
                    key={t.full_name}
                    onClick={() => setSql(`SELECT *\nFROM ${t.full_name}\nLIMIT 100;`)}
                    className="block w-full text-left px-2 py-1.5 text-xs font-mono text-ink-2 hover:bg-surface-2 rounded transition-colors truncate"
                    title={t.full_name}
                  >
                    {t.type === 'view' && <span className="text-ink-3 mr-1">v</span>}
                    {t.name}
                  </button>
                ))
              )}
              {!tables.loading && tables.data?.tables?.length === 0 && (
                <p className="text-xs text-ink-3">No tables found</p>
              )}
            </div>
          </div>
        </div>

        {/* Editor + results */}
        <div className="flex-1 space-y-4">
          <div className="card overflow-hidden">
            <Editor
              height="220px"
              defaultLanguage="sql"
              value={sql}
              onChange={(val) => setSql(val || '')}
              onMount={handleEditorMount}
              theme="vs-light"
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: '"JetBrains Mono", monospace',
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                padding: { top: 12, bottom: 12 },
                renderLineHighlight: 'none',
                overviewRulerBorder: false,
                hideCursorInOverviewRuler: true,
                scrollbar: { verticalScrollbarSize: 6 },
              }}
            />
          </div>

          {error && (
            <div className="card border-red-200 bg-red-50 px-4 py-3">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {result && (
            <div className="card overflow-hidden">
              <div className="panel-header">
                <span className="panel-title">
                  Results
                  <span className="ml-2 text-ink-3 font-normal">
                    {result.row_count} row{result.row_count !== 1 ? 's' : ''}
                    {result.truncated && ' (truncated)'}
                  </span>
                </span>
                <span className="text-xs text-ink-3 font-mono">{result.duration_ms}ms</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-surface-1">
                      {result.columns.map((col) => (
                        <th key={col} className="table-header whitespace-nowrap">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, ri) => (
                      <tr key={ri} className="table-row">
                        {row.map((val, ci) => (
                          <td key={ci} className="table-cell text-xs font-mono whitespace-nowrap">
                            {val === null ? (
                              <span className="text-ink-3 italic">null</span>
                            ) : (
                              String(val)
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
