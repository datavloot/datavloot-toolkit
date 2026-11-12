'use client';
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { useApi, formatTimestamp } from '../lib/hooks';

// The first page: a welcome while the project is still empty, then an overview
// that says what needs attention today. Colour only where something needs doing.
// Everything comes from the endpoints the other panels use.
export default function OverviewPanel({ onNavigate, branding }) {
  // Every 3 seconds while Dagster is starting, so the page follows it; then
  // every 30, and the pipelines load again the moment Dagster is up.
  const [healthEvery, setHealthEvery] = useState(30000);
  const health = useApi(() => api.getHealth(), [], healthEvery);
  const services = useApi(() => api.getServices(), []);
  const pipelines = useApi(() => api.getPipelineSummary(), [], 30000);
  const runs = useApi(() => api.getPipelineRuns(5), [], 30000);
  const dagsterStatus = health.data?.services?.dagster;
  useEffect(() => {
    setHealthEvery(dagsterStatus === 'starting' ? 3000 : 30000);
    if (dagsterStatus === 'ok') {
      pipelines.reload();
      runs.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dagsterStatus]);
  const quality = useApi(() => api.getQualitySummary(), [], 30000);
  const models = useApi(() => api.getCatalogModels(), []);
  const apps = useApi(() => api.getApps(), []);
  const notebooks = useApi(() => api.getNotebooks(), []);

  // #welcome shows the welcome on any project, to look at it.
  const [forceWelcome, setForceWelcome] = useState(false);
  useEffect(() => {
    const fromHash = () => setForceWelcome(window.location.hash === '#welcome');
    fromHash();
    window.addEventListener('hashchange', fromHash);
    return () => window.removeEventListener('hashchange', fromHash);
  }, []);

  const dagsterUrl = services.data?.dagster_url || 'http://localhost:3000';
  const s = health.data?.services || {};
  const p = pipelines.data?.by_status || {};
  const q = quality.data;
  // The business tables: the project's own, not those of packages such as Elementary.
  const modelCount = models.data?.business_total ?? (models.data?.models || []).filter((m) => !m.metadata).length;
  const appList = apps.data?.apps || [];
  const notebookList = notebooks.data?.notebooks || [];

  // While `datavloot start` is loading the project there is nothing to do but
  // wait (the banner above shows how long); when it failed, the banner says why.
  const dagsterStep = {
    starting: {
      help: 'Dagster is loading the project, which takes a minute or two. It ticks itself off here when it is ready.',
      waiting: true,
    },
    failed: {
      help: 'Dagster did not start; the message above says why.',
    },
  }[s.dagster] || {
    help: 'The orchestrator that runs your pipelines. Start it with datavloot start.',
    action: { label: 'Open Dagster', href: dagsterUrl },
  };

  const steps = [
    {
      title: 'Dagster is running',
      done: s.dagster === 'ok',
      ...dagsterStep,
    },
    {
      title: 'A first pipeline run succeeded',
      help: 'Put your source files in place (often the data folder), then Materialize all in Pipelines.',
      done: (p.success || 0) > 0,
      action: { label: 'Pipelines', tab: 'pipelines' },
    },
    {
      title: 'Tables in the lakehouse',
      help: 'dbt builds the tables from the raw data; they show up in the catalog.',
      done: modelCount > 0,
      action: { label: 'Catalog', tab: 'catalog' },
    },
    {
      title: 'Tests guard the data',
      help: 'dbt tests and Elementary report here on every run.',
      done: (q?.total_tests || 0) > 0,
      action: { label: 'Data quality', tab: 'quality' },
    },
    {
      title: 'A first dashboard',
      // An app without tables to read shows nothing yet (the demo's dashboard
      // before its first run), so it counts once the lakehouse has tables.
      help: appList.length > 0
        ? 'The dashboard is there; it shows data once a pipeline run has built the tables.'
        : 'A Marimo app in apps/ becomes a dashboard for everyone.',
      done: appList.length > 0 && modelCount > 0,
      action: appList.length > 0 && modelCount === 0
        ? { label: 'Pipelines', tab: 'pipelines' }
        : { label: 'Dashboards', tab: 'apps' },
    },
  ];
  const stepsDone = steps.filter((step) => step.done).length;

  // Wait only for what decides between welcome and overview; the service
  // probes fill in their hints when they answer.
  // With runs it is the overview, so the catalog count may follow.
  const hasRuns = pipelines.data?.total_runs > 0;
  const loading = pipelines.loading || (!hasRuns && models.loading);
  const empty = !loading && !(pipelines.data?.total_runs > 0) && modelCount === 0;

  if (loading && !forceWelcome) return <Loading />;

  if (empty || forceWelcome) {
    return (
      <div className="max-w-3xl w-full m-auto space-y-5 py-4">
        <Welcome onNavigate={onNavigate} />
        <Checklist steps={steps} done={stepsDone} onNavigate={onNavigate} />
      </div>
    );
  }

  return (
    // my-auto: in the middle of the screen when it fits, from the top when it scrolls.
    <div className="max-w-5xl w-full m-auto space-y-5">
      {/* Head: the date, a greeting, the quick actions */}
      <div className="page-head">
        <div>
          <div className="text-sm text-ink-3">{today()}</div>
          <h2 className="text-[28px] font-semibold text-ink-0 tracking-tight leading-tight mt-1">
            {greeting()}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <a href={dagsterUrl} target="_blank" rel="noopener noreferrer" className="btn h-9 px-4 text-sm">
            Open Dagster ↗
          </a>
          <button onClick={() => onNavigate('query')} className="btn btn-primary h-9 px-4 text-sm">
            New query
          </button>
        </div>
      </div>

      {/* Three numbers; the first in navy */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <PipelinesKpi summary={pipelines.data} error={pipelines.data?.error || pipelines.error} dagster={s.dagster} onClick={() => onNavigate('pipelines')} />
        <QualityKpi quality={q} onClick={() => onNavigate('quality')} />
        <button onClick={() => onNavigate('catalog')} className="card p-5 text-left hover:border-datavloot-200 transition-colors">
          <div className="text-xs font-semibold text-ink-2">Lakehouse</div>
          <div className="text-3xl font-semibold text-ink-0 tracking-tight mt-2 tabular-nums">{models.loading ? <span className="text-ink-3">…</span> : modelCount}</div>
          <div className="text-sm text-ink-2 mt-1">tables in the catalog →</div>
        </button>
      </div>

      {/* Hints: colour only in the stripe, the icon and the link */}
      <Hints
        s={s}
        failing={pipelines.data?.failing_jobs || []}
        q={q}
        dagsterUrl={dagsterUrl}
        onNavigate={onNavigate}
      />

      {/* The welcome's checklist, until every step is done; then one line */}
      <SetupCard steps={steps} done={stepsDone} project={services.data?.project} onNavigate={onNavigate} />

      {/* Recent runs, and what there is to open */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4 items-start">
        <section className="card overflow-hidden">
          <div className="panel-header">
            <span className="panel-title">Recent runs</span>
            <button onClick={() => onNavigate('pipelines')} className="text-xs font-medium text-datavloot-600 hover:underline">
              All runs
            </button>
          </div>
          {runs.error ? (
            <p className="px-4 py-8 text-sm text-ink-3 text-center">No runs to show: Dagster is not reachable.</p>
          ) : !runs.data?.runs?.length ? (
            <p className="px-4 py-8 text-sm text-ink-3 text-center">No runs yet.</p>
          ) : (
            <table className="w-full">
              <tbody>
                {runs.data.runs.map((run) => (
                  <tr key={run.id} className="table-row">
                    <td className="table-cell font-medium">{run.job}</td>
                    <td className="table-cell text-ink-2">{formatTimestamp(run.started_at)}</td>
                    <td className="table-cell text-right">
                      <span className={`status-badge status-${run.status} ${run.error ? 'cursor-help' : ''}`} title={run.error || undefined}>
                        {run.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card overflow-hidden">
          <div className="panel-header">
            <span className="panel-title">Open</span>
          </div>
          <ul className="divide-y divide-surface-2">
            {appList.map((app) => (
              <ShortcutRow key={app.name} kind="Dashboard" title={app.title} onClick={() => onNavigate('apps')} />
            ))}
            {notebookList.map((nb) => (
              <ShortcutRow key={nb.name} kind="Notebook" title={nb.stem || nb.name} mono onClick={() => onNavigate('notebooks')} />
            ))}
            {appList.length + notebookList.length === 0 && (
              <li className="px-4 py-6 text-sm text-ink-3">
                No dashboards or notebooks yet. Put a Marimo app in <code className="font-mono">apps/</code>.
              </li>
            )}
          </ul>
        </section>
      </div>

      <div className="text-xs text-ink-3 pt-1">
        {pipelines.data?.latest_run?.started_at
          ? `Last run: ${formatTimestamp(pipelines.data.latest_run.started_at)}`
          : 'No runs yet'}
        {' · '}DuckDB {s.duckdb === 'ok' ? 'connected' : 'offline'}
        {services.data?.version && ` · datavloot v${services.data.version}`}
      </div>
    </div>
  );
}

// The demo is a project of its own (`datavloot demo`), so the welcome does not
// offer it: nothing here could load it into this project.
function Welcome({ onNavigate }) {
  return (
    <section className="card px-8 pt-12 pb-8 text-center">
      <div className="flex flex-col items-center">
        <img src="/datavloot-logo.png" alt="" className="w-20 h-20" />
        <div className="w-24 h-1 rounded-full bg-highlight/60 mt-3" />
      </div>
      <h1 className="text-[28px] font-semibold text-ink-0 tracking-tight mt-6">
        {/* The captain, as on the overview: the project's name is in the sidebar */}
        Welcome aboard, captain!
      </h1>
      <p className="text-[15px] leading-relaxed text-ink-2 max-w-xl mx-auto mt-3">
        The Crows Nest is the lookout of your data platform: pipelines, data quality,
        the lakehouse and your dashboards in one place. Run a first pipeline to fill the lakehouse,
        or add a source of your own. Nothing here changes your data unless you ask it to.
      </p>
      <div className="flex flex-wrap justify-center gap-3 mt-7">
        {/* Pipelines, where Materialize all is: the run starts here, not in Dagster */}
        <button
          onClick={() => onNavigate('pipelines')}
          className="btn btn-primary h-11 px-6 text-sm flex-1 basis-56 max-w-xs"
        >
          <PlayIcon /> Run a first pipeline
        </button>
        <a
          href="https://github.com/datavloot/datavloot-toolkit/blob/main/docs/ingestion.md"
          target="_blank"
          rel="noopener noreferrer"
          className="btn h-11 px-6 text-sm flex-1 basis-56 max-w-xs"
        >
          <PlusIcon /> Add a source
        </a>
      </div>
    </section>
  );
}

// On the overview: the checklist as long as a step is open. Once all are done,
// one line that opens it again, and that can be put away for good (per project,
// in this browser).
function SetupCard({ steps, done, project, onNavigate }) {
  const key = `cn-setup-dismissed:${project || ''}`;
  const allDone = done === steps.length;
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(key) === '1');
    } catch {
      // No storage (private window): the line simply shows again.
    }
  }, [key]);
  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(key, '1');
    } catch {
      // Put away for this visit only.
    }
  };

  if (!allDone || open) {
    return (
      <Checklist
        steps={steps}
        done={done}
        onNavigate={onNavigate}
        onClose={allDone ? () => setOpen(false) : undefined}
      />
    );
  }
  if (dismissed) return null;
  return (
    <section className="card flex items-center gap-3 px-5 py-3">
      <span className="w-6 h-6 shrink-0 rounded-full flex items-center justify-center bg-datavloot-600 text-white">
        <CheckIcon />
      </span>
      <span className="flex-1 text-sm font-medium text-ink-0">
        All {steps.length} setup steps done. Ready to sail.
      </span>
      <button onClick={() => setOpen(true)} className="text-sm font-semibold text-datavloot-600 hover:underline">
        Show the steps
      </button>
      <button onClick={dismiss} className="btn btn-ghost h-8 px-2 text-sm" title="Do not show this again">
        Hide
      </button>
    </section>
  );
}

function Checklist({ steps, done, onNavigate, onClose }) {
  return (
    <section className="card px-6 py-5">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-base font-semibold text-ink-0 tracking-tight">Ready to sail</h2>
        <span className="text-sm text-ink-3">
          {done} of {steps.length} done
          {onClose && (
            <button onClick={onClose} className="ml-3 font-semibold text-datavloot-600 hover:underline">
              Close
            </button>
          )}
        </span>
      </div>
      <ul className="divide-y divide-surface-2">
        {steps.map((step, i) => {
          const first = !step.done && steps.findIndex((x) => !x.done) === i;
          return (
            <li key={step.title} className="flex items-center gap-4 py-3.5">
              <span
                className={`w-6 h-6 shrink-0 rounded-full flex items-center justify-center ${
                  step.done ? 'bg-datavloot-600 text-white'
                    : step.waiting ? 'ring-[1.5px] ring-inset ring-datavloot-200 text-datavloot-600'
                    : 'ring-[1.5px] ring-inset ring-surface-3'
                }`}
              >
                {step.done && <CheckIcon />}
                {!step.done && step.waiting && <span className="w-2 h-2 rounded-full bg-current pulse-dot" aria-hidden="true" />}
              </span>
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-semibold ${step.done ? 'text-ink-3 line-through decoration-surface-3' : 'text-ink-0'}`}>
                  {step.title}
                </div>
                {!step.done && <div className="text-sm text-ink-2">{step.help}</div>}
              </div>
              {!step.done && step.action && (
                step.action.href ? (
                  <a href={step.action.href} target="_blank" rel="noopener noreferrer" className={`btn ${first ? '' : 'btn-ghost'}`}>
                    {step.action.label}
                  </a>
                ) : (
                  <button onClick={() => onNavigate(step.action.tab)} className={`btn ${first ? '' : 'btn-ghost'}`}>
                    {step.action.label}
                  </button>
                )
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// The tile takes the colour of the latest run: green when it succeeded, red
// when it failed. Which jobs are still failing is in the hints below it.
const LAST_RUN = {
  success: { text: 'Last run succeeded', tile: 'bg-emerald-700 hover:bg-emerald-800' },
  failure: { text: 'Last run failed', tile: 'bg-red-700 hover:bg-red-800' },
  // Ochre while a run is under way; the darker shade keeps white text readable.
  running: { text: 'Running', tile: 'bg-highlight-700 hover:brightness-90' },
  queued: { text: 'Queued', tile: 'bg-highlight-700 hover:brightness-90' },
  cancelled: { text: 'Last run cancelled', tile: 'bg-datavloot-800 hover:bg-datavloot-900' },
};

function PipelinesKpi({ summary, error, dagster, onClick }) {
  const last = summary?.latest_run;
  const look = (last && LAST_RUN[last.status]) || { text: 'No runs yet', tile: 'bg-datavloot-800 hover:bg-datavloot-900' };
  return (
    <button
      onClick={onClick}
      className={`rounded-lg p-5 text-left transition-colors ${error ? 'bg-datavloot-800 hover:bg-datavloot-900' : look.tile} text-white shadow-sm`}
    >
      <div className="text-xs font-semibold text-white/70">Pipelines</div>
      {error && dagster === 'starting' ? (
        <>
          <div className="text-3xl font-semibold tracking-tight mt-2">Starting…</div>
          <div className="text-sm text-white/70 mt-1">Dagster is loading the project →</div>
        </>
      ) : error ? (
        <>
          <div className="text-3xl font-semibold tracking-tight mt-2">Offline</div>
          <div className="text-sm text-white/70 mt-1">Dagster is not reachable →</div>
        </>
      ) : (
        <>
          <div className="text-2xl font-semibold tracking-tight mt-2">{look.text}</div>
          <div className="text-sm text-white/70 mt-1 truncate">
            {last ? `${last.job} · ${formatTimestamp(last.started_at)}` : 'Materialize all in Pipelines'} →
          </div>
        </>
      )}
    </button>
  );
}

function QualityKpi({ quality, onClick }) {
  const score = quality?.health_score;
  const total = quality?.total_tests || 0;
  const bar = score == null ? 'bg-surface-3' : score >= 95 ? 'bg-emerald-600' : score >= 80 ? 'bg-amber-500' : 'bg-red-600';
  return (
    <button onClick={onClick} className="card p-5 text-left hover:border-datavloot-200 transition-colors">
      <div className="text-xs font-semibold text-ink-2">Data quality</div>
      <div className="text-3xl font-semibold text-ink-0 tracking-tight mt-2 tabular-nums">
        {score == null ? '—' : `${score}%`}
      </div>
      <div className="h-1.5 rounded-full bg-surface-2 mt-3 overflow-hidden">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${score ?? 0}%` }} />
      </div>
      <div className="text-sm text-ink-2 mt-2">
        {total > 0 ? `${total} tests, latest result of each →` : 'No test results yet →'}
      </div>
    </button>
  );
}

function Hints({ s, failing, q, dagsterUrl, onNavigate }) {
  const hints = [];
  // Only jobs whose latest run failed: one that succeeded since is fine again.
  for (const run of failing) {
    hints.push({
      tone: 'bad',
      text: `${run.job}: the last run failed ${formatTimestamp(run.started_at)}.`,
      title: run.error,
      link: 'See the runs',
      tab: 'pipelines',
    });
  }
  if ((q?.by_status?.fail || 0) > 0) {
    hints.push({ tone: 'bad', text: `${q.by_status.fail} test${q.by_status.fail > 1 ? 's' : ''} failing.`, link: 'See the tests', tab: 'quality' });
  }
  // Dagster starting or failed to start: the banner above every tab says so (StartupBanner).
  if (s.dagster === 'offline') {
    hints.push({ tone: 'warn', text: 'Dagster is not running, so no pipeline runs right now. Start it with datavloot start.', link: 'Open Dagster', href: dagsterUrl });
  }
  if ((q?.by_status?.warn || 0) > 0) {
    hints.push({ tone: 'warn', text: `${q.by_status.warn} test warning${q.by_status.warn > 1 ? 's' : ''}.`, link: 'See the tests', tab: 'quality' });
  }
  // The setup steps are in their own card below (SetupCard).
  if (!hints.length) return null;

  const tones = {
    bad: { stripe: 'bg-red-600', icon: 'text-red-600', link: 'text-red-700' },
    warn: { stripe: 'bg-amber-500', icon: 'text-amber-600', link: 'text-amber-800' },
    note: { stripe: 'bg-highlight', icon: 'text-highlight', link: 'text-highlight-700' },
  };
  return (
    <div className="space-y-2">
      {hints.map((hint) => {
        const t = tones[hint.tone];
        const body = (
          <>
            <span className={`absolute left-0 top-0 bottom-0 w-1 ${t.stripe}`} />
            <span className={t.icon}>{hint.tone === 'note' ? <CompassIcon /> : <AlertIcon />}</span>
            <span className="flex-1 text-sm font-medium text-ink-0">{hint.text}</span>
            <span className={`text-sm font-semibold ${t.link} whitespace-nowrap`}>{hint.link} →</span>
          </>
        );
        const cls = 'card relative overflow-hidden flex items-center gap-3 pl-5 pr-4 py-3 w-full text-left hover:bg-surface-1 transition-colors';
        return hint.href ? (
          <a key={hint.text} href={hint.href} target="_blank" rel="noopener noreferrer" className={cls} title={hint.title || undefined}>{body}</a>
        ) : (
          <button key={hint.text} onClick={() => onNavigate(hint.tab)} className={cls} title={hint.title || undefined}>{body}</button>
        );
      })}
    </div>
  );
}

function ShortcutRow({ kind, title, mono, onClick }) {
  return (
    <li>
      <button onClick={onClick} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-1 transition-colors">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-3 w-20 shrink-0">{kind}</span>
        <span className={`flex-1 text-sm font-medium text-ink-0 truncate ${mono ? 'font-mono' : ''}`}>{title}</span>
        <span className="text-ink-3">→</span>
      </button>
    </li>
  );
}

function Loading() {
  return (
    <div className="py-24 text-center">
      <div className="inline-block w-5 h-5 border-2 border-surface-3 border-t-datavloot-600 rounded-full animate-spin" />
    </div>
  );
}

function today() {
  const text = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  return text;
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 6) return 'On the night watch, captain?';
  if (hour < 12) return 'Good morning, captain!';
  if (hour < 18) return 'Good afternoon, captain!';
  return 'Good evening, captain!';
}

const iconProps = {
  width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round',
};
function PlayIcon() {
  return <svg {...iconProps} width={16} height={16}><path d="M7 4v16l13-8z" /></svg>;
}
function PlusIcon() {
  return <svg {...iconProps} width={16} height={16}><path d="M12 5v14M5 12h14" /></svg>;
}
function CheckIcon() {
  return <svg {...iconProps} width={14} height={14} strokeWidth={2.5}><path d="M5 12l5 5 9-10" /></svg>;
}
function AlertIcon() {
  return (
    <svg {...iconProps}>
      <path d="M12 3l9.5 17h-19z" />
      <path d="M12 10v4M12 17.5v.01" />
    </svg>
  );
}
function CompassIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5l-2 5-5 2 2-5z" />
    </svg>
  );
}
