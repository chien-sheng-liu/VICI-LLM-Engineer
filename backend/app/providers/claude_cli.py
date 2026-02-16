from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import asyncio
import os
import json

from .base import Provider


class ClaudeProvider(Provider):
    name = "claude"

    async def generate(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int, api_key: Optional[str] = None
    ) -> Tuple[str, Dict[str, int], Dict[str, Any]]:
        # Try real CLI if available; fallback to simulation in restricted env
        joined = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        cli_path = os.getenv("GATEWAY_CLAUDE_CLI_PATH", "claude")
        model = os.getenv("GATEWAY_CLAUDE_MODEL", "claude-3-haiku")

        # Construct a single prompt for simple CLI usage
        prompt = joined

        # Prepare environment with API key for Anthropic/Claude CLI
        child_env = os.environ.copy()
        key = api_key or os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if key:
            child_env.setdefault("ANTHROPIC_API_KEY", key)

        text_out: Optional[str] = None
        used_cli = False
        exit_code: Optional[int] = None

        # Common CLI styles vary; attempt a couple of patterns:
        # 1) claude -m <model> -t <temp> -M <max_tokens>
        # 2) claude -m <model>
        for args in [
            [cli_path, "-m", model, "-t", str(temperature), "-M", str(max_tokens)],
            [cli_path, "-m", model],
        ]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=child_env,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(input=prompt.encode("utf-8")), timeout=10.0)
                exit_code = proc.returncode
                if exit_code == 0 and stdout:
                    txt = stdout.decode("utf-8", "ignore").strip()
                    # Some CLIs may output JSON; unwrap simple {"output": "..."}
                    try:
                        j = json.loads(txt)
                        if isinstance(j, dict) and "output" in j:
                            txt = str(j["output"]) or txt
                    except Exception:
                        pass
                    text_out = txt
                    used_cli = True
                    break
            except FileNotFoundError:
                break  # CLI not available
            except Exception:
                # Try next pattern or fall back
                continue

        if not text_out:
            # Fallback simulation when CLI unavailable or failed
            text_out = f"[CLAUDE SIM] {joined[:max_tokens]}"

        usage = {
            "prompt_tokens": max(1, len(joined) // 4),
            "completion_tokens": max(1, len(text_out) // 4),
            "total_tokens": max(2, (len(joined) + len(text_out)) // 4),
        }
        meta: Dict[str, Any] = {
            "provider": self.name,
            "model_family": "claude",
            "api_key_present": bool(key),
            "cli_path": cli_path,
            "used_cli": used_cli,
            "exit_code": exit_code,
        }
        # Truncate text according to max_tokens semantics (approx)
        text = text_out[: max_tokens] if max_tokens else text_out
        return text, usage, meta
