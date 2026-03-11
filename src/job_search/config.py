from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "job_search.db"
LOCAL_TARGETS_PATH = DATA_DIR / "company_targets.local.json"
LOCAL_PROFILE_PATH = DATA_DIR / "profile.local.json"


def load_json_config(name: str) -> list[dict]:
    return json.loads((CONFIG_DIR / name).read_text())


@lru_cache
def load_company_targets() -> list[dict]:
    merged: dict[str, dict] = {}
    for target in load_json_config("company_targets.json"):
        normalized = _normalize_target(target)
        merged[normalized["name"]] = normalized
    for target in load_local_company_targets():
        normalized = _normalize_target(target)
        merged[normalized["name"]] = normalized
    return list(merged.values())


def load_active_company_targets(*, include_demo: bool = False) -> list[dict]:
    targets = load_company_targets()
    active = [target for target in targets if target.get("enabled", True)]
    if include_demo:
        return active
    return [target for target in active if not target.get("is_demo")]


def load_local_company_targets() -> list[dict]:
    if not LOCAL_TARGETS_PATH.exists():
        return []
    return json.loads(LOCAL_TARGETS_PATH.read_text())


def save_local_company_target(target: dict) -> dict:
    target = _normalize_target(target)
    targets = load_local_company_targets()
    targets = [item for item in targets if item["name"] != target["name"]]
    targets.append(target)
    LOCAL_TARGETS_PATH.write_text(json.dumps(targets, indent=2) + "\n")
    load_company_targets.cache_clear()
    return target


def load_profile() -> dict:
    profile = json.loads((CONFIG_DIR / "profile.json").read_text())
    if LOCAL_PROFILE_PATH.exists():
        profile.update(json.loads(LOCAL_PROFILE_PATH.read_text()))
    return profile


def save_profile(profile: dict) -> dict:
    LOCAL_PROFILE_PATH.write_text(json.dumps(profile, indent=2) + "\n")
    return profile


def _normalize_target(target: dict) -> dict:
    normalized = dict(target)
    normalized["enabled"] = bool(normalized.get("enabled", True))
    return normalized
