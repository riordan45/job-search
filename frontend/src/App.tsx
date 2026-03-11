import { useEffect, useMemo, useRef, useState } from "react";

type JobStatus = "new" | "saved" | "reviewing" | "applied" | "ignore";

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
  language_signals: string[];
  application_status: JobStatus;
  canonical_url: string;
  description_text?: string;
  requirements_text?: string;
  seniority?: string | null;
  source_name?: string;
};

type Run = {
  id: number;
  source_name: string;
  status: string;
  inserted_count: number;
  updated_count: number;
  skipped_count?: number;
};

type Source = {
  name: string;
  company_name: string;
  adapter: string;
  country: string;
  employer_class: string;
  priority_weight: number;
  careers_url: string;
  enabled: boolean;
  source_kind?: string | null;
  board_token?: string | null;
  company_slug?: string | null;
  company_identifier?: string | null;
  job_board_name?: string | null;
  api_url?: string | null;
  domain?: string | null;
  queries?: string[] | null;
  search_locations?: string[] | null;
  target_country_codes?: string[] | null;
  target_country_names?: string[] | null;
  max_pages?: number | null;
  page_size?: number | null;
  limit?: number | null;
  run_count: number;
  success_rate: number;
  last_run_status?: string | null;
  discovered_total: number;
  inserted_total: number;
  updated_total: number;
  skipped_total: number;
  retained_job_count: number;
  yield_rate: number;
};

type RunStatus = {
  running: boolean;
  running_sources: string[];
  completed_sources: number;
  total_sources: number;
  failed_sources: string[];
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
const STATUS_OPTIONS: JobStatus[] = ["saved", "reviewing", "applied", "ignore"];
const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "All" },
  { value: "new", label: "New" },
  { value: "saved", label: "Saved" },
  { value: "reviewing", label: "Reviewing" },
  { value: "applied", label: "Applied" },
  { value: "ignore", label: "Ignored" },
];

function statusLabel(status: string) {
  switch (status) {
    case "saved":
      return "Saved";
    case "reviewing":
      return "Reviewing";
    case "applied":
      return "Applied";
    case "ignore":
      return "Ignored";
    default:
      return "New";
  }
}

function employerLabel(value: string) {
  return value.split("_").join(" ");
}

function languageLabel(value: string) {
  return value;
}

export function App() {
  const detailScrollRef = useRef<HTMLDivElement | null>(null);
  const stickyControlsRef = useRef<HTMLDivElement | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [country, setCountry] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [showConfig, setShowConfig] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [controlsStuck, setControlsStuck] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus>({
    running: false,
    running_sources: [],
    completed_sources: 0,
    total_sources: 0,
    failed_sources: [],
  });
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
    const nextJobs = data.items as Job[];
    setJobs(nextJobs);
    setSelectedJobId((current) => {
      if (nextJobs.length === 0) return null;
      return nextJobs.some((job) => job.id === current) ? current : nextJobs[0].id;
    });
  }

  async function loadRuns() {
    const response = await fetch(`${API_BASE}/runs`);
    const data = await response.json();
    setRuns(data.items);
  }

  async function loadSources() {
    const response = await fetch(`${API_BASE}/sources?include_disabled=true`);
    const data = await response.json();
    setSources(data.items);
  }

  async function triggerRun(sourceNames?: string[]) {
    setIsRefreshing(true);
    try {
      const startResponse = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_names: sourceNames ?? [] }),
      });
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
        const statusData = (await statusResponse.json()) as RunStatus;
        const runsData = await runsResponse.json();
        setRunStatus(statusData);
        setRuns(runsData.items);
        running = Boolean(statusData.running);
      }

      setRunStatus({
        running: false,
        running_sources: [],
        completed_sources: 0,
        total_sources: 0,
        failed_sources: [],
      });
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

  async function updateSourceEnabled(source: Source, enabled: boolean) {
    setSources((current) =>
      current.map((item) => (item.name === source.name ? { ...item, enabled } : item)),
    );
    try {
      await fetch(`${API_BASE}/sources/${source.name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: source.name,
          company_name: source.company_name,
          adapter: source.adapter,
          country: source.country,
          employer_class: source.employer_class,
          source_kind: source.source_kind ?? undefined,
          enabled,
          priority_weight: source.priority_weight,
          careers_url: source.careers_url,
          board_token: source.board_token ?? undefined,
          company_slug: source.company_slug ?? undefined,
          company_identifier: source.company_identifier ?? undefined,
          job_board_name: source.job_board_name ?? undefined,
          api_url: source.api_url ?? undefined,
          domain: source.domain ?? undefined,
          queries: source.queries ?? undefined,
          search_locations: source.search_locations ?? undefined,
          target_country_codes: source.target_country_codes ?? undefined,
          target_country_names: source.target_country_names ?? undefined,
          max_pages: source.max_pages ?? undefined,
          page_size: source.page_size ?? undefined,
          limit: source.limit ?? undefined,
        }),
      });
      await loadSources();
    } catch (error) {
      setSources((current) =>
        current.map((item) => (item.name === source.name ? { ...item, enabled: source.enabled } : item)),
      );
      throw error;
    }
  }

  function applyStatusLocally(jobId: number, nextStatus: JobStatus) {
    setJobs((current) =>
      current.map((job) => (job.id === jobId ? { ...job, application_status: nextStatus } : job)),
    );
  }

  async function updateStatus(jobId: number, nextStatus: JobStatus) {
    applyStatusLocally(jobId, nextStatus);
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

  useEffect(() => {
    let cancelled = false;

    async function pollStatus() {
      const response = await fetch(`${API_BASE}/runs/status`);
      const data = (await response.json()) as RunStatus;
      if (!cancelled) {
        setRunStatus(data);
        setIsRefreshing(Boolean(data.running));
      }
    }

    void pollStatus();
    const interval = window.setInterval(() => {
      void pollStatus();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!detailScrollRef.current) return;
    detailScrollRef.current.scrollTo({ top: 0, behavior: "auto" });
  }, [selectedJobId]);

  useEffect(() => {
    function syncStickyState() {
      const element = stickyControlsRef.current;
      if (!element) return;
      const top = element.getBoundingClientRect().top;
      setControlsStuck(top <= 0);
    }

    syncStickyState();
    window.addEventListener("scroll", syncStickyState, { passive: true });
    window.addEventListener("resize", syncStickyState);
    return () => {
      window.removeEventListener("scroll", syncStickyState);
      window.removeEventListener("resize", syncStickyState);
    };
  }, []);

  const latestRun = runs[0];
  const quickSourceNames = sources
    .filter(
      (source) =>
        source.enabled && (source.employer_class === "big_tech" || source.employer_class === "finance"),
    )
    .map((source) => source.name);
  const restSourceNames = sources
    .filter(
      (source) =>
        source.enabled && source.employer_class !== "big_tech" && source.employer_class !== "finance",
    )
    .map((source) => source.name);
  const activeSourcesLabel = runStatus.running_sources.slice(0, 3).join(", ");
  const activeSourcesExtra =
    runStatus.running_sources.length > 3 ? ` +${runStatus.running_sources.length - 3} more` : "";
  const progressLabel =
    runStatus.total_sources > 0
      ? `${runStatus.completed_sources}/${runStatus.total_sources} sources done`
      : "starting...";

  const displayedJobs = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return jobs;
    return jobs.filter((job) =>
      [
        job.title,
        job.company,
        job.location_text,
        job.country,
        ...job.role_tags,
        ...job.language_signals,
        employerLabel(job.employer_class),
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [jobs, query]);

  const selectedJob =
    displayedJobs.find((job) => job.id === selectedJobId) ??
    jobs.find((job) => job.id === selectedJobId) ??
    displayedJobs[0] ??
    null;

  const counts = useMemo(() => {
    return jobs.reduce<Record<string, number>>(
      (acc, job) => {
        acc[job.application_status] = (acc[job.application_status] ?? 0) + 1;
        return acc;
      },
      { new: 0, saved: 0, reviewing: 0, applied: 0, ignore: 0 },
    );
  }, [jobs]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-title">
          <p className="eyebrow">Europe job search workspace</p>
          <h1>Review, tag, open, apply.</h1>
        </div>
        <div className="topbar-actions">
          <button className="ghost" onClick={() => setShowConfig((value) => !value)}>
            {showConfig ? "Hide source settings" : "Source settings"}
          </button>
          <button
            className="primary"
            onClick={() => void triggerRun(quickSourceNames)}
            disabled={isRefreshing || quickSourceNames.length === 0}
          >
            {isRefreshing ? `Refreshing ${progressLabel}` : `Quick refresh (${quickSourceNames.length})`}
          </button>
          <button
            className="ghost"
            onClick={() => void triggerRun(restSourceNames)}
            disabled={isRefreshing || restSourceNames.length === 0}
          >
            Refresh rest ({restSourceNames.length})
          </button>
        </div>
      </header>

      <div
        ref={stickyControlsRef}
        className={`sticky-controls ${controlsStuck ? "is-stuck" : ""}`}
      >
        <section className="command-bar">
          <div className="command-left">
            <input
              className="search-input"
              placeholder="Filter jobs by title, company, location, or tags"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <select value={country} onChange={(event) => setCountry(event.target.value)}>
              <option value="">All countries</option>
              <option value="CH">Switzerland</option>
              <option value="DE">Germany</option>
              <option value="NL">Netherlands</option>
              <option value="RO">Romania</option>
            </select>
          </div>
          <div className="command-right">
            <span className="metric-pill">{displayedJobs.length} visible</span>
            <span className="metric-pill">
              {sources.filter((source) => source.enabled).length} active / {sources.length} tracked
            </span>
            {isRefreshing ? (
              <span className="metric-pill metric-live">
                {progressLabel}
                {activeSourcesLabel ? ` · ${activeSourcesLabel}${activeSourcesExtra}` : ""}
              </span>
            ) : null}
            {runStatus.failed_sources.length > 0 ? (
              <span className="metric-pill metric-warn">
                failed: {runStatus.failed_sources.slice(0, 2).join(", ")}
              </span>
            ) : null}
            {latestRun ? (
              <span className="metric-pill metric-muted">
                last: +{latestRun.inserted_count} / ~{latestRun.updated_count} / -{latestRun.skipped_count ?? 0}
              </span>
            ) : null}
          </div>
        </section>

        <section className="status-strip">
          {STATUS_FILTERS.map((item) => {
            const count = item.value ? counts[item.value] ?? 0 : jobs.length;
            const active = status === item.value;
            return (
              <button
                key={item.value || "all"}
                className={`status-tab ${active ? "active" : ""}`}
                onClick={() => setStatus(item.value)}
              >
                <span>{item.label}</span>
                <strong>{count}</strong>
              </button>
            );
          })}
        </section>
      </div>

      {showConfig ? (
        <section className="config-panel">
          <div className="config-header">
            <div>
              <h2>Tracked sources</h2>
              <p className="muted">Keep this tucked away unless you are actively expanding coverage.</p>
            </div>
            <div className="source-chips">
              {sources.slice(0, 14).map((source) => (
                <span key={source.name}>{source.company_name}</span>
              ))}
            </div>
          </div>

          <div className="source-chips">
            {sources.slice(0, 12).map((source) => (
              <span key={`${source.name}-quality`}>
                {source.company_name} · {Math.round(source.success_rate * 100)}% ok ·{" "}
                {Math.round(source.yield_rate * 100)}% yield
                {!source.enabled ? " · disabled" : ""}
              </span>
            ))}
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
              <option value="ashby">Ashby</option>
              <option value="booking_jobs">Booking.com Careers</option>
              <option value="microsoft_careers">Microsoft Careers</option>
              <option value="revolut_jobs">Revolut Careers</option>
              <option value="smartrecruiters">SmartRecruiters</option>
              <option value="uber_jobs">Uber Careers</option>
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
              onChange={(event) => setSourceForm({ ...sourceForm, company_identifier: event.target.value })}
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
                onChange={(event) => setSourceForm({ ...sourceForm, employer_class: event.target.value })}
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
                onChange={(event) => setSourceForm({ ...sourceForm, priority_weight: event.target.value })}
              />
            </div>
            <button className="primary secondary" onClick={() => void createSource()}>
              Add source
            </button>
          </div>

          <div className="source-grid">
            {sources.map((source) => (
              <article key={source.name} className={`source-card ${source.enabled ? "" : "is-disabled"}`}>
                <div className="source-card-top">
                  <div>
                    <strong>{source.company_name}</strong>
                    <p className="muted">
                      {source.name} · {source.adapter} · {source.country} · {employerLabel(source.employer_class)}
                    </p>
                  </div>
                  <button
                    className={source.enabled ? "ghost subtle" : "primary secondary"}
                    onClick={() => void updateSourceEnabled(source, !source.enabled)}
                    disabled={isRefreshing}
                  >
                    {source.enabled ? "Disable" : "Enable"}
                  </button>
                </div>
                <div className="source-card-metrics">
                  <span>{Math.round(source.success_rate * 100)}% success</span>
                  <span>{Math.round(source.yield_rate * 100)}% yield</span>
                  <span>{source.retained_job_count} kept</span>
                  <span>{source.discovered_total} seen</span>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <main className="workspace">
        <section className="queue-panel">
          <div className="queue-header">
            <div>
              <p className="eyebrow">Triage queue</p>
              <h2>{displayedJobs.length} jobs ready</h2>
            </div>
            <button className="ghost subtle" onClick={() => void triggerRun()}>
              Refresh all
            </button>
          </div>

          <div className="job-list">
            {displayedJobs.map((job) => (
              <article
                key={job.id}
                className={`job-row job-status-${job.application_status} ${selectedJob?.id === job.id ? "selected" : ""}`}
                onClick={() => setSelectedJobId(job.id)}
              >
                <div className="job-row-main">
                  <div className="job-row-copy">
                    <div className="job-row-top">
                      <h3>{job.title}</h3>
                      <span className="rank-chip">Rank {Math.round(job.score)}</span>
                    </div>
                    <p className="job-company">{job.company}</p>
                    <p className="job-subline">
                      {job.location_text || job.country} · {employerLabel(job.employer_class)}
                      {job.seniority ? ` · ${job.seniority}` : ""}
                    </p>
                    {job.language_signals.length > 0 ? (
                      <p className="job-language-line">
                        {job.language_signals.slice(0, 2).map(languageLabel).join(" · ")}
                      </p>
                    ) : null}
                  </div>
                  <span className={`status-pill status-${job.application_status}`}>
                    {statusLabel(job.application_status)}
                  </span>
                </div>

                <div className="job-row-bottom">
                  <div className="tags compact-tags">
                    {job.role_tags.slice(0, 4).map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                  <div className="row-actions">
                    <a
                      className="row-link"
                      href={job.canonical_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(event) => event.stopPropagation()}
                    >
                      Open
                    </a>
                    {STATUS_OPTIONS.map((candidate) => (
                      <button
                        key={candidate}
                        className={candidate === job.application_status ? "active" : ""}
                        onClick={(event) => {
                          event.stopPropagation();
                          void updateStatus(job.id, candidate);
                        }}
                      >
                        {statusLabel(candidate)}
                      </button>
                    ))}
                  </div>
                </div>
              </article>
            ))}
            {displayedJobs.length === 0 ? (
              <div className="empty-state">
                <h2>No jobs in view</h2>
                <p className="muted">Change the filters or refresh sources.</p>
              </div>
            ) : null}
          </div>
        </section>

        <aside className="detail-panel">
          <div ref={detailScrollRef} className="detail-sticky">
            {selectedJob ? (
              <div className="detail-content">
                <div className="detail-hero">
                  <div className="detail-copy">
                    <p className="eyebrow">Selected job</p>
                    <h2>{selectedJob.title}</h2>
                    <p className="job-company">{selectedJob.company}</p>
                    <p className="job-subline">
                      {selectedJob.location_text || selectedJob.country} ·{" "}
                      {employerLabel(selectedJob.employer_class)}
                    </p>
                    {selectedJob.language_signals.length > 0 ? (
                      <div className="detail-language-row">
                        {selectedJob.language_signals.map((signal) => (
                          <span key={signal} className="language-pill">
                            {languageLabel(signal)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="detail-meta">
                      <span className={`status-pill status-${selectedJob.application_status}`}>
                        {statusLabel(selectedJob.application_status)}
                      </span>
                      <span className="rank-large">Rank {Math.round(selectedJob.score)}</span>
                    </div>
                  </div>
                </div>

                <a className="primary open-button" href={selectedJob.canonical_url} target="_blank" rel="noreferrer">
                  Open position
                </a>

                <div className="detail-actions">
                  {STATUS_OPTIONS.map((candidate) => (
                    <button
                      key={candidate}
                      className={candidate === selectedJob.application_status ? "active" : ""}
                      onClick={() => void updateStatus(selectedJob.id, candidate)}
                    >
                      {statusLabel(candidate)}
                    </button>
                  ))}
                </div>

                <div className="detail-block">
                  <h3>Why it ranked</h3>
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

                <div className="detail-block prose-block">
                  <h3>Job description</h3>
                  <p>{selectedJob.description_text || "No normalized description available yet."}</p>
                </div>

                <div className="detail-block prose-block">
                  <h3>Requirements</h3>
                  <p>{selectedJob.requirements_text || "No normalized requirements available yet."}</p>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <h2>No job selected</h2>
                <p className="muted">Pick a row from the queue to inspect details.</p>
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
