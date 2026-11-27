"""LLM backend: the `claude` CLI in headless mode.

Runs under whatever login the CLI already has, so no API key is needed, and
gives the model built-in web search. Each call is a fresh, tool-restricted
session started in an empty directory with no project settings, hooks or MCP
servers, so nothing on this machine leaks into a forecast.

The model can search and read the web; it cannot run commands, read files or
place orders. Web content is untrusted input and its only outlet is the
structured answer.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

SCRUB_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID")


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: dict[str, Any]
    cost_usd: float
    duration_s: float
    model: str
    turns: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class ClaudeCLI:
    def __init__(self, binary: str = "claude", workdir: str | None = None):
        self.binary = binary
        self.workdir = workdir or tempfile.mkdtemp(prefix="pmbot-llm-")

    def run(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        system: str,
        web: bool = False,
        effort: str | None = None,
        timeout_s: int = 900,
        max_budget_usd: float | None = None,
    ) -> LLMResult:
        cmd = [
            self.binary, "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--system-prompt", system,
            "--json-schema", json.dumps(schema),
            "--no-session-persistence",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--tools", "WebSearch,WebFetch" if web else "",
        ]
        if web:
            cmd += ["--allowedTools", "WebSearch", "WebFetch"]
        if effort:
            cmd += ["--effort", effort]
        if max_budget_usd:
            cmd += ["--max-budget-usd", str(max_budget_usd)]
        env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}
        if "TMPDIR" in env and not os.path.isdir(env["TMPDIR"]):
            env.pop("TMPDIR")
        if not os.path.isdir(self.workdir):
            tempfile.tempdir = None
            self.workdir = tempfile.mkdtemp(prefix="pmbot-llm-")
        started = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, cwd=self.workdir, env=env)
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"timed out after {timeout_s}s") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMError(f"unparseable output (exit {proc.returncode}): {proc.stdout[:300]} {proc.stderr[:300]}") from e
        if out.get("is_error") or out.get("subtype") != "success":
            raise LLMError(f"{out.get('subtype')}: {str(out.get('result'))[:300]}")
        data = out.get("structured_output")
        if not isinstance(data, dict):
            raise LLMError(f"no structured output: {str(out.get('result'))[:300]}")
        return LLMResult(
            data=data,
            cost_usd=float(out.get("total_cost_usd") or 0.0),
            duration_s=time.time() - started,
            model=model,
            turns=int(out.get("num_turns") or 0),
            raw=out,
        )
