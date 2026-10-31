"""Dew point, dew margin, and Safe/Unsafe hysteresis."""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "astromation"
    / "decision.py"
)
_SPEC = importlib.util.spec_from_file_location("astromation_decision", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
decision = importlib.util.module_from_spec(_SPEC)
sys.modules["astromation_decision"] = decision
_SPEC.loader.exec_module(decision)

ControlSettings = decision.ControlSettings
Decision = decision.Decision
Risk = decision.Risk
Snapshot = decision.Snapshot
decide = decision.decide
dew_point_c = decision.dew_point_c
held_sample = decision.held_sample

NOW = datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc)


def settings(**overrides: object) -> ControlSettings:
    base = dict(
        dew_margin_c=2.8,  # ~5°F
        hysteresis_c=1.1,  # ~2°F
    )
    base.update(overrides)
    return ControlSettings(**base)


def snap(**overrides: object) -> Snapshot:
    base = dict(
        outdoor_c=10.0,
        outdoor_rh=50.0,
        previous_unsafe=None,
        mode_on=True,
    )
    base.update(overrides)
    return Snapshot(**base)


def test_dew_point_matches_known_magnus_value() -> None:
    # 20°C at 50% RH → dew point ≈ 9.3°C
    td = dew_point_c(20.0, 50.0)
    assert td is not None
    assert abs(td - 9.3) < 0.2


def test_safe_when_margin_is_comfortable() -> None:
    # 15°C / 40% RH → dew point ~1.5°C → margin ~13.5°C
    result = decide(snap(outdoor_c=15.0, outdoor_rh=40.0), settings())
    assert result.risk is Risk.SAFE
    assert result.unsafe is False
    assert result.dew_margin_c is not None and result.dew_margin_c > 10
    assert result.became_unsafe is False


def test_unsafe_when_air_is_near_dew_point() -> None:
    # 10°C / 90% RH → dew point ~8.4°C → margin ~1.6°C (< 2.8)
    result = decide(snap(outdoor_c=10.0, outdoor_rh=90.0), settings())
    assert result.risk is Risk.UNSAFE
    assert result.unsafe is True
    assert result.became_unsafe is True
    assert "threshold" in result.reason


def test_hysteresis_holds_unsafe_until_margin_clears() -> None:
    # Still below clear line (2.8 + 1.1 = 3.9): 10°C / 80% → Td ~6.7 → margin ~3.3
    held = decide(
        snap(outdoor_c=10.0, outdoor_rh=80.0, previous_unsafe=True),
        settings(),
    )
    assert held.risk is Risk.UNSAFE
    assert held.became_safe is False

    # Clear: 10°C / 60% → Td ~2.6 → margin ~7.4
    cleared = decide(
        snap(outdoor_c=10.0, outdoor_rh=60.0, previous_unsafe=True),
        settings(),
    )
    assert cleared.risk is Risk.SAFE
    assert cleared.became_safe is True


def test_mode_off_reports_risk_but_suppresses_transitions() -> None:
    result = decide(
        snap(outdoor_c=10.0, outdoor_rh=90.0, mode_on=False),
        settings(),
    )
    assert result.risk is Risk.UNSAFE
    assert result.unsafe is True
    assert result.became_unsafe is False
    assert "mode is off" in result.reason


def test_missing_sensors_are_unknown() -> None:
    no_temp = decide(snap(outdoor_c=None), settings())
    no_rh = decide(snap(outdoor_rh=None), settings())
    assert no_temp.risk is Risk.UNKNOWN
    assert no_rh.risk is Risk.UNKNOWN


def test_held_sample_keeps_a_fresh_reading_through_a_dropout() -> None:
    now = NOW
    value, held = held_sample(12.0, now, None, now, timedelta(minutes=30))
    assert value == 12.0
    assert held == (12.0, now)

    later = now + timedelta(minutes=5)
    value, held = held_sample(None, None, held, later, timedelta(minutes=30))
    assert value == 12.0

    too_late = now + timedelta(minutes=31)
    value, held = held_sample(None, None, held, too_late, timedelta(minutes=30))
    assert value is None
    assert held is None
