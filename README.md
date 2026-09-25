# Config bridge

Keep Home Assistant settings in YAML even after Home Assistant has moved them
out of `configuration.yaml`.

Home Assistant keeps moving settings into config entries, private `.storage`
files and registries, where they're set from the UI and stop being
reviewable, reproducible or in git. MQTT's broker went years ago. `http:` is
imported once and then ignored (and the key breaks in 2027.2). Areas never had
YAML at all. This component reads a `config_bridge:` block and makes Home
Assistant match it on every boot. Anything changed in the UI is put back at
the next restart.

```yaml
config_bridge:
  http:
    use_x_forwarded_for: true
    trusted_proxies: [10.244.0.0/16, 10.96.0.0/12]
  mqtt:
    broker: mosquitto.automation.svc.cluster.local
    username: !secret mqtt_username
    password: !secret mqtt_password
  network:
    adapters: [eth0, 192.168.20.0/24]
  areas:
    mode: exclusive
    items:
      kitchen: { name: Kitchen, icon: mdi:stove, floor_id: ground }
      lounge: { name: Living Room, aliases: [family room] }
```

It is ordinary YAML, so `!secret`, `!include` and packages all work. The
block can be split across package files; Home Assistant merges it, and a
setting defined twice is an error.

## How it behaves

Each thing it manages is a **kind**. Each kind is reconciled at boot, inside
its own error boundary, and ends up in one of three states:

- **In sync:** nothing to do.
- **Applied:** the writes were made, and re-reading Home Assistant confirmed
  them. They're logged at info level.
- **Reported:** nothing was written. A repair issue (Settings → Repairs) gives
  the reason and the exact changes it would have made, with secrets redacted.

A kind reports instead of applying in three cases:

- `report_only: true` is set on it.
- It refuses the plan itself, for example an HTTP config Home Assistant
  couldn't bind.
- Anything goes wrong: an unfamiliar storage version, a live object with
  settings the bridge doesn't know, a reference to something that doesn't
  exist, or an unexpected exception.

It is built to degrade. The bridge leans on Home Assistant internals that
will move. When one does, that kind goes quiet and says so, the others carry
on, and Home Assistant's setup never fails because of it. Nothing sticks:
every boot tries again, so updating the bridge is enough to resume.

Typos are different. Every kind's YAML is checked by `CONFIG_SCHEMA`, so
`check_config` rejects a bad block in CI before it ships. Home Assistant's
*own* rules for a kind (the HTTP store's schema, for example) are applied
inside that kind's boundary instead, because they're what an upgrade can
change.

## Kinds

### `http`

The settings the `http:` block used to take (`base_url` excepted), in the same
shape. Anything left out is Home Assistant's default. The whole config comes
from the YAML.

The HTTP server binds before any custom component loads, so a change can
never apply on the boot where the bridge runs. Home Assistant's own mechanism
for this is a store with a `stable` slot and a `pending` trial for the next
boot. If nothing promotes the trial within five minutes, Home Assistant
reverts it and restarts. The bridge works with that mechanism:

- **The YAML differs from `stable`:** it stages the YAML as `pending`. This
  takes effect at the next restart. **The bridge never restarts Home
  Assistant.**
- **Home Assistant is running on that trial:** it promotes the trial straight
  away, before the timer fires.
- **Home Assistant is running on a trial made in the UI:** it discards that
  trial, or replaces it with the YAML's config and cancels the revert. Either
  way no restart happens, and the UI change is gone at the next boot.
- **Home Assistant couldn't bind the YAML's config:** it reports, and never
  stages that config again until the YAML changes.
- **A trial was reverted before it could be promoted:** it re-stages it once,
  then reports.

After a rebuild with an empty `.storage`, the first boot runs on Home
Assistant's defaults, so ingress is broken until the second boot. Restart the
pod once (`kubectl rollout restart`) to get it back.

Leave `report_only` alone while a staged config is waiting. Report-only
doesn't promote, so Home Assistant's own timer reverts the trial and restarts
once.

### `mqtt`

The broker connection entry. MQTT allows only one entry, so an existing entry
made in the UI is adopted and updated in place. It keeps the same entry id,
so its devices and history stay attached. An entry is created only if none
exists. MQTT reconnects on the same boot.

| setting | default |
|---|---|
| `broker` | required |
| `port` | `1883` |
| `protocol` | `"5"` (or `"3.1.1"`, `"3.1"`) |
| `transport` | `tcp` (or `websockets`, with `ws_path`, `ws_headers`) |
| `username`, `password`, `client_id`, `keepalive` | unset |
| `certificate` (`auto` or a PEM), `client_cert` + `client_key`, `tls_insecure` | unset |
| `discovery` | `true` |
| `discovery_prefix` | `homeassistant` |
| `discovery_qos` | `0` |
| `birth_message`, `will_message` | Home Assistant's `homeassistant/status` messages; `false` disables them |

The bridge writes the same shape MQTT's own dialogs would store. It refuses to
write in two cases:

- **MQTT's config entry version isn't 2.1:** the version this was written
  against.
- **The live entry has settings the bridge doesn't know:** replacing the entry
  would delete them.

### `network`

Which adapters Home Assistant's discovery (mDNS and SSDP) listens on: Settings
→ System → Network. `adapters` lists interface names, networks, or both. A
network picks every adapter with an address in it. That matters here because
multus names its interfaces `net1`, `net2`, … in the order the pod's
annotation lists them, while the subnet is what actually identifies the VLAN.
Every entry has to match an adapter. Home Assistant quietly falls back to
auto-detection on an unknown name, so the bridge reports instead.
`adapters: []` means auto-detect.

Discovery binds before the bridge runs, so a change takes effect at the next
restart.

### `areas`

The area registry. Each key under `items` is the area id: the thing
automations, templates and dashboards refer to. That makes a rename an
update, not a recreate that would drop every device's assignment.

```yaml
areas:
  mode: exclusive        # or owned — required
  items:
    kitchen:
      name: Kitchen                 # required
      icon: mdi:stove
      floor_id: ground              # must exist
      labels: [downstairs]          # label ids; must exist
      aliases: [cooking]
      picture: /local/kitchen.jpg
      temperature_entity_id: sensor.kitchen_temperature
      humidity_entity_id: sensor.kitchen_humidity
```

- **`exclusive`:** the YAML is every area. Areas it doesn't list are deleted.
- **`owned`:** the YAML is the bridge's share. Areas it lists are managed, and
  existing ones are adopted. An area is deleted only if the bridge managed it
  and it has since left the YAML. Areas made in the UI and never listed are
  left alone. The owned set is kept in `.storage/config_bridge`. If that file
  is lost, previously owned areas are left in place rather than deleted.

Fields the YAML leaves out are cleared. Areas are reconciled once Home
Assistant has started, because the temperature and humidity sensors have to
exist first. Anything that would make a write fail is checked before anything
is written:

- a missing floor or label
- a sensor that isn't one
- a name another area already has

`mode: exclusive` with no items is refused.

## Getting started

1. Add an empty `config_bridge:` block and restart. That loads the component
   with nothing to manage.
2. Call `config_bridge.export` from Developer Tools → Actions. It returns what
   Home Assistant has now for every kind, in this YAML's shape, with secrets
   redacted. For `network`, it also lists the available adapters and their
   subnets.
3. Paste that into the YAML, with `report_only: true` on each kind, and deploy.
4. Check Settings → Repairs. A kind with no issue is in sync. An issue lists
   exactly what would change.
5. Remove `report_only` from each kind once its diff is what you meant.

## Adding a kind

1. **The YAML's schema:** in `model/schema.py`, added to `KIND_SCHEMAS`.
2. **The rendering and the decisions:** in `model/`. No Home Assistant imports
   here; this is what the unit tests cover.
3. **The adapter:** in `kinds/`, a `Kind` subclass that plans, applies,
   verifies and exports, registered in `kinds/__init__.py`. Import Home
   Assistant internals inside its methods rather than at module level. A
   renamed module then fails that kind, not the whole bridge.
4. **A guard:** check the internal it depends on (a storage version, an entry
   version) is the one it was written against, and raise `KindError` if not.
   That turns an upgrade that moved it into a report instead of a bad write.

## What it depends on

| kind | Home Assistant internal |
|---|---|
| `http` | `components.http.config`: the store, storage version 2.2 (new in 2026.7, likely to change around 2027.2) |
| `mqtt` | `hass.config_entries`; MQTT entry version 2.1 |
| `network` | `components.network.network.async_get_network`; storage version 1 |
| `areas` | the area, floor and label registries (public helpers) |

When a kind starts reporting after an upgrade, its repair issue names what
moved. The integration tests run against the Home Assistant release homelab
deploys, so a release that moves something should turn CI red before it
reaches the cluster.

## Development

Schemas are written with probatio, the validation library Home Assistant
uses (it answers to `import voluptuous` inside Home Assistant as well). The
unit tests need only pytest and probatio. The integration tests need Python
3.14.2 or later, because they run against the Home Assistant release homelab
deploys, pinned in `.github/workflows/ci.yml`.

```sh
pip install pytest probatio==0.11.4 pytest-homeassistant-custom-component==0.13.365 tzdata ruff==0.16.8
python -m pytest tests/ -c tests/pytest.ini
python -m pytest tests_integration/ -c tests_integration/pytest.ini
ruff check custom_components/ tests/ tests_integration/
ruff format --check custom_components/ tests/ tests_integration/
```
