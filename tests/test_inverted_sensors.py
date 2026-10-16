"""Test inverted sensors (alarmo-max) on startup and unknown transitions.

An inverted sensor is in violation when its raw state is closed/off.
"""

from typing import Any

import pytest
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import mock_restore_cache

from tests.helpers import (
    advance_time,
    cleanup_timers,
    assert_alarm_state,
    setup_alarmo_entry,
    patch_alarmo_integration_dependencies,
)
from tests.factories import AreaFactory, SensorFactory

ALARM_ENTITY = "alarm_control_panel.test_area_1"
GENERIC_DOOR_SENSOR = "binary_sensor.generic_area_1_door_sensor"


def get_inverted_door_sensor(allow_open: bool = False) -> dict[str, Any]:
    """Get an inverted door sensor configuration."""
    sensor_config = SensorFactory.create_door_sensor(
        entity_id=GENERIC_DOOR_SENSOR,
        area="area_1",
        modes=["armed_away", "armed_home"],
        allow_open=allow_open,
    )
    sensor_config["inverted"] = True
    return sensor_config


async def disarm_and_cleanup(hass: Any) -> None:
    """Disarm the alarm and cancel pending timers."""
    await hass.services.async_call(
        "alarmo",
        "disarm",
        {"entity_id": ALARM_ENTITY, "code": "1234"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert_alarm_state(hass, ALARM_ENTITY, "disarmed")
    await cleanup_timers(hass)


@pytest.mark.asyncio
async def test_inverted_sensor_unknown_to_off_triggers_alarm(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """Unknown -> off is a violation for an inverted sensor and must trigger."""
    area = AreaFactory.create_area(
        area_id="area_1", name="Test Area 1", armed_away_entry_time=10
    )
    storage, entry = setup_alarmo_entry(
        hass,
        areas=[area],
        sensors=[get_inverted_door_sensor()],
        entry_id="test_inverted_unknown_to_off",
    )
    mock_restore_cache(
        hass, [State(ALARM_ENTITY, "armed_away", {"arm_mode": "armed_away"})]
    )

    with patch_alarmo_integration_dependencies(storage):
        hass.states.async_set(GENERIC_DOOR_SENSOR, "unknown")
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "armed_away")

        hass.states.async_set(GENERIC_DOOR_SENSOR, "off")
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "pending")

        await advance_time(hass, area["modes"]["armed_away"]["entry_time"] + 1)
        assert_alarm_state(hass, ALARM_ENTITY, "triggered")

        await disarm_and_cleanup(hass)


@pytest.mark.asyncio
async def test_inverted_sensor_unknown_to_on_does_not_trigger(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """Unknown -> on is the safe state for an inverted sensor (initial state)."""
    area = AreaFactory.create_area(area_id="area_1", name="Test Area 1")
    storage, entry = setup_alarmo_entry(
        hass,
        areas=[area],
        sensors=[get_inverted_door_sensor()],
        entry_id="test_inverted_unknown_to_on",
    )
    mock_restore_cache(
        hass, [State(ALARM_ENTITY, "armed_away", {"arm_mode": "armed_away"})]
    )

    with patch_alarmo_integration_dependencies(storage):
        hass.states.async_set(GENERIC_DOOR_SENSOR, "unknown")
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await advance_time(hass, 1)

        hass.states.async_set(GENERIC_DOOR_SENSOR, "on")
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "armed_away")

        await disarm_and_cleanup(hass)


@pytest.mark.asyncio
async def test_inverted_sensor_off_on_startup_triggers_alarm(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """An inverted sensor already off when HA starts armed must trigger."""
    area = AreaFactory.create_area(
        area_id="area_1", name="Test Area 1", armed_away_entry_time=10
    )
    storage, entry = setup_alarmo_entry(
        hass,
        areas=[area],
        sensors=[get_inverted_door_sensor()],
        entry_id="test_inverted_off_on_startup",
    )
    mock_restore_cache(
        hass, [State(ALARM_ENTITY, "armed_away", {"arm_mode": "armed_away"})]
    )

    with patch_alarmo_integration_dependencies(storage):
        hass.states.async_set(GENERIC_DOOR_SENSOR, "off")
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "pending")

        await advance_time(hass, area["modes"]["armed_away"]["entry_time"] + 1)
        assert_alarm_state(hass, ALARM_ENTITY, "triggered")

        await disarm_and_cleanup(hass)


@pytest.mark.asyncio
async def test_inverted_allow_open_sensor_off_on_startup_does_not_trigger(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """An inverted allow_open sensor logically open at startup is skipped."""
    area = AreaFactory.create_area(area_id="area_1", name="Test Area 1")
    storage, entry = setup_alarmo_entry(
        hass,
        areas=[area],
        sensors=[get_inverted_door_sensor(allow_open=True)],
        entry_id="test_inverted_allow_open_startup",
    )
    mock_restore_cache(
        hass, [State(ALARM_ENTITY, "armed_away", {"arm_mode": "armed_away"})]
    )

    with patch_alarmo_integration_dependencies(storage):
        hass.states.async_set(GENERIC_DOOR_SENSOR, "off")
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "armed_away")

        await disarm_and_cleanup(hass)


@pytest.mark.asyncio
async def test_inverted_sensor_on_to_off_while_armed_triggers(
    hass: Any, enable_custom_integrations: Any
) -> None:
    """Regular inverted case: on -> off while armed triggers the alarm."""
    area = AreaFactory.create_area(
        area_id="area_1", name="Test Area 1", armed_away_entry_time=10
    )
    storage, entry = setup_alarmo_entry(
        hass,
        areas=[area],
        sensors=[get_inverted_door_sensor()],
        entry_id="test_inverted_on_to_off",
    )
    mock_restore_cache(
        hass, [State(ALARM_ENTITY, "armed_away", {"arm_mode": "armed_away"})]
    )

    with patch_alarmo_integration_dependencies(storage):
        hass.states.async_set(GENERIC_DOOR_SENSOR, "on")
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "armed_away")

        hass.states.async_set(GENERIC_DOOR_SENSOR, "off")
        await hass.async_block_till_done()
        await advance_time(hass, 1)
        assert_alarm_state(hass, ALARM_ENTITY, "pending")

        await disarm_and_cleanup(hass)
