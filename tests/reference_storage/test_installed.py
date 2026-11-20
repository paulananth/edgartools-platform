"""Installed normal RDM commands on the selected engine, outside the checkout."""
import json

from tests.support.duty import duty_url
from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401


def test_installed_reference_lifecycle_and_search(installed, database_factory):
    python, root = installed
    with database_factory(store="rdm") as (owner, runtime, role):
        owner_env = {"DATA_URL": duty_url(owner, "rdm")}
        runtime_env = {"DATA_URL": duty_url(runtime, "rdm")}
        name = "invented-installed-reference"
        body = {"code_set": {"code_set": name, "name": "Invented reference"}, "version": "1",
                "created_by": "drafter", "codes": [{"code": "a", "label": "AI the well-known reference"}],
                "labels": [{"code": "a", "label": "An alternate", "kind": "synonym"}]}
        draft = root / "reference-draft.json"
        draft.write_text(json.dumps(body))
        out = root / "reference-published"
        program = '''
import json, sys
from edgar_warehouse.cli import main
sys.exit(main(json.load(sys.stdin)))
'''
        def command(parts):
            result = _run(python, "-c", program, env=owner_env if parts[:2] == ["rdm", "init"] else runtime_env, cwd=root, document=parts)
            assert result.returncode == 0, "Installed RDM command failed; connection details withheld"
            return json.loads(result.stdout)
        assert command(["rdm", "init", "--runtime-role", role])
        command(["rdm", "draft", "--file", str(draft)])
        command(["rdm", "approve", name, "1", "--by", "operator", "--words", "Approve this invented test version"])
        command(["rdm", "publish", name, "1", "--out", str(out)])
        assert command(["rdm", "verify", name, "1"])["matches"]
        for words, method in [("AI", "label"), ("the", "label"), ("-second", "label"),
                              ("well-known", "label"), ("an", "synonym")]:
            found = command(["context", name, "--search", words] if not words.startswith('-') else
                            ["context", name, "--search=" + words])
            assert found["matches"][0]["code"] == "a"
            assert found["matches"][0]["matched_by"] == method
        body.update(version="2", supersedes="1")
        body["codes"][0]["label"] = "AI replacement reference"
        draft.write_text(json.dumps(body))
        command(["rdm", "draft", "--file", str(draft)])
        command(["rdm", "approve", name, "2", "--by", "operator", "--words", "Approve this invented replacement"])
        assert command(["rdm", "publish", name, "2", "--out", str(out)])["superseded"] == "1"
        assert command(["context", name, "a"])["trust"]["version"] == "2"  # a code set keeps one version
        command(["rdm", "init", "--runtime-role", role])
        assert command(["rdm", "verify", name, "2"])["matches"]
        assert command(["rdm", "retire", name, "2"])["status"] == "retired"
