'use client';
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import PipelinesPanel from '../components/PipelinesPanel';
import QualityPanel from '../components/QualityPanel';
import QueryPanel from '../components/QueryPanel';
import CatalogPanel from '../components/CatalogPanel';
import NotebooksPanel from '../components/NotebooksPanel';
import AppsPanel from '../components/AppsPanel';
import HealthBanner from '../components/HealthBanner';
import OverviewPanel from '../components/OverviewPanel';

const NAV = [
  {
    label: null,
    tabs: [{ id: 'overview', label: 'Overview', icon: OverviewIcon }],
  },
  {
    label: 'Monitor',
    tabs: [{ id: 'pipelines', label: 'Pipelines', icon: PipelineIcon }],
  },
  {
    label: 'Explore',
    tabs: [
      { id: 'query', label: 'SQL editor', icon: QueryIcon },
      { id: 'notebooks', label: 'Notebooks', icon: NotebooksIcon },
    ],
  },
  {
    label: 'Insights',
    tabs: [{ id: 'apps', label: 'Dashboards', icon: AppsIcon }],
  },
  {
    label: 'Governance',
    tabs: [
      { id: 'catalog', label: 'Catalog', icon: CatalogIcon },
      { id: 'quality', label: 'Data quality', icon: QualityIcon },
    ],
  },
];
const TAB_IDS = NAV.flatMap((group) => group.tabs.map((tab) => tab.id));

export default function CrowsNestPage() {
  const [activeTab, setActiveTab] = useState('overview');

  // The tab lives in the address (#query), so a link or a reload opens the same tab.
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.slice(1);
      if (TAB_IDS.includes(id)) setActiveTab(id);
      else if (id === 'welcome') setActiveTab('overview');
    };
    fromHash();
    window.addEventListener('hashchange', fromHash);
    return () => window.removeEventListener('hashchange', fromHash);
  }, []);
  const selectTab = (id) => {
    setActiveTab(id);
    window.history.replaceState(null, '', `#${id}`);
  };
  const { data: branding } = useApi(() => api.getBranding(), []);
  const { data: services } = useApi(() => api.getServices(), []);

  // The project's colours (branding/ in the project) replace the defaults in globals.css.
  useEffect(() => {
    if (!branding) return;
    for (const [name, value] of Object.entries(branding.variables || {})) {
      document.documentElement.style.setProperty(name, value);
    }
    // Remembered for the next page load, which applies them before the first
    // paint (app/layout.js) instead of flashing the default colours.
    try {
      localStorage.setItem('cn-branding', JSON.stringify(branding.variables || {}));
    } catch {
      // storage blocked: the colours still arrive, a moment later
    }
    if (branding.name) document.title = `${branding.name} · Crows Nest`;
  }, [branding]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* TEST BANNER — uncomment when iterating on the Crows Nest to confirm the correct build is deployed */}
      {/* <div className="w-full bg-amber-400 text-amber-900 text-xs font-semibold text-center py-1 tracking-wide z-20 shrink-0">
        Testing build — Iteration 7
      </div> */}

      <div className="flex flex-1 min-h-0">
      {/* Sidebar: datavloot's deep navy (a project's branding darkens its own accent) */}
      <aside className="w-60 bg-datavloot-900 text-white flex flex-col fixed h-full z-10">
        {/* Logo: the project's own from branding/, else datavloot's */}
        <div className="px-5 pt-5 pb-4">
          <div className="flex items-center gap-3">
            {branding?.logo ? (
              <span className="h-10 max-w-[7.5rem] shrink-0 rounded-md bg-white px-2 py-1.5 flex items-center">
                <img src={branding.logo} alt={branding.name || 'Logo'} className="max-h-full max-w-full" />
              </span>
            ) : (
              <img src="/datavloot-logo.png" alt="" className="w-10 h-10 shrink-0" />
            )}
            <div className="min-w-0">
              <div className="font-semibold text-[15px] leading-tight tracking-tight truncate">
                {branding?.name || 'datavloot'}
              </div>
              <div className="text-[11px] text-white/55 leading-tight mt-0.5">crows nest</div>
            </div>
          </div>
        </div>

        {/* Nav, in groups */}
        <nav className="flex-1 px-3 pt-2 pb-4 space-y-5 overflow-y-auto">
          {NAV.map((group) => (
            <div key={group.label || 'home'}>
              {group.label && <div className="px-3 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-white/40">
                {group.label}
              </div>}
              <div className="space-y-0.5">
                {group.tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => selectTab(tab.id)}
                    aria-current={activeTab === tab.id ? 'page' : undefined}
                    className={`sidebar-link w-full ${
                      activeTab === tab.id ? 'sidebar-link-active' : 'sidebar-link-inactive'
                    }`}
                  >
                    <tab.icon active={activeTab === tab.id} />
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer: datavloot, the toolkit the Crows Nest comes with; also under a project's own branding */}
        <div className="mx-3 px-3 py-3 border-t border-white/10">
          <div className="flex items-center gap-2 text-[11px] text-white/50">
            {branding?.logo && <img src="/datavloot-logo.png" alt="" className="w-5 h-5" />}
            <span>datavloot</span>
            {services?.version && <span className="ml-auto font-mono">v{services.version}</span>}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-60 flex-1 flex flex-col overflow-hidden">
        {/* The overview says all of this itself */}
        {activeTab !== 'overview' && <HealthBanner />}

        <div className="flex-1 min-h-0 flex flex-col overflow-y-auto overflow-x-hidden px-8 py-6">
          {activeTab === 'overview' && <OverviewPanel onNavigate={selectTab} branding={branding} />}
          {activeTab === 'pipelines' && <PipelinesPanel />}
          {activeTab === 'quality' && <QualityPanel />}
          {activeTab === 'query' && <QueryPanel />}
          {activeTab === 'catalog' && <CatalogPanel />}
          {activeTab === 'notebooks' && <NotebooksPanel />}
          {activeTab === 'apps' && <AppsPanel />}
        </div>
      </main>
      </div>
    </div>
  );
}

function OverviewIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {/* a compass: the lookout's first look */}
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5l-2 5-5 2 2-5z" />
    </svg>
  );
}

function PipelineIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16M4 12h10M4 18h6" />
    </svg>
  );
}

function AppsIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  );
}

function QualityIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 12l2 2 4-4" />
      <path d="M12 3a9 9 0 110 18 9 9 0 010-18z" />
    </svg>
  );
}

function QueryIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 9l3 3-3 3" />
      <path d="M14 15h3" />
      <rect x="3" y="4" width="18" height="16" rx="2" />
    </svg>
  );
}

function CatalogIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
      <path d="M8 7h8M8 11h5" />
    </svg>
  );
}

function NotebooksIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" className={active ? 'text-highlight' : 'opacity-80'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
      <path d="M9 8l2 2-2 2" />
      <path d="M13 12h3" />
    </svg>
  );
}
