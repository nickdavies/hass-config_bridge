"""Energy's model: the YAML's schema, and the preferences it renders to."""

from __future__ import annotations

from collections.abc import Mapping

import probatio
import pytest

from custom_components.config_bridge.object_types.energy.model import (
    SCHEMA,
    export_energy,
    flatten,
    render_energy,
    unknown_keys,
)

# The homelab's meters: a net meter on the grid and a production meter on
# the solar.
GRID = {
    "type": "grid",
    "stat_energy_from": "sensor.xcel_grid_current_summation_delivered_value",
    "stat_energy_to": "sensor.xcel_grid_current_summation_received_value",
}
SOLAR = {
    "type": "solar",
    "stat_energy_from": "sensor.xcel_solar_current_summation_delivered_value",
}

# What the energy dialogs store for those two.
GRID_STORED = {
    **GRID,
    "stat_cost": None,
    "entity_energy_price": None,
    "number_energy_price": None,
    "stat_compensation": None,
    "entity_energy_price_export": None,
    "number_energy_price_export": None,
    "cost_adjustment_day": 0.0,
}
SOLAR_STORED = {**SOLAR, "config_entry_solar_forecast": None}


def power_sensor_id(source_type: str, config: Mapping[str, str]) -> str:
    """Stands in for Home Assistant's `generate_power_sensor_entity_id`."""
    return f"sensor.energy_{source_type}_generated"


def render(conf: dict) -> dict:
    return render_energy(SCHEMA(conf), power_sensor_id)


def test_renders_what_the_dialogs_store() -> None:
    assert render({"energy_sources": [GRID, SOLAR]}) == {
        "energy_sources": [GRID_STORED, SOLAR_STORED],
        "device_consumption": [],
        "device_consumption_water": [],
    }


def test_nothing_is_the_defaults() -> None:
    assert render({}) == {
        "energy_sources": [],
        "device_consumption": [],
        "device_consumption_water": [],
    }


def test_order_is_kept() -> None:
    sources = render({"energy_sources": [SOLAR, GRID]})["energy_sources"]
    assert [source["type"] for source in sources] == ["solar", "grid"]


def test_power_config_sets_stat_rate_as_home_assistant_does() -> None:
    direct = render(
        {"energy_sources": [{**GRID, "power_config": {"stat_rate": "sensor.w"}}]}
    )
    assert direct["energy_sources"][0]["stat_rate"] == "sensor.w"

    inverted = render(
        {
            "energy_sources": [
                {**GRID, "power_config": {"stat_rate_inverted": "sensor.w"}}
            ]
        }
    )
    assert inverted["energy_sources"][0]["stat_rate"] == "sensor.energy_grid_generated"


def test_devices() -> None:
    device = {"stat_consumption": "sensor.fridge_energy", "name": "Fridge"}
    assert render({"device_consumption": [device]})["device_consumption"] == [device]


def test_external_statistics_are_allowed() -> None:
    conf = SCHEMA(
        {"energy_sources": [{**GRID, "stat_energy_from": "opower:xcel_elec"}]}
    )
    assert conf["energy_sources"][0]["stat_energy_from"] == "opower:xcel_elec"


# --- the YAML ----------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        {"type": "wind", "stat_energy_from": "sensor.x"},
        {"type": "solar"},
        {"type": "solar", "stat_energy_from": "not an id"},
        {**SOLAR, "stat_energy_form": "sensor.x"},
        {"type": "grid"},
        {**GRID, "entity_energy_price": "sensor.price", "number_energy_price": 0.12},
        {**GRID, "stat_rate": "sensor.w", "power_config": {"stat_rate": "sensor.w"}},
        {**GRID, "power_config": {}},
        {
            **GRID,
            "power_config": {"stat_rate": "sensor.a", "stat_rate_inverted": "sensor.b"},
        },
        {**GRID, "power_config": {"stat_rate_from": "sensor.a"}},
        {"type": "battery", "stat_energy_from": "sensor.out"},
        {
            "type": "battery",
            "stat_energy_from": "sensor.out",
            "stat_energy_to": "sensor.in",
            "capacity": 0,
        },
    ],
)
def test_refused(source: dict) -> None:
    with pytest.raises(probatio.Invalid):
        SCHEMA({"energy_sources": [source]})


def test_unknown_top_level_key_is_a_typo() -> None:
    with pytest.raises(probatio.Invalid):
        SCHEMA({"energy_source": [GRID]})


def test_a_grid_may_be_power_only() -> None:
    SCHEMA({"energy_sources": [{"type": "grid", "stat_rate": "sensor.w"}]})


# --- the live preferences ----------------------------------------------------


def test_unknown_keys() -> None:
    assert unknown_keys(render({"energy_sources": [GRID, SOLAR]})) == []
    assert unknown_keys(
        {
            "energy_sources": [{**SOLAR_STORED, "forecast_tilt": 30}, {"type": "wind"}],
            "device_consumption": [{"stat_consumption": "sensor.x", "colour": "red"}],
        }
    ) == [
        "device_consumption[0].colour",
        "energy_sources[0].forecast_tilt",
        "energy_sources[1].type: wind",
    ]


def test_flatten_names_each_items_key() -> None:
    flat = flatten(render({"energy_sources": [GRID, SOLAR]}))
    assert flat["energy_sources[0].stat_energy_from"] == GRID["stat_energy_from"]
    assert flat["energy_sources[1].type"] == "solar"


def test_export_round_trips() -> None:
    conf = {
        "energy_sources": [
            {
                **GRID,
                "number_energy_price": 0.12,
                "power_config": {"stat_rate_inverted": "sensor.w"},
            },
            SOLAR,
        ],
        "device_consumption": [{"stat_consumption": "sensor.fridge_energy"}],
    }
    exported = export_energy(render(conf))
    # Unset keys, the zero adjustment and the derived stat_rate are left out.
    assert exported == conf
    assert render(exported) == render(conf)


def test_export_of_the_defaults_is_empty() -> None:
    assert export_energy(render({})) == {}
