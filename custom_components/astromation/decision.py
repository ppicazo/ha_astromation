"""Pure dew-risk and session decisions.

Temperatures are Celsius. Dew margin and hysteresis are Celsius degrees,
not absolute temperatures — do not run them through an absolute converter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from math import log


class Risk(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ControlSettings:
    """Thresholds. Margins are Celsius degrees."""

    dew_margin_c: float
    hysteresis_c: float


@dataclass(frozen=True)
class Snapshot:
    """Inputs for one evaluation.

    Future factors (sky temperature, allsky star detection) land here
    without touching Home Assistant.
    """

    outdoor_c: float | None
    outdoor_rh: float | None
    previous_unsafe: bool | None
    mode_on: bool
    sky_temp_c: float | None = None
    stars_detected: bool | None = None


@dataclass(frozen=True)
class Decision:
    """Result of one evaluation."""

    risk: Risk
    unsafe: bool | None
    dew_point_c: float | None
    dew_margin_c: float | None
    reason: str
    became_unsafe: bool
    became_safe: bool


def dew_point_c(temp_c: float, relative_humidity: float) -> float | None:
    """Magnus dew point. RH is 0–100. Returns None for impossible inputs."""

    if relative_humidity <= 0 or relative_humidity > 100:
        return None
    # Sonntag / Magnus coefficients for water over liquid.
    a = 17.625
    b = 243.04
    gamma = log(relative_humidity / 100.0) + (a * temp_c) / (b + temp_c)
    denominator = a - gamma
    if abs(denominator) < 1e-9:
        return None
    return (b * gamma) / denominator


def resolve_risk(
    margin_c: float | None,
    settings: ControlSettings,
    previous_unsafe: bool | None,
) -> tuple[Risk, bool | None]:
    """Map dew margin onto Safe/Unsafe with hysteresis."""

    if margin_c is None:
        return Risk.UNKNOWN, None

    if previous_unsafe is True:
        if margin_c > settings.dew_margin_c + settings.hysteresis_c:
            return Risk.SAFE, False
        return Risk.UNSAFE, True

    if margin_c <= settings.dew_margin_c:
        return Risk.UNSAFE, True
    return Risk.SAFE, False


def decide(snapshot: Snapshot, settings: ControlSettings) -> Decision:
    """Choose Safe / Unsafe from outdoor temperature and humidity."""

    if snapshot.outdoor_c is None:
        return Decision(
            risk=Risk.UNKNOWN,
            unsafe=None,
            dew_point_c=None,
            dew_margin_c=None,
            reason="Outdoor temperature is unavailable.",
            became_unsafe=False,
            became_safe=False,
        )
    if snapshot.outdoor_rh is None:
        return Decision(
            risk=Risk.UNKNOWN,
            unsafe=None,
            dew_point_c=None,
            dew_margin_c=None,
            reason="Outdoor humidity is unavailable.",
            became_unsafe=False,
            became_safe=False,
        )

    td = dew_point_c(snapshot.outdoor_c, snapshot.outdoor_rh)
    if td is None:
        return Decision(
            risk=Risk.UNKNOWN,
            unsafe=None,
            dew_point_c=None,
            dew_margin_c=None,
            reason="Dew point could not be calculated from the outdoor readings.",
            became_unsafe=False,
            became_safe=False,
        )

    margin = snapshot.outdoor_c - td
    risk, unsafe = resolve_risk(margin, settings, snapshot.previous_unsafe)

    if risk is Risk.UNSAFE:
        reason = (
            f"Dew margin is {margin:.1f}°C "
            f"(air {snapshot.outdoor_c:.1f}°C, dew point {td:.1f}°C). "
            f"At or below the {settings.dew_margin_c:.1f}°C threshold."
        )
    else:
        clear_at = settings.dew_margin_c + settings.hysteresis_c
        reason = (
            f"Dew margin is {margin:.1f}°C "
            f"(air {snapshot.outdoor_c:.1f}°C, dew point {td:.1f}°C). "
            f"Above the {settings.dew_margin_c:.1f}°C threshold"
        )
        if snapshot.previous_unsafe is True:
            reason += f" by more than the {settings.hysteresis_c:.1f}°C hysteresis"
            reason += f" (clears above {clear_at:.1f}°C)"
        reason += "."

    became_unsafe = unsafe is True and snapshot.previous_unsafe is not True
    became_safe = unsafe is False and snapshot.previous_unsafe is True

    if not snapshot.mode_on:
        # Still report risk for planning, but do not pulse transitions that
        # would fire heaters or notifications while the session is off.
        return Decision(
            risk=risk,
            unsafe=unsafe,
            dew_point_c=td,
            dew_margin_c=margin,
            reason=f"Astrophotography mode is off. {reason}",
            became_unsafe=False,
            became_safe=False,
        )

    return Decision(
        risk=risk,
        unsafe=unsafe,
        dew_point_c=td,
        dew_margin_c=margin,
        reason=reason,
        became_unsafe=became_unsafe,
        became_safe=became_safe,
    )


def held_sample(
    fresh: float | None,
    fresh_at: datetime | None,
    held: tuple[float, datetime] | None,
    now: datetime,
    stale_after: timedelta,
) -> tuple[float | None, tuple[float, datetime] | None]:
    """Keep the last good sample through a short dropout."""

    if (
        fresh is not None
        and fresh_at is not None
        and now - fresh_at <= stale_after
    ):
        return fresh, (fresh, fresh_at)
    if held is not None and now - held[1] <= stale_after:
        return held[0], held
    return None, None
