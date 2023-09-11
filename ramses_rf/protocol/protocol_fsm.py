#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - RAMSES-II compatible packet protocol finite state machine."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime as dt
from datetime import timedelta as td
from enum import IntEnum
from queue import Empty, Full, PriorityQueue
from threading import Lock
from typing import TYPE_CHECKING, Awaitable, Callable, NoReturn

from .exceptions import ProtocolError, ProtocolFsmError, ProtocolSendFailed

# skipcq: PY-W2000
from .const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    Code,
)

if TYPE_CHECKING:  # mypy TypeVars and similar (e.g. Index, Verb)
    # skipcq: PY-W2000
    from .const import Index, Verb  # noqa: F401, pylint: disable=unused-import

if TYPE_CHECKING:
    from . import Command, Packet

_ProtocolT = asyncio.Protocol
_TransportT = asyncio.Transport


_LOGGER = logging.getLogger(__name__)

# All debug flags should be False for end-users
_DEBUG_MAINTAIN_STATE_CHAIN = False  # maintain Context._prev_state


class SendPriority(IntEnum):
    _MAX = -9
    HIGH = -2
    DEFAULT = 0
    LOW = 2
    _MIN = 9


DEFAULT_PRIORITY = SendPriority.DEFAULT

DEFAULT_TIMEOUT = 3.0  # total waiting for successful send
DEFAULT_ECHO_TIMEOUT = 0.50  # waiting for echo pkt after cmd sent
DEFAULT_RPLY_TIMEOUT = 0.50  # waiting for reply pkt after echo pkt received

_DEFAULT_TIMEOUT = td(seconds=DEFAULT_TIMEOUT)
_DEFAULT_ECHO_TIMEOUT = td(seconds=DEFAULT_ECHO_TIMEOUT)
_DEFAULT_RPLY_TIMEOUT = td(seconds=DEFAULT_RPLY_TIMEOUT)

DEFAULT_MAX_RETRIES = 3

POLLING_INTERVAL = 0.0005


class _ProtocolWaitFailed(ProtocolSendFailed):
    """The Command timed out when waiting for its turn to send."""


class _ProtocolEchoFailed(ProtocolSendFailed):
    """The Command was sent OK, but failed to elicit its echo."""


class _ProtocolRplyFailed(ProtocolSendFailed):
    """The Command received an echo OK, but failed to elicit the expected reply."""


class ProtocolContext:
    """A mixin is to add state to a Protocol."""

    MAX_BUFFER_SIZE: int = 10

    _state: _StateT = None  # type: ignore[assignment]
    _proc_queue_task: asyncio.Task = None  # type: ignore[assignment]

    def __init__(self, protocol: _ProtocolT, *args, **kwargs) -> None:
        # super().__init__(*args, **kwargs)
        self._protocol = protocol

        self._loop = asyncio.get_running_loop()
        self._que = PriorityQueue(maxsize=self.MAX_BUFFER_SIZE)
        self._mutex = Lock()

        self.set_state(Inactive)  # set initiate state, pre connection_made

    def __repr__(self) -> str:
        state_name = self.state.__class__.__name__
        return f"Context({state_name}, len(queue)={self._que.unfinished_tasks})"

    def set_state(
        self,
        state: type[_StateT],
        cmd: None | Command = None,
        cmd_sends: int = 0,
    ) -> None:
        """Set the State of the Protocol (context)."""

        # assert not isinstance(self._state, state)  # check a transition has occurred
        _LOGGER.info(f" ... State was moved from {self._state!r} to {state.__name__}")

        if state == IsFailed:  # FailedRetryLimit?
            _LOGGER.warning(f"!!! failed: {self}")

        if _DEBUG_MAINTAIN_STATE_CHAIN:  # HACK for debugging
            prev_state = self._state

        if state in (IsInIdle, IsFailed):
            self._state = state(self)
        else:
            self._state = state(self, cmd=cmd, cmd_sends=cmd_sends)

        if _DEBUG_MAINTAIN_STATE_CHAIN:  # HACK for debugging
            setattr(self._state, "_prev_state", prev_state)

        if isinstance(self._state, (IsInIdle, IsFailed)):
            self._process_queue()

    @property
    def state(self) -> _StateT:
        return self._state

    def connection_made(self, transport: _TransportT) -> None:
        _LOGGER.warning(f"### {self}: connection_made()")  # TODO: remove
        self.state.made_connection(transport)
        self._proc_queue_task = self._loop.create_task(self._send_next_in_queue())

    def connection_lost(self, exc: None | Exception) -> None:
        fut: asyncio.Future  # mypy

        _LOGGER.warning(f"### {self}: connection_lost({exc})")  # TODO: debug
        self.state.lost_connection(exc)

        if self._proc_queue_task:
            self._proc_queue_task.cancel()

        # with self._que.mutex.acquire():
        while True:
            try:
                *_, fut = self._que.get_nowait()
            except Empty:
                break
            fut.cancel()

    def pause_writing(self) -> None:
        _LOGGER.warning(f"### {self}: pause_writing()")  # TODO: debug
        self.state.writing_paused()

    def resume_writing(self) -> None:
        _LOGGER.warning(f"### {self}: resume_writing()")  # TODO: debug
        self.state.writing_resumed()

    def pkt_received(self, pkt: Packet) -> None:
        _LOGGER.warning(f"### {self}: pkt_received({pkt._hdr})")  # TODO: remove
        self.state.rcvd_pkt(pkt)

    async def send_cmd(
        self,
        send_fnc: Awaitable,
        cmd: Command,
        max_retries: int = DEFAULT_MAX_RETRIES,
        wait_for_reply: None | bool = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Packet:
        """Send the Command (with retries) and wait for the expected Packet.

        if wait_for reply is True, wait for the RP/I corresponding to the RQ/W,
        otherwise simply return the echo Packet.

        Raises a ProtocolSendFailed if either max_retires or timeout is exceeded before
        receiving the expected packet.
        """

        def is_future_done(item: tuple) -> bool:
            """Return True if the item's Future is done."""
            fut: asyncio.Future
            *_, fut = item
            return fut.done()

        # HACK: I have no idea if this is kosher (it does appear thread-safe)
        def remove_entries(queue: PriorityQueue, condition: Callable):
            """Removes all entries from the queue that satisfy the condition.."""
            with queue.mutex.acquire():
                queue_copy = queue.queue[:]  # queue attr is a list
                for entry in queue_copy:
                    if condition(entry):
                        queue.queue.remove(entry)

        _LOGGER.warning(f"### {self}: send_cmd({cmd._hdr})")  # TODO: debug

        # _LOGGER.warning(f"### {self} send_cmd({cmd._hdr}): Submitted")  # TODO: remove
        # if self.state.is_active_cmd(cmd):  # no need to queue?

        _LOGGER.error(f"*** send_cmd({cmd._hdr}): Submitted, queueing...")  # TODO

        dt_sent = dt.now()
        dt_expires = dt_sent + td(seconds=timeout)
        fut = self._loop.create_future()
        send_coro = self._send_cmd(send_fnc, cmd, max_retries, wait_for_reply)

        remove_entries(self._que, is_future_done)
        try:
            self._que.put_nowait(  # priority / dt_sent is the priority
                (DEFAULT_PRIORITY, dt_sent, cmd, dt_expires, send_coro, fut)
            )
        except Full:
            _LOGGER.error(f"*** send_cmd({cmd._hdr}): Queue full, cmd discarded")
            fut.set_exception(ProtocolFsmError("Send queue full, cmd discarded"))

        _LOGGER.error(f"*** send_cmd({cmd._hdr}): Processing queue...")  # TODO
        self._process_queue()

        _LOGGER.error(f"*** send_cmd({cmd._hdr}): Waiting for result...")  # TODO
        try:
            pkt: Packet = await asyncio.wait_for(fut, timeout)  # TODO: make return
        except (asyncio.TimeoutError, ProtocolError) as exc:
            _LOGGER.eror(f"*** send_cmd({cmd._hdr}): {exc}")  # TODO
            raise ProtocolSendFailed(f"{cmd._hdr}: {exc}")

        _LOGGER.error(f"*** send_cmd({cmd._hdr}): Returning: {pkt._hdr}")  # TODO
        return pkt

    def _process_queue(self) -> None:
        """Start processing the send queue (called when an appropriate event occurs)."""
        if self._mutex.acquire(blocking=False):
            if self._proc_queue_task.done():
                self._loop.create_task(self._send_next_in_queue())
            self._mutex.release()

    async def _send_next_in_queue(self) -> None:
        """Recurse through the queue until the first 'ready' Command, then send it."""

        cmd: Command  # mypy
        fut: asyncio.Future  # mypy

        try:
            *_, cmd, dt_expires, send_coro, fut = self._que.get_nowait()
        except Empty:
            return

        if fut.cancelled():  # by the wait_for(), no need to log/raise # # TODO: remove
            _LOGGER.error(f"##1 {self}: Cancelled send_cmd: {cmd._hdr}")  # TODO: remove
            await self._send_next_in_queue()  # NOTE: recursion

        elif fut.done():  # incl. cancelled() - no need for above
            _LOGGER.error(f"##1 {self}: Completed send_cmd: {cmd._hdr}")  # TODO: remove
            await self._send_next_in_queue()  # NOTE: recursion

        elif dt_expires <= dt.now():  # ?needed
            _LOGGER.error(f"##1 {self}: Expired send_cmd:   {cmd._hdr}")  # TODO: remove
            fut.set_exception(_ProtocolWaitFailed("Timeout (inner) has expired"))
            await self._send_next_in_queue()  # NOTE: recursion

        else:
            _LOGGER.error(f"##1 {self}: Activated send_cmd: {cmd._hdr}")  # TODO: remove
            fut.set_result(await send_coro)  # mark as DONE

        self._que.task_done()

    async def _send_cmd(
        self,
        send_fnc: Awaitable,
        cmd: Command,
        max_retries: int,
        wait_for_reply: None | bool,
    ) -> Packet:
        """Wrapper to send a command with retries, until success or Exception."""

        try:
            assert isinstance(self.state, IsInIdle)

            self.state.sent_cmd(cmd, max_retries)  # must be *before* actually sent
            assert isinstance(self.state, WantEcho)

        except (AssertionError, ProtocolFsmError, ProtocolSendFailed) as exc:
            raise _ProtocolWaitFailed(f"{self}: Failed ready to send command:  {exc}")

        num_sends = 0
        while num_sends < max_retries:  # if required, resend until RetryLimitExceeded
            num_sends += 1
            await send_fnc(cmd)  # the wrapped function

            try:
                assert isinstance(self.state, WantEcho)
                prev_state, next_state = await self._wait_for_rcvd_echo(
                    self.state, cmd, _DEFAULT_ECHO_TIMEOUT
                )
                assert isinstance(self.state, (WantRply, IsInIdle))
                assert prev_state._echo

                if not cmd.rx_header:  # no reply to wait for
                    # self.set_state(ProtocolState.IDLE)  # state will do this
                    assert isinstance(next_state, IsInIdle)
                    return prev_state._echo

                if (
                    wait_for_reply is False
                    or (wait_for_reply is None and cmd.verb != RQ)
                    or cmd.code == Code._1FC9  # otherwise issues with binding FSM
                ):
                    # binding FSM is implemented at higher layer
                    self.set_state(IsInIdle)  # maybe was: WantRply
                    assert isinstance(next_state, IsInIdle)
                    return prev_state._echo

                assert isinstance(next_state, WantRply)

            except (AssertionError, ProtocolFsmError, ProtocolSendFailed) as exc:
                raise _ProtocolEchoFailed(
                    f"{self}: Failed to receive echo packet: {exc}"
                )

            try:
                prev_state, next_state = await self._wait_for_rcvd_rply(
                    next_state, cmd, _DEFAULT_RPLY_TIMEOUT
                )  # NOTE: is next_state, not self.state
                assert isinstance(next_state, IsInIdle)
                assert prev_state._rply

            except (AssertionError, ProtocolFsmError, ProtocolSendFailed) as exc:
                raise _ProtocolRplyFailed(
                    f"{self}: Failed to receive rply packet: {exc}"
                )

            break  # TODO: remove

        return prev_state._rply

    async def _wait_for_transition(self, old_state: _StateT, until: dt) -> _StateT:
        """Return the new state that the context transitioned to from the old state..

        Raises a TimeoutError if a transition doesn't occur before the timer expires.
        """

        _LOGGER.debug(f"...  - WAITING to leave {old_state}...")
        while until > dt.now():
            if old_state._next_state:
                break
            await asyncio.sleep(POLLING_INTERVAL)
        else:
            _LOGGER.debug(f"...  - FAILURE to leave {old_state} in time")
            raise ProtocolFsmError(f"Failed to leave {old_state} in time")

        _LOGGER.debug(
            f"...  - SUCCESS leaving  {old_state}, to {old_state._next_state}"
        )
        return old_state._next_state

    async def _wait_for_rcvd_echo(
        self, this_state: _StateT, cmd: Command, timeout: dt
    ) -> tuple[_StateT, _StateT]:
        """Wait until the state machine has received the expected echo pkt.

        Raises a InvalidStateError if transitions to the incorrect state.
        Raises a SendTimeoutError if the timeout is exceeded before transitioning.
        """

        _LOGGER.info(f"##1 {self}: Waiting to receive an echo for: {cmd}")

        if not isinstance(this_state, (WantEcho, WantRply)):
            raise ProtocolFsmError(f"Bad transition from {this_state}")

        # may: SendTimeoutError (NB: may have already transitioned)
        next_state = await self._wait_for_transition(this_state, dt.now() + timeout)

        if not isinstance(next_state, (WantRply if cmd.rx_header else IsInIdle)):
            raise ProtocolFsmError(f"Bad transition to {next_state}")

        return this_state, next_state  # for: this_state._echo

    async def _wait_for_rcvd_rply(
        self, this_state: _StateT, cmd: Command, timeout: dt
    ) -> tuple[_StateT, _StateT]:
        """Wait until the state machine has received the expected reply pkt.

        Raises a InvalidStateError if transitiones to the incorrect state.
        Raises a SendTimeoutError if the timeout is exceeded before transitioning.
        """

        _LOGGER.info(f"##1 {self}: Waiting to receive a reply for: {cmd}")

        if not isinstance(this_state, WantRply):
            raise ProtocolFsmError(f"Bad transition from {this_state}")

        # may: SendTimeoutError (NB: may have already transitioned)
        next_state = await self._wait_for_transition(this_state, dt.now() + timeout)

        if not isinstance(next_state, IsInIdle):
            raise ProtocolFsmError(f"Bad transition to {next_state}")

        return this_state, next_state  # for: this_state._rply


class ProtocolStateBase:
    """Protocol may Tx / can Rx according to it's internal state."""

    # state attrs
    cmd: None | Command
    cmd_sends: int

    _next_state: None | _StateT = None

    def __init__(
        self,
        context: ProtocolContext,
        cmd: None | Command = None,
        cmd_sends: int = 0,
    ) -> None:
        self._context = context  # a Protocol

        self.cmd: None | Command = cmd
        self.cmd_sends: None | int = cmd_sends

    def __repr__(self) -> str:
        hdr = self.cmd.tx_header if self.cmd else None
        if hdr:
            return f"{self.__class__.__name__}(hdr={hdr}, tx={self.cmd_sends})"
        assert self.cmd_sends == 0
        return f"{self.__class__.__name__}(hdr={hdr})"

    def _set_context_state(self, state: _StateT, *args, **kwargs) -> None:
        self._context.set_state(state, *args, **kwargs)  # pylint: disable=W0212
        self._next_state = self._context.state

    def is_active_cmd(self, cmd: Command) -> bool:
        """Return True if a Puzzle cmd, or this cmd is the active active cmd."""
        if cmd.verb == Code._PUZZ:  # TODO: need to work this out, ?include
            return True  # an exception to the rule
        return self.cmd and (
            cmd._hdr == self.cmd._hdr
            and cmd._addrs == self.cmd._addrs
            and cmd.payload == self.cmd.payload
        )

    def made_connection(self, transport: _TransportT) -> None:
        """Set the Context to IsInIdle (can Tx/Rx) or IsPaused."""
        if self._context._protocol._pause_writing:
            self._set_context_state(IsPaused)
        else:
            self._set_context_state(IsInIdle)

    def lost_connection(self, exc: None | Exception) -> None:
        """Set the Context to Inactive (can't Tx, will not Rx)."""
        self._set_context_state(Inactive)

    def writing_paused(self) -> None:
        """Set the Context to IsPaused (shouldn't Tx, might Rx)."""
        self._set_context_state(IsPaused)

    def writing_resumed(self) -> None:
        """Set the Context to IsInIdle (can Tx/Rx)."""
        self._set_context_state(IsInIdle)

    def rcvd_pkt(self, pkt: Packet) -> None:
        """Receive a Packet without complaint (most times this is OK)."""
        pass

    def sent_cmd(self, cmd: Command, max_retries: int) -> NoReturn:  # raises exception
        """Object to sending a Command (most times this is OK)."""
        raise ProtocolFsmError(f"{self}: Not implemented")


class Inactive(ProtocolStateBase):
    """Protocol cannot Tx at all, and wont Rx (no active connection to a Transport)."""

    def __repr__(self) -> str:
        assert self.cmd is None
        return f"{self.__class__.__name__}()"

    # method should be OK, but for a timing issue in _make_connection_after_signature()
    # means pkt received here *before* state changed by state.connection_made()
    # def rcvd_pkt(self, pkt: Packet) -> None:  # raise an exception
    #     raise ProtocolFsmError(f"{self}: Can't rcvd {pkt._hdr}: not connected")

    def sent_cmd(self, cmd: Command, max_retries: int) -> NoReturn:  # raises exception
        raise ProtocolFsmError(f"{self}: Can't send {cmd._hdr}: no Transport connected")


class IsPaused(ProtocolStateBase):
    """Protocol cannot Tx at all, but may Rx (Transport has no capacity to Tx)."""

    def sent_cmd(self, cmd: Command, max_retries: int) -> NoReturn:  # raises exception
        raise ProtocolFsmError(f"{self}: Can't send {cmd._hdr}: Protocol is paused")


class IsInIdle(ProtocolStateBase):
    """Protocol can Tx next Command, may Rx (has no current Command)."""

    _cmd_: None | Command = None  # used only for debugging

    def sent_cmd(self, cmd: Command, max_retries: int) -> None:
        _LOGGER.debug(f"     - sending a cmd: {cmd._hdr}")
        self._cmd_ = cmd
        self._set_context_state(WantEcho, cmd=cmd, cmd_sends=1)


class WantEcho(ProtocolStateBase):
    """Protocol can re-Tx this Command, wanting a Rx (has an outstanding Command)."""

    _echo: None | Packet = None

    def rcvd_pkt(self, pkt: Packet) -> None:
        """The Transport has received a Packet, possibly the expected echo."""

        if self.cmd.rx_header and pkt._hdr == self.cmd.rx_header:  # expected pkt
            raise ProtocolFsmError(f"{self}: Reply received before echo: {pkt._hdr}")

        if pkt._hdr != self.cmd.tx_header:
            _LOGGER.debug(f"     - received pkt_: {pkt._hdr} (unexpected, ignored)")

        elif self.cmd.rx_header:
            _LOGGER.debug(f"     - received echo: {pkt._hdr} (now expecting a reply)")
            self._echo = pkt
            self._set_context_state(WantRply, cmd=self.cmd, cmd_sends=self.cmd_sends)

        else:
            _LOGGER.debug(f"     - received echo: {pkt._hdr} (no reply expected)")
            self._echo = pkt
            self._set_context_state(IsInIdle)

    def sent_cmd(self, cmd: Command, max_retries: int) -> None:  # raise an exception
        """The Transport has re-sent a Command.

        Raise ProtocolFsmError if sending command other than the active command.
        Raise RetryLimitExceeded if sending command woudl exceed retry limit.
        """

        if not self.is_active_cmd(cmd):
            raise ProtocolFsmError(f"{self}: Can't send {cmd._hdr}: not active Command")

        if self.cmd_sends > max_retries:
            raise ProtocolSendFailed(f"{self}: Exceeded retry limit of {max_retries}")
        self.cmd_sends += 1
        _LOGGER.debug(f"     - sending cmd..: {cmd._hdr} (again)")


class WantRply(ProtocolStateBase):
    """Protocol can re-Tx this Command, wanting a Rx (has received echo)."""

    _rply: None | Packet = None

    def rcvd_pkt(self, pkt: Packet) -> None:
        """The Transport has received a Packet, possibly the expected response."""

        if pkt._hdr == self.cmd.tx_header:  # expected pkt
            _LOGGER.debug(f"     - received echo: {pkt._hdr} (again B2)")

        elif pkt._hdr != self.cmd.rx_header:
            _LOGGER.debug(f"     - received pkt_: {pkt._hdr} (unexpected, ignored)")

        elif pkt._hdr == self.cmd.rx_header:  # expected pkt
            _LOGGER.debug(f"     - received rply: {pkt._hdr} (as expected)")
            self._rply = pkt
            self._set_context_state(IsInIdle)

    def sent_cmd(self, cmd: Command, max_retries: int) -> None:
        """The Transport has re-sent a Command.

        Raise ProtocolFsmError if sending command other than the active command.
        Raise RetryLimitExceeded if sending command woudl exceed retry limit.
        """

        if not self.is_active_cmd(cmd):
            raise ProtocolFsmError(f"{self}: Can't send {cmd._hdr}: not active Command")

        if self.cmd_sends > max_retries:
            raise ProtocolSendFailed(f"{self}: Exceeded retry limit of {max_retries}")
        self.cmd_sends += 1
        _LOGGER.debug(f"     - sending cmd..: {cmd._hdr} (again)")


class IsFailed(ProtocolStateBase):
    """Protocol can't (yet) Tx next Command, but may Rx (last Command has failed)."""

    def sent_cmd(self, cmd: Command, max_retries: int) -> NoReturn:  # raises exception
        raise ProtocolFsmError(f"{self}: Can't send {cmd._hdr}: in a failed state")


_StateT = Inactive | IsPaused | IsInIdle | WantEcho | WantRply | IsFailed
