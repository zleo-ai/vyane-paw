// Continuous advancement of vyane-paw work packages that require vyane-rs
// integration (对接). Re-reads live STATUS / lock / packages every run.
// Rhai — not the model — enforces: do not start vyane-paw VP-15 phase two
// (result contract / lock-consuming adoption) until the stable lock pin is
// known to contain the vyane-rs provider phase-one revision.

let meta = #{
    name: "advance-vyane-paw",
    description: "Advance vyane-paw ↔ vyane-rs integration work packages from STATUS, enforcing provider (vyane-rs) phase-one before consumer (vyane-paw) phase-two",
    when_to_use: "Continue durable-workflow or other cross-repo vyane-paw needs against vyane-rs without starting consumer phase-two early",
    phases: [
        #{ title: "Assess", detail: "tool-read STATUS, work package, lock, branches" },
        #{ title: "Gate", detail: "Rhai order gate for vyane-rs before paw adoption" },
        #{ title: "Act", detail: "status handoff or optional bounded implement" },
    ],
};

let assessment_schema = #{
    "type": "object",
    "required": [
        "priority_summary",
        "owner_repo",
        "work_package_ids",
        "provider_phase_landed_in_lock",
        "next_action",
        "verification_commands",
        "blockers",
    ],
    "properties": #{
        "priority_summary": #{ "type": "string", "minLength": 1 },
        "owner_repo": #{
            "type": "string",
            "enum": ["vyane-rs", "vyane-paw", "both", "blocked", "none"],
        },
        "work_package_ids": #{
            "type": "array",
            "items": #{ "type": "string" },
            "maxItems": 8,
        },
        "provider_phase_landed_in_lock": #{ "type": "boolean" },
        "next_action": #{ "type": "string", "minLength": 1 },
        "verification_commands": #{
            "type": "array",
            "items": #{ "type": "string" },
            "maxItems": 12,
        },
        "blockers": #{
            "type": "array",
            "items": #{ "type": "string" },
            "maxItems": 12,
        },
    },
};

let implement_schema = #{
    "type": "object",
    "required": ["summary", "changed_paths", "verification_ran", "remaining_blockers"],
    "properties": #{
        "summary": #{ "type": "string" },
        "changed_paths": #{
            "type": "array",
            "items": #{ "type": "string" },
            "maxItems": 32,
        },
        "verification_ran": #{ "type": "boolean" },
        "remaining_blockers": #{
            "type": "array",
            "items": #{ "type": "string" },
            "maxItems": 12,
        },
    },
};

// --- args -----------------------------------------------------------------
// focus: "status" (default) | "implement"
// work_package: optional package id hint (e.g. "VP-15"); agent still re-reads STATUS

let focus = "status";
let work_package_hint = "";
if args != () {
    if args.focus != () {
        let f = args.focus;
        if type_of(f) == "string" {
            f.trim();
            if f != "" { focus = f; }
        }
    }
    if args.work_package != () {
        let wp = args.work_package;
        if type_of(wp) == "string" {
            wp.trim();
            work_package_hint = wp;
        }
    }
}
if focus != "status" && focus != "implement" {
    pause("verification", "args.focus must be \"status\" or \"implement\" (default status).");
}

// --- Assess ---------------------------------------------------------------

phase("Assess");
log("Assessing next vyane-paw ↔ vyane-rs increment from live STATUS and lock");

let assess_prompt = "";
assess_prompt += "You are a cold agent advancing the private integration repo vyane-paw against the public provider vyane-rs.\n";
assess_prompt += "Do NOT answer from memory. Use tools (read_file, grep, list_dir, shell git status only as needed).\n";
assess_prompt += "Mandatory reads in this workspace (vyane-paw root):\n";
assess_prompt += "1) AGENTS.md\n";
assess_prompt += "2) docs/STATUS.md — Current priorities and ledger\n";
assess_prompt += "3) the active work package under work-packages/ (today usually VP-15.md; ";
if work_package_hint != "" {
    assess_prompt += "caller hinted work_package=" + work_package_hint + "; still verify against STATUS)\n";
} else {
    assess_prompt += "if unclear, take STATUS priority #1)\n";
}
assess_prompt += "4) upstreams.lock.json — exact pinned revisions only; never claim compatibility from version ranges\n";
assess_prompt += "If a sibling checkout exists at ../vyane-rs or under ../vyane-rs-worktrees/, read the relevant WP plan (e.g. docs/plan/WP-127.md) and git branch/status with tools.\n";
assess_prompt += "Decide the single next engineering increment. Ownership rules:\n";
assess_prompt += "- vyane-rs owns provider protocol/view changes (e.g. WorkflowView output projection / WP-127).\n";
assess_prompt += "- vyane-paw owns consumer result_contract, plugin, evidence, and lock promotion (VP-15 phase two).\n";
assess_prompt += "- Never invent a permanent middle gateway merely to bridge MCP.\n";
assess_prompt += "- Never start vyane-paw phase-two output retrieval / result-contract work unless the STABLE lock revision is proven to already contain the provider phase-one change. Local unmerged branches or worktrees do NOT count as landed in lock.\n";
assess_prompt += "Set provider_phase_landed_in_lock=true ONLY if you verified via tools that upstreams.lock.json pins a vyane_rs revision that includes the phase-one capability (or STATUS explicitly records that lock promotion already happened for that phase). Otherwise false.\n";
assess_prompt += "Fill owner_repo with exactly one of: vyane-rs | vyane-paw | both | blocked | none.\n";
assess_prompt += "work_package_ids: short ids like VP-15, WP-127.\n";
assess_prompt += "verification_commands: concrete shell commands for the owning repo (e.g. cargo test -p vyane-mcp, bash scripts/check-repository.sh).\n";
assess_prompt += "blockers: merge/review/CI/lock gaps; empty array only after tools showed none.\n";
assess_prompt += "next_action: one imperative sentence for the next human or agent step.\n";

let assess = agent(assess_prompt, #{
    label: "assess-status",
    capability_mode: "read-only",
    output_schema: assessment_schema,
});

// Canned validate_only and failed slots: never treat missing evidence as progress.
let priority_summary = "assessment-unavailable";
let owner_repo = "blocked";
let work_package_ids = [];
let provider_landed = false;
let next_action = "Re-run assessment; agent did not return a usable structured result.";
let verification_commands = [];
let blockers = ["assessment agent failed or returned unusable output"];
let assess_ok = false;

if assess != () && assess.success && assess.output != () {
    let o = assess.output;
    if o.priority_summary != () && type_of(o.priority_summary) == "string" && o.priority_summary != "" {
        priority_summary = o.priority_summary;
    }
    if o.owner_repo != () && type_of(o.owner_repo) == "string" && o.owner_repo != "" {
        owner_repo = o.owner_repo;
    }
    if o.work_package_ids != () {
        work_package_ids = o.work_package_ids;
    }
    if o.provider_phase_landed_in_lock != () && type_of(o.provider_phase_landed_in_lock) == "bool" {
        provider_landed = o.provider_phase_landed_in_lock;
    }
    if o.next_action != () && type_of(o.next_action) == "string" && o.next_action != "" {
        next_action = o.next_action;
    }
    if o.verification_commands != () {
        verification_commands = o.verification_commands;
    }
    if o.blockers != () {
        blockers = o.blockers;
    }
    // Only clear the synthetic blocker when we actually got a priority line.
    if priority_summary != "assessment-unavailable" {
        assess_ok = true;
        if blockers.len() == 1 && blockers[0] == "assessment agent failed or returned unusable output" {
            blockers = [];
        }
    }
}

// --- Gate (script-enforced order) ----------------------------------------

phase("Gate");

// Consumer phase-two on vyane-paw must not proceed without lock-proven provider.
let consumer_blocked = false;
if owner_repo == "vyane-paw" || owner_repo == "both" {
    if !provider_landed {
        consumer_blocked = true;
    }
}
// Explicit safety: if assess claims paw work for output retrieval without lock, force block.
if !provider_landed {
    // Keep provider work allowed; only block consumer ownership / implement on paw.
    if owner_repo == "vyane-paw" {
        owner_repo = "vyane-rs";
        consumer_blocked = true;
        if next_action == "" || assess_ok {
            next_action = "Land and merge vyane-rs provider phase-one (e.g. WP-127), then promote the exact SHA into vyane-paw upstreams.lock.json before any VP-15 phase-two result_contract work.";
        }
        blockers.push("Rhai gate: provider_phase_landed_in_lock is false — refuse vyane-paw phase-two / result-contract adoption");
        if verification_commands.len() == 0 {
            verification_commands.push("cd ../vyane-rs && cargo fmt --all -- --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test -p vyane-mcp --test workflow_control && cargo test -p vyane-cli --test daemon_workflow_acceptance mcp_workflow");
            verification_commands.push("After merge: pin exact vyane_rs revision in upstreams.lock.json (VP-10 process); bash scripts/check-repository.sh");
        }
    }
}

let landed_s = if provider_landed { "true" } else { "false" };
let blocked_s = if consumer_blocked { "true" } else { "false" };
log("owner_repo=" + owner_repo + " provider_landed=" + landed_s + " consumer_blocked=" + blocked_s);

// --- Act -----------------------------------------------------------------

phase("Act");

let result = #{
    priority_summary: priority_summary,
    owner_repo: owner_repo,
    work_package_ids: work_package_ids,
    provider_phase_landed_in_lock: provider_landed,
    next_action: next_action,
    verification_commands: verification_commands,
    blockers: blockers,
    focus: focus,
    consumer_phase_two_blocked: consumer_blocked,
    implement: (),
};

if focus == "status" {
    let report = "";
    report += "# advance-vyane-paw status handoff\n\n";
    report += "- priority: " + priority_summary + "\n";
    report += "- owner_repo: " + owner_repo + "\n";
    report += "- provider_phase_landed_in_lock: " + landed_s + "\n";
    report += "- consumer_phase_two_blocked: " + blocked_s + "\n";
    report += "- next_action: " + next_action + "\n";
    report += "- work_package_ids: " + json_encode(work_package_ids) + "\n";
    report += "- verification_commands: " + json_encode(verification_commands) + "\n";
    report += "- blockers: " + json_encode(blockers) + "\n";
    let path = write_scratch_file("advance-vyane-paw-status.md", report);
    result.scratch_path = path;
    complete(result);
}

// focus == implement
if focus == "implement" && (consumer_blocked || owner_repo != "vyane-rs" && !provider_landed) {
    // Only pure provider implement is allowed while lock lacks phase-one.
    if owner_repo != "vyane-rs" {
        result.next_action = "Do not implement on vyane-paw yet. Finish provider phase-one on vyane-rs and lock promotion first.";
        result.blockers.push("Rhai gate blocked focus=implement on consumer until provider_phase_landed_in_lock");
        let path = write_scratch_file("advance-vyane-paw-blocked.md", json_encode(result));
        result.scratch_path = path;
        complete(result);
    }
}

if owner_repo == "blocked" || owner_repo == "none" || !assess_ok {
    result.next_action = "Assessment incomplete or blocked; fix blockers before implement.";
    let path = write_scratch_file("advance-vyane-paw-blocked.md", json_encode(result));
    result.scratch_path = path;
    complete(result);
}

// Bounded implement agent — only when gates pass for the chosen owner.
let impl_prompt = "";
impl_prompt += "Implement the NEXT bounded increment for owner_repo=" + owner_repo + ".\n";
impl_prompt += "You MUST re-read with tools: docs/STATUS.md, the work package(s) ";
impl_prompt += json_encode(work_package_ids);
impl_prompt += ", and upstreams.lock.json. Do not use memory.\n";
impl_prompt += "Agreed next_action from assessment: " + next_action + "\n";
impl_prompt += "Rules from AGENTS.md: no credentials; no permanent middle gateway; pin exact revisions for compatibility claims; work from origin/main feature branches.\n";
if owner_repo == "vyane-rs" {
    impl_prompt += "Work in the sibling vyane-rs checkout or existing worktree for the provider package (e.g. WP-127). Run cargo fmt/clippy/targeted tests for changed crates.\n";
} else if owner_repo == "vyane-paw" {
    impl_prompt += "Consumer work only because provider_phase_landed_in_lock was true. Project new fields through result_contract and evidence; run scripts/check-repository.sh and package gates.\n";
} else {
    impl_prompt += "If both, prefer the smaller provider-safe step first; do not skip lock gates.\n";
}
impl_prompt += "Return summary, changed_paths, verification_ran, remaining_blockers. Do not claim lock promotion without editing upstreams.lock.json to an exact SHA you verified.\n";

let impl = agent(impl_prompt, #{
    label: "implement-increment",
    capability_mode: "all",
    output_schema: implement_schema,
});

if impl != () && impl.success && impl.output != () {
    result.implement = impl.output;
    if impl.output.summary != () {
        result.next_action = impl.output.summary;
    }
    if impl.output.remaining_blockers != () {
        result.blockers = impl.output.remaining_blockers;
    }
} else {
    result.blockers.push("implement agent failed or returned unusable output");
    result.next_action = "Implement agent did not finish; resume after inspecting journal.";
}

let path = write_scratch_file("advance-vyane-paw-implement.md", json_encode(result));
result.scratch_path = path;
complete(result);
