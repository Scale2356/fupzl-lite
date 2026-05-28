import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def _steps(workflow: dict, job: str) -> list[dict]:
    return workflow["jobs"][job]["steps"]


def _step(workflow: dict, job: str, name: str) -> dict:
    matches = [step for step in _steps(workflow, job) if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_artifacts_upload_is_manual_opt_in_for_both_workflows():
    for filename, job in [("oneshot.yml", "oneshot"), ("probes.yml", "probe")]:
        workflow = load_workflow(filename)
        inputs = workflow[True]["workflow_dispatch"]["inputs"]
        assert inputs["upload_artifacts"]["default"] == "false"
        upload = _step(workflow, job, "Upload redacted artifacts")
        assert upload["uses"] == "actions/upload-artifact@v4"
        condition = upload["if"]
        assert "github.event_name == 'workflow_dispatch'" in condition
        assert "inputs.upload_artifacts == 'true'" in condition
        assert condition.strip() != "always()"
        assert "${{ env.LITEFUPZL_OUTPUT_DIR }}/" in upload["with"]["path"]
        assert "output/phase3" not in upload["with"]["path"]


def test_oneshot_workflow_removed_write_action_env_and_schedule_uses_refresh_variable():
    workflow = load_workflow("oneshot.yml")
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["cookie_refresh_enabled"]["default"] == "true"
    env = workflow["jobs"]["oneshot"]["env"]
    forbidden_env = [key for key in env if "LOTTERY" in key]
    assert forbidden_env == []
    assert "LITEFUPZL_MUTUAL_LIKE_USERS_JSON" in env
    assert "secrets.LITEFUPZL_MUTUAL_LIKE_USERS_JSON" in env["LITEFUPZL_MUTUAL_LIKE_USERS_JSON"]
    refresh_expr = env["LITEFUPZL_COOKIE_REFRESH_ENABLED"]
    assert "github.event_name == 'workflow_dispatch'" in refresh_expr
    assert "inputs.cookie_refresh_enabled" in refresh_expr
    assert "vars.LITEFUPZL_COOKIE_REFRESH_ENABLED" in refresh_expr
    assert "vars.FUCKPZL_ONESHOT_COOKIE_REFRESH_ENABLED" in refresh_expr
    assert "|| 'true'" in refresh_expr
    assert "inputs.cookie_refresh_enabled == 'true' && 'true' || 'false'" not in refresh_expr


def test_probe_workflow_never_refreshes_cookies():
    workflow = load_workflow("probes.yml")
    env = workflow["jobs"]["probe"]["env"]
    assert env["LITEFUPZL_COOKIE_REFRESH_ENABLED"] == "false"


def test_cleanup_old_workflow_runs_keeps_pagination_and_retention():
    for filename, job in [("oneshot.yml", "oneshot"), ("probes.yml", "probe")]:
        workflow = load_workflow(filename)
        cleanup = _step(workflow, job, "Cleanup old workflow runs")
        assert cleanup["env"]["ACTIONS_RUNS_KEEP"] == "${{ vars.LITEFUPZL_ACTIONS_RUNS_KEEP || vars.FUCKPZL_ACTIONS_RUNS_KEEP || '15' }}"
        script = cleanup["run"]
        assert "per_page" in script and "100" in script
        assert "page += 1" in script
        assert "all_runs.extend" in script
        assert "cleanup_runs_seen=" in script


def test_workflows_install_selected_browser_backend():
    for filename, job in [("oneshot.yml", "oneshot"), ("probes.yml", "probe")]:
        workflow = load_workflow(filename)
        install = _step(workflow, job, "Install dependencies")
        script = install["run"]
        assert "LITEFUPZL_BROWSER" in script
        assert "patchright install --with-deps chromium" in script
        assert "camoufox)" in script
        assert "camoufox fetch" in script
        assert "playwright install-deps firefox" in script
        assert "playwright install --with-deps firefox" in script
        assert "playwright install --with-deps chromium" in script


def test_oneshot_workflow_runs_auth_probe_only_after_oneshot_failure():
    workflow = load_workflow("oneshot.yml")
    run_oneshot = _step(workflow, "oneshot", "Run oneshot")
    auth_probe = _step(workflow, "oneshot", "Run auth probe")

    assert run_oneshot["id"] == "run_oneshot"
    assert "always()" not in auth_probe["if"]
    assert "steps.run_oneshot.outcome == 'failure'" in auth_probe["if"]
    assert "failure()" in auth_probe["if"]
