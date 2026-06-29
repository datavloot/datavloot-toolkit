const API_BASE = '/api';

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Pipelines
  getPipelineRuns: (limit = 20) => apiFetch(`/pipelines/runs?limit=${limit}`),
  getPipelineSummary: () => apiFetch('/pipelines/summary'),
  getJobs: () => apiFetch('/pipelines/jobs'),

  // Data Quality
  getTestResults: (limit = 100) => apiFetch(`/quality/test-results?limit=${limit}`),
  getQualitySummary: () => apiFetch('/quality/summary'),
  getQualityByModel: () => apiFetch('/quality/by-model'),
  getAnomalies: () => apiFetch('/quality/anomalies'),

  // SQL Query
  executeQuery: (sql, limit = 1000) =>
    apiFetch('/query/execute', {
      method: 'POST',
      body: JSON.stringify({ sql, limit }),
    }),
  getTables: () => apiFetch('/query/tables'),
  getColumns: (table) => apiFetch(`/query/columns/${table}`),

  // Catalog
  getCatalogModels: (search) =>
    apiFetch(`/catalog/models${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  getModelDetail: (name) => apiFetch(`/catalog/models/${name}`),
  getSources: () => apiFetch('/catalog/sources'),
  searchCatalog: (q) => apiFetch(`/catalog/search?q=${encodeURIComponent(q)}`),

  // Notebooks
  getNotebooks: () => apiFetch('/notebooks/list'),
  launchNotebook: (name) =>
    apiFetch('/notebooks/launch', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  // Health & Services
  getHealth: () => apiFetch('/health'),
  getServices: () => apiFetch('/services'),
};
