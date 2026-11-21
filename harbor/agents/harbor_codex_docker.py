"""Harbor 0.24.0 BaseAgent running Codex CLI strictly INSIDE the task Docker container
using ONLY the container's neutral /usr/local/bin/websearch and /usr/local/bin/webfetch CLIs
(OpenAI's proprietary --search tool is disabled for fair, containerized benchmarking).
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _extract_json_from_text(text: str) -> dict | None:
    for raw in reversed(_JSON_BLOCK.findall(text or "")):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and ("url" in obj or "no_official_source" in obj):
                return obj
        except Exception:
            continue
    return None


class CodexDockerNeutralAgent(BaseAgent):
    @staticmethod
    @override
    def name() -> str:
        return "codex-docker-neutral"

    @override
    def version(self) -> str:
        return "0.171.0"

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        vendor_dir = Path(os.environ.get("CODEX_LINUX_VENDOR_DIR", "/private/tmp/codex_linux_bin"))
        if not (vendor_dir / "bin" / "codex").exists():
            raise FileNotFoundError(
                f"Linux codex vendor dir not found at {vendor_dir}. Set CODEX_LINUX_VENDOR_DIR."
            )
        await environment.exec("mkdir -p /opt/codex /root/.codex")
        await environment.upload_dir(vendor_dir, "/opt/codex")
        await environment.exec("chmod +x /opt/codex/bin/*")

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        model = self.model_name or "gpt-6.1-sol"
        if "/" in model:
            model = model.split("/", 1)[1]

        auth_path = Path(os.environ.get("CODEX_AUTH_JSON", str(Path.home() / ".codex" / "auth.json")))
        if not auth_path.exists():
            raise FileNotFoundError(f"Codex auth.json not found at {auth_path}")

        await environment.upload_file(auth_path, "/root/.codex/auth.json")
        # Disable OpenAI native web_search so the agent uses ONLY neutral container CLIs
        cfg = 'web_search = "disabled"\n'
        cfg_b64 = base64.b64encode(cfg.encode()).decode("ascii")
        await environment.exec(
            f"python3 -c \"import base64; open('/root/.codex/config.toml','wb').write(base64.b64decode('{cfg_b64}'))\""
        )

        prompt_b64 = base64.b64encode(instruction.encode("utf-8")).decode("ascii")
        await environment.exec(
            f"python3 -c \"import base64; open('/tmp/codex-prompt.txt','wb').write(base64.b64decode('{prompt_b64}'))\""
        )

        env_vars = {
            "CODEX_HOME": "/root/.codex",
            "HOME": "/root",
        }
        for k in ("SERPER_API_KEY", "BRAVE_API_KEY", "TAVILY_API_KEY", "WEBSEARCH_PROVIDER"):
            if os.environ.get(k):
                env_vars[k] = os.environ[k]

        cmd = (
            "cd /workspace && "
            f"/opt/codex/bin/codex exec --model {model} "
            "--dangerously-bypass-approvals-and-sandbox "
            "--skip-git-repo-check "
            "--json "
            "-o /tmp/codex-last-message.txt "
            "\"$(cat /tmp/codex-prompt.txt)\" "
            "< /dev/null > /tmp/codex-trajectory.jsonl 2> /tmp/codex-stderr.txt; "
            "RC=$?; echo EXIT_CODE=$RC"
        )
        try:
            res = await environment.exec(cmd, env=env_vars, timeout_sec=280)
            traj_res = await environment.exec("cat /tmp/codex-trajectory.jsonl 2>/dev/null || true")
            err_res = await environment.exec("cat /tmp/codex-stderr.txt 2>/dev/null || true")
            msg_res = await environment.exec("cat /tmp/codex-last-message.txt 2>/dev/null || true")
            ans_res = await environment.exec("cat /workspace/answer.json 2>/dev/null || true")
        finally:
            # Never leave auth credentials inside the container
            await environment.exec("rm -rf /root/.codex /tmp/codex-prompt.txt")

        traj = traj_res.stdout or ""
        stderr = err_res.stdout or ""
        last_msg = msg_res.stdout or ""
        ans_raw = ans_res.stdout or ""

        (self.logs_dir / "trajectory.jsonl").write_text(traj)
        if stderr:
            (self.logs_dir / "codex_stderr.txt").write_text(stderr)
        if last_msg:
            (self.logs_dir / "last_message.txt").write_text(last_msg)

        # Parse token usage & command count from Codex JSONL stream
        in_tok, out_tok, n_cmds = 0, 0, 0
        for line in traj.splitlines():
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "turn.completed" and isinstance(ev.get("usage"), dict):
                in_tok += int(ev["usage"].get("input_tokens", 0) or 0)
                out_tok += int(ev["usage"].get("output_tokens", 0) or 0)
            item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
            if ev.get("type") == "item.completed" and item.get("type") == "command_execution":
                n_cmds += 1

        if in_tok or out_tok:
            context.n_input_tokens = in_tok
            context.n_output_tokens = out_tok

        # Fallback: if agent printed fenced JSON but didn't write /workspace/answer.json
        if not ans_raw.strip():
            extracted = _extract_json_from_text(last_msg)
            if extracted:
                b64 = base64.b64encode(json.dumps(extracted, indent=2).encode("utf-8")).decode("ascii")
                await environment.exec(
                    f"python3 -c \"import base64; open('/workspace/answer.json','wb').write(base64.b64decode('{b64}'))\""
                )
                ans_raw = json.dumps(extracted, indent=2)

        (self.logs_dir / "trajectory_summary.json").write_text(
            json.dumps(
                {
                    "model": model,
                    "runner": "docker-container-neutral-cli",
                    "n_shell_commands": n_cmds,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "exec_stdout": (res.stdout or "").strip(),
                    "answer_raw": ans_raw.strip(),
                },
                indent=2,
            )
            + "\n"
        )
