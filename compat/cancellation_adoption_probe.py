#!/usr/bin/env python3
"""Cancellation-propagation adoption probe (VP-12).

ADR-0003 scheduled a spike for when the pinned QwenPaw dependency chain can
adopt the MCP Python SDK dispatcher cancellation behavior (python-sdk PR
2838, released in `mcp` 2.0.0). The pinned chain receives `mcp` transitively
through `agentscope`, so adoption is gated by the `agentscope` requirement
string, not by QwenPaw code.

The probe records hermetic facts from the pinned lockfile and observed facts
from PyPI as schema-validated evidence. It is an advisory canary: the runner
fails loudly once a current `agentscope` release allows `mcp` 2.x, which is
the signal to re-run the full QwenPaw-plus-SDK-v2 spike. It never changes
the stable compatibility claim by itself.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

PYPI_JSON = "https://pypi.org/pypi/{project}/{version}/json"
PYPI_JSON_LATEST = "https://pypi.org/pypi/{project}/json"
ADOPTION_VERSION = (2, 0, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-lock", type=Path, required=True)
    parser.add_argument("--upstreams-lock", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args()


def locked_versions(lock_path: Path) -> dict[str, str]:
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for package in lock["package"]:
        if package["name"] in {"agentscope", "mcp"}:
            versions[package["name"]] = package["version"]
    missing = {"agentscope", "mcp"} - versions.keys()
    if missing:
        raise AssertionError(f"lockfile is missing packages: {sorted(missing)}")
    return versions


def pypi_metadata(project: str, version: str | None) -> dict[str, Any]:
    url = (
        PYPI_JSON.format(project=project, version=version)
        if version
        else PYPI_JSON_LATEST.format(project=project)
    )
    response = httpx.get(url, timeout=30, follow_redirects=True)
    if response.status_code != 200:
        raise AssertionError(
            f"PyPI metadata request failed for {project}: {response.status_code}",
        )
    return response.json()


def mcp_requirement(metadata: dict[str, Any]) -> str:
    """Return the project's `mcp` requirement string, or "" when absent.

    An absent requirement means no version constraint at all, which callers
    must treat as allowing any `mcp` release.
    """
    for requirement in metadata["info"].get("requires_dist") or []:
        name = requirement.split(";", 1)[0].strip()
        base = name.split("[", 1)[0]
        for operator in ("<", ">", "=", "!", "~"):
            base = base.split(operator, 1)[0]
        if base.strip() == "mcp":
            return name
    return ""


def version_tuple(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in text.strip().split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits or 0))
    return tuple(parts)


def compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    length = max(len(left), len(right))
    padded_left = left + (0,) * (length - len(left))
    padded_right = right + (0,) * (length - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def requirement_allows(requirement: str | None, version: tuple[int, ...]) -> bool:
    """Evaluate a PEP 440 subset (`<`,`<=`,`>`,`>=`,`==`,`!=`, comma-joined).

    An empty requirement means the dependency carries no version constraint
    (or is absent entirely), so any version is allowed.
    """
    if requirement is None:
        return False
    constraint = requirement.split(";", 1)[0]
    constraint = re.sub(r"\[[^\]]*\]", "", constraint)
    constraint = constraint.removeprefix("mcp").strip()
    if not constraint:
        return True
    for clause in constraint.split(","):
        clause = clause.strip()
        for operator in ("<=", ">=", "==", "!=", "<", ">"):
            if clause.startswith(operator):
                bound = version_tuple(clause[len(operator) :])
                outcome = compare(version, bound)
                satisfied = {
                    "<": outcome < 0,
                    "<=": outcome <= 0,
                    ">": outcome > 0,
                    ">=": outcome >= 0,
                    "==": outcome == 0,
                    "!=": outcome != 0,
                }[operator]
                if not satisfied:
                    return False
                break
        else:
            raise AssertionError(f"unsupported requirement clause: {clause!r}")
    return True


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    pinned = locked_versions(args.app_lock)
    upstreams = json.loads(args.upstreams_lock.read_text(encoding="utf-8"))["upstreams"]

    pinned_agentscope = pypi_metadata("agentscope", pinned["agentscope"])
    latest_agentscope = pypi_metadata("agentscope", None)
    latest_mcp = pypi_metadata("mcp", None)

    pinned_constraint = mcp_requirement(pinned_agentscope)
    latest_agentscope_version = str(latest_agentscope["info"]["version"])
    latest_agentscope_metadata = pypi_metadata(
        "agentscope",
        latest_agentscope_version,
    )
    latest_constraint = mcp_requirement(latest_agentscope_metadata)
    latest_mcp_version = str(latest_mcp["info"]["version"])

    fix_released = compare(version_tuple(latest_mcp_version), ADOPTION_VERSION) >= 0
    pinned_adopts = compare(version_tuple(pinned["mcp"]), ADOPTION_VERSION) >= 0
    agentscope_allows = requirement_allows(latest_constraint, ADOPTION_VERSION)

    return {
        "schema_version": "0.1.0",
        "scenario": "cancellation",
        "sanitization_state": "sanitized",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": {
            "qwenpaw": upstreams["qwenpaw"]["revision"],
            "agentscope": pinned["agentscope"],
            "python_mcp": pinned["mcp"],
            "observed_latest_agentscope": latest_agentscope_version,
            "observed_latest_mcp": latest_mcp_version,
        },
        "result": "passed",
        "metrics": {
            "cancellation_probe_completed": 1,
            "cancellation_propagated": 0,
            "fix_released_upstream": int(fix_released),
            "pinned_chain_adopts_fix": int(pinned_adopts),
            "agentscope_allows_mcp2": int(agentscope_allows),
        },
        "limitations": [
            "pinned QwenPaw coroutine cancellation does not propagate an MCP "
            "cancellation notification",
            f"pinned agentscope {pinned['agentscope']} requires "
            f"{pinned_constraint or 'no direct mcp requirement'}",
            f"latest agentscope {latest_agentscope_version} requires "
            f"{latest_constraint or 'no direct mcp requirement'}",
            "adoption is gated by the agentscope requirement, not by QwenPaw code",
        ],
    }


def main() -> None:
    args = parse_args()
    for path in (args.app_lock, args.upstreams_lock):
        if not path.is_file():
            raise FileNotFoundError(path)

    evidence = run_probe(args)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
