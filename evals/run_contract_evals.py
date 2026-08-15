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
WORKER_RESULT_MAX_BYTES = 16_384

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
    "developer_change": {"type", "actor", "transport", "required_checks"},
    "fixer_change": {"type", "actor", "transport", "required_checks", "failure_packet_keys"},
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
    "worker transport before body": r"Inspect the host delegation/tool status before reading the worker body",
    "whole-object JSON parsing": r"Never extract JSON from mixed prose with a regular expression",
    "single format retry": r"allow one format-only retry in the same\s+worker context",
    "completed worker semantics": r"`completed` requires `termination: completed`",
    "bounded worker envelope": r"entire UTF-8 worker result at or below 16 KiB",
    "verified artifact handoff": r"byte count and SHA-256 digest",
    "lazy artifact reads": r"Do not read artifacts into controller context on a successful path",
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
        require(len(value) <= schema.get("maxLength", len(value)), f"{path}: string is too long")
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


def validate_worker_semantics(
    result: dict[str, Any],
    expected_role: str | None,
    label: str,
    host_termination: str | None = None,
) -> None:
    validate_result("worker", result)
    encoded_size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    require(encoded_size <= WORKER_RESULT_MAX_BYTES, f"{label}: worker result exceeds the byte budget")
    if expected_role is not None:
        require(result["role"] == expected_role, f"{label}: worker role disagrees with controller event")

    status = result["status"]
    termination = result["termination"]
    checks = result["checks"]
    tool_failures = result["tool_failures"]
    artifacts = result["artifacts"]
    blocker = result["blocker"]

    artifact_root = (ROOT / "evals/fixtures/artifacts").resolve()
    artifact_paths = [item["path"] for item in artifacts]
    require(len(artifact_paths) == len(set(artifact_paths)), f"{label}: artifact paths are duplicated")
    for index, artifact in enumerate(artifacts):
        unresolved_path = ROOT / artifact["path"]
        require(not unresolved_path.is_symlink(), f"{label}.artifacts[{index}]: artifact must not be a symlink")
        path = resolve_repo_path(artifact["path"], f"{label}.artifacts[{index}]")
        require(artifact_root in path.parents, f"{label}.artifacts[{index}]: artifact is outside isolated storage")
        payload = path.read_bytes()
        require(len(payload) == artifact["bytes"], f"{label}.artifacts[{index}]: artifact byte count is incorrect")
        require(
            re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]) is not None,
            f"{label}.artifacts[{index}]: artifact digest format is invalid",
        )
        require(
            hashlib.sha256(payload).hexdigest() == artifact["sha256"],
            f"{label}.artifacts[{index}]: artifact digest is incorrect",
        )

    referenced_artifacts = {
        item["artifact_path"]
        for item in [*checks, *tool_failures]
        if item["artifact_path"] is not None
    }
    require(referenced_artifacts == set(artifact_paths), f"{label}: artifact declarations and references disagree")

    if host_termination is not None:
        require(
            host_termination in {"completed", "tool_error", "timeout", "cancelled", "context_limit"},
            f"{label}: unsupported host termination",
        )
        if host_termination == "completed":
            require(termination in {"completed", "invalid_result"}, f"{label}: worker termination contradicts normal transport")
        else:
            require(termination == host_termination, f"{label}: worker body contradicts host termination")

    for index, check in enumerate(checks):
        exit_code = check["exit_code"]
        if check["kind"] == "command":
            require(exit_code is not None, f"{label}.checks[{index}]: command check lacks an exit code")
            if check["result"] == "pass":
                require(exit_code == 0, f"{label}.checks[{index}]: pass has a nonzero exit code")
            if check["result"] == "fail":
                require(exit_code != 0, f"{label}.checks[{index}]: fail has a zero exit code")
        else:
            require(exit_code is None, f"{label}.checks[{index}]: observable assertion has a command exit code")

    if status == "completed":
        require(termination == "completed", f"{label}: completed worker has non-completed termination")
        require(blocker is None, f"{label}: completed worker has a blocker")
        require(not tool_failures, f"{label}: completed worker has tool failures")
        require(checks and all(item["result"] == "pass" for item in checks), f"{label}: completed worker has non-passing checks")
    else:
        require(blocker is not None, f"{label}: blocked or failed worker lacks a blocker")

    if termination != "completed":
        require(status != "completed", f"{label}: abnormal transport was treated as completed")
    abnormal = {
        "tool_error": ("failed", "tool_error"),
        "timeout": ("blocked", "timeout"),
        "cancelled": ("blocked", "cancelled"),
        "context_limit": ("blocked", "context_limit"),
        "invalid_result": ("blocked", "invalid_result"),
    }
    if termination in abnormal:
        expected_status, expected_blocker = abnormal[termination]
        require(status == expected_status, f"{label}: status contradicts abnormal termination")
        require(blocker and blocker["code"] == expected_blocker, f"{label}: blocker contradicts termination")
    if termination == "tool_error":
        require(tool_failures, f"{label}: tool error lacks tool failure evidence")


def parse_worker_response(raw: str, expected_role: str, label: str) -> dict[str, Any]:
    """Parse one whole worker response; mixed prose is deliberately not recoverable."""
    require(isinstance(raw, str) and raw.strip(), f"{label}: worker response is empty")
    require(len(raw.encode("utf-8")) <= WORKER_RESULT_MAX_BYTES, f"{label}: response exceeds the byte budget")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvalFailure(f"{label}: response is not one raw JSON object: {error}") from error
    require(isinstance(result, dict), f"{label}: worker response is not a JSON object")
    validate_worker_semantics(result, expected_role, label, "completed")
    return result


def resolve_worker_response_fallback(
    responses: list[str],
    expected_role: str,
    label: str,
) -> dict[str, Any]:
    """Model the raw-JSON fallback and its single format-only retry."""
    require(1 <= len(responses) <= 2, f"{label}: fallback allows at most one retry")
    errors: list[str] = []
    for index, raw in enumerate(responses, start=1):
        try:
            return parse_worker_response(raw, expected_role, f"{label}.attempt[{index}]")
        except EvalFailure as error:
            errors.append(str(error))
    return {
        "role": expected_role,
        "status": "blocked",
        "termination": "invalid_result",
        "changed_files": [],
        "checks": [],
        "tool_failures": [],
        "artifacts": [],
        "blocker": {
            "code": "invalid_result",
            "message": f"worker result remained invalid after {len(errors)} attempt(s)",
            "needs_user_input": False,
        },
    }


def validate_worker_archive(
    relative_path: str,
    expected_role: str,
    required_module: str,
    required_symbols: list[str],
    target_files: list[str],
    required_checks: list[str],
    host_termination: str,
    label: str,
) -> dict[str, Any]:
    result = load_json(resolve_repo_path(relative_path, label))
    validate_worker_semantics(result, expected_role, label, host_termination)
    require(set(result["changed_files"]).issubset(target_files), f"{label}: worker changed files outside the fixture target")
    if result["status"] == "completed":
        require(result["changed_files"], f"{label}: completed change event has no changed files")
        require({item["criterion"] for item in result["checks"]} == set(required_checks), f"{label}: worker checks do not match assigned checks")
        for index, check in enumerate(result["checks"]):
            execute_fixture_check(
                check["check"],
                check["result"],
                check["evidence"],
                required_module,
                required_symbols,
                f"{label}.checks[{index}]",
            )
    return result


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

    run = case["run_result"]
    validate_result("run", run)
    seen_agents: set[str] = set()
    reviews: list[dict[str, Any]] = []
    acceptances: list[dict[str, Any]] = []
    acceptance_revisions: list[tuple[int, str]] = []
    developer_assignments: list[tuple[int, set[str]]] = []
    worker_index = 0
    required_worker_exit: str | None = None
    latest_acceptance: dict[str, tuple[int, str]] = {}
    latest_review: str | None = None
    pending_fix_source: str | None = None
    pending_fix_checks: set[str] | None = None
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
        if required_worker_exit is not None:
            require(event_type == "exit", f"{label}: work continued after incomplete worker")

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
                role = "fixer"
                require(pending_fix_source is not None, f"{label}: fixer ran without a failed review or gate")
                require(
                    set(event.get("failure_packet_keys", [])) == {"title", "file", "line", "evidence"},
                    f"{label}: fixer packet leaked or omitted context",
                )
                require(
                    set(event["required_checks"]) == pending_fix_checks,
                    f"{label}: fixer checks do not match the failed findings or probes",
                )
            else:
                role = "developer"
                require(latest_review is None, f"{label}: developer ran after review started")
                require(event["required_checks"], f"{label}: developer has no assigned acceptance checks")

            require(worker_index < len(run["worker_files"]), f"{label}: worker result archive is missing")
            worker_result = validate_worker_archive(
                run["worker_files"][worker_index],
                role,
                required_module,
                required_symbols,
                case["target_files"],
                event["required_checks"],
                event["transport"],
                f"{case_id}.workers[{worker_index + 1}]",
            )
            worker_index += 1
            if worker_result["status"] == "completed":
                if role == "fixer":
                    pending_fix_source = None
                    pending_fix_checks = None
            elif worker_result["termination"] == "invalid_result":
                required_worker_exit = "worker_result_invalid"
            elif worker_result["status"] == "blocked":
                required_worker_exit = "worker_blocked"
            else:
                required_worker_exit = "worker_failed"
            revision += 1
            if role == "developer" and worker_result["status"] == "completed":
                developer_assignments.append((revision, set(event["required_checks"])))
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
            acceptance_revisions.append((revision, event["criterion"]))
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
            pending_fix_checks = {item["title"] for item in failed_findings} or None

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
            if gate_status == "fail":
                failed_probe_checks = {
                    f"gate probe: {probe['category']}"
                    for probe in event["result"]["probes"]
                    if probe["result"] == "fail"
                }
                pending_fix_checks = {
                    item["title"] for item in event["result"]["findings"]
                } | failed_probe_checks
                require(pending_fix_checks, f"{label}: failed gate has no fixer check source")
            else:
                pending_fix_checks = None

        elif event_type == "exit":
            require(index == len(events) - 1, f"{label}: exit must be the last event")
            exit_reason = event.get("reason")

    require(exit_reason is not None, f"{case_id}: missing exit event")
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
    for assignment_revision, assigned_checks in developer_assignments:
        executed = {
            criterion
            for acceptance_revision, criterion in acceptance_revisions
            if acceptance_revision == assignment_revision
        }
        require(
            assigned_checks.issubset(executed),
            f"{case_id}: developer checks were not rerun as acceptance on its revision",
        )
    require(worker_index == len(run["worker_files"]), f"{case_id}: worker artifacts disagree with controller events")
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
    if exit_reason in {"worker_blocked", "worker_failed", "worker_result_invalid"}:
        require(exit_reason == required_worker_exit, f"{case_id}: worker exit reason contradicts worker result")
        require(gate_status != "hold", f"{case_id}: worker exit cannot follow a held gate")
    if required_worker_exit is not None:
        require(exit_reason == required_worker_exit, f"{case_id}: incomplete worker did not control run exit")


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


def expect_worker_rejected(
    result: dict[str, Any],
    mutation: str,
    host_termination: str | None = None,
) -> None:
    try:
        validate_worker_semantics(result, None, mutation, host_termination)
    except EvalFailure:
        return
    raise EvalFailure(f"worker guard mutation was not rejected: {mutation}")


def run_worker_contract_tests() -> tuple[int, int]:
    paths = [
        ROOT / "evals/fixtures/archives/developer-clean.json",
        ROOT / "evals/fixtures/archives/developer-fleet.json",
        ROOT / "evals/fixtures/archives/fixer-fleet.json",
    ]
    completed_results = [load_json(path) for path in paths]
    for index, result in enumerate(completed_results, start=1):
        validate_worker_semantics(result, result["role"], f"worker-positive[{index}]", "completed")

    blocked = copy.deepcopy(completed_results[0])
    blocked.update(
        {
            "status": "blocked",
            "termination": "timeout",
            "changed_files": [],
            "checks": [],
            "artifacts": [],
            "blocker": {"code": "timeout", "message": "delegation timed out", "needs_user_input": False},
        }
    )
    validate_worker_semantics(blocked, "developer", "worker-positive-blocked", "timeout")

    failed = copy.deepcopy(completed_results[0])
    failed.update(
        {
            "status": "failed",
            "termination": "tool_error",
            "checks": [],
            "tool_failures": [
                {
                    "tool": "exec",
                    "operation": "test",
                    "error": "process failed",
                    "artifact_path": None,
                }
            ],
            "artifacts": [],
            "blocker": {"code": "tool_error", "message": "test tool failed", "needs_user_input": False},
        }
    )
    validate_worker_semantics(failed, "developer", "worker-positive-failed", "tool_error")

    invalid = copy.deepcopy(blocked)
    invalid["termination"] = "invalid_result"
    invalid["blocker"] = {
        "code": "invalid_result",
        "message": "format retry was schema-invalid",
        "needs_user_input": False,
    }
    validate_worker_semantics(invalid, "developer", "worker-positive-invalid", "completed")

    assertion = copy.deepcopy(completed_results[0])
    assertion["checks"][0].update(
        {
            "kind": "assertion",
            "check": "documentation states that ISO dates are preserved",
            "exit_code": None,
            "evidence": "observed in the confirmed documentation",
        }
    )
    validate_worker_semantics(assertion, "developer", "worker-positive-assertion", "completed")

    completed_with_failure = copy.deepcopy(completed_results[0])
    completed_with_failure["checks"][0]["result"] = "fail"
    completed_with_failure["checks"][0]["exit_code"] = 1
    expect_worker_rejected(completed_with_failure, "completed with failed check")

    completed_timeout = copy.deepcopy(completed_results[0])
    completed_timeout["termination"] = "timeout"
    expect_worker_rejected(completed_timeout, "timeout treated as completed")

    completed_tool_failure = copy.deepcopy(completed_results[0])
    completed_tool_failure["tool_failures"] = [
        {
            "tool": "exec",
            "operation": "test",
            "error": "process failed",
            "artifact_path": None,
        }
    ]
    expect_worker_rejected(completed_tool_failure, "completed with tool failure")

    blocked_without_reason = copy.deepcopy(blocked)
    blocked_without_reason["blocker"] = None
    expect_worker_rejected(blocked_without_reason, "blocked without blocker")

    false_pass = copy.deepcopy(completed_results[0])
    false_pass["checks"][0]["exit_code"] = 1
    expect_worker_rejected(false_pass, "pass with nonzero exit code")

    missing_exit = copy.deepcopy(completed_results[0])
    missing_exit["checks"][0]["exit_code"] = None
    expect_worker_rejected(missing_exit, "command pass with missing exit code")

    tool_error_without_evidence = copy.deepcopy(failed)
    tool_error_without_evidence["tool_failures"] = []
    expect_worker_rejected(tool_error_without_evidence, "tool error without evidence")

    extra_field = copy.deepcopy(completed_results[0])
    extra_field["reasoning"] = "should not be accepted"
    expect_worker_rejected(extra_field, "schema accepted an extra field")

    host_timeout_with_completed_body = copy.deepcopy(completed_results[0])
    expect_worker_rejected(
        host_timeout_with_completed_body,
        "host timeout paired with completed body",
        "timeout",
    )

    body_timeout_after_normal_return = copy.deepcopy(blocked)
    expect_worker_rejected(
        body_timeout_after_normal_return,
        "normal host return paired with timeout body",
        "completed",
    )

    mismatched_blocker = copy.deepcopy(blocked)
    mismatched_blocker["blocker"]["code"] = "cancelled"
    expect_worker_rejected(mismatched_blocker, "timeout paired with cancelled blocker", "timeout")

    assertion_with_exit = copy.deepcopy(assertion)
    assertion_with_exit["checks"][0]["exit_code"] = 0
    expect_worker_rejected(assertion_with_exit, "assertion disguised as a command")

    oversized_evidence = copy.deepcopy(completed_results[0])
    oversized_evidence["checks"][0]["evidence"] = "x" * 513
    expect_worker_rejected(oversized_evidence, "oversized evidence excerpt")

    oversized_envelope = copy.deepcopy(completed_results[0])
    oversized_envelope["checks"] = []
    for index in range(32):
        item = copy.deepcopy(completed_results[0]["checks"][0])
        item["criterion"] = f"check {index}"
        item["check"] = "x" * 2048
        item["evidence"] = "x" * 512
        oversized_envelope["checks"].append(item)
    expect_worker_rejected(oversized_envelope, "oversized worker envelope")

    bad_digest = copy.deepcopy(completed_results[0])
    bad_digest["artifacts"][0]["sha256"] = "0" * 64
    expect_worker_rejected(bad_digest, "artifact digest mismatch")

    missing_artifact = copy.deepcopy(completed_results[0])
    missing_path = "evals/fixtures/artifacts/missing.log"
    missing_artifact["checks"][0]["artifact_path"] = missing_path
    missing_artifact["artifacts"][0]["path"] = missing_path
    expect_worker_rejected(missing_artifact, "missing artifact")

    undeclared_artifact = copy.deepcopy(completed_results[0])
    undeclared_artifact["artifacts"] = []
    expect_worker_rejected(undeclared_artifact, "referenced artifact was undeclared")

    unreferenced_artifact = copy.deepcopy(completed_results[0])
    unreferenced_artifact["checks"][0]["artifact_path"] = None
    expect_worker_rejected(unreferenced_artifact, "declared artifact was unreferenced")

    wrong_artifact_size = copy.deepcopy(completed_results[0])
    wrong_artifact_size["artifacts"][0]["bytes"] += 1
    expect_worker_rejected(wrong_artifact_size, "artifact byte count mismatch")

    duplicate_artifact = copy.deepcopy(completed_results[0])
    duplicate_artifact["artifacts"].append(copy.deepcopy(duplicate_artifact["artifacts"][0]))
    expect_worker_rejected(duplicate_artifact, "duplicate artifact declaration")

    escaped_artifact = copy.deepcopy(completed_results[0])
    escaped_payload = (ROOT / "LICENSE").read_bytes()
    escaped_artifact["checks"][0]["artifact_path"] = "LICENSE"
    escaped_artifact["artifacts"][0] = {
        "path": "LICENSE",
        "bytes": len(escaped_payload),
        "sha256": hashlib.sha256(escaped_payload).hexdigest(),
    }
    expect_worker_rejected(escaped_artifact, "artifact escaped isolated storage")
    return 7, 21


def run_worker_exit_transition_tests(cases: list[dict[str, Any]]) -> int:
    base = next(case for case in cases if case["id"] == "clean-diff-held-by-gate")
    scenarios = [
        ("timeout", "evals/fixtures/archives/developer-timeout.json", "worker_blocked"),
        ("tool_error", "evals/fixtures/archives/developer-tool-error.json", "worker_failed"),
        ("completed", "evals/fixtures/archives/developer-invalid.json", "worker_result_invalid"),
    ]
    for transport, worker_file, exit_reason in scenarios:
        case = copy.deepcopy(base)
        case["id"] = f"worker-exit-{exit_reason}"
        developer = copy.deepcopy(next(event for event in case["events"] if event["type"] == "developer_change"))
        developer["transport"] = transport
        case["events"] = [case["events"][0], developer, {"type": "exit", "reason": exit_reason}]
        case["run_result"]["exit_reason"] = exit_reason
        case["run_result"]["iterations"] = []
        case["run_result"]["acceptance"] = []
        case["run_result"]["worker_files"] = [worker_file]
        case["run_result"]["gate_files"] = []
        case["run_result"]["gate"] = {
            "status": "not_run",
            "snapshot": None,
            "independence": None,
        }
        validate_case(case)
    return len(scenarios)


def run_worker_fallback_tests() -> tuple[int, int]:
    completed = load_json(ROOT / "evals/fixtures/archives/developer-clean.json")
    raw = json.dumps(completed)
    require(
        resolve_worker_response_fallback([raw], "developer", "fallback-valid") == completed,
        "fallback changed a valid whole-object response",
    )
    require(
        resolve_worker_response_fallback(["not json", raw], "developer", "fallback-retry") == completed,
        "fallback did not accept the one allowed format retry",
    )

    rejected = 0
    for label, responses in [
        ("mixed prose", [f"completed\n{raw}", f"```json\n{raw}\n```"]),
        ("malformed twice", ["{", "still not json"]),
        ("oversized twice", ["x" * (WORKER_RESULT_MAX_BYTES + 1)] * 2),
    ]:
        result = resolve_worker_response_fallback(responses, "developer", label)
        validate_worker_semantics(result, "developer", label, "completed")
        require(result["termination"] == "invalid_result", f"{label}: invalid fallback did not fail closed")
        rejected += 1

    try:
        resolve_worker_response_fallback(["{}", "{}", "{}"], "developer", "too-many-retries")
    except EvalFailure:
        rejected += 1
    else:
        raise EvalFailure("fallback accepted more than one retry")
    return 2, rejected


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

    substituted_fixer_check = copy.deepcopy(by_id["failed-review-fixed-by-fresh-reviewer"])
    substituted_fixer = next(
        event for event in substituted_fixer_check["events"] if event["type"] == "fixer_change"
    )
    substituted_fixer["required_checks"] = ["Known callers still return totals"]
    substituted_fixer_check["run_result"]["worker_files"][1] = (
        "evals/fixtures/archives/fixer-unrelated.json"
    )
    expect_rejected(substituted_fixer_check, "fixer substituted an unrelated passing check")

    changed = copy.deepcopy(by_id["blind-context-unavailable"])
    changed["events"].insert(
        1,
        {
            "type": "developer_change",
            "actor": "developer-1",
            "transport": "completed",
            "required_checks": ["The formatter preserves ISO dates"],
        },
    )
    expect_rejected(changed, "code changed after failed preflight")

    fabricated = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    acceptance = next(event for event in fabricated["events"] if event["type"] == "acceptance")
    acceptance["check"] = "definitely-not-a-real-command"
    expect_rejected(fabricated, "fabricated acceptance result")

    unreviewed = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    snapshot_index = next(index for index, event in enumerate(unreviewed["events"]) if event["type"] == "snapshot")
    unreviewed["events"].insert(
        snapshot_index,
        {
            "type": "developer_change",
            "actor": "developer-after-review",
            "transport": "completed",
            "required_checks": ["The formatter preserves ISO dates"],
        },
    )
    expect_rejected(unreviewed, "target changed after passing review")

    post_gate = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    post_gate["events"].insert(
        -1,
        {
            "type": "developer_change",
            "actor": "developer-after-gate",
            "transport": "completed",
            "required_checks": ["The formatter preserves ISO dates"],
        },
    )
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

    host_body_mismatch = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    next(event for event in host_body_mismatch["events"] if event["type"] == "developer_change")[
        "transport"
    ] = "timeout"
    expect_rejected(host_body_mismatch, "host timeout contradicted completed worker artifact")

    extra_worker_archive = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    extra_worker_archive["run_result"]["worker_files"].append(
        "evals/fixtures/archives/developer-clean.json"
    )
    expect_rejected(extra_worker_archive, "unmatched worker archive")

    wrong_worker_role = copy.deepcopy(by_id["clean-diff-held-by-gate"])
    wrong_worker_role["run_result"]["worker_files"][0] = "evals/fixtures/archives/fixer-fleet.json"
    expect_rejected(wrong_worker_role, "worker role contradicted controller event")
    return 24


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
    worker_exit_count = run_worker_exit_transition_tests(cases)
    guard_count = 0 if args.no_guard_tests else run_guard_tests(cases)
    worker_positive_count, worker_guard_count = run_worker_contract_tests()
    fallback_positive_count, fallback_guard_count = run_worker_fallback_tests()
    print(
        f"\n{len(cases)} contract traces passed; {transition_count} authorized reduced transition passed; "
        f"{worker_exit_count} worker-exit transitions passed; {guard_count} guard mutations rejected; "
        f"{worker_positive_count} worker results passed; {worker_guard_count} worker-result mutations rejected; "
        f"{fallback_positive_count} raw-JSON fallback paths passed; {fallback_guard_count} fallback guards rejected."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvalFailure, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL {error}")
        raise SystemExit(1)
