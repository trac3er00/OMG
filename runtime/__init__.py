"""Runtime package for OAL."""

from .compat import (
    build_compat_gap_report,
    build_omc_gap_report,
    dispatch_compat_skill,
    dispatch_omc_skill,
    get_compat_skill_contract,
    get_omc_skill_contract,
    list_compat_skill_contracts,
    list_compat_skills,
    list_omc_skill_contracts,
    list_omc_skills,
)
from .ecosystem import ecosystem_status, list_ecosystem_repos, resolve_ecosystem_selection, sync_ecosystem_repos

__all__ = [
    "build_compat_gap_report",
    "build_omc_gap_report",
    "dispatch_compat_skill",
    "dispatch_omc_skill",
    "get_compat_skill_contract",
    "get_omc_skill_contract",
    "list_compat_skill_contracts",
    "list_compat_skills",
    "list_omc_skill_contracts",
    "list_omc_skills",
    "ecosystem_status",
    "list_ecosystem_repos",
    "resolve_ecosystem_selection",
    "sync_ecosystem_repos",
]
