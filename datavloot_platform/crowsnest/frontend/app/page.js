'use client';
import { useState } from 'react';
import PipelinesPanel from '../components/PipelinesPanel';
import QualityPanel from '../components/QualityPanel';
import QueryPanel from '../components/QueryPanel';
import CatalogPanel from '../components/CatalogPanel';
import NotebooksPanel from '../components/NotebooksPanel';
import HealthBanner from '../components/HealthBanner';

const TABS = [
  { id: 'pipelines', label: 'Pipelines', icon: PipelineIcon },
  { id: 'quality', label: 'Data quality', icon: QualityIcon },
  { id: 'query', label: 'SQL editor', icon: QueryIcon },
  { id: 'catalog', label: 'Catalog', icon: CatalogIcon },
  { id: 'notebooks', label: 'Notebooks', icon: NotebooksIcon },
];

export default function CrowsNestPage() {
  const [activeTab, setActiveTab] = useState('pipelines');

  return (
    <div className="min-h-screen flex flex-col">
      {/* TEST BANNER — uncomment when iterating on the Crows Nest to confirm the correct build is deployed */}
      {/* <div className="w-full bg-amber-400 text-amber-900 text-xs font-semibold text-center py-1 tracking-wide z-20 shrink-0">
        Testing build — Iteration 7
      </div> */}

      <div className="flex flex-1">
      {/* Sidebar */}
      <aside className="w-60 bg-white border-r border-surface-3 flex flex-col fixed h-full z-10">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-surface-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-datavloot-600 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="white" strokeLinecap="round" strokeLinejoin="round">
                {/* barrel */}
                <rect x="3" y="1" width="12" height="8" rx="1.5" strokeWidth="1.5"/>
                {/* barrel staves */}
                <line x1="7" y1="2" x2="7" y2="8" strokeWidth="1" strokeOpacity="0.6"/>
                <line x1="11" y1="2" x2="11" y2="8" strokeWidth="1" strokeOpacity="0.6"/>
                {/* mast */}
                <line x1="9" y1="9" x2="9" y2="17" strokeWidth="1.5"/>
                {/* yard */}
                <line x1="5" y1="13" x2="13" y2="13" strokeWidth="1.5"/>
              </svg>
            </div>
            <div>
              <div className="font-semibold text-sm text-ink-0 tracking-tight">Optimist</div>
              <div className="text-[11px] text-ink-3">crows nest</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`sidebar-link w-full ${
                activeTab === tab.id ? 'sidebar-link-active' : 'sidebar-link-inactive'
              }`}
            >
              <tab.icon active={activeTab === tab.id} />
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-surface-3">
          <div className="text-[11px] text-ink-3">
            Crows Nest v0.1.0
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-60 flex-1 overflow-x-hidden">
        <HealthBanner />

        <div className="p-6">
          {activeTab === 'pipelines' && <PipelinesPanel />}
          {activeTab === 'quality' && <QualityPanel />}
          {activeTab === 'query' && <QueryPanel />}
          {activeTab === 'catalog' && <CatalogPanel />}
          {activeTab === 'notebooks' && <NotebooksPanel />}
        </div>
      </main>
      </div>
    </div>
  );
}

function PipelineIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke={active ? '#2C80A5' : '#9b8870'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16M4 12h10M4 18h6" />
    </svg>
  );
}

function QualityIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke={active ? '#2C80A5' : '#9b8870'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 12l2 2 4-4" />
      <path d="M12 3a9 9 0 110 18 9 9 0 010-18z" />
    </svg>
  );
}

function QueryIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke={active ? '#2C80A5' : '#9b8870'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 9l3 3-3 3" />
      <path d="M14 15h3" />
      <rect x="3" y="4" width="18" height="16" rx="2" />
    </svg>
  );
}

function CatalogIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke={active ? '#2C80A5' : '#9b8870'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
      <path d="M8 7h8M8 11h5" />
    </svg>
  );
}

function NotebooksIcon({ active }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke={active ? '#2C80A5' : '#9b8870'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
      <path d="M9 8l2 2-2 2" />
      <path d="M13 12h3" />
    </svg>
  );
}
