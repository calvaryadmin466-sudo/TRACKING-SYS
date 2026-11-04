"""Notification matching and dispatch. Webhook delivery is real (HTTP POST);
email is only attempted when SMTP is configured, otherwise reported as skipped —
never silently 'delivered'."""
from __future__ import annotations

import os

import httpx

from .store.base import NotificationRule

_SEV_RANK = {"info": 0, "warning": 1, "alarm": 2}


def severity_rank(s: str) -> int:
    return _SEV_RANK.get(s, 0)


def rule_matches(rule: NotificationRule, event_type: str, severity: str) -> bool:
    if not rule.active:
        return False
    if severity_rank(severity) < severity_rank(rule.min_severity):
        return False
    if rule.event_types:
        # support exact match or prefix wildcard like "alarm_*"
        for pat in rule.event_types:
            if pat.endswith("*") and event_type.startswith(pat[:-1]):
                return True
            if pat == event_type:
                return True
        return False
    return True


async def dispatch(rule: NotificationRule, payload: dict) -> tuple[str, str]:
    """Returns (status, detail). status is 'delivered' | 'failed' | 'skipped'."""
    if rule.channel == "webhook":
        if not rule.target:
            return "failed", "no webhook URL configured"
        try:
            async with httpx.AsyncClient(timeout=6.0) as c:
                r = await c.post(rule.target, json=payload)
            if r.status_code >= 400:
                return "failed", f"HTTP {r.status_code}"
            return "delivered", f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            return "failed", str(e)[:200]
    if rule.channel == "email":
        if not os.getenv("SMTP_HOST"):
            return "skipped", "email requires SMTP_HOST/… env (not configured)"
        return "skipped", "SMTP delivery not implemented in this build"
    return "failed", f"unknown channel '{rule.channel}'"
