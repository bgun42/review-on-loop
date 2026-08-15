#!/usr/bin/env python3
"""Run dependency-free Veriloop controller-trace contract evaluations."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
DEFAULT_CASES = Path(__file__).with_name("contract-cases.json")

REVIEW_BRIEF = {
    "strict_blind",
    "repository_path",
    "target",
    "spec_path",
    "scope_bounds",
    "risk_focus",
}
GATE_BRIEF = REVIEW_BRIEF | {"snapshot"}
MUTATIONS = {"developer_change", "fixer_change"}
EVENT_KEYS = {
    "preflight": {"type", "result", "unsupported"},
    "authorization": {"type", "decision", "reason", "authorization"},
    "developer_change": {"type", "actor"},
    "fixer_change": {"type", "actor", "failure_packet_keys"},
    "acceptance": {"type", "criterion", "check", "result", "evidence"},
    "review": {"type", "actor", "brief_keys", "result"},
    "snapshot": {"type", "value"},
    "gate": {"type", "actor", "brief_keys", "probe_metadata", "result"},
    "exit": {"type", "reason"},
}
SKILL_CONTRACTS = {
    "strict preflight before mutation": r"Before development, verify that the host can:",
    "unique reviewer and gate agents": r"unique internal subagent for every iteration reviewer and final gate",
    "fresh reviewer per iteration": r"Create a new reviewer subagent for this iteration\. Never reuse",
    "minimal blind-gate fix packet": r"withhold passed probes and the\s+rest of the gate's reasoning",
    "executable acceptance evidence": r"An unevaluable acceptance check fails",
    "snapshot invalidation": r"Any target change invalidates the gate",
    "no-progress stop": r"failed count did not decrease from\s+the previous iteration",
    "explicit reduced authorization": r"Ask whether the user authorizes relaxed review \*\*for this run only\*\*",
}


class EvalFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalFailure(message)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_repo_path(relative_path: str, label: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    require(candidate == ROOT or ROOT in candidate.parents, f"{label}: path escapes repository")
    require(candidate.is_file(), f"{label}: file does not exist: {relative_path}")
    return candidate


def target_snapshot(case: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(case["target_files"]):
        path = resolve_repo_path(relative_path, case["id"])
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    require(ref.startswith("#/"), f"unsupported schema reference: {ref}")
    node: Any = root
    for segment in ref[2:].split("/"):
        node = node[segment.replace("~1", "/").replace("~0", "~")]
    return node


def validate_schema(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        validate_schema(value, resolve_ref(root, schema["$ref"]), root, path)
        return

    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        require(
            any(json_type_matches(value, item) for item in expected_types),
            f"{path}: expected type {expected_types}, got {type(value).__name__}",
        )

    if "const" in schema:
        require(value == schema["const"], f"{path}: expected {schema['const']!r}")
    if "enum" in schema:
        require(value in schema["enum"], f"{path}: {value!r} is outside enum")

    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), f"{path}: string is too short")
    if isinstance(value, int) and not isinstance(value, bool):
        require(value >= schema.get("minimum", value), f"{path}: below minimum")
        require(value <= schema.get("maximum", value), f"{path}: above maximum")
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), f"{path}: too few items")
        require(len(value) <= schema.get("maxItems", len(value)), f"{path}: too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        require(not missing, f"{path}: missing required keys {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            require(not extra, f"{path}: unexpected keys {extra}")
        for key, child in value.items():
            if key in properties:
                validate_schema(child, properties[key], root, f"{path}.{key}")


def validate_result(name: str, result: dict[str, Any]) -> None:
    schema = load_json(SCHEMA_DIR / f"{name}-result.schema.json")
    validate_schema(result, schema, schema)


def validate_review_archive(relative_path: str, result: dict[str, Any], label: str) -> None:
    text = resolve_repo_path(relative_path, label).read_text(encoding="utf-8")
    blocks = re.findall(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL)
    require(blocks, f"{label}: review archive lacks a JSON block")
    try:
        archived_result = json.loads(blocks[-1])
    except json.JSONDecodeError as error:
        raise EvalFailure(f"{label}: review archive JSON is invalid: {error}") from error
    require(archived_result == result, f"{label}: review archive disagrees with trace")


def validate_gate_archive(relative_path: str, result: dict[str, Any], label: str) -> None:
    archived_result = load_json(resolve_repo_path(relative_path, label))
    require(archived_result == result, f"{label}: gate archive disagrees with trace")


def validate_review_semantics(result: dict[str, Any], label: str) -> None:
    verdict = result["verdict"]
    findings = result["findings"]
    failed = [item for item in findings if item["severity"] == "failed"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    if verdict == "pass":
        require(not findings, f"{label}: pass must have no findings")
    elif verdict == "pass_with_warnings":
        require(warnings and not failed, f"{label}: warning verdict is contradictory")
    else:
        require(failed, f"{label}: fail must contain a failed finding")


def execute_fixture_check(
    check: str,
    result: str,
    evidence: str,
    required_module: str,
    required_symbols: list[str],
    label: str,
) -> None:
    require(result in {"pass", "fail"}, f"{label}: blocked fixture checks are not executable")
    try:
        argv = shlex.split(check)
    except ValueError as error:
        raise EvalFailure(f"{label}: invalid check command: {error}") from error
    require(argv[:2] == ["python3", "-c"], f"{label}: fixture commands must use python3 -c assertions")
    require(required_module in check, f"{label}: check is not grounded in the fixture target")
    try:
        tree = ast.parse(argv[2])
    except SyntaxError as error:
        raise EvalFailure(f"{label}: invalid Python assertion: {error}") from error

    def called_name(node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    asserted_calls = {
        called_name(node)
        for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert))
        for node in ast.walk(assertion.test)
        if isinstance(node, ast.Call)
    }
    require(asserted_calls.intersection(required_symbols), f"{label}: assertion does not call a target function")
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EvalFailure(f"{label}: check could not execute: {error}") from error
    expected_success = result == "pass"
    require((completed.returncode == 0) == expected_success, f"{label}: claimed {result}, exit was {completed.returncode}")
    require(evidence.startswith(f"exit {completed.returncode}"), f"{label}: evidence omits captured exit code")


def validate_gate_semantics(
    event: dict[str, Any],
    snapshot: str,
    acceptance_checks: set[str],
    required_module: str,
    required_symbols: list[str],
    label: str,
) -> None:
    result = event["result"]
    require(result["snapshot"] == snapshot, f"{label}: gate used a different snapshot")
    metadata = event.get("probe_metadata", [])
    require(len(metadata) == len(result["probes"]), f"{label}: probe metadata is incomplete")
    require(all(item.get("late_bound") is True for item in metadata), f"{label}: probe was predeclared")
    require(
        any(item.get("in_spec_unnamed") is True for item in metadata),
        f"{label}: no unnamed in-spec behavior was probed",
    )
    require(len({probe["category"] for probe in result["probes"]}) >= 2, f"{label}: probes need two categories")
    unnamed_checks = [
        result["probes"][index]["check"]
        for index, item in enumerate(metadata)
        if item.get("in_spec_unnamed") is True
    ]
    require(
        any(check not in acceptance_checks for check in unnamed_checks),
        f"{label}: unnamed probe duplicates a named acceptance check",
    )

    probe_results = [probe["result"] for probe in result["probes"]]
    for index, probe in enumerate(result["probes"]):
        execute_fixture_check(
            probe["check"],
            probe["result"],
            probe["evidence"],
            required_module,
            required_symbols,
            f"{label}.probes[{index}]",
        )
    if result["gate"] == "hold":
        require(all(item == "pass" for item in probe_results), f"{label}: held with a failed probe")
        require(not result["findings"], f"{label}: held with a new failed finding")
    elif result["gate"] == "fail":
        require("fail" in probe_results or result["findings"], f"{label}: fail has no evidence")
    else:
        require("blocked" in probe_results, f"{label}: blocked has no blocked probe")


def validate_case(case: dict[str, Any]) -> None:
    case_id = case.get("id", "<unnamed>")
    require(
        set(case)
        == {
            "id",
            "capabilities",
            "spec_path",
            "target_files",
            "required_check_module",
            "required_check_symbols",
            "events",
            "run_result",
        },
        f"{case_id}: case contains unexpected or missing fields",
    )
    events = case.get("events", [])
    require(events and events[0].get("type") == "preflight", f"{case_id}: preflight must be first")
    spec_path = resolve_repo_path(case["spec_path"], case_id)
    require(spec_path.suffix == ".md" and "acceptance" in spec_path.read_text(encoding="utf-8").lower(), f"{case_id}: fixture spec lacks acceptance criteria")
    require(case["run_result"]["spec_path"] == case["spec_path"], f"{case_id}: run uses a different specification")
    require(case["target_files"], f"{case_id}: no target files declared")
    frozen_target = target_snapshot(case)
    required_module = case["required_check_module"]
    require(isinstance(required_module, str) and required_module, f"{case_id}: missing check module")
    module_target = required_module.replace(".", "/") + ".py"
    require(module_target in case["target_files"], f"{case_id}: checked module is outside the frozen target")
    required_symbols = case["required_check_symbols"]
    require(
        isinstance(required_symbols, list) and required_symbols and all(isinstance(item, str) for item in required_symbols),
        f"{case_id}: missing target check symbols",
    )

    capabilities = case.get("capabilities", {})
    required_capabilities = {"unique_internal_agents", "clean_context", "allowlisted_brief"}
    require(set(capabilities) == required_capabilities, f"{case_id}: capability set is incomplete")
    require(all(isinstance(value, bool) for value in capabilities.values()), f"{case_id}: capabilities must be booleans")
    unsupported = sorted(key for key, supported in capabilities.items() if not supported)
    preflight = events[0]
    require(set(preflight) == EVENT_KEYS["preflight"], f"{case_id}: malformed preflight event")
    expected_preflight = "fail" if unsupported else "pass"
    require(preflight.get("result") == expected_preflight, f"{case_id}: incorrect preflight result")
    require(sorted(preflight.get("unsupported", [])) == unsupported, f"{case_id}: unsupported capabilities mismatch")

    validate_result("run", case["run_result"])
    seen_agents: set[str] = set()
    reviews: list[dict[str, Any]] = []
    acceptances: list[dict[str, Any]] = []
    latest_acceptance: dict[str, tuple[int, str]] = {}
    latest_review: str | None = None
    pending_fix_source: str | None = None
    authorization_event: dict[str, Any] | None = None
    can_run = not unsupported
    expected_independence = "strict"
    previous_failed_count: int | None = None
    active_failed_findings: set[tuple[str, str]] = set()
    passed_failed_findings: set[tuple[str, str]] = set()
    detected_no_progress = False
    revision = 0
    reviewed_revision: int | None = None
    snapshot: str | None = None
    snapshot_dirty = False
    gate_status = "not_run"
    gate_result: dict[str, Any] | None = None
    gate_results: list[dict[str, Any]] = []
    gate_revision: int | None = None
    gate_count = 0
    exit_reason: str | None = None

    def claim_actor(event: dict[str, Any], label: str) -> None:
        actor = event.get("actor")
        require(actor and actor not in seen_agents, f"{label}: agent context was reused")
        seen_agents.add(actor)

    for index, event in enumerate(events[1:], start=1):
        event_type = event.get("type")
        label = f"{case_id}.events[{index}]"
        require(event_type in EVENT_KEYS, f"{label}: unknown event type {event_type!r}")
        require(set(event) == EVENT_KEYS[event_type], f"{label}: event contains leaked or missing fields")

        if unsupported and not can_run:
            require(event_type in {"authorization", "exit"}, f"{label}: action occurred before reduced-mode authorization")
        if pending_fix_source is not None:
            require(event_type in {"fixer_change", "exit"}, f"{label}: {pending_fix_source} failure was bypassed")
        if detected_no_progress:
            require(event_type == "exit", f"{label}: work continued after no progress was detected")

        if event_type == "authorization":
            require(unsupported and authorization_event is None, f"{label}: authorization is unexpected or repeated")
            require(event["decision"] in {"approve", "deny"}, f"{label}: invalid authorization decision")
            require(event["reason"] and event["authorization"], f"{label}: authorization evidence is incomplete")
            authorization_event = event
            can_run = event["decision"] == "approve"
            if can_run:
                expected_independence = "reduced"

        elif event_type in MUTATIONS:
            require(can_run, f"{label}: mutation is forbidden without blind capability or authorization")
            claim_actor(event, label)
            if event_type == "fixer_change":
                require(pending_fix_source is not None, f"{label}: fixer ran without a failed review or gate")
                require(
                    set(event.get("failure_packet_keys", [])) == {"title", "file", "line", "evidence"},
                    f"{label}: fixer packet leaked or omitted context",
                )
                pending_fix_source = None
            else:
                require(latest_review is None, f"{label}: developer ran after review started")
            revision += 1
            reviewed_revision = None
            snapshot_dirty = snapshot is not None

        elif event_type == "acceptance":
            execute_fixture_check(
                event["check"],
                event["result"],
                event["evidence"],
                required_module,
                required_symbols,
                label,
            )
            acceptances.append(event)
            latest_acceptance[event["criterion"]] = (revision, event["result"])

        elif event_type == "review":
            require(pending_fix_source is None, f"{label}: new review started before fixing failed findings")
            require(set(event.get("brief_keys", [])) == REVIEW_BRIEF, f"{label}: reviewer brief is not allowlisted")
            claim_actor(event, label)
            validate_result("review", event["result"])
            validate_review_semantics(event["result"], label)
            failed_findings = [item for item in event["result"]["findings"] if item["severity"] == "failed"]
            failed_keys = {(item["file"], item["title"]) for item in failed_findings}
            if failed_findings:
                if previous_failed_count is not None:
                    detected_no_progress = len(failed_findings) >= previous_failed_count
                detected_no_progress = detected_no_progress or bool(failed_keys & passed_failed_findings)
            passed_failed_findings.update(active_failed_findings - failed_keys)
            active_failed_findings = failed_keys
            previous_failed_count = len(failed_findings)
            reviews.append(event)
            latest_review = event["result"]["verdict"]
            reviewed_revision = revision
            pending_fix_source = "review" if latest_review == "fail" else None

        elif event_type == "snapshot":
            require(latest_review in {"pass", "pass_with_warnings"}, f"{label}: snapshot preceded a passing review")
            require(reviewed_revision == revision, f"{label}: target changed after its passing review")
            require(
                latest_acceptance and all(item == (revision, "pass") for item in latest_acceptance.values()),
                f"{label}: every acceptance check must pass on the reviewed revision",
            )
            snapshot = event.get("value")
            require(snapshot == frozen_target == target_snapshot(case), f"{label}: snapshot is not the target digest")
            snapshot_dirty = False

        elif event_type == "gate":
            require(snapshot is not None and not snapshot_dirty, f"{label}: gate target changed after freeze")
            require(reviewed_revision == revision, f"{label}: gate target lacks a current passing review")
            require(set(event.get("brief_keys", [])) == GATE_BRIEF, f"{label}: gate brief is not allowlisted")
            claim_actor(event, label)
            validate_result("gate", event["result"])
            require(event["result"]["independence"] == expected_independence, f"{label}: independence label is incorrect")
            validate_gate_semantics(
                event,
                snapshot,
                {item["check"] for item in acceptances},
                required_module,
                required_symbols,
                label,
            )
            gate_status = event["result"]["gate"]
            gate_result = event["result"]
            gate_results.append(event["result"])
            gate_revision = revision
            gate_count += 1
            pending_fix_source = "gate" if gate_status == "fail" else None

        elif event_type == "exit":
            require(index == len(events) - 1, f"{label}: exit must be the last event")
            exit_reason = event.get("reason")

    require(exit_reason is not None, f"{case_id}: missing exit event")
    run = case["run_result"]
    require(run["exit_reason"] == exit_reason, f"{case_id}: run exit reason disagrees with trace")
    require(len(run["iterations"]) == len(reviews), f"{case_id}: archived iteration count disagrees with trace")
    for index, (archived, review) in enumerate(zip(run["iterations"], reviews), start=1):
        findings = review["result"]["findings"]
        require(archived["iteration"] == index, f"{case_id}: archived iterations are out of order")
        validate_review_archive(archived["review_file"], review["result"], f"{case_id}.iterations[{index}]")
        require(archived["verdict"] == review["result"]["verdict"], f"{case_id}: archived verdict disagrees with review")
        require(archived["independence"] == expected_independence, f"{case_id}: archived review independence is incorrect")
        require(
            archived["failed_count"] == sum(item["severity"] == "failed" for item in findings),
            f"{case_id}: archived failed count is incorrect",
        )
        require(
            archived["warning_count"] == sum(item["severity"] == "warning" for item in findings),
            f"{case_id}: archived warning count is incorrect",
        )
    trace_acceptance = [{key: value for key, value in item.items() if key != "type"} for item in acceptances]
    require(run["acceptance"] == trace_acceptance, f"{case_id}: archived acceptance evidence disagrees with trace")
    require(run["gate"]["status"] == gate_status, f"{case_id}: archived gate status disagrees with trace")
    if gate_result is not None:
        require(run["gate"]["snapshot"] == gate_result["snapshot"], f"{case_id}: archived snapshot disagrees with gate")
        require(run["gate"]["independence"] == gate_result["independence"], f"{case_id}: archived independence disagrees with gate")
        require(len(run["gate_files"]) == gate_count, f"{case_id}: gate artifacts were not all archived")
        for index, (gate_file, result) in enumerate(zip(run["gate_files"], gate_results), start=1):
            validate_gate_archive(gate_file, result, f"{case_id}.gates[{index}]")
    relaxation = run["relaxation"]
    if authorization_event and authorization_event["decision"] == "approve":
        require(relaxation["authorized"] is True, f"{case_id}: reduced independence lacks authorization")
        require(relaxation["reason"] == authorization_event["reason"], f"{case_id}: relaxation reason was not preserved")
        require(relaxation["authorization"] == authorization_event["authorization"], f"{case_id}: authorization was not preserved")
    else:
        require(relaxation["authorized"] is False, f"{case_id}: run claims unobserved authorization")
        require(relaxation["reason"] is None and relaxation["authorization"] is None, f"{case_id}: unauthorized relaxation metadata")
    if exit_reason == "goal_met":
        require(gate_status == "hold", f"{case_id}: goal met without a held gate")
        require(gate_revision == revision and not snapshot_dirty, f"{case_id}: goal met after the held target changed")
        require(target_snapshot(case) == frozen_target, f"{case_id}: target files changed during evaluation")
        require(
            latest_acceptance and all(item == (revision, "pass") for item in latest_acceptance.values()),
            f"{case_id}: goal met without final-revision acceptance",
        )
        require(pending_fix_source is None, f"{case_id}: goal met with an unresolved failure")
        require(not detected_no_progress, f"{case_id}: goal met after no progress")
    if exit_reason == "iteration_cap":
        require(len(reviews) == 3, f"{case_id}: iteration cap requires three reviews")
        require(gate_status != "hold", f"{case_id}: iteration cap cannot override a held gate")
        require(latest_review == "fail" or gate_status in {"fail", "blocked"}, f"{case_id}: iteration cap lacks a failed stop state")
    if exit_reason == "no_progress":
        require(detected_no_progress and len(reviews) < 3, f"{case_id}: no-progress exit lacks the required stop condition")
    if exit_reason == "blind_context_unavailable":
        require(unsupported and not can_run, f"{case_id}: blind exit without an unresolved capability failure")
        require(not reviews and gate_status == "not_run", f"{case_id}: blind exit performed review work")


def validate_skill_contracts() -> None:
    text = (ROOT / "skills" / "run-review-loop" / "SKILL.md").read_text(encoding="utf-8")
    for label, pattern in SKILL_CONTRACTS.items():
        require(re.search(pattern, text) is not None, f"run-review-loop skill lost contract: {label}")


def expect_rejected(case: dict[str, Any], mutation: str) -> None:
    try:
        validate_case(case)
    except EvalFailure:
        return
    raise EvalFailure(f"guard mutation was not rejected: {mutation}")


def run_guard_tests(cases: list[dict[str, Any]]) -> int:
    by_id = {case["id"]: case for case in cases}

    reused = copy.deepcopy(by_id["failed-review-fixed-by-fresh-reviewer"])
    review_events = [event for event in reused["events"] if event["type"] == "review"]
    review_events[1]["actor"] = review_events[0]["actor"]
    expect_rejected(reused, "reused reviewer")

    leaked = copy.deepcopy(by_id["failed-review-fixed-by-fresh-reviewer"])
    fixer = next(event for event in leaked["events"] if event["type"] == "fixer_change")
    fixer["failure_packet_keys"].append("passed_probes")
    expect_rejected(leaked, "fixer received passed probes")

    changed = copy.deepcopy(by_id["blind-context-unavailable"])
    changed["events"].insert(1, {"type": "developer_change", "actor": "developer-1"})
    expect_rejected(changed, "code changed after failed preflight")

    fabricated = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    acceptance = next(event for event in fabricated["events"] if event["type"] == "acceptance")
    acceptance["check"] = "definitely-not-a-real-command"
    expect_rejected(fabricated, "fabricated acceptance result")

    unreviewed = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    snapshot_index = next(index for index, event in enumerate(unreviewed["events"]) if event["type"] == "snapshot")
    unreviewed["events"].insert(snapshot_index, {"type": "developer_change", "actor": "developer-after-review"})
    expect_rejected(unreviewed, "target changed after passing review")

    post_gate = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    post_gate["events"].insert(-1, {"type": "developer_change", "actor": "developer-after-gate"})
    expect_rejected(post_gate, "target changed after held gate")

    hidden_context = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    review = next(event for event in hidden_context["events"] if event["type"] == "review")
    review["developer_reasoning"] = "leaked"
    expect_rejected(hidden_context, "review event carried hidden context")

    reduced = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    reduced_gate = next(event for event in reduced["events"] if event["type"] == "gate")
    reduced_gate["result"]["independence"] = "reduced"
    reduced["run_result"]["gate"]["independence"] = "reduced"
    expect_rejected(reduced, "reduced independence without authorization")

    bypassed_gate = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    gate_index = next(index for index, event in enumerate(bypassed_gate["events"]) if event["type"] == "gate")
    failed_gate = copy.deepcopy(bypassed_gate["events"][gate_index])
    failed_gate["actor"] = "gate-failed-before-hold"
    failed_gate["result"]["gate"] = "fail"
    failed_gate["result"]["probes"][0]["check"] = (
        "python3 -c \"from evals.fixtures.sample_project import normalize_iso_date; "
        "assert normalize_iso_date('2026-08-15') == 'invalid'\""
    )
    failed_gate["result"]["probes"][0]["result"] = "fail"
    failed_gate["result"]["probes"][0]["evidence"] = "exit 1: seeded gate failure"
    bypassed_gate["events"].insert(gate_index, failed_gate)
    expect_rejected(bypassed_gate, "failed gate bypassed without fix and review")

    duplicate_probe = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    duplicate_acceptance = next(event for event in duplicate_probe["events"] if event["type"] == "acceptance")
    duplicate_gate = next(event for event in duplicate_probe["events"] if event["type"] == "gate")
    duplicate_gate["result"]["probes"][0]["check"] = duplicate_acceptance["check"]
    expect_rejected(duplicate_probe, "unnamed probe duplicated acceptance check")

    stale_acceptance = copy.deepcopy(by_id["failed-review-fixed-by-fresh-reviewer"])
    repeated_index = next(
        index
        for index, event in enumerate(stale_acceptance["events"])
        if event.get("evidence") == "exit 0: known caller totals matched after repair"
    )
    stale_acceptance["events"].pop(repeated_index)
    stale_acceptance["run_result"]["acceptance"].pop(1)
    expect_rejected(stale_acceptance, "acceptance was not rerun after repair")

    failing_final = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    failed_acceptance = {
        "type": "acceptance",
        "criterion": "The formatter preserves ISO dates",
        "check": (
            "python3 -c \"from evals.fixtures.sample_project import normalize_iso_date; "
            "assert normalize_iso_date('2026-08-15') == 'invalid'\""
        ),
        "result": "fail",
        "evidence": "exit 1: final acceptance failed",
    }
    failing_final["events"].insert(-1, failed_acceptance)
    failing_final["run_result"]["acceptance"].append(
        {key: value for key, value in failed_acceptance.items() if key != "type"}
    )
    expect_rejected(failing_final, "goal met with failing final acceptance")

    no_progress = copy.deepcopy(by_id["failed-review-fixed-by-fresh-reviewer"])
    second_review = [event for event in no_progress["events"] if event["type"] == "review"][1]
    second_review["result"] = copy.deepcopy(
        next(event for event in no_progress["events"] if event["type"] == "review")["result"]
    )
    second_review["result"]["findings"][0]["title"] = "A different failure keeps the failed count flat"
    no_progress["run_result"]["iterations"][1]["verdict"] = "fail"
    no_progress["run_result"]["iterations"][1]["failed_count"] = 1
    expect_rejected(no_progress, "failed count did not decrease")

    tampered_snapshot = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    fake_snapshot = "sha256:" + "0" * 64
    next(event for event in tampered_snapshot["events"] if event["type"] == "snapshot")["value"] = fake_snapshot
    next(event for event in tampered_snapshot["events"] if event["type"] == "gate")["result"]["snapshot"] = fake_snapshot
    tampered_snapshot["run_result"]["gate"]["snapshot"] = fake_snapshot
    expect_rejected(tampered_snapshot, "snapshot did not match target digest")

    no_op = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    no_op_acceptance = next(event for event in no_op["events"] if event["type"] == "acceptance")
    no_op_acceptance["check"] = (
        "python3 -c \"from evals.fixtures.sample_project import normalize_iso_date; assert True\""
    )
    no_op["run_result"]["acceptance"][0]["check"] = no_op_acceptance["check"]
    expect_rejected(no_op, "no-op assertion did not exercise target function")

    unrelated_target = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    unrelated_target["target_files"] = ["LICENSE"]
    fake_target_snapshot = target_snapshot(unrelated_target)
    next(event for event in unrelated_target["events"] if event["type"] == "snapshot")["value"] = fake_target_snapshot
    next(event for event in unrelated_target["events"] if event["type"] == "gate")["result"]["snapshot"] = fake_target_snapshot
    unrelated_target["run_result"]["gate"]["snapshot"] = fake_target_snapshot
    expect_rejected(unrelated_target, "checked module was outside frozen target")

    wrong_no_progress = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    wrong_no_progress["events"][-1]["reason"] = "no_progress"
    wrong_no_progress["run_result"]["exit_reason"] = "no_progress"
    expect_rejected(wrong_no_progress, "no-progress exit without no-progress state")

    wrong_cap = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    wrong_cap["events"][-1]["reason"] = "iteration_cap"
    wrong_cap["run_result"]["exit_reason"] = "iteration_cap"
    expect_rejected(wrong_cap, "iteration cap before iteration three")

    missing_archive = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    missing_archive["run_result"]["iterations"][0]["review_file"] = "evals/fixtures/archives/missing.md"
    expect_rejected(missing_archive, "missing review archive")

    string_capability = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    string_capability["capabilities"]["clean_context"] = "false"
    expect_rejected(string_capability, "non-boolean capability")
    return 20


def run_reduced_transition_test(cases: list[dict[str, Any]]) -> int:
    clean = copy.deepcopy(next(case for case in cases if case["id"] == "clean-diff-held-by-gate"))
    clean["capabilities"]["clean_context"] = False
    clean["events"][0] = {"type": "preflight", "result": "fail", "unsupported": ["clean_context"]}
    clean["events"].insert(
        1,
        {
            "type": "authorization",
            "decision": "approve",
            "reason": "host cannot create a clean context",
            "authorization": "user approved reduced mode for this fixture run",
        },
    )
    clean["run_result"]["relaxation"] = {
        "authorized": True,
        "reason": "host cannot create a clean context",
        "authorization": "user approved reduced mode for this fixture run",
    }
    for iteration in clean["run_result"]["iterations"]:
        iteration["independence"] = "reduced"
    next(event for event in clean["events"] if event["type"] == "gate")["result"]["independence"] = "reduced"
    clean["run_result"]["gate"]["independence"] = "reduced"
    clean["run_result"]["gate_files"] = ["evals/fixtures/archives/clean-gate-reduced.json"]
    validate_case(clean)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="?", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--no-guard-tests", action="store_true", help="skip deliberate negative mutations")
    args = parser.parse_args()

    payload = load_json(args.cases)
    cases = payload.get("cases", [])
    require(cases, "no contract cases found")
    validate_skill_contracts()
    for case in cases:
        validate_case(case)
        print(f"PASS {case['id']}")

    transition_count = run_reduced_transition_test(cases)
    guard_count = 0 if args.no_guard_tests else run_guard_tests(cases)
    print(
        f"\n{len(cases)} contract traces passed; {transition_count} authorized reduced transition passed; "
        f"{guard_count} guard mutations rejected."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvalFailure, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL {error}")
        raise SystemExit(1)
