"""Endpoints and the credential service never branch on provider names (CLAUDE.md rule)."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
# provider_settings takes the provider id as its URL parameter, so naming providers is its job.
ALLOWED = {"provider_settings.py"}
FORBIDDEN = re.compile(r"""claude-|["'](anthropic|openai|ollama|ollama_cloud)["']""")


def _sources():
    files = [p for p in (APP / "api" / "v1" / "endpoints").glob("*.py") if p.name not in ALLOWED]
    files += [
        APP / "services" / "credential_service.py",
        APP / "services" / "model_settings_service.py",
        APP / "api" / "deps.py",
    ]
    return files


def test_no_provider_names_in_endpoints_or_the_credential_service():
    offenders = []
    for path in _sources():
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(APP)}:{number}: {line.strip()}")
    assert offenders == []


def test_the_boundary_check_would_catch_a_violation():
    assert FORBIDDEN.search('if model.startswith("claude-"):')
    assert FORBIDDEN.search("provider = 'ollama'")
    assert FORBIDDEN.search('if provider == "ollama_cloud":')
    assert not FORBIDDEN.search("provider = LLMService.provider_for(model)")
