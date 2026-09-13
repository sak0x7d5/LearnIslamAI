from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
EXPRESSION = re.compile(r"[$][{][{]\s*([a-zA-Z_]+)[.]")

# Contexts GitHub Actions only resolves inside steps, never in job-level env.
STEP_ONLY_CONTEXTS = {"runner", "steps", "env", "job", "secrets"}


def test_job_level_env_uses_only_job_scoped_contexts():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job_name, job in workflow["jobs"].items():
        for key, value in (job.get("env") or {}).items():
            for context in EXPRESSION.findall(str(value)):
                assert context not in STEP_ONLY_CONTEXTS, (job_name, key, value)


def test_workflow_gates_run_on_pull_requests_and_main():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow[True] if True in workflow else workflow["on"]

    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]
    step_names = [step.get("name", "") for step in workflow["jobs"]["test"]["steps"]]
    for required in ("Verify lock file", "Lint", "Test", "Import application"):
        assert required in step_names, required
