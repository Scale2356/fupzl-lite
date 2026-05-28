import pathlib
import ast

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "litefupzl"


def test_lite_repo_shape_excludes_old_surfaces():
    forbidden_paths = [
        ROOT / "packages",
        ROOT / "apps" / "phase2-web",
        SRC / "web",
        SRC / "scheduler",
        SRC / "models",
        SRC / "notify",
        SRC / "actions" / "like.py",
        SRC / "actions" / "lottery.py",
        SRC / "actions" / "connect.py",
    ]
    assert not [str(path.relative_to(ROOT)) for path in forbidden_paths if path.exists()]
    assert (ROOT / "apps" / "litefupzl" / "main.py").exists()
    assert (SRC / "oneshot" / "session.py").exists()


def test_runtime_source_has_no_lottery_or_reply_write_path():
    assert SRC.exists()
    forbidden_markers = [
        "create_reply",
        "reply_lottery",
        "maybe_reply_lottery",
        "get_lottery_topics",
    ]
    hits = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)}:{marker}")
    assert hits == []


def test_only_mutual_like_module_uses_post_actions_write_path():
    allowed = {
        SRC / "actions" / "mutual_like.py",
        SRC / "discourse" / "http_bypass.py",
    }
    hits = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in ["/post_actions", "post_action_type_id", "like_post_via_post_actions"]):
            if path not in allowed:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_readme_is_standalone_litefupzl_documentation():
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    forbidden_markers = ["phase3", "phase 3", "fuckpzl", "original project", "原项目"]
    assert [marker for marker in forbidden_markers if marker in text] == []


def test_login_detail_steps_are_artifact_only():
    session_source = (SRC / "oneshot" / "session.py").read_text(encoding="utf-8")
    tree = ast.parse(session_source)
    detail_steps = {"identity", "login-proof", "login-device-proof"}
    public_detail_calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "emit":
            continue
        if len(node.args) < 2:
            continue
        step_arg = node.args[1]
        if not isinstance(step_arg, ast.Constant) or step_arg.value not in detail_steps:
            continue
        public_kw = next((kw.value for kw in node.keywords if kw.arg == "public"), None)
        if not (isinstance(public_kw, ast.Constant) and public_kw.value is False):
            public_detail_calls.append((step_arg.value, node.lineno))

    assert public_detail_calls == []
