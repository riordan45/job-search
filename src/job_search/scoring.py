from __future__ import annotations

import re
from urllib.parse import urlparse

from job_search.enums import EmployerClass, RoleTag
from job_search.models import NormalizedJob


ROLE_KEYWORDS = {
    RoleTag.ML: ["machine learning", "ml engineer", "mlops", "ai engineer"],
    RoleTag.BACKEND: ["backend", "distributed systems", "api", "python", "golang"],
    RoleTag.FULL_STACK: ["full stack", "frontend", "react", "typescript"],
    RoleTag.PLATFORM: ["platform", "infrastructure", "developer platform", "sre"],
    RoleTag.KUBERNETES: ["kubernetes", "k8s", "helm", "container orchestration"],
    RoleTag.LLM_INFRA: ["llm", "rag", "inference", "prompt", "agent"],
    RoleTag.DISTRIBUTED_SYSTEMS: ["distributed systems", "streaming", "messaging", "kafka"],
    RoleTag.DATA: ["data pipeline", "etl", "analytics", "warehouse"],
    RoleTag.FINANCE: [
        "trading",
        "quant",
        "quantitative",
        "quant trader",
        "quant researcher",
        "quant developer",
        "systematic trading",
        "risk",
        "payments",
        "capital markets",
    ],
}


def classify_role_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = [
        tag.value
        for tag, keywords in ROLE_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
    if "software engineer" in lowered and RoleTag.BACKEND.value not in tags:
        tags.append(RoleTag.BACKEND.value)
    return sorted(set(tags))


def infer_remote_mode(text: str) -> str | None:
    lowered = text.lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered:
        return "remote"
    if "on-site" in lowered or "onsite" in lowered:
        return "onsite"
    return None


COUNTRY_ALIASES = {
    "CH": ["switzerland", "zurich", "geneva", "zug", "bern", "basel", "lausanne"],
    "DE": ["germany", "deutschland", "berlin", "munich", "muenchen", "hamburg", "cologne", "stuttgart"],
    "NL": ["netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven", "holland"],
    "RO": ["romania", "bucharest", "cluj", "timisoara", "iasi"],
}

NON_TARGET_COUNTRY_ALIASES = {
    "AR": ["argentina", "buenos aires", "caba"],
    "AT": ["austria", "vienna"],
    "BE": ["belgium", "brussels"],
    "BO": ["bolivia", "la paz", "cochabamba", "santa cruz de la sierra"],
    "BR": ["brazil", "sao paulo", "rio de janeiro"],
    "CA": ["canada", "toronto", "vancouver", "montreal"],
    "ES": ["spain", "barcelona", "madrid", "valencia"],
    "FR": ["france", "paris"],
    "HU": ["hungary", "budapest", "szeged"],
    "IE": ["ireland", "dublin"],
    "IT": ["italy", "milan", "rome"],
    "PL": ["poland", "warsaw", "krakow"],
    "PT": ["portugal", "lisbon"],
    "SE": ["sweden", "stockholm"],
    "UK": ["united kingdom", "london"],
    "US": ["united states", "usa", "new york", "chicago", "san francisco"],
    "UY": ["uruguay", "montevideo"],
}

GLOBAL_SCOPE_TERMS = [
    "global",
    "worldwide",
    "emea",
    "apac",
    "americas",
    "europe",
    "western europe",
    "eastern europe",
    "southern europe",
    "northern europe",
    "remote-anywhere",
]


def detect_country(text: str, default: str | None = None) -> str | None:
    lowered = text.lower()
    tokens = {token.strip(",.()") for token in lowered.replace("/", " ").replace("-", " ").split()}
    if "de" in tokens:
        return "DE"
    if "nl" in tokens:
        return "NL"
    if "ro" in tokens:
        return "RO"
    if "ch" in tokens:
        return "CH"
    for country, aliases in COUNTRY_ALIASES.items():
        if any(_contains_alias(lowered, alias) for alias in aliases):
            return country
    return default


def mentioned_target_countries(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for country, aliases in COUNTRY_ALIASES.items():
        if any(_contains_alias(lowered, alias) for alias in aliases):
            found.add(country)
    return found


def mentioned_non_target_countries(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for country, aliases in NON_TARGET_COUNTRY_ALIASES.items():
        if any(_contains_alias(lowered, alias) for alias in aliases):
            found.add(country)
    return found


def has_global_scope(text: str) -> bool:
    lowered = text.lower()
    return any(_contains_alias(lowered, term) for term in GLOBAL_SCOPE_TERMS)


def matches_target_geography(job: NormalizedJob, profile: dict) -> bool:
    target_countries = set(profile.get("target_countries", []))
    if not target_countries:
        return True
    location_text = job.location_text.strip()
    mentioned_targets = mentioned_target_countries(location_text)
    mentioned_foreign = mentioned_non_target_countries(location_text)

    if has_global_scope(location_text):
        return False
    if mentioned_foreign:
        return False
    if job.location_country_code:
        return job.location_country_code in target_countries
    if mentioned_targets:
        return bool(mentioned_targets.intersection(target_countries))

    detected = detect_country(location_text)
    if detected is not None:
        return detected in target_countries
    return job.country.value in target_countries and not location_text


def matches_search_profile(job: NormalizedJob, profile: dict) -> bool:
    if not matches_target_geography(job, profile):
        return False

    text = " ".join([job.title, job.description_text, job.requirements_text]).lower()
    if any(term.lower() in text for term in profile.get("excluded_keywords", [])):
        return False

    required_tags = set(profile.get("required_role_tags_any", []))
    if required_tags and not required_tags.intersection(job.role_tags):
        return False

    return True


def score_job(job: NormalizedJob, company_target: dict, profile: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    text = " ".join([job.title, job.description_text, job.requirements_text]).lower()
    tags = classify_role_tags(text)
    job.role_tags = tags
    job.source_kind = infer_source_kind(company_target, job.canonical_url)
    job.source_priority = source_truth_priority(company_target, job.canonical_url)

    if job.country in {"CH", "DE", "NL", "RO"}:
        score += 20
        reasons.append(f"target-country:{job.country}")
    if job.country == "NL" and job.employer_class == EmployerClass.FINANCE:
        score += 20
        reasons.append("nl-finance-boost")
    if job.employer_class == EmployerClass.BIG_TECH:
        score += 18
        reasons.append("big-tech")
    score += company_target.get("priority_weight", 0) * 3
    if company_target.get("priority_weight"):
        reasons.append("priority-company")
    if job.source_kind == "direct_company_page":
        score += 16
        reasons.append("company-page-primary")
    elif job.source_kind == "ats_company_page":
        score += 8
        reasons.append("company-page-hosted-ats")
    elif job.source_kind == "aggregator":
        score -= 8
        reasons.append("aggregator-penalty")

    profile_terms = profile.get("priority_keywords", [])
    overlap = [term for term in profile_terms if re.search(rf"\b{re.escape(term.lower())}\b", text)]
    if overlap:
        score += min(24, len(overlap) * 4)
        reasons.append(f"profile-match:{len(overlap)}")

    preferred_tags = {"ml", "backend", "platform", "kubernetes", "llm_infra", "distributed_systems"}
    matched_preferred = preferred_tags.intersection(tags)
    if matched_preferred:
        score += len(matched_preferred) * 6
        reasons.append("target-role-fit")

    if job.remote_mode == "remote":
        score += 2
        reasons.append("remote")

    return score, reasons


def _contains_alias(text: str, alias: str) -> bool:
    pattern = r"\b" + re.escape(alias).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def infer_source_kind(company_target: dict, canonical_url: str) -> str:
    explicit = company_target.get("source_kind")
    if explicit:
        return str(explicit)

    adapter = str(company_target.get("adapter", ""))
    source_name = str(company_target.get("name", ""))
    if source_name.startswith("demo-"):
        return "demo"
    if adapter == "arbeitnow":
        return "aggregator"

    careers_host = _host(company_target.get("careers_url", ""))
    posting_host = _host(canonical_url)
    if careers_host and posting_host:
        if posting_host == careers_host or posting_host.endswith(f".{careers_host}"):
            return "direct_company_page"
        if careers_host in posting_host or posting_host in careers_host:
            return "direct_company_page"
        if "greenhouse" in posting_host or "lever.co" in posting_host or "smartrecruiters" in posting_host:
            return "ats_company_page"

    if adapter in {"greenhouse", "lever", "smartrecruiters"}:
        return "ats_company_page"
    return "unknown"


def source_truth_priority(company_target: dict, canonical_url: str) -> int:
    kind = infer_source_kind(company_target, canonical_url)
    return {
        "direct_company_page": 40,
        "ats_company_page": 25,
        "unknown": 10,
        "aggregator": 0,
        "demo": -100,
    }.get(kind, 10)


def _host(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")
