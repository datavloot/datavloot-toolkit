'use client';
import { useState } from 'react';
import { api } from '../lib/api';
import { useApi, formatTimestamp } from '../lib/hooks';

export default function CatalogPanel() {
  const [search, setSearch] = useState('');
  const [selectedModel, setSelectedModel] = useState(null);

  const { data, loading, error } = useApi(
    () => api.getCatalogModels(search || undefined),
    [search],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink-0 tracking-tight">Data catalog</h2>
      </div>

      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          type="text"
          placeholder="Search models..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setSelectedModel(null); }}
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-surface-3 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-datavloot-200 focus:border-datavloot-400 transition-all"
        />
      </div>

      <div className="flex gap-4">
        <div className="w-80 shrink-0">
          <div className="card overflow-hidden">
            {loading ? (
              <div className="px-4 py-12 text-center">
                <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
              </div>
            ) : error ? (
              <div className="px-4 py-8 text-center text-sm text-ink-2">{error}</div>
            ) : (
              <div className="max-h-[600px] overflow-y-auto">
                {data?.models?.length === 0 && (
                  <div className="px-4 py-12 text-center text-sm text-ink-3">
                    {search ? `No models matching "${search}"` : 'No models found in catalog'}
                  </div>
                )}
                {data?.source === 'information_schema'
                  ? <SchemaGroupedList models={data?.models || []} selectedModel={selectedModel} onSelect={setSelectedModel} />
                  : data?.models?.map((m) => (
                    <ModelRow key={m.unique_id || m.name} model={m} selected={selectedModel === m.name} onSelect={setSelectedModel} />
                  ))
                }
                {data?.source === 'information_schema' && (
                  <div className="px-4 py-2 bg-amber-50 text-xs text-amber-700">
                    Showing tables from information_schema — Elementary catalog not available
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex-1">
          {selectedModel ? (
            <ModelDetail name={selectedModel} />
          ) : (
            <div className="card px-4 py-16 text-center">
              <p className="text-sm text-ink-3">Select a model to see details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ModelDetail({ name }) {
  const { data, loading, error } = useApi(() => api.getModelDetail(name), [name]);

  if (loading) {
    return (
      <div className="card px-4 py-12 text-center">
        <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return <div className="card px-4 py-8 text-center text-sm text-ink-2">{error}</div>;
  }

  const model = data?.model;
  const columns = data?.columns || [];
  const tests = data?.recent_tests || [];

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <h3 className="text-base font-semibold font-mono text-ink-0">{model?.name}</h3>
        {model?.description && <p className="text-sm text-ink-2 mt-2">{model.description}</p>}
        <div className="flex gap-4 mt-3 flex-wrap">
          {model?.schema && <Detail label="Schema" value={model.schema} />}
          {model?.database && <Detail label="Database" value={model.database} />}
          {model?.owner && <Detail label="Owner" value={model.owner} />}
          {model?.path && <Detail label="Path" value={model.path} />}
        </div>
      </div>

      {columns.length > 0 && (
        <div className="card overflow-hidden">
          <div className="panel-header">
            <span className="panel-title">Columns ({columns.length})</span>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-surface-1">
                <th className="table-header">Name</th>
                <th className="table-header">Type</th>
                <th className="table-header">Description</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((col) => (
                <tr key={col.column_name} className="table-row">
                  <td className="table-cell font-mono text-xs font-medium">{col.column_name}</td>
                  <td className="table-cell">
                    <span className="text-xs text-ink-3 bg-surface-2 px-1.5 py-0.5 rounded font-mono">{col.data_type}</span>
                  </td>
                  <td className="table-cell text-xs text-ink-2">{col.description || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tests.length > 0 && (
        <div className="card overflow-hidden">
          <div className="panel-header">
            <span className="panel-title">Recent tests</span>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-surface-1">
                <th className="table-header">Status</th>
                <th className="table-header">Test</th>
                <th className="table-header">Column</th>
                <th className="table-header">Time</th>
              </tr>
            </thead>
            <tbody>
              {tests.map((t, i) => (
                <tr key={i} className="table-row">
                  <td className="table-cell">
                    <span className={`status-badge status-${t.status?.toLowerCase()}`}>{t.status}</span>
                  </td>
                  <td className="table-cell text-xs font-mono">{t.test_name}</td>
                  <td className="table-cell text-xs text-ink-2">{t.column_name || '—'}</td>
                  <td className="table-cell text-xs text-ink-3">{formatTimestamp(t.test_timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ModelRow({ model: m, selected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(m.name)}
      className={`w-full text-left px-4 py-3 border-b border-surface-2 hover:bg-surface-1 transition-colors ${
        selected ? 'bg-datavloot-50' : ''
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium font-mono text-ink-0">{m.name}</span>
        {m.schema && (
          <span className="text-[10px] text-ink-3 bg-surface-2 px-1.5 py-0.5 rounded">{m.schema}</span>
        )}
      </div>
      {m.description && (
        <p className="text-xs text-ink-3 mt-1 line-clamp-2">{m.description}</p>
      )}
      {m.owner && (
        <p className="text-[10px] text-ink-3 mt-1">Owner: {m.owner}</p>
      )}
    </button>
  );
}

function SchemaGroupedList({ models, selectedModel, onSelect }) {
  const bySchema = {};
  models.forEach((m) => {
    const s = m.schema || 'main';
    if (!bySchema[s]) bySchema[s] = [];
    bySchema[s].push(m);
  });
  return Object.entries(bySchema).map(([schema, schemaModels]) => (
    <div key={schema}>
      <div className="px-4 py-1.5 text-[9px] font-semibold text-ink-3 uppercase tracking-widest bg-surface-1 border-b border-surface-2 sticky top-0">
        {schema}
      </div>
      {schemaModels.map((m) => (
        <ModelRow key={m.unique_id || m.name} model={m} selected={selectedModel === m.name} onSelect={onSelect} />
      ))}
    </div>
  ));
}

function Detail({ label, value }) {
  return (
    <div>
      <span className="text-[10px] text-ink-3 uppercase tracking-wider">{label}</span>
      <p className="text-xs text-ink-1 font-mono mt-0.5">{value}</p>
    </div>
  );
}
