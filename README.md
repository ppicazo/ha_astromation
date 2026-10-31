# Astromation

Home Assistant controller for backyard astrophotography sessions. It watches the outdoor temperature and humidity sensors you choose, computes dew point and dew margin, and reports **Safe** or **Unsafe**. While **Astrophotography Mode** is on, it keeps selected lights off or dimmed, and can turn dew heaters / 12V relays / outlets on or off when risk crosses the threshold.

This integration does not talk to lights or relays over a vendor API. Point it at existing Home Assistant `light` and `switch` entities (Z-Wave relays, smart outlets, etc.).

## What it does

**Dew risk.** Outdoor temperature and humidity are each the average of the sensors you select. Dew point uses the Magnus formula. Dew margin is `air temperature − dew point`. **Unsafe** when the margin is at or below the threshold (default 5°F / ~2.8°C). It returns to **Safe** only after the margin clears the threshold by the hysteresis (default 2°F), so a fog bank does not chatter heaters and notifications. If a sensor drops out, Astromation keeps its last reading in the average until that reading is 30 minutes old.

**Astrophotography Mode** is a manual switch for now. Later it can follow whether a ZWO ASIAir on the LAN is actively capturing. While the mode is on:

- **Blocked lights** are turned off, and turned off again if something else turns them on.
- **Dimmed lights** that are on above the max brightness are capped (default 20%).
- Turning the mode off restores the brightness / on-off state Astromation changed.

**Actuators.** Four lists, so each device can react on Safe, Unsafe, or both:

| List | When |
|------|------|
| Turn on when Unsafe | Dew heaters, 12V relay powering dew straps |
| Turn off when Unsafe | Optional loads you never want during dew risk |
| Turn on when Safe | Optional “all clear” indicators |
| Turn off when Safe | Heaters that should stop once the air dries |

Put a heater in both **Turn on when Unsafe** and **Turn off when Safe**. Leaving a session (mode off) also turns off anything in **Turn on when Unsafe**.

**Notifications.** Use Home Assistant’s normal automation UI. The Astromation device exposes triggers: Became Unsafe, Became Safe, Astrophotography Mode turned on/off. Wire those to Telegram, Discord, or Persistent Notification. The same edges also fire an `astromation_event` bus event if you prefer YAML.

Future factors (sky temperature for cloud cover, an allsky “stars detected” REST feed) plug into the same decision Snapshot without changing the HA shell.

## Install

Home Assistant 2025.1 or newer.

### HACS

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/ppicazo/ha_astromation` and set the type to **Integration**.
3. Search for **Astromation**, download, restart Home Assistant.
4. **Settings → Devices & services → Add integration → Astromation**.

### Manual

1. Copy `custom_components/astromation` into `config/custom_components/astromation`.
2. Restart Home Assistant.
3. Add the **Astromation** integration.

### Setup

1. Select one or more outdoor temperature sensors (`temperature` device class) and humidity sensors (`humidity`).
2. Optionally pick blocked lights, dimmed lights, and the Safe/Unsafe actuator lists.
3. Set dew margin, hysteresis, max brightness, and stale window (thresholds follow your °F/°C unit system).

Entities include outdoor averages, dew point, dew margin, risk, status, Dew Unsafe, Session active, and the Astrophotography Mode switch.

## Example automation

Device trigger **Became Unsafe** → call `notify.telegram` / Discord with the status sensor’s reason. Device trigger **Became Safe** → optional “heaters clearing” message.
