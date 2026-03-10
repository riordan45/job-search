from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from job_search.config import DB_PATH
from job_search.enums import ApplicationStatus, Country, EmployerClass
from job_search.models import ApplicationRecord, JobRecord, NormalizedJob, SourceRunRecord


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_job_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location_text TEXT NOT NULL,
                    country TEXT NOT NULL,
                    location_country_code TEXT,
                    employment_type TEXT,
                    remote_mode TEXT,
                    posted_at TEXT,
                    description_text TEXT NOT NULL,
                    requirements_text TEXT NOT NULL,
                    seniority TEXT,
                    employer_class TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'unknown',
                    source_priority INTEGER NOT NULL DEFAULT 0,
                    role_tags TEXT NOT NULL,
                    language_signals TEXT NOT NULL,
                    score REAL NOT NULL,
                    score_reasons TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_name, source_job_id),
                    UNIQUE(canonical_url)
                );
                CREATE TABLE IF NOT EXISTS applications (
                    job_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    follow_up_date TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS source_runs (
                    id INTEGER PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    error_text TEXT
                );
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    filters_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_snapshots (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(source_runs)").fetchall()
            }
            if "skipped_count" not in columns:
                connection.execute(
                    "ALTER TABLE source_runs ADD COLUMN skipped_count INTEGER NOT NULL DEFAULT 0"
                )
            job_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "location_country_code" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN location_country_code TEXT")
            if "source_kind" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'unknown'")
            if "source_priority" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN source_priority INTEGER NOT NULL DEFAULT 0")

    def create_run(self, source_name: str) -> int:
        started_at = utcnow().isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO source_runs (source_name, status, started_at) VALUES (?, ?, ?)",
                (source_name, "running", started_at),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        discovered_count: int,
        inserted_count: int,
        updated_count: int,
        skipped_count: int = 0,
        error_text: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE source_runs
                SET status = ?, finished_at = ?, discovered_count = ?, inserted_count = ?, updated_count = ?, skipped_count = ?, error_text = ?
                WHERE id = ?
                """,
                (
                    status,
                    utcnow().isoformat(),
                    discovered_count,
                    inserted_count,
                    updated_count,
                    skipped_count,
                    error_text,
                    run_id,
                ),
            )

    def mark_running_runs_abandoned(self, error_text: str = "service restarted before run finished") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE source_runs
                SET status = ?, finished_at = ?, error_text = COALESCE(error_text, ?)
                WHERE status = ?
                """,
                ("abandoned", utcnow().isoformat(), error_text, "running"),
            )
            return int(cursor.rowcount)

    def upsert_job(self, job: NormalizedJob) -> tuple[int, str]:
        now = utcnow().isoformat()
        fingerprint = _fingerprint(job.company, job.title, job.country.value, job.location_text)
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM jobs
                WHERE (source_name = ? AND source_job_id = ?)
                   OR canonical_url = ?
                   OR fingerprint = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (job.source_name, job.source_job_id, job.canonical_url, fingerprint),
            ).fetchone()

            payload = (
                job.source_name,
                job.source_job_id,
                job.canonical_url,
                job.company,
                job.title,
                job.location_text,
                job.country.value,
                job.location_country_code,
                job.employment_type,
                job.remote_mode,
                _serialize_datetime(job.posted_at),
                job.description_text,
                job.requirements_text,
                job.seniority,
                job.employer_class.value,
                job.source_kind,
                job.source_priority,
                json.dumps(job.role_tags),
                json.dumps(job.language_signals),
                job.score,
                json.dumps(job.score_reasons),
                fingerprint,
                1 if job.is_active else 0,
                now,
                now,
                now,
            )

            if existing:
                connection.execute(
                    """
                    UPDATE jobs SET
                        source_name = ?, source_job_id = ?, canonical_url = ?, company = ?, title = ?, location_text = ?,
                        country = ?, location_country_code = ?, employment_type = ?, remote_mode = ?, posted_at = ?, description_text = ?,
                        requirements_text = ?, seniority = ?, employer_class = ?, source_kind = ?, source_priority = ?, role_tags = ?, language_signals = ?,
                        score = ?, score_reasons = ?, fingerprint = ?, is_active = ?, last_seen_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    self._update_payload(existing, payload, now),
                )
                job_id = int(existing["id"])
                action = "updated"
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO jobs (
                        source_name, source_job_id, canonical_url, company, title, location_text, country,
                        location_country_code, employment_type, remote_mode, posted_at, description_text, requirements_text, seniority,
                        employer_class, source_kind, source_priority, role_tags, language_signals, score, score_reasons, fingerprint, is_active,
                        last_seen_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                job_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO applications (job_id, status, notes, updated_at)
                    VALUES (?, ?, '', ?)
                    """,
                    (job_id, ApplicationStatus.NEW.value, now),
                )
                action = "inserted"

            connection.execute(
                "INSERT INTO job_snapshots (job_id, payload_json, captured_at) VALUES (?, ?, ?)",
                (job_id, json.dumps(job.model_dump(mode="json")), now),
            )
            return job_id, action

    def list_jobs(
        self,
        *,
        country: str | None = None,
        application_status: str | None = None,
        employer_class: str | None = None,
        include_inactive: bool = False,
        include_demo: bool = False,
    ) -> list[JobRecord]:
        query = """
            SELECT
                jobs.*,
                applications.status AS application_status,
                applications.notes AS application_notes,
                applications.follow_up_date AS follow_up_date
            FROM jobs
            JOIN applications ON applications.job_id = jobs.id
            WHERE 1 = 1
              AND (? OR jobs.source_name NOT LIKE 'demo-%')
        """
        params: list[str | bool] = [include_demo]
        if not include_inactive:
            query += " AND jobs.is_active = 1"
        if country:
            query += " AND jobs.country = ?"
            params.append(country)
        if application_status:
            query += " AND applications.status = ?"
            params.append(application_status)
        if employer_class:
            query += " AND jobs.employer_class = ?"
            params.append(employer_class)
        query += " ORDER BY jobs.score DESC, jobs.updated_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._job_from_row(row) for row in rows]

    def _update_payload(self, existing: sqlite3.Row, payload: tuple, now: str) -> tuple:
        incoming_priority = int(payload[16])
        existing_priority = int(existing["source_priority"])
        keep_existing_source = existing_priority > incoming_priority

        current = list(payload)
        if keep_existing_source:
            current[0] = existing["source_name"]
            current[1] = existing["source_job_id"]
            current[2] = existing["canonical_url"]
            current[15] = existing["source_kind"]
            current[16] = existing["source_priority"]

        return (
            *current[:24],
            now,
            int(existing["id"]),
        )

    def set_job_active(self, job_id: int, *, is_active: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, utcnow().isoformat(), job_id),
            )

    def get_job(self, job_id: int) -> JobRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    jobs.*,
                    applications.status AS application_status,
                    applications.notes AS application_notes,
                    applications.follow_up_date AS follow_up_date
                FROM jobs
                JOIN applications ON applications.job_id = jobs.id
                WHERE jobs.id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def update_application(
        self, job_id: int, *, status: ApplicationStatus, notes: str | None, follow_up_date: date | None
    ) -> ApplicationRecord:
        now = utcnow().isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE applications
                SET status = ?, notes = COALESCE(?, notes), follow_up_date = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, notes, follow_up_date.isoformat() if follow_up_date else None, now, job_id),
            )
            row = connection.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        return ApplicationRecord(
            job_id=int(row["job_id"]),
            status=ApplicationStatus(row["status"]),
            notes=row["notes"],
            follow_up_date=date.fromisoformat(row["follow_up_date"]) if row["follow_up_date"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_runs(self) -> list[SourceRunRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_runs ORDER BY started_at DESC, id DESC"
            ).fetchall()
        return [
            SourceRunRecord(
                id=int(row["id"]),
                source_name=row["source_name"],
                status=row["status"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                discovered_count=int(row["discovered_count"]),
                inserted_count=int(row["inserted_count"]),
                updated_count=int(row["updated_count"]),
                skipped_count=int(row["skipped_count"]),
                error_text=row["error_text"],
            )
            for row in rows
        ]

    def save_searches(self) -> None:
        defaults = {
            "Big Tech Europe": {"employer_class": "big_tech"},
            "Netherlands Finance": {"country": "NL", "employer_class": "finance"},
            "ML Platform": {"role_tags": ["ml", "platform"]},
            "Backend/Kubernetes": {"role_tags": ["backend", "kubernetes"]},
        }
        with self.connect() as connection:
            for name, filters_json in defaults.items():
                connection.execute(
                    "INSERT OR IGNORE INTO saved_searches (name, filters_json) VALUES (?, ?)",
                    (name, json.dumps(filters_json)),
                )

    def list_saved_searches(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM saved_searches ORDER BY name ASC").fetchall()
        return [{"name": row["name"], "filters": json.loads(row["filters_json"])} for row in rows]

    def save_search(self, name: str, filters: dict) -> dict:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO saved_searches (name, filters_json)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET filters_json = excluded.filters_json
                """,
                (name, json.dumps(filters)),
            )
        return {"name": name, "filters": filters}

    def _job_from_row(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=int(row["id"]),
            source_name=row["source_name"],
            source_job_id=row["source_job_id"],
            canonical_url=row["canonical_url"],
            company=row["company"],
            title=row["title"],
            location_text=row["location_text"],
            country=Country(row["country"]),
            location_country_code=row["location_country_code"],
            employment_type=row["employment_type"],
            remote_mode=row["remote_mode"],
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            description_text=row["description_text"],
            requirements_text=row["requirements_text"],
            seniority=row["seniority"],
            employer_class=EmployerClass(row["employer_class"]),
            source_kind=row["source_kind"],
            source_priority=int(row["source_priority"]),
            role_tags=json.loads(row["role_tags"]),
            language_signals=json.loads(row["language_signals"]),
            score=float(row["score"]),
            score_reasons=json.loads(row["score_reasons"]),
            is_active=bool(row["is_active"]),
            application_status=ApplicationStatus(row["application_status"]),
            application_notes=row["application_notes"],
            follow_up_date=date.fromisoformat(row["follow_up_date"]) if row["follow_up_date"] else None,
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _fingerprint(company: str, title: str, country: str, location_text: str) -> str:
    return "|".join(
        [
            _normalize(company),
            _normalize(title),
            country,
            _normalize(location_text),
        ]
    )


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())
