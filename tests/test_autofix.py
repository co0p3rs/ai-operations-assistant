from pathlib import Path

import pytest

from app.autofix.agent import propose_fix
from app.autofix.guardrails import GuardrailError, assert_readable, assert_writable
from app.store import Incident


def test_agent_cannot_read_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("WEBHOOK_SIGNING_SECRET=do-not-read\n", encoding="utf-8")
    with pytest.raises(GuardrailError):
        assert_readable(tmp_path, ".env")


def test_agent_cannot_write_its_own_package(tmp_path: Path) -> None:
    target = tmp_path / "app" / "autofix" / "guardrails.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(GuardrailError):
        assert_writable(tmp_path, "app/autofix/guardrails.py")


def test_agent_cannot_escape_the_repo(tmp_path: Path) -> None:
    with pytest.raises(GuardrailError, match="escapes"):
        assert_readable(tmp_path, "../outside.py")


def test_proposal_stays_inside_readable_files(tmp_path: Path) -> None:
    for path in (
        "app/assistant.py",
        "app/providers/registry.py",
        "app/llm/service.py",
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")
    incident = Incident(
        incident_id="inc_1",
        request_id="req_1",
        event_id="evt_1",
        summary="demo model returned an empty answer",
    )
    proposal = propose_fix(incident, root=tmp_path)
    assert proposal.incident_id == "inc_1"
    assert "app/assistant.py" in proposal.suspected_files
    assert proposal.blocked == []
