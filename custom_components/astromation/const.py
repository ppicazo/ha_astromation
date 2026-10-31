"""Constants for the Astromation controller."""

DOMAIN = "astromation"

PLATFORMS = ["sensor", "binary_sensor", "switch"]

CONF_OUTDOOR_TEMP_SENSORS = "outdoor_temp_sensors"
CONF_OUTDOOR_HUMIDITY_SENSORS = "outdoor_humidity_sensors"
CONF_BLOCKED_LIGHTS = "blocked_lights"
CONF_DIMMED_LIGHTS = "dimmed_lights"
CONF_TURN_ON_UNSAFE = "turn_on_when_unsafe"
CONF_TURN_OFF_UNSAFE = "turn_off_when_unsafe"
CONF_TURN_ON_SAFE = "turn_on_when_safe"
CONF_TURN_OFF_SAFE = "turn_off_when_safe"

CONF_DEW_MARGIN = "dew_margin_c"
CONF_HYSTERESIS = "hysteresis_c"
CONF_MAX_BRIGHTNESS = "max_brightness_pct"
CONF_STALE_MINUTES = "stale_minutes"

# Defaults written in °F so they stay readable. Margins are deltas.
DEFAULTS_F = {
    CONF_DEW_MARGIN: 5.0,
    CONF_HYSTERESIS: 2.0,
}

DELTA_KEYS = {CONF_DEW_MARGIN, CONF_HYSTERESIS}

DEFAULT_MAX_BRIGHTNESS = 20
DEFAULT_STALE_MINUTES = 30
DEFAULT_NAME = "Astromation"

FORM_RANGES_F = {
    CONF_DEW_MARGIN: (0.5, 20.0, 0.5),
    CONF_HYSTERESIS: (0.5, 10.0, 0.5),
}

EVENT_ASTROMATION = "astromation_event"
