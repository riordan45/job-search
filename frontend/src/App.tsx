import { useEffect, useState } from "react";

type Job = {
  id: number;
  company: string;
  title: string;
  country: string;
  location_text: string;
  employer_class: string;
  score: number;
  score_reasons: string[];
  role_tags: string[];
  application_status: string;
  canonical_url: string;
};

type Run = {
  id: number;
  source_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  discovered_count: number;
  inserted_count: number;
  updated_count: number;
  skipped_count?: number;
  error_text: string | null;
};

type Source = {
  name: string;
  company_name: string;
  adapter: string;
  country: string;
  employer_class: string;
  priority_weight: number;
  careers_url: string;
};

type SourceFormState = {
  name: string;
  company_name: string;
  adapter: string;
  country: string;
  employer_class: string;
  priority_weight: string;
  careers_url: string;
  board_token: string;
  company_identifier: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:38471";
const STATUS_OPTIONS = ["saved", "reviewing", "applied", "ignore"];

export function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [country, setCountry] = useState("");
  const [status, setStatus] = useState("");
  const [showConfig, setShowConfig] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [sourceForm, setSourceForm] = useState<SourceFormState>({
    name: "",
    company_name: "",
    adapter: "greenhouse",
    country: "DE",
    employer_class: "enterprise",
    priority_weight: "3",
    careers_url: "",
    board_token: "",
    company_identifier: "",
  });

  async function loadJobs() {
    const params = new URLSearchParams();
    if (country) params.set("country", country);
    if (status) params.set("application_status", status);
    const response = await fetch(`${API_BASE}/jobs?${params.toString()}`);
    const data = await response.json();
    setJobs(data.items);
    if (data.items.length === 0) {
      setSelectedJob(null);
      return;
    }
    setSelectedJob((current) => data.items.find((job: Job) => job.id === current?.id) ?? data.items[0]);
  }

  async function loadRuns() {
    const response = await fetch(`${API_BASE}/runs`);
    const data = await response.json();
    setRuns(data.items);
  }

  async function loadSources() {
    const response = await fetch(`${API_BASE}/sources`);
    const data = await response.json();
    setSources(data.items);
  }

  async function triggerRun() {
    setIsRefreshing(true);
    try {
      const startResponse = await fetch(`${API_BASE}/runs`, { method: "POST" });
      const startData = await startResponse.json();
      const runState = startData.items?.[0]?.status;
      if (runState === "already_running") {
        return;
      }

      let running = true;
      while (running) {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        const [statusResponse, runsResponse] = await Promise.all([
          fetch(`${API_BASE}/runs/status`),
          fetch(`${API_BASE}/runs`),
        ]);
        const statusData = await statusResponse.json();
        const runsData = await runsResponse.json();
        setRuns(runsData.items);
        running = Boolean(statusData.running);
      }

      await loadJobs();
    } finally {
      setIsRefreshing(false);
    }
  }

  async function createSource() {
    const payload = {
      ...sourceForm,
      priority_weight: Number(sourceForm.priority_weight),
      board_token: sourceForm.board_token || undefined,
      company_identifier: sourceForm.company_identifier || undefined,
    };
    await fetch(`${API_BASE}/sources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSourceForm((current) => ({
      ...current,
      name: "",
      company_name: "",
      careers_url: "",
      board_token: "",
      company_identifier: "",
    }));
    await loadSources();
  }

  async function updateStatus(jobId: number, nextStatus: string) {
    await fetch(`${API_BASE}/applications/${jobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus }),
    });
    await loadJobs();
  }

  useEffect(() => {
    void Promise.all([loadJobs(), loadRuns(), loadSources()]);
  }, [country, status]);

  const latestRun = runs[0];

  return (
    <div className="shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Europe job search tracker</p>
          <h1>ML and software roles across your target countries.</h1>
          <p className="lede">
            One button refresh. Ranked inbox on the left. Sticky detail panel on the right.
          </p>
        </div>
        <div className="hero-actions">
          <button className="ghost" onClick={() => setShowConfig((value) => !value)}>
            {showConfig ? "Hide source settings" : "Source settings"}
          </button>
          <button className="primary" onClick={() => void triggerRun()} disabled={isRefreshing}>
            {isRefreshing ? "Refreshing..." : "Refresh target jobs"}
          </button>
        </div>
      </header>

      <section className="toolbar">
        <div className="toolbar-filters">
          <select value={country} onChange={(event) => setCountry(event.target.value)}>
            <option value="">All countries</option>
            <option value="CH">Switzerland</option>
            <option value="DE">Germany</option>
            <option value="NL">Netherlands</option>
            <option value="RO">Romania</option>
          </select>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All statuses</option>
            <option value="new">New</option>
            <option value="saved">Saved</option>
            <option value="reviewing">Reviewing</option>
            <option value="applied">Applied</option>
            <option value="ignore">Ignore</option>
          </select>
        </div>
        <div className="toolbar-stats">
          <span>{jobs.length} visible jobs</span>
          <span>{sources.length} sources</span>
          {latestRun ? (
            <span>
              last run: +{latestRun.inserted_count} / ~{latestRun.updated_count} / -{latestRun.skipped_count ?? 0}
            </span>
          ) : null}
        </div>
      </section>

      {showConfig ? (
        <section className="config-panel">
          <div className="config-header">
            <div>
              <h2>Tracked sources</h2>
              <p className="muted">Add sources here when you want more coverage. Keep this hidden otherwise.</p>
            </div>
            <div className="source-chips">
              {sources.slice(0, 10).map((source) => (
                <span key={source.name}>{source.company_name}</span>
              ))}
            </div>
          </div>

          <div className="source-form">
            <input
              placeholder="source name"
              value={sourceForm.name}
              onChange={(event) => setSourceForm({ ...sourceForm, name: event.target.value })}
            />
            <input
              placeholder="company"
              value={sourceForm.company_name}
              onChange={(event) => setSourceForm({ ...sourceForm, company_name: event.target.value })}
            />
            <select
              value={sourceForm.adapter}
              onChange={(event) => setSourceForm({ ...sourceForm, adapter: event.target.value })}
            >
              <option value="greenhouse">Greenhouse</option>
              <option value="smartrecruiters">SmartRecruiters</option>
              <option value="lever">Lever</option>
            </select>
            <input
              placeholder="board token / slug"
              value={sourceForm.board_token}
              onChange={(event) => setSourceForm({ ...sourceForm, board_token: event.target.value })}
            />
            <input
              placeholder="smartrecruiters identifier"
              value={sourceForm.company_identifier}
              onChange={(event) =>
                setSourceForm({ ...sourceForm, company_identifier: event.target.value })
              }
            />
            <input
              placeholder="careers url"
              value={sourceForm.careers_url}
              onChange={(event) => setSourceForm({ ...sourceForm, careers_url: event.target.value })}
            />
            <div className="source-form-row">
              <select
                value={sourceForm.country}
                onChange={(event) => setSourceForm({ ...sourceForm, country: event.target.value })}
              >
                <option value="CH">CH</option>
                <option value="DE">DE</option>
                <option value="NL">NL</option>
                <option value="RO">RO</option>
              </select>
              <select
                value={sourceForm.employer_class}
                onChange={(event) =>
                  setSourceForm({ ...sourceForm, employer_class: event.target.value })
                }
              >
                <option value="big_tech">big_tech</option>
                <option value="finance">finance</option>
                <option value="enterprise">enterprise</option>
                <option value="startup">startup</option>
                <option value="other">other</option>
              </select>
              <input
                placeholder="priority"
                value={sourceForm.priority_weight}
                onChange={(event) =>
                  setSourceForm({ ...sourceForm, priority_weight: event.target.value })
                }
              />
            </div>
            <button className="primary secondary" onClick={() => void createSource()}>
              Add source
            </button>
          </div>
        </section>
      ) : null}

      <main className="workspace">
        <section className="panel inbox-panel">
          <div className="panel-header">
            <h2>Inbox</h2>
            <span>{jobs.length}</span>
          </div>
          <div className="job-list">
            {jobs.map((job) => (
              <button
                key={job.id}
                className={`job-card ${selectedJob?.id === job.id ? "selected" : ""}`}
                onClick={() => setSelectedJob(job)}
              >
                <div className="job-topline">
                  <strong>{job.title}</strong>
                  <span className="score">{Math.round(job.score)}</span>
                </div>
                <div className="job-company">{job.company}</div>
                <div className="muted">
                  {job.location_text || job.country} · {job.employer_class}
                </div>
                <div className="tags compact-tags">
                  {job.role_tags.slice(0, 4).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="panel detail-panel">
          <div className="detail-sticky">
            {selectedJob ? (
              <div className="detail-content">
                <div className="detail-head">
                  <div>
                    <p className="eyebrow">Selected job</p>
                    <h2>{selectedJob.title}</h2>
                    <p className="job-company">{selectedJob.company}</p>
                    <p className="muted">{selectedJob.location_text || selectedJob.country}</p>
                  </div>
                  <div className="score-badge">{Math.round(selectedJob.score)}</div>
                </div>

                <div className="action-row">
                  <a className="ghost link-button" href={selectedJob.canonical_url} target="_blank" rel="noreferrer">
                    Open posting
                  </a>
                  {STATUS_OPTIONS.map((candidate) => (
                    <button
                      key={candidate}
                      className={candidate === selectedJob.application_status ? "selected-status" : ""}
                      onClick={() => void updateStatus(selectedJob.id, candidate)}
                    >
                      {candidate}
                    </button>
                  ))}
                </div>

                <div className="detail-block">
                  <h3>Why this is here</h3>
                  <div className="tags">
                    {selectedJob.score_reasons.map((reason) => (
                      <span key={reason}>{reason}</span>
                    ))}
                  </div>
                </div>

                <div className="detail-block">
                  <h3>Role tags</h3>
                  <div className="tags">
                    {selectedJob.role_tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                </div>

                <div className="detail-block">
                  <h3>Run activity</h3>
                  <div className="run-list">
                    {runs.slice(0, 8).map((run) => (
                      <div key={run.id} className="run-card">
                        <strong>{run.source_name}</strong>
                        <div className="muted">
                          {run.status} · +{run.inserted_count} / ~{run.updated_count} / -{run.skipped_count ?? 0}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <h2>No jobs in view</h2>
                <p className="muted">Try another country filter or run a refresh.</p>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
