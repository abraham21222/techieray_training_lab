"""Harbor 0.24.0 BaseAgent running Antigravity CLI (Gemini 4 Neon) with full stream-json trajectory capture."""
import asyncio
import base64
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_BLOCKED = re.compile(r"(?<![a-z0-9-])(?:[a-z0-9-]+\.)*techieray\.com(?![a-z0-9-])", re.I)


def _extract_answer(text: str, workdir: Path) -> dict | None:
    p = workdir / "answer.json"
    if p.exists():
        try:
            obj = json.loads(p.read_text())
            if isinstance(obj, dict) and ("url" in obj or "no_official_source" in obj):
                return obj
        except Exception:
            pass
    for raw in reversed(_JSON_BLOCK.findall(text or "")):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and ("url" in obj or "no_official_source" in obj):
                return obj
        except Exception:
            continue
    try:
        obj = json.loads((text or "").strip())
        if isinstance(obj, dict) and ("url" in obj or "no_official_source" in obj):
            return obj
    except Exception:
        pass
    return None


class AgyNeonAgent(BaseAgent):
    @staticmethod
    @override
    def name() -> str:
        return "agy-neon"

    @override
    def version(self) -> str:
        return "1.5.13"

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        model = self.model_name or "gemini-4-neon-medium"
        if "/" in model:
            model = model.split("/", 1)[1]

        prompt = (
            instruction
            + "\n\nNote: Use ONLY web research tools (do NOT inspect local files or parent directories). "
            + "Keep searches focused (at most 5-6 searches); if you cannot find an official primary source after checking official government portals, conclude no_official_source=true rather than looping. "
            + "Finish with the final ```json fenced block AND (optionally) ./answer.json."
        )

        with tempfile.TemporaryDirectory(prefix="harbor_agy_neon_") as td:
            workdir = Path(td)
            agy_bin = os.environ.get("AGY_BIN") or shutil.which("agy") or "agy"
            cmd = [
                agy_bin,
                "--model", model,
                "--dangerously-skip-permissions",
                "--disable-slash-commands",
                "--output-format", "stream-json",
                "--print-timeout", "300s",
                f"-p={prompt}",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await proc.communicate()
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")

            # Save full NDJSON trajectory for Harbor inspection
            (self.logs_dir / "trajectory.jsonl").write_text(stdout)
            if stderr:
                (self.logs_dir / "agy_stderr.txt").write_text(stderr)

            resp_text = ""
            usage = {}
            tool_calls = []
            for line in stdout.splitlines():
                line = line.strip()
                if not (line.startswith("{") and line.endswith("}")):
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if "response" in ev and ev.get("response"):
                    resp_text = ev["response"]
                elif ev.get("type") in ("assistant", "message", "text") and isinstance(ev.get("text"), str):
                    resp_text = ev["text"]
                if ev.get("usage"):
                    usage = ev["usage"]
                if ev.get("tool_name") or ev.get("type") in ("tool_use", "tool_call"):
                    tool_calls.append(ev)

            if usage:
                context.n_input_tokens = usage.get("input_tokens")
                context.n_output_tokens = usage.get("output_tokens")

            ans = _extract_answer(resp_text or stdout, workdir) or {}
            if _BLOCKED.search(stdout) or _BLOCKED.search(resp_text):
                ans["blocked_domain_seen"] = True

            (self.logs_dir / "parsed_answer.json").write_text(json.dumps(ans, indent=2) + "\n")
            (self.logs_dir / "trajectory_summary.json").write_text(json.dumps({
                "model": model,
                "n_events": len([l for l in stdout.splitlines() if l.strip().startswith("{")]),
                "n_tool_calls_detected": len(tool_calls),
                "usage": usage,
                "blocked_domain_seen": bool(ans.get("blocked_domain_seen")),
                "answer": ans,
            }, indent=2) + "\n")

            b64 = base64.b64encode(json.dumps(ans, indent=2).encode("utf-8")).decode("ascii")
            await environment.exec(
                f"python3 -c \"import base64; open('/workspace/answer.json','wb').write(base64.b64decode('{b64}'))\""
            )
