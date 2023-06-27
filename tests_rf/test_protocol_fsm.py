#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Test the binding protocol with a virtual RF - **using binding FSM**.

    NB: This test will likely fail with pytest-repeat (pytest -n x); maybe because of
    concurrent access to pty.openpty().
"""

import asyncio
import functools
from datetime import datetime as dt
from typing import TypeVar
from unittest.mock import patch

import pytest

from ramses_rf import Command, Gateway, Packet
from ramses_rf.bind_state import Context, State
from ramses_rf.device.base import Fakeable
from ramses_rf.protocol.protocol import QosProtocol, protocol_factory
from ramses_rf.protocol.protocol_fsm import ProtocolState
from ramses_rf.protocol.transport import transport_factory

from .virtual_rf import VirtualRf, stifle_impersonation_alert

_DeviceStateT = TypeVar("_DeviceStateT", bound=State)
_FakedDeviceT = TypeVar("_FakedDeviceT", bound=Fakeable)


DEFAULT_MAX_WAIT = 0.01  # #  to patch: ramses_rf.protocol.protocol
MIN_GAP_BETWEEN_WRITES = 0  # to patch: ramses_rf.protocol.transport

ASSERT_CYCLE_TIME = 0.001  # max_cycles_per_assert = max_sleep / ASSERT_CYCLE_TIME
DEFAULT_MAX_SLEEP = 1


TEST_DATA = (
    (("40:111111", "CO2"), ("41:888888", "FAN"), ("1298",)),
)  # supplicant, respondent, codes


async def assert_context_state(
    ctx: Context,
    expected_state: type[_DeviceStateT],
    max_sleep: int = DEFAULT_MAX_SLEEP,
):
    for _ in range(int(max_sleep / ASSERT_CYCLE_TIME)):
        await asyncio.sleep(ASSERT_CYCLE_TIME)
        if isinstance(ctx._state, expected_state):
            break
    assert isinstance(ctx._state, expected_state)


async def assert_protocol_state(
    protocol: QosProtocol,
    expected_state: type[ProtocolState],
    max_sleep: int = DEFAULT_MAX_SLEEP,
) -> None:
    for _ in range(int(max_sleep / ASSERT_CYCLE_TIME)):
        await asyncio.sleep(ASSERT_CYCLE_TIME)
        if isinstance(protocol._context._state, expected_state):
            break
    assert isinstance(protocol._context._state, expected_state), expected_state


async def assert_protocol_ready(
    protocol: QosProtocol, max_sleep: int = DEFAULT_MAX_SLEEP
) -> None:
    for _ in range(int(max_sleep / ASSERT_CYCLE_TIME)):
        await asyncio.sleep(ASSERT_CYCLE_TIME)
        if protocol._this_msg is not None:
            break
    assert protocol._this_msg and protocol._this_msg.code == "7FFF"


def gateway_decorator(fnc):
    """Create a virtual RF network with a gateway."""

    @functools.wraps(fnc)
    async def test_wrapper():
        rf = VirtualRf(1)
        rf.set_gateway(rf.ports[0], "18:000730")

        gwy = Gateway(rf.ports[0])
        await gwy.start()

        # quiesce
        await assert_protocol_ready(gwy._protocol)
        # ait assert_device(gwy_0, "18:000730")

        await assert_protocol_state(gwy._protocol, ProtocolState.IDLE)

        try:
            await fnc(gwy)
        finally:
            gwy._transport.close()
            await rf.stop()

    return test_wrapper


def protocol_decorator(fnc):
    """Create a virtual RF network with a protocol stack."""

    @functools.wraps(fnc)
    async def test_wrapper():
        def msg_handler(msg) -> None:
            pass

        rf = VirtualRf(1, start=True)

        protocol = protocol_factory(msg_handler)
        await assert_protocol_state(protocol, ProtocolState.DEAD, max_sleep=0)

        transport = transport_factory(
            protocol,
            port_name=rf.ports[0],
            port_config={},
            enforce_include_list=False,
            exclude_list={},
            include_list={},
        )

        # quiesce
        await assert_protocol_ready(protocol)
        # ait assert_device(gwy_0, "18:000730")

        await assert_protocol_state(protocol, ProtocolState.IDLE)

        try:
            await fnc(protocol)
        finally:
            transport.close()
            await rf.stop()

    return test_wrapper


# Command("RQ --- 18:111111 01:222222 --:------ 12B0 003 07")  # TODO: better handling than AttributeError

II_CMD_STR_0 = " I --- 01:006056 --:------ 01:006056 1F09 003 0005C8"
II_CMD_0 = Command(II_CMD_STR_0)
II_PKT_0 = Packet(dt.now(), f"... {II_CMD_STR_0}")

# TIP: using 18:000730 as the source will prevent impersonation alerts

RQ_CMD_STR_0 = "RQ --- 18:000730 01:222222 --:------ 12B0 001 00"
RP_CMD_STR_0 = "RP --- 01:222222 18:000730 --:------ 12B0 003 000000"

RQ_CMD_0 = Command(RQ_CMD_STR_0)
RQ_PKT_0 = Packet(dt.now(), f"... {RQ_CMD_STR_0}")
RP_PKT_0 = Packet(dt.now(), f"... {RP_CMD_STR_0}")

RQ_CMD_STR_1 = "RQ --- 18:000730 01:222222 --:------ 12B0 001 01"
RP_CMD_STR_1 = "RP --- 01:222222 18:000730 --:------ 12B0 003 010000"

RQ_CMD_1 = Command(RQ_CMD_STR_1)
RQ_PKT_1 = Packet(dt.now(), f"... {RQ_CMD_STR_1}")
RP_PKT_1 = Packet(dt.now(), f"... {RP_CMD_STR_1}")


async def _send_rq_cmd_via_context(
    protocol: QosProtocol, rq_cmd: Command, rq_pkt: Packet, rp_pkt: Packet
) -> None:
    """Using context primitives, send an RQ, and wait for the corresponding RP."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    protocol._context.send_cmd(rq_cmd)
    await assert_context_state(protocol._context, ProtocolState.ECHO)

    protocol._context.pkt_received(rq_pkt)
    await assert_context_state(protocol._context, ProtocolState.WAIT)

    protocol._context.pkt_received(rp_pkt)
    await assert_context_state(protocol._context, ProtocolState.IDLE)


async def _send_rq_cmd_via_protocol(
    protocol: QosProtocol, rq_cmd: Command, rp_pkt: Packet
) -> None:
    """Using protocol methods, send and RQ, and wait for the corresponding RP."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    await protocol.send_cmd(rq_cmd)
    await assert_context_state(protocol._context, ProtocolState.ECHO)

    # Virtual RF will echo the sent cmd
    # await assert_context_state(protocol._context, ProtocolState.WAIT)
    await assert_protocol_state(protocol, ProtocolState.WAIT)
    await assert_context_state(protocol._context, ProtocolState.WAIT)

    protocol.pkt_received(rp_pkt)
    await assert_protocol_state(protocol, ProtocolState.IDLE)


# ######################################################################################


@protocol_decorator
async def _test_flow_00(protocol: QosProtocol):
    """Send two cmds (with no intervening awaits) via context primitives."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    protocol._context.send_cmd(II_CMD_0)
    protocol._context.pkt_received(II_PKT_0)

    protocol._context.send_cmd(RQ_CMD_0)
    protocol._context.pkt_received(RQ_PKT_0)
    protocol._context.pkt_received(RP_PKT_0)

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)


@protocol_decorator
async def _test_flow_01(protocol: QosProtocol):
    """Send an RQ via context primitives."""
    await _send_rq_cmd_via_context(protocol, RQ_CMD_0, RQ_PKT_0, RP_PKT_0)


@protocol_decorator
async def _test_flow_02(protocol: QosProtocol):
    """Send two RQs back-to-back via context primitives."""
    await _send_rq_cmd_via_context(protocol, RQ_CMD_0, RQ_PKT_0, RP_PKT_0)
    await _send_rq_cmd_via_context(protocol, RQ_CMD_1, RQ_PKT_1, RP_PKT_1)


@protocol_decorator
async def _test_flow_03(protocol: QosProtocol):
    """Send an RQ twice (with no RP), then a different RQ via context primitives."""

    await assert_protocol_state(protocol, ProtocolState.IDLE, max_sleep=0)

    protocol._context.send_cmd(RQ_CMD_0)
    await assert_protocol_state(protocol, ProtocolState.ECHO)

    protocol._context.pkt_received(RQ_PKT_0)
    await assert_protocol_state(protocol, ProtocolState.WAIT)

    protocol._context.send_cmd(RQ_CMD_0)  # a re-transmit
    await assert_protocol_state(protocol, ProtocolState.WAIT)

    try:
        protocol._context.send_cmd(RQ_CMD_1)  # a different RQ and still sending
    except RuntimeError:
        pass
    else:
        assert False


@protocol_decorator
async def _test_flow_09(protocol: QosProtocol):
    """Send a second RQ before the first gets its RP via context primitives."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    protocol._context.send_cmd(RQ_CMD_0)
    # protocol._context.pkt_received(RQ_PKT_0)  # required if wanting to assert for WAIT

    # NOTE: above pkt_received() isn't required, but below asserts must be WAIT not ECHO
    await assert_context_state(protocol._context, ProtocolState.ECHO, max_sleep=0)

    try:
        protocol._context.send_cmd(RQ_CMD_1)
    except RuntimeError:
        pass
    else:
        raise False

    await assert_context_state(protocol._context, ProtocolState.ECHO, max_sleep=0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@protocol_decorator
async def _test_flow_10(protocol: QosProtocol):
    """Send two cmds (with no intervening awaits) via protocol methods."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    await protocol.send_cmd(II_CMD_0)  # no response expected
    protocol.pkt_received(II_PKT_0)

    await protocol.send_cmd(RQ_CMD_0)
    await asyncio.sleep(0.005)  # TODO: figure out why this is needed
    protocol.pkt_received(RP_PKT_0)  # TODO: why this here?

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@protocol_decorator
async def _test_flow_11(protocol: QosProtocol):
    """Send an RQ via protocol methods."""
    await _send_rq_cmd_via_protocol(protocol, RQ_CMD_0, RP_PKT_0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@protocol_decorator
async def _test_flow_12(protocol: QosProtocol):
    """Send two RQs back-to-back via protocol methods."""
    await _send_rq_cmd_via_protocol(protocol, RQ_CMD_0, RP_PKT_0)
    await _send_rq_cmd_via_protocol(protocol, RQ_CMD_1, RP_PKT_1)


@patch("ramses_rf.protocol.protocol.DEFAULT_MAX_WAIT", DEFAULT_MAX_WAIT)
@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@protocol_decorator
async def _test_flow_19(protocol: QosProtocol):
    """Send a second RQ before the first gets its RP via protocol methods."""

    await assert_context_state(protocol._context, ProtocolState.IDLE, max_sleep=0)

    await protocol.send_cmd(RQ_CMD_0)
    await assert_context_state(protocol._context, ProtocolState.ECHO, max_sleep=0)

    # protocol.pkt_received(RQ_PKT_0)  # not needed as will be echoed by virtual RF?
    await assert_context_state(protocol._context, ProtocolState.WAIT)

    try:
        await protocol.send_cmd(RQ_CMD_1)
    except asyncio.TimeoutError:
        pass
    else:
        raise False

    await assert_context_state(protocol._context, ProtocolState.WAIT)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@gateway_decorator
async def _test_flow_20(gwy: Gateway):
    """Send two cmds (with no intervening awaits) via the async public API."""

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)

    # await gwy.async_send_cmd(II_CMD_0)  # no response expected
    await gwy.async_send_cmd(RQ_CMD_0)
    # await gwy.async_send_cmd(RQ_CMD_0)
    await gwy.async_send_cmd(RQ_CMD_1)

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@gateway_decorator
async def _test_flow_21(gwy: Gateway):
    """Send two cmds (with no intervening awaits) via the async public API."""

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)

    # await gwy.async_send_cmd(II_CMD_0)  # no response expected
    await gwy.async_send_cmd(RQ_CMD_0)
    # await gwy.async_send_cmd(RQ_CMD_0)
    await gwy.async_send_cmd(RQ_CMD_1)

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@gateway_decorator
async def _test_flow_29(gwy: Gateway):
    """Send a second RQ before the first gets its RP via the async public API."""

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)

    await gwy.async_send_cmd(RQ_CMD_0)
    await assert_context_state(gwy._protocol._context, ProtocolState.ECHO, max_sleep=0)

    #
    await assert_context_state(gwy._protocol._context, ProtocolState.WAIT)

    try:
        await gwy.async_send_cmd(RQ_CMD_1)
    except TypeError:
        pass
    else:
        pass

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)


@patch("ramses_rf.protocol.transport.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES)
@patch(
    "ramses_rf.protocol.protocol._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@gateway_decorator
async def _test_flow_30(gwy: Gateway):
    """Send two cmds (with no intervening awaits) via the non-async public API."""

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)

    gwy.send_cmd(II_CMD_0)  # no response expected
    gwy.send_cmd(RQ_CMD_0)

    await assert_context_state(gwy._protocol._context, ProtocolState.IDLE, max_sleep=0)


# ######################################################################################


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_00():
    """Check state change of two sends using context primitives."""
    await _test_flow_00()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_01():
    """Check state change of a faultless send using context primitives."""
    await _test_flow_01()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_02():
    """Check state change of two faultless sends using context primitives."""
    await _test_flow_02()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_03():
    """Check state change of inappropriate send during a RQ/RP pair."""
    await _test_flow_03()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_09():
    """Check context sending 2nd RQ before first RQ has finished being sent."""
    await _test_flow_09()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_10():
    """Check state change of two sends using protocol methods."""
    await _test_flow_10()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_11():
    """Check state change of a faultless send using protocol methods."""
    await _test_flow_11()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_12():
    """Check state change of a faultless send using protocol methods."""
    await _test_flow_12()


@pytest.mark.xdist_group(name="virtual_rf")
async def test_flow_19():
    """Check protocol sending 2nd RQ before first RQ has finished being sent."""
    await _test_flow_19()


@pytest.mark.xdist_group(name="virtual_rf")
async def OUT_test_flow_20():
    """Check state change of two sends using async gateway methods."""
    await _test_flow_20()


@pytest.mark.xdist_group(name="virtual_rf")
async def OUT_test_flow_21():
    """Check state change of two sends using async gateway methods."""
    await _test_flow_21()


@pytest.mark.xdist_group(name="virtual_rf")
async def OUT_test_flow_29():
    """Check gateway sending 2nd RQ before first RQ has finished being sent."""
    await _test_flow_29()


@pytest.mark.xdist_group(name="virtual_rf")
async def OUT_test_flow_30():
    """Check state change of two sends using non-async gateway methods."""
    await _test_flow_30()
