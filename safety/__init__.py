from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple


@dataclass
class SafeguardConfig:
    """Configuration carrier for SafeguardrailsAdapter.

    The prefix argument allows reusing the guard in both backend and agent code
    with different env variables.
    """

    enabled: bool = True
    prefix: str = "GATEWAY_SAFEGUARD"
    audit_path: Optional[Path] = None
    policy_path: Optional[Path] = None
    fail_open: bool = False
    redact: bool = True
    label: str = "gateway"
    extra_patterns: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "GATEWAY_SAFEGUARD") -> "SafeguardConfig":
        env = os.getenv
        enabled = env(f"{prefix}_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        audit_path_raw = env(f"{prefix}_AUDIT_PATH")
        policy_path_raw = env(f"{prefix}_POLICY_PATH")
        fail_open = env(f"{prefix}_FAIL_OPEN", "1").strip().lower() in {"1", "true", "yes", "on"}
        redact = env(f"{prefix}_REDACT", "1").strip().lower() in {"1", "true", "yes", "on"}
        label = env(f"{prefix}_LABEL", prefix.lower().replace("_safeguard", ""))
        extra = env(f"{prefix}_EXTRA_PATTERNS", "").strip()
        extra_patterns: Dict[str, str] = {}
        if extra:
            for chunk in extra.split(";"):
                if not chunk.strip():
                    continue
                if ":" in chunk:
                    name, pattern = chunk.split(":", 1)
                    extra_patterns[name.strip()] = pattern.strip()
                else:
                    key = f"custom_{len(extra_patterns) + 1}"
                    extra_patterns[key] = chunk.strip()
        return cls(
            enabled=enabled,
            prefix=prefix,
            audit_path=Path(audit_path_raw).expanduser() if audit_path_raw else None,
            policy_path=Path(policy_path_raw).expanduser() if policy_path_raw else None,
            fail_open=fail_open,
            redact=redact,
            label=label,
            extra_patterns=extra_patterns,
        )


@dataclass
class SafeguardDecision:
    stage: str
    allowed: bool
    sanitized_text: str
    reasons: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""
    provider_results: Dict[str, Any] = field(default_factory=dict)

    @property
    def flagged(self) -> bool:
        return not self.allowed

    def to_meta(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "allowed": self.allowed,
            "reasons": self.reasons,
            "findings": self.findings,
            "provider": self.provider_results,
        }


class SafeguardrailsAdapter:
    """Lightweight safeguard rails implementation available to both gateway and agent."""

    DEFAULT_SECRET_PATTERNS: Dict[str, str] = {
        "api_key": r"sk-[a-z0-9]{20,}",
        "openai_key": r"sk-(live|test)-[a-z0-9]{20,}",
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "rsa_private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "ssh_private_key": r"-----BEGIN OPENSSH PRIVATE KEY-----",
        "password_assignment": r"(?i)password\s*[:=]",
    }
    DEFAULT_PII_PATTERNS: Dict[str, str] = {
        "email": r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "us_ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",
        "tw_phone": r"\b09\d{2}-?\d{3}-?\d{3}\b",
    }
    DEFAULT_KEYWORDS: Tuple[str, ...] = (
        "drop table",
        "truncate table",
        "rm -rf",
        "sudo rm",
        "format c:",
        "自殺",
        "炸彈",
    )

    def __init__(self, config: SafeguardConfig):
        self.config = config
        self._regex_patterns: List[Tuple[Pattern[str], str]] = []
        if config.enabled:
            self._regex_patterns = self._compile_patterns(config)
        self._external_guard = self._maybe_load_external_guard(config)
        if config.audit_path is not None:
            config.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def inspect_text(self, text: str, stage: str = "response", actor: str = "gateway") -> SafeguardDecision:
        if not self.config.enabled:
            return SafeguardDecision(stage=stage, allowed=True, sanitized_text=text, raw_text=text)

        findings: List[Dict[str, Any]] = []
        sanitized = text
        for pattern, label in self._regex_patterns:
            for match in pattern.finditer(text):
                snippet = match.group(0)
                findings.append({"label": label, "snippet": snippet})
                if self.config.redact:
                    sanitized = sanitized.replace(snippet, "[REDACTED]")
        allowed = not findings

        provider_meta: Dict[str, Any] = {}
        if self._external_guard is not None:
            ext_allowed, provider_meta = self._external_guard.scan(text, stage)
            allowed = allowed and ext_allowed
            if not ext_allowed and provider_meta:
                findings.append({"label": "safeguardrails", "snippet": provider_meta.get("reason", "blocked")})

        decision = SafeguardDecision(
            stage=stage,
            allowed=allowed,
            sanitized_text=sanitized if (findings and self.config.redact) else text,
            reasons=[f["label"] for f in findings],
            findings=findings,
            raw_text=text,
            provider_results=provider_meta,
        )
        self._write_audit(decision, actor)
        return decision

    def inspect_messages(self, messages: Iterable[Dict[str, str]], actor: str = "gateway") -> SafeguardDecision:
        joined = "\n".join(str(m.get("content", "")) for m in messages)
        return self.inspect_text(joined, stage="prompt", actor=actor)

    def _compile_patterns(self, config: SafeguardConfig) -> List[Tuple[Pattern[str], str]]:
        patterns: List[Tuple[Pattern[str], str]] = []
        for label, regex in {**self.DEFAULT_SECRET_PATTERNS, **self.DEFAULT_PII_PATTERNS, **config.extra_patterns}.items():
            patterns.append((re.compile(regex, re.IGNORECASE), label))
        for keyword in self.DEFAULT_KEYWORDS:
            patterns.append((re.compile(re.escape(keyword), re.IGNORECASE), "keyword"))
        if config.policy_path and config.policy_path.exists():
            try:
                text = config.policy_path.read_text(encoding="utf-8")
                try:
                    policy = json.loads(text)
                except json.JSONDecodeError:
                    policy = self._load_yaml(text)
                block_patterns = policy.get("block_patterns", {}) if isinstance(policy, dict) else {}
                if isinstance(block_patterns, dict):
                    for label, regex in block_patterns.items():
                        patterns.append((re.compile(str(regex), re.IGNORECASE), str(label)))
            except Exception:
                pass
        return patterns

    def _maybe_load_external_guard(self, config: SafeguardConfig):
        try:
            from safeguardrails import SafeGuard  # type: ignore
        except Exception:
            return None
        try:
            if config.policy_path and config.policy_path.exists():
                guard = SafeGuard.from_file(str(config.policy_path))  # type: ignore[attr-defined]
            else:
                preset = getattr(SafeGuard, "from_preset", None)
                guard = preset("pii") if callable(preset) else SafeGuard()  # type: ignore[call-arg]
        except Exception:
            return None

        class _Wrapper:
            def __init__(self, guard_obj: Any):
                self._guard_obj = guard_obj

            def scan(self, text: str, stage: str):
                try:
                    scan_fn = getattr(self._guard_obj, "scan", None)
                    if callable(scan_fn):
                        result = scan_fn(text=text, stage=stage)
                    else:
                        call_fn = getattr(self._guard_obj, "__call__", None)
                        if callable(call_fn):
                            result = call_fn(text=text, stage=stage)
                        else:
                            return True, {}
                except Exception as exc:  # pragma: no cover
                    return False, {"reason": str(exc)}
                if isinstance(result, dict):
                    allowed = bool(result.get("valid", True))
                    meta = {k: v for k, v in result.items() if k != "valid"}
                    meta.setdefault("source", "safeguardrails")
                    return allowed, meta
                return True, {}

        return _Wrapper(guard)

    def _write_audit(self, decision: SafeguardDecision, actor: str) -> None:
        if not self.config.audit_path:
            return
        try:
            entry = {
                "stage": decision.stage,
                "allowed": decision.allowed,
                "reasons": decision.reasons,
                "actor": actor,
                "label": self.config.label,
            }
            with self.config.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @staticmethod
    def _load_yaml(text: str) -> Dict[str, Any]:
        try:
            import yaml  # type: ignore
        except Exception:
            return {}
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}


__all__ = ["SafeguardrailsAdapter", "SafeguardDecision", "SafeguardConfig"]
