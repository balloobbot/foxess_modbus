"""Tests for the settings registers having their own, slower poll rate"""

from typing import Callable

from modbus_connection import ModbusConnectionError
from modbus_connection import ModbusTimeoutError

from custom_components.foxess_modbus.common.types import RegisterPollType

from .conftest import Harness

# In the settings block (work mode, the charge/discharge limits, the SoC limits)
_SETTING = 41007  # reads come out in address order, so after _READING
_OTHER_SETTING = 41008
# A reading, so polled every time
_READING = 31000

_POLLS_FOR_DISCONNECTION = 5


def _reads(harness: Harness) -> list[int]:
    return [x.address for x in harness.unit.read_events]


async def _poll_until_settings_due(harness: Harness) -> None:
    """Poll until the settings are due again, leaving that poll to the caller"""
    for _ in range(harness.controller._polls_between_slow_reads - 1):  # noqa: SLF001
        await harness.poll()


async def test_a_setting_is_polled_on_the_first_poll(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()

    assert _reads(harness) == [_READING, _SETTING]


async def test_a_setting_sits_out_the_polls_in_between(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()
    harness.unit.read_events.clear()
    await harness.poll()
    await harness.poll()

    # The reading is still fetched every poll; the setting isn't fetched at all
    assert _reads(harness) == [_READING, _READING]


async def test_a_setting_is_polled_again_once_it_comes_due(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()
    await _poll_until_settings_due(harness)
    harness.unit.read_events.clear()
    await harness.poll()

    assert _reads(harness) == [_READING, _SETTING]


async def test_a_setting_is_read_far_less_often_than_a_reading(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    polls = harness.controller._polls_between_slow_reads * 2  # noqa: SLF001
    for _ in range(polls):
        await harness.poll()

    assert _reads(harness).count(_READING) == polls
    assert _reads(harness).count(_SETTING) == 2
    assert polls > 2


async def test_the_settings_poll_failing_leaves_the_readings_alone(make_harness: Callable[..., Harness]) -> None:
    """A settings read going quiet mustn't cost the readings their poll, or vice versa"""
    harness = make_harness()
    reading = harness.add_entity(_READING)
    setting = harness.add_entity(_SETTING)
    harness.unit.holding[_READING] = 5
    harness.unit.holding[_SETTING] = 9
    harness.unit.fail_read(_SETTING, ModbusTimeoutError())

    await harness.poll()

    # The setting never answered, but the reading did
    assert harness.controller.read(_SETTING, signed=False) is None
    assert harness.controller.read(_READING, signed=False) == 5
    assert reading.changed_addresses == [{_READING}]
    assert setting.changed_addresses == [{_READING}]


async def test_a_failed_settings_poll_is_retried_on_the_next_poll(make_harness: Callable[..., Harness]) -> None:
    """A settings read which didn't get through mustn't wait out the whole interval before trying again"""
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)
    harness.unit.fail_read(_SETTING, ModbusTimeoutError())

    await harness.poll()
    harness.unit.fail_read(_SETTING, None)
    harness.unit.read_events.clear()
    await harness.poll()

    assert _SETTING in _reads(harness)


async def test_writing_a_setting_reads_it_back_on_the_next_poll(make_harness: Callable[..., Harness]) -> None:
    """The write-through cache only covers the value for a moment, so don't wait out the interval after a write"""
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()
    await harness.controller.write_register(_SETTING, 3)
    harness.unit.read_events.clear()
    await harness.poll()

    assert _SETTING in _reads(harness)


async def test_writing_a_reading_does_not_bring_the_settings_forward(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()
    await harness.controller.write_register(_READING, 3)
    harness.unit.read_events.clear()
    await harness.poll()

    assert _SETTING not in _reads(harness)


async def test_settings_are_read_again_after_a_reconnection(make_harness: Callable[..., Harness]) -> None:
    """A reconnected inverter may be a different one, or have been reconfigured while it was away"""
    harness = make_harness()
    harness.add_entity(_READING)
    harness.add_entity(_SETTING)

    await harness.poll()
    harness.unit.fail_requests(ModbusConnectionError("connection refused"))
    for _ in range(_POLLS_FOR_DISCONNECTION):
        await harness.poll()
    assert not harness.controller.is_connected

    harness.unit.fail_requests(None)
    harness.unit.read_events.clear()
    await harness.poll()

    assert harness.controller.is_connected
    assert _SETTING in _reads(harness)


async def test_both_entities_on_a_settings_address_agree_on_its_poll_rate(
    make_harness: Callable[..., Harness],
) -> None:
    """Several settings back both a number and the sensor kept for back compat"""
    harness = make_harness()
    harness.add_entity(_SETTING, _OTHER_SETTING)
    harness.add_entity(_SETTING)

    assert harness.controller._data[_SETTING].poll_type == RegisterPollType.SLOWLY  # noqa: SLF001
    assert harness.controller._data[_OTHER_SETTING].poll_type == RegisterPollType.SLOWLY  # noqa: SLF001
