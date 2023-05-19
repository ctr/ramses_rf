#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Test the gwy Addr detection and the Gateway.send_cmd API from '18:000730'.
"""

import asyncio
from unittest.mock import patch

import pytest
from serial.tools.list_ports import comports

from ramses_rf import Command, Device, Gateway
from tests_rf.virtual_rf import HgiFwTypes, VirtualRf

MIN_GAP_BETWEEN_WRITES = 0  # to patch ramses_rf.protocol.transport

ASSERT_CYCLE_TIME = 0.001  # max_cycles_per_assert = max_sleep / ASSERT_CYCLE_TIME
DEFAULT_MAX_SLEEP = 0.01  # 0.005 fails occasionally


GWY_ID_ = "18:111111"

CONFIG = {
    "config": {
        "disable_discovery": True,
        "enforce_known_list": False,
    }
}


CMDS_COMMON = (  # test command strings
    r" I --- 18:000730 --:------ 18:000730 30C9 003 000666",
    f" I --- 18:000730 --:------ {GWY_ID_} 30C9 003 000777",
    f" I --- {GWY_ID_} --:------ 18:000730 30C9 003 000888",
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000999",
    r"RQ --- 18:000730 63:262142 --:------ 10E0 001 00",
    f"RQ --- {GWY_ID_} 63:262142 --:------ 10E0 001 00",
)
PKTS_NATIVE = (  # expected packet strings
    f" I --- {GWY_ID_} --:------ 18:000730 30C9 003 000666",  # exception from pkt layer: There is more than one HGI80-compatible gateway: Blacklisting a Foreign gateway (or is it HVAC?): 18:000730 (Active gateway: 18:111111), configure the known_list/block_list as required (consider enforcing a known_list)
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000777",
    f" I --- {GWY_ID_} --:------ 18:000730 30C9 003 000888",  # exception from pkt layer: There is more than one HGI80-compatible gateway: Blacklisting a Foreign gateway (or is it HVAC?): 18:000730 (Active gateway: 18:111111), configure the known_list/block_list as required (consider enforcing a known_list)
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000999",
    f"RQ --- {GWY_ID_} 63:262142 --:------ 10E0 001 00",
    f"RQ --- {GWY_ID_} 63:262142 --:------ 10E0 001 00",
)
PKTS_EVOFW3 = (  # expected packet strings
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000666",
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000777",
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000888",
    f" I --- {GWY_ID_} --:------ {GWY_ID_} 30C9 003 000999",
    f"RQ --- {GWY_ID_} 63:262142 --:------ 10E0 001 00",
    f"RQ --- {GWY_ID_} 63:262142 --:------ 10E0 001 00",
)


async def _alert_is_impersonating(self, cmd: Command) -> None:
    """Stifle impersonation alerts when testing."""
    pass


async def assert_devices(
    gwy: Gateway, devices: list[Device], max_sleep: int = DEFAULT_MAX_SLEEP
):
    for _ in range(int(max_sleep / ASSERT_CYCLE_TIME)):
        await asyncio.sleep(ASSERT_CYCLE_TIME)
        if len(gwy.devices) == len(devices):
            break
    assert sorted(d.id for d in gwy.devices) == sorted(devices)


async def assert_expected_pkt(
    gwy: Gateway, expected_frame: str, max_sleep: int = DEFAULT_MAX_SLEEP
):
    for _ in range(int(max_sleep / ASSERT_CYCLE_TIME)):
        await asyncio.sleep(ASSERT_CYCLE_TIME)
        if gwy._this_msg and str(gwy._this_msg._pkt) == expected_frame:
            break
    assert str(gwy._this_msg._pkt) == expected_frame


def pytest_generate_tests(metafunc):
    def id_fnc(param):
        return param._name_

    metafunc.parametrize("test_idx", range(len(CMDS_COMMON)))  # , ids=id_fnc)


@patch(
    "ramses_rf.protocol.transport.PacketProtocolPort._alert_is_impersonating",
    _alert_is_impersonating,
)
async def _test_hgi_device(port_name, cmd_str, pkt_str):
    """Check the virtual RF network behaves as expected (device discovery)."""

    gwy_0 = Gateway(port_name, **CONFIG)  # , known_list={GWY_ID_: {"class": "HGI"}})

    assert gwy_0.devices == []
    assert gwy_0.hgi is None

    await gwy_0.start()
    try:
        await assert_devices(gwy_0, [GWY_ID_])
        assert gwy_0.hgi.id == GWY_ID_

        gwy_0.send_cmd(Command(cmd_str, qos={"retries": 0}))
        await assert_expected_pkt(gwy_0, pkt_str)
    except AssertionError:
        raise
    finally:
        await gwy_0.stop()


@pytest.mark.xdist_group(name="real_serial")
async def test_hgi_actual_evofw3(test_idx):
    """Check the virtual RF network behaves as expected (device discovery)."""

    ports = [p.device for p in comports() if "evofw3" in p.product]

    if ports:
        await _test_hgi_device(ports[0], CMDS_COMMON[test_idx], PKTS_EVOFW3[test_idx])


@pytest.mark.xdist_group(name="real_serial")
async def test_hgi_actual_native(test_idx):
    """Check the virtual RF network behaves as expected (device discovery)."""

    ports = [p.device for p in comports() if "TUSB3410" in p.product]

    if ports:
        await _test_hgi_device(ports[0], CMDS_COMMON[test_idx], PKTS_NATIVE[test_idx])


@pytest.mark.xdist_group(name="mock_serial")
@patch("ramses_rf.protocol.transport._MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
async def test_hgi_mocked_evofw3(test_idx):
    """Check the virtual RF network behaves as expected (device discovery)."""

    rf = VirtualRf(1)
    rf.set_gateway(rf.ports[0], GWY_ID_, fw_version=HgiFwTypes.EVOFW3)

    with patch("ramses_rf.protocol.transport.comports", rf.comports):
        try:
            await _test_hgi_device(
                rf.ports[0], CMDS_COMMON[test_idx], PKTS_EVOFW3[test_idx]
            )
        finally:
            await rf.stop()


@pytest.mark.xdist_group(name="mock_serial")
@patch("ramses_rf.protocol.transport._MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
async def test_hgi_mocked_native(test_idx):
    """Check the virtual RF network behaves as expected (device discovery)."""

    rf = VirtualRf(1)
    rf.set_gateway(rf.ports[0], GWY_ID_, fw_version=HgiFwTypes.NATIVE)

    with patch("ramses_rf.protocol.transport.comports", rf.comports):
        try:
            await _test_hgi_device(
                rf.ports[0], CMDS_COMMON[test_idx], PKTS_NATIVE[test_idx]
            )
        finally:
            await rf.stop()