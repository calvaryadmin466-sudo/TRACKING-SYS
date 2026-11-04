"""Tests for notification rule matching logic (app.notify.rule_matches)."""
from app.notify import rule_matches
from app.store.base import NotificationRule


def _rule(*, event_types=None, min_severity="warning", active=True):
    return NotificationRule(
        id=1, name="test", organization_id=1,
        event_types=event_types or [], min_severity=min_severity,
        channel="webhook", target="https://example.com/hook", active=active,
    )


def test_inactive_rule_never_matches():
    r = _rule(active=False)
    assert rule_matches(r, "overspeed", "alarm") is False


def test_severity_gating():
    r = _rule(min_severity="alarm")
    assert rule_matches(r, "overspeed", "warning") is False
    assert rule_matches(r, "overspeed", "alarm") is True


def test_empty_event_types_matches_any():
    r = _rule(event_types=[])
    assert rule_matches(r, "overspeed", "alarm") is True
    assert rule_matches(r, "geofence_enter", "warning") is True
    # But severity still gates
    assert rule_matches(r, "geofence_enter", "info") is False


def test_exact_event_type_match():
    r = _rule(event_types=["overspeed", "harsh_braking"])
    assert rule_matches(r, "overspeed", "alarm") is True
    assert rule_matches(r, "harsh_braking", "warning") is True
    assert rule_matches(r, "geofence_enter", "alarm") is False


def test_wildcard_alarm_star():
    r = _rule(event_types=["alarm_*"])
    assert rule_matches(r, "alarm_sos", "alarm") is True
    assert rule_matches(r, "alarm_fatigue", "alarm") is True
    assert rule_matches(r, "overspeed", "alarm") is False


def test_mixed_exact_and_wildcard():
    r = _rule(event_types=["overspeed", "alarm_*"])
    assert rule_matches(r, "overspeed", "alarm") is True
    assert rule_matches(r, "alarm_sos", "alarm") is True
    assert rule_matches(r, "harsh_braking", "alarm") is False


def test_info_severity_passes_info():
    r = _rule(min_severity="info")
    assert rule_matches(r, "overspeed", "info") is True
    assert rule_matches(r, "overspeed", "warning") is True
    assert rule_matches(r, "overspeed", "alarm") is True
