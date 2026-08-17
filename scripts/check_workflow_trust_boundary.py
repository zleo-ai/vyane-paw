#!/usr/bin/env python3
"""Fail closed unless every public-repository workflow is hosted-only."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

ALLOWED_EVENTS = {"pull_request", "push", "schedule", "workflow_dispatch"}
ALLOWED_RUNNERS = {"ubuntu-24.04"}
BANNED_EVENTS = {"pull_request_target", "repository_dispatch", "workflow_run"}
KEY_LINE = re.compile(
    r"^(?P<indent> *)(?P<key>\"[^\"]+\"|'[^']+'|[A-Za-z0-9_-]+)"
    r"\s*:\s*(?P<value>.*?)\s*$"
)


def parse_key_line(line: str) -> tuple[int, str, str] | None:
    match = KEY_LINE.fullmatch(line)
    if not match:
        return None
    raw_key = match.group("key")
    key = raw_key[1:-1] if raw_key[:1] in {"'", '"'} else raw_key
    value = match.group("value").split(" #", 1)[0].strip()
    return len(match.group("indent")), key, value


def workflow_events(text: str) -> set[str]:
    """Extract block-style top-level triggers and fail closed on odd keys."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        parsed_on = parse_key_line(line)
        if parsed_on is None or parsed_on[:2] != (0, "on"):
            continue
        inline = parsed_on[2]
        if inline:
            return {"<unsupported-inline-on>"}

        block_lines: list[str] = []
        for block_line in lines[index + 1 :]:
            if not block_line.strip() or block_line.lstrip().startswith("#"):
                continue
            if not block_line[0].isspace():
                break
            block_lines.append(block_line)
        if not block_lines:
            return set()
        event_indent = min(len(line) - len(line.lstrip(" ")) for line in block_lines)
        events: set[str] = set()
        for block_line in block_lines:
            indent = len(block_line) - len(block_line.lstrip(" "))
            if indent != event_indent:
                continue
            parsed_event = parse_key_line(block_line)
            if parsed_event is None:
                events.add("<unparsed-event-key>")
            else:
                events.add(parsed_event[1])
        return events
    return set()


def workflow_paths(repo_root: Path) -> list[Path]:
    workflow_dir = repo_root / ".github" / "workflows"
    return sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))


def check_jobs(text: str) -> list[str]:
    """Validate every job using indentation-aware YAML key parsing.

    actionlint remains the syntax authority. This parser deliberately accepts
    only block-style jobs with an explicit scalar ``runs-on`` so quoted keys or
    unusual-but-valid indentation cannot hide a second runner.
    """
    errors: list[str] = []
    lines = text.splitlines()
    parsed = [
        (index, parsed_line)
        for index, line in enumerate(lines)
        if (parsed_line := parse_key_line(line))
    ]
    jobs_roots = [
        (index, value)
        for index, (indent, key, value) in parsed
        if indent == 0 and key == "jobs"
    ]
    if len(jobs_roots) != 1:
        return [f"expected exactly one top-level jobs mapping, found {len(jobs_roots)}"]

    jobs_index, jobs_value = jobs_roots[0]
    if jobs_value:
        return ["top-level jobs must use block mapping syntax"]
    block_end = len(lines)
    for index in range(jobs_index + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parsed_line = parse_key_line(line)
        if parsed_line and parsed_line[0] == 0:
            block_end = index
            break

    block_keys = [
        (index, indent, key, value)
        for index, (indent, key, value) in parsed
        if jobs_index < index < block_end and indent > 0
    ]
    if not block_keys:
        return ["jobs mapping is empty or could not be parsed"]
    job_indent = min(indent for _, indent, _, _ in block_keys)
    jobs = [entry for entry in block_keys if entry[1] == job_indent]
    if not jobs:
        return ["no job definitions found"]

    for position, (start, _, job_name, job_value) in enumerate(jobs):
        end = jobs[position + 1][0] if position + 1 < len(jobs) else block_end
        if job_value:
            errors.append(f"job {job_name}: inline job mappings are not allowed")
            continue
        property_keys = [
            entry
            for entry in block_keys
            if start < entry[0] < end and entry[1] > job_indent
        ]
        if not property_keys:
            errors.append(f"job {job_name}: no explicit properties found")
            continue
        property_indent = min(entry[1] for entry in property_keys)
        properties = [entry for entry in property_keys if entry[1] == property_indent]
        if any(key == "uses" for _, _, key, _ in properties):
            errors.append(f"job {job_name}: reusable workflow jobs are not allowed")
        runners = [value for _, _, key, value in properties if key == "runs-on"]
        if len(runners) != 1:
            errors.append(
                f"job {job_name}: expected exactly one explicit runs-on, found {len(runners)}"
            )
            continue
        runner = runners[0]
        if len(runner) >= 2 and runner[0] == runner[-1] and runner[0] in {"'", '"'}:
            runner = runner[1:-1]
        if runner not in ALLOWED_RUNNERS:
            errors.append(
                f"job {job_name}: runner is not allowlisted: {runner}; "
                f"allowed={sorted(ALLOWED_RUNNERS)}"
            )
    return errors


def check_workflows(repo_root: Path) -> list[str]:
    errors: list[str] = []
    paths = workflow_paths(repo_root)
    if not paths:
        return ["no workflow files found"]

    for path in paths:
        relative = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8")
        events = workflow_events(text)
        if not events:
            errors.append(f"{relative}: workflow events could not be determined")
        banned = events.intersection(BANNED_EVENTS)
        if banned:
            errors.append(f"{relative}: banned workflow events: {sorted(banned)}")
        unknown = events.difference(ALLOWED_EVENTS)
        if unknown:
            errors.append(f"{relative}: events are not allowlisted: {sorted(unknown)}")

        if "self-hosted" in text.lower():
            errors.append(
                f"{relative}: public repository must not reference self-hosted"
            )
        errors.extend(f"{relative}: {error}" for error in check_jobs(text))

    return errors


def write_workflow(repo_root: Path, name: str, content: str) -> None:
    workflow_dir = repo_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / name).write_text(content, encoding="utf-8")


def expect_rejected(name: str, content: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_workflow(root, name, content)
        errors = check_workflows(root)
        assert errors, f"unsafe fixture unexpectedly accepted: {name}"


def self_test() -> None:
    hosted = """name: quality
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-24.04
"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_workflow(root, "quality.yml", hosted)
        assert check_workflows(root) == []

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_workflow(
            root,
            "quoted.yml",
            hosted.replace("runs-on", '"runs-on"').replace(
                "ubuntu-24.04", '"ubuntu-24.04"'
            ),
        )
        assert check_workflows(root) == []

    expect_rejected(
        "self-hosted.yml",
        hosted.replace("ubuntu-24.04", "[self-hosted, vyane-paw]"),
    )
    expect_rejected("custom-label.yml", hosted.replace("ubuntu-24.04", "vyane-paw"))
    expect_rejected(
        "expression.yml", hosted.replace("ubuntu-24.04", "${{ matrix.runner }}")
    )
    expect_rejected("workflow-run.yml", hosted.replace("pull_request", "workflow_run"))
    expect_rejected(
        "workflow-run-custom-label.yml",
        hosted.replace("pull_request", "workflow_run").replace(
            "ubuntu-24.04", "vyane-paw"
        ),
    )
    expect_rejected(
        "pull-request-target.yml",
        hosted.replace("pull_request", "pull_request_target"),
    )
    expect_rejected(
        "repository-dispatch.yml",
        hosted.replace("pull_request", "repository_dispatch"),
    )
    expect_rejected(
        "escaped-event-key.yml",
        """name: escaped event
on:
  pull_request:
  "workflow_\\u0072un":
    workflows: [quality]
    types: [completed]
jobs:
  test:
    runs-on: ubuntu-24.04
""",
    )
    expect_rejected(
        "inline-event-map.yml",
        """name: inline event
on: {pull_request: {}, "workflow_\\u0072un": {workflows: [quality], types: [completed]}}
jobs:
  test:
    runs-on: ubuntu-24.04
""",
    )
    expect_rejected(
        "reusable.yml",
        """name: reusable
on:
  pull_request:
jobs:
  call:
    uses: owner/repository/.github/workflows/ci.yml@main
""",
    )
    expect_rejected(
        "quoted-second-runner.yml",
        hosted.replace(
            "  test:\n    runs-on: ubuntu-24.04",
            '  safe:\n    runs-on: ubuntu-24.04\n  other:\n    "runs-on": windows-latest',
        ),
    )
    expect_rejected(
        "deeply-indented-reusable.yml",
        """name: reusable
on:
  pull_request:
jobs:
    call:
      uses: owner/repository/.github/workflows/ci.yml@main
""",
    )
    print("Workflow trust-boundary self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    errors = check_workflows(args.repo_root.resolve())
    if errors:
        for error in errors:
            print(f"workflow trust boundary: {error}")
        return 1
    print("Workflow trust boundary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
