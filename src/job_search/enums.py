from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    CH = "CH"
    DE = "DE"
    NL = "NL"
    RO = "RO"


class EmployerClass(StrEnum):
    BIG_TECH = "big_tech"
    FINANCE = "finance"
    STARTUP = "startup"
    ENTERPRISE = "enterprise"
    RESEARCH_PUBLIC = "research_public"
    OTHER = "other"


class ApplicationStatus(StrEnum):
    NEW = "new"
    SAVED = "saved"
    REVIEWING = "reviewing"
    APPLIED = "applied"
    REJECTED = "rejected"
    CLOSED = "closed"
    IGNORE = "ignore"


class RoleTag(StrEnum):
    ML = "ml"
    BACKEND = "backend"
    FULL_STACK = "full_stack"
    PLATFORM = "platform"
    KUBERNETES = "kubernetes"
    LLM_INFRA = "llm_infra"
    DISTRIBUTED_SYSTEMS = "distributed_systems"
    DATA = "data"
    FINANCE = "finance"
