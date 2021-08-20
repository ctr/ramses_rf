#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Decode/process a packet (packet that was received).
"""

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import ByteString, Optional, Tuple, Union

from .address import NON_DEV_ADDR, pkt_addrs
from .const import DONT_CREATE_ENTITIES, MESSAGE_REGEX

# from .devices import Device  # TODO: fix cyclic reference
from .exceptions import CorruptAddrSetError, CorruptStateError
from .logger import getLogger
from .ramses import (
    CODE_IDX_COMPLEX,
    CODE_IDX_DOMAIN,
    CODE_IDX_NONE,
    CODE_IDX_SIMPLE,
    CODE_ONLY_FROM_CTL,
    CODES_WITH_ARRAYS,
    EXPIRES,
    RAMSES_CODES,
)

from .const import I_, RP, RQ, W_, __dev_mode__  # noqa: F401, isort: skip
from .const import (  # noqa: F401, isort: skip
    _0001,
    _0002,
    _0004,
    _0005,
    _0006,
    _0008,
    _0009,
    _000A,
    _000C,
    _000E,
    _0016,
    _0100,
    _01D0,
    _01E9,
    _0404,
    _0418,
    _042F,
    _1030,
    _1060,
    _1090,
    _10A0,
    _10E0,
    _1100,
    _1260,
    _1280,
    _1290,
    _1298,
    _12A0,
    _12B0,
    _12C0,
    _12C8,
    _1F09,
    _1F41,
    _1FC9,
    _1FD4,
    _2249,
    _22C9,
    _22D0,
    _22D9,
    _22F1,
    _22F3,
    _2309,
    _2349,
    _2D49,
    _2E04,
    _30C9,
    _3120,
    _313F,
    _3150,
    _31D9,
    _31DA,
    _31E0,
    _3220,
    _3B00,
    _3EF0,
    _3EF1,
    _PUZZ,
)

DEV_MODE = __dev_mode__ and False  # or True

_LOGGER = logging.getLogger(__name__)
if DEV_MODE:
    _LOGGER.setLevel(logging.DEBUG)

_PKT_LOGGER = getLogger(f"{__name__}_log", pkt_log=True)


class PacketBase:
    """The packet base - used by Command and Packet classes."""

    def __init__(self) -> None:

        self.__has_array = None
        self.__has_ctl = None
        self.__ctx = None
        self.__idx = None
        self.__hdr = None

    # def __repr__(self) -> str:
    #     """Return an unambiguous string representation of this object."""
    #     return self.raw_frame or self.packet

    # def __str__(self) -> str:
    #     """Return an string representation of this object."""
    #     return self._hdr

    @property
    def _has_array(self) -> Optional[bool]:
        """Return the True if the packet payload is an array, False if not.

        May return false negatives (e.g. arrays of length 1), and None if undetermined.

        An example of a false negative is evohome with only one zone (i.e. the periodic
        2309/30C9/000A packets).
        """

        if self.__has_array is not None:
            return self.__has_array

        # False -ves (array length is 1) are an acceptable compromise to extensive checking

        #  W --- 01:145038 34:092243 --:------ 1FC9 006 07230906368E
        #  I --- 01:145038 --:------ 01:145038 1FC9 018 07000806368E-FC3B0006368E-071FC906368E
        #  I --- 01:145038 --:------ 01:145038 1FC9 018 FA000806368E-FC3B0006368E-FA1FC906368E
        #  I --- 34:092243 --:------ 34:092243 1FC9 030 0030C9896853-002309896853-001060896853-0010E0896853-001FC9896853
        if self.code == _1FC9:
            self.__has_array = self.verb != RQ  # safe to treat all as array, even len=1

        elif self.verb != I_ or self.code not in CODES_WITH_ARRAYS:
            self.__has_array = False

        elif self.len == CODES_WITH_ARRAYS[self.code][0]:  # NOTE: can be false -ves
            self.__has_array = False

        else:
            _len = CODES_WITH_ARRAYS[self.code][0]
            assert (
                self.len % _len == 0
            ), f"{self} << array has length ({self.len}) that is not multiple of {_len}"
            assert (
                self.src.type in ("12", "22") or self.src == self.dst
            ), f"{self} << array is from a non-controller (01)"
            assert (
                self.src.type not in ("12", "22") or self.dst == NON_DEV_ADDR
            ), f"{self} << array is from a non-controller (02)"
            self.__has_array = True

        #  I --- 10:040239 01:223036 --:------ 0009 003 000000        # not array
        #  I --- 01:102458 --:------ 01:102458 0009 006 FC01FF-F901FF
        #  I --- 01:145038 --:------ 01:145038 0009 006 FC00FF-F900FF
        #  I 034 --:------ --:------ 12:126457 2309 006 017EFF-027EFF
        #  I --- 01:223036 --:------ 01:223036 000A 012 081001F40DAC-091001F40DAC  # 2nd fragment
        #  I 024 --:------ --:------ 12:126457 000A 012 010001F40BB8-020001F40BB8
        #  I --- 02:044328 --:------ 02:044328 22C9 018 0001F40A2801-0101F40A2801-0201F40A2801
        #  I --- 23:100224 --:------ 23:100224 2249 007 007EFF7EFFFFFF  # can have 2 zones
        #  I --- 02:044328 --:------ 02:044328 22C9 018 0001F40A2801-0101F40A2801-0201F40A2801
        #  I --- 02:001107 --:------ 02:001107 3150 010 007A-017A-027A-036A-046A

        return self.__has_array

    @property
    def _has_ctl(self) -> Optional[bool]:
        """Return True if the packet is to/from a controller."""

        if self.__has_ctl is not None:
            return self.__has_ctl

        # TODO: handle RQ/RP to/from HGI/RFG, handle HVAC

        # TODO: Not needed? Relies upon MSG layer in any case
        # if getattr(self.src, "_is_controller", False):
        #     # _LOGGER.info("HAS Controller (00)")
        #     return True
        # if getattr(self.dst, "_is_controller", False):
        #     # _LOGGER.info("HAS controller (01)")
        #     return True

        if {self.src.type, self.dst.type} & {"01", "02", "23"}:
            _LOGGER.debug(f"{self} # HAS controller (10)")
            self.__has_ctl = True

        #  I --- 12:010740 --:------ 12:010740 30C9 003 0008D9 # not ctl
        elif self.dst is self.src:  # (not needed?) & self.code == I_:
            _LOGGER.debug(
                f"{self} << "
                + ("HAS" if self.code in CODE_ONLY_FROM_CTL + [_31D9, _31DA] else "no")
                + " controller (20)"
            )
            self.__has_ctl = any(
                (
                    self.code == _3B00 and self.payload[:2] == "FC",
                    self.code in CODE_ONLY_FROM_CTL + [_31D9, _31DA],
                )
            )

        #  I --- --:------ --:------ 10:050360 1FD4 003 002ABE # no ctl
        #  I 095 --:------ --:------ 12:126457 1F09 003 000BC2 # HAS ctl
        #  I --- --:------ --:------ 20:001473 31D9 003 000001 # ctl? (HVAC)
        elif self.dst is NON_DEV_ADDR:
            _LOGGER.debug(f"{self} # HAS controller (21)")
            self.__has_ctl = self.src.type != "10"

        #  I --- 10:037879 --:------ 12:228610 3150 002 0000   # HAS ctl
        #  I --- 04:029390 --:------ 12:126457 1060 003 01FF01 # HAS ctl
        elif self.dst.type in ("12", "22"):
            _LOGGER.debug(f"{self} # HAS controller (22)")
            self.__has_ctl = True

        # RQ --- 30:258720 10:050360 --:------ 3EF0 001 00           # UNKNOWN (99)
        # RP --- 10:050360 30:258720 --:------ 3EF0 006 000011010A1C # UNKNOWN (99)

        # RQ --- 18:006402 13:049798 --:------ 1FC9 001 00
        # RP --- 13:049798 18:006402 --:------ 1FC9 006 003EF034C286
        # RQ --- 30:258720 10:050360 --:------ 22D9 001 00
        # RP --- 10:050360 30:258720 --:------ 22D9 003 0003E8
        # RQ --- 30:258720 10:050360 --:------ 3220 005 0000120000
        # RP --- 10:050360 30:258720 --:------ 3220 005 0040120166
        # RQ --- 30:258720 10:050360 --:------ 3EF0 001 00
        # RP --- 10:050360 30:258720 --:------ 3EF0 006 000011010A1C

        #  I --- 34:021943 63:262142 --:------ 10E0 038 000001C8380A01... # unknown
        #  I --- 32:168090 30:082155 --:------ 31E0 004 0000C800          # unknown
        if self.__has_ctl is None:
            if DEV_MODE and "18" not in (self.src.type, self.dst.type):
                _LOGGER.warning(f"{self} # has_ctl - undetermined (99)")
            self.__has_ctl = False

        return self.__has_ctl

    @property
    def _idx(self) -> Union[str, bool]:
        """Return the payload's index, if any (e.g. zone_idx, domain_id, or log_idx).

        Used to route a packet to the correct entity's (i.e. zone/domain) msg handler.
        """

        if self.__idx is None and self.is_valid:
            self.__idx = _pkt_idx(self) or False
        return self.__idx

    @property
    def _ctx(self) -> Union[str, bool]:
        """Return the payload's full context, if any (e.g. for 0404: zone_idx/frag_idx).

        Used to store packets in the entity's message DB.
        """

        if self.__ctx is None and self.is_valid:
            if self.code in (_0005, _000C):  # zone_idx, zone_type (device_class)
                self.__ctx = self.payload[:4]
            elif self.code == _0404:  # zone_idx, frag_idx
                self.__ctx = self.payload[:2] + self.payload[10:12]
            else:
                self.__ctx = self._idx
        return self.__ctx

    @property
    def _hdr(self) -> str:
        """Return the QoS header (fingerprint) of this packet (i.e. device_id/code/hdr).

        Used for QoS (timeouts, retries), callbacks, etc.
        """

        if self.__hdr is None and self.is_valid:
            self.__hdr = _pkt_hdr(self)
        return self.__hdr


class Packet(PacketBase):
    """The packet class; should trap/log all invalid PKTs appropriately."""

    def __init__(self, gwy, dtm: dt, frame: str, **kwargs) -> None:
        """Create a packet from a valid frame."""
        super().__init__()

        assert kwargs.get("dtm_str") is None or (
            kwargs.get("dtm_str") == dtm.isoformat(timespec="microseconds")
        ), "dtm_str doesn't match dtm.isoformat"

        self._gwy = gwy
        self.dtm = dtm
        self._date, self._time = (
            kwargs.get("dtm_str") or dtm.isoformat(timespec="microseconds")
        ).split("T")
        # self.created = dtm.timestamp()  # HACK: used by logger
        # self.msecs = (self.created - int(self.created)) * 1000

        self.packet = frame
        self.comment = kwargs.get("comment")
        self.error_text = kwargs.get("err_msg")
        self.raw_frame = kwargs.get("raw_frame")

        # addrs are populated in self.is_valid()
        self.addrs = [None] * 3
        self.src = self.dst = None

        self._is_valid = None
        if not self.is_valid:
            raise ValueError(f"not a valid packet: {frame}")

        # TODO: these are not presently used
        self.rssi = self.packet[0:3]
        self.verb = self.packet[4:6]
        self.seqn = self.packet[7:10]
        self.code = self.packet[41:45]
        self.len = int(self.packet[46:49])
        self.payload = self.packet[50:]

        # these are calculated if/when required
        self.__timeout = None

        _ = self._has_array  # TODO: remove (is for testing only)
        _ = self._has_ctl  # # TODO: remove (is for testing only)

    @classmethod
    def from_dict(cls, gwy, dtm: str, pkt: str):
        """Constructor to create a packet from a saved state (a curated dict)."""
        return cls(gwy, dt.fromisoformat(dtm), pkt, dtm_str=dtm)

    @classmethod
    def from_file(cls, gwy, dtm: str, pkt_line: str):
        """Constructor to create a packet from a log file line."""
        frame, err_msg, comment = cls._partition(pkt_line)
        return cls(
            gwy,
            dt.fromisoformat(dtm),
            frame,
            dtm_str=dtm,
            err_msg=err_msg,
            comment=comment,
        )

    @classmethod
    def from_port(cls, gwy, dtm: dt, pkt_line: str, raw_line: ByteString = None):
        """Constructor to create a packet from a usb port (HGI80, evofw3)."""
        frame, err_msg, comment = cls._partition(pkt_line)
        return cls(
            gwy, dtm, frame, err_msg=err_msg, comment=comment, raw_frame=raw_line
        )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of this object."""
        return self.raw_frame or self.packet

    def __str__(self) -> str:
        """Return a brief readable string representation of this object."""
        return self.packet

    def __eq__(self, other) -> bool:
        if not hasattr(other, "packet"):
            return NotImplemented
        return self.packet == other.packet

    @staticmethod
    def _partition(pkt_line: str) -> Tuple[str, str, str]:
        """Partition a packet line into its three parts.

        Format: packet[ < parser-hint: ...][ * evofw3-err_msg][ # evofw3-comment]
        """

        fragment, _, comment = pkt_line.partition("#")
        fragment, _, err_msg = fragment.partition("*")
        pkt_str, _, _ = fragment.partition("<")  # discard any parser hints
        return (
            pkt_str.strip(),
            f" * {err_msg.strip()}" if err_msg else " *" if "*" in pkt_line else "",
            f" # {comment.strip()}" if comment else "",
        )

    @property
    def _expired(self) -> float:
        """Return fraction used of the normal lifetime of packet.

        A packet is 'expired' when >1.0, and should be tombstoned when >2.0. Returns
        False if the packet does not expire.
        """

        if self.__timeout is None and self.is_valid:
            self.__timeout = pkt_timeout(self) or False

        if self.__timeout is False:
            return False

        return (self._gwy._dt_now() - self.dtm) / self.__timeout

    @property
    def is_valid(self) -> Optional[bool]:
        """Return True if the packet is valid (will log all packets, regardless)."""

        def invalid_addresses(addr_set: str) -> Optional[bool]:
            """Return True if the address fields are invalid (create any addresses)."""
            try:
                self.src, self.dst, self.addrs = pkt_addrs(addr_set)
                # print(pkt_addrs.cache_info())
            except CorruptAddrSetError:
                return True

        if self._is_valid is not None or not self.packet:
            return self._is_valid

        self._is_valid = False
        if self.error_text:  # log all packets with an error
            if self.packet:
                _PKT_LOGGER.warning("%s < Bad packet:", self, extra=self.__dict__)
            else:
                _PKT_LOGGER.warning("< Bad packet:", extra=self.__dict__)
            return False

        if not self.packet and self.comment:  # log null packets only if has a comment
            _PKT_LOGGER.warning(
                "< Null packet", extra=self.__dict__
            )  # best as a debug?
            return False

        # TODO: these packets shouldn't go to the packet log, only STDERR?
        if not MESSAGE_REGEX.match(self.packet):
            err_msg = "invalid packet structure"
        elif int(self.packet[46:49]) * 2 != len(self.packet[50:]):
            err_msg = "mismatched payload length"
        elif invalid_addresses(self.packet[11:40]):
            err_msg = "invalid packet addresses"
        # elif self.code not in RAMSES_CODES:
        #     return False
        else:
            _PKT_LOGGER.info("%s", self.packet, extra=self.__dict__)
            self._is_valid = True
            return True

        _PKT_LOGGER.warning("%s < Bad packet: %s", self, err_msg, extra=self.__dict__)
        return False  # TODO: remove


def _pkt_idx(pkt) -> Union[str, bool, None]:  # _has_array, _has_ctl
    """Return the payload's 2-byte context (e.g. zone_idx, log_idx, domain_id).

    May return a 2-byte string (usu. pkt.payload[:2]), or:
    - False if there is no context at all
    - True if the payload is an array
    - None if it is indeterminable
    """
    # The three iterables (none, simple, complex) are mutex

    # FIXME: 0016 is broken

    # mutex 2/4, CODE_IDX_COMPLEX: are not payload[:2]
    if pkt.code == _0005:
        return pkt._has_array

    #  I --- 10:040239 01:223036 --:------ 0009 003 000000
    if pkt.code == _0009 and pkt.src.type == "10":
        return False

    if pkt.code == _000C:  # zone_idx/domain_id (complex, payload[0:4])
        if pkt.payload[2:4] in ("0D", "0E"):  # ("000D", _000E, "010E")
            return "FA"
        if pkt.payload[2:4] == "0F":  # ("000F", )
            return "FC"
        return pkt.payload[:2]

    # if pkt.code == _0404:  # TODO: is entry needed here, esp. for DHW?

    if pkt.code == _0418:  # log_idx (payload[4:6])
        return pkt.payload[4:6]

    if pkt.code == _1100:  # TODO; can do in parser
        return pkt.payload[:2] if pkt.payload[:1] == "F" else False  # only FC

    if pkt.code == _3220:  # msg_id/data_id (payload[4:6])
        return pkt.payload[4:6]

    if pkt.code in CODE_IDX_COMPLEX:
        raise NotImplementedError(f"{pkt} # CODE_IDX_COMPLEX")  # a coding error

    # mutex 1/4, CODE_IDX_NONE: always returns False
    if pkt.code in CODE_IDX_NONE:  # returns False
        assert (
            RAMSES_CODES[pkt.code].get(pkt.verb, "")[:3] != "^00"
            or pkt.payload[:2] == "00"
        ), f"{pkt} # index is {pkt.payload[:2]}, expecting 00"
        return False

    # mutex 3/4, CODE_IDX_SIMPLE: potentially some false -ves?
    if pkt._has_array:
        return True  # excludes len==1 for 000A, 2309, 30C9

    # TODO: is this needed?: exceptions to CODE_IDX_SIMPLE
    if pkt.payload[:2] in ("F8", "F9", "FA", "FC"):  # TODO: FB, FD
        assert (
            pkt.code in CODE_IDX_DOMAIN
        ), f"Payload index is {pkt.payload[:2]}, not expecting a domain_id"
        return pkt.payload[:2]

    if pkt._has_ctl:  # risk of false -ves, TODO: pkt.src.type == "18" too?
        # 02:    22C9: would be picked up as an array, if len==1 counted
        # 03:    #  I 028 03:094242 --:------ 03:094242 30C9 003 010B22  # ctl
        # 12/22: 000A|1030|2309|30C9 from (addr0 --:), 1060|3150 (addr0 04:)
        # 23:    0009|10A0
        return pkt.payload[:2]  # pkt._gwy.config.max_zones checked elsewhere

    if pkt.payload[:2] != "00":
        _LOGGER.warning(f"{pkt} # Expecting payload index to be 00")  # return None?
        return pkt.payload[:2]

    if pkt.code in CODE_IDX_SIMPLE:
        return  # False  # TODO: return None (less precise) or risk false -ves?

    # mutex 4/4, CODE_IDX_UNKNOWN: an unknown code
    _LOGGER.warning(f"{pkt} # Unable to determine payload index")  # and: return None


def _pkt_hdr(pkt, rx_header=None) -> Optional[str]:  # NOTE: used in command.py
    """Return the QoS header of a packet.

    If rx_header, return the header of the response packet, if one is expected.
    """

    if pkt.code == _1FC9:
        #  I --- 34:021943 --:------ 34:021943 1FC9 024 00-2309-8855B7 00-1FC9-8855B7
        #  W --- 01:145038 34:021943 --:------ 1FC9 006 00-2309-06368E  # wont know src until it arrives
        #  I --- 34:021943 01:145038 --:------ 1FC9 006 00-2309-8855B7
        if not rx_header:
            return "|".join((pkt.code, pkt.verb, pkt.dst.id))
        if pkt.src == pkt.dst:  # and pkt.verb == I_:
            return "|".join((pkt.code, W_, pkt.dst.id))
        if pkt.verb == W_:  # and pkt.src != pkt.dst:
            return "|".join((pkt.code, I_, pkt.dst.id))
        return

    addr = pkt.dst if pkt.src.type == "18" else pkt.src
    if not rx_header:
        header = "|".join((pkt.code, pkt.verb, addr.id))

    elif pkt.verb in (I_, RP) or pkt.src == pkt.dst:  # announcements, etc.: no response
        return

    else:  # RQ/RP, or W/I
        header = "|".join((pkt.code, RP if pkt.verb == RQ else I_, addr.id))

    return f"{header}|{pkt._ctx}" if isinstance(pkt._ctx, str) else header


def pkt_timeout(pkt) -> Optional[float]:  # NOTE: imports OtbGateway
    """Return the pkt lifetime.

    Will return None if the packet does not expire (e.g. 10E0).

    Some codes require a valid payload: 1F09, 3220
    """

    timeout = None

    if pkt.verb in (RQ, W_):
        timeout = td(seconds=3)

    elif pkt.code in (_0005, _000C, _10E0):
        return  # TODO: exclude/remove devices caused by corrupt ADDRs?

    elif pkt.code == _1FC9 and pkt.verb == RP:
        return  # TODO: check other verbs, they seem variable

    elif pkt.code == _1F09:
        # if msg: td(seconds=pkt.payload["remaining_seconds"])
        timeout = td(seconds=300)  # usu: 180-300

    elif pkt.code == _000A and pkt._has_array:
        timeout = td(minutes=60)  # sends I /1h

    elif pkt.code in (_2309, _30C9) and pkt._has_array:
        timeout = td(minutes=15)  # sends I /sync_cycle

    elif pkt.code == _3220:
        # if msg: complicated
        return

    # elif pkt.code in (_3B00, _3EF0, ):  # TODO: 0008, 3EF0, 3EF1
    #     timeout = td(minutes=6.7)  # TODO: WIP

    elif pkt.code in RAMSES_CODES:
        timeout = RAMSES_CODES[pkt.code].get(EXPIRES)

    return timeout or td(minutes=60)


def _create_devices(this: Packet) -> None:
    """Discover and create any new devices."""
    from .devices import Device  # TODO: remove this

    if this.src.type in ("01", "23") and this.src is not this.dst:  # TODO: all CTLs
        this.src = this._gwy._get_device(this.src, ctl_addr=this.src)
        ctl_addr = this.src if this._gwy.config.enable_eavesdrop else None
        this._gwy._get_device(this.dst, ctl_addr=ctl_addr)

    elif this.dst.type in ("01", "23") and this.src is not this.dst:  # all CTLs
        this.dst = this._gwy._get_device(this.dst, ctl_addr=this.dst)
        ctl_addr = this.dst if this._gwy.config.enable_eavesdrop else None
        this._gwy._get_device(this.src, ctl_addr=ctl_addr)

    # this should catch all non-controller (and *some* controller) devices
    elif this.src is this.dst:
        this._gwy._get_device(this.src)

    # otherwise one will be a controller, *unless* dst is in ("--", "63")
    elif isinstance(this.src, Device) and this.src._is_controller:
        this._gwy._get_device(this.dst, ctl_addr=this.src)

    # TODO: may create a controller that doesn't exist
    elif isinstance(this.dst, Device) and this.dst._is_controller:
        this._gwy._get_device(this.src, ctl_addr=this.dst)

    else:
        # beware:  I --- --:------ --:------ 10:078099 1FD4 003 00F079
        [this._gwy._get_device(d) for d in (this.src, this.dst)]

    # where possible, swap each Address for its corresponding Device
    this.src = this._gwy.device_by_id.get(this.src.id, this.src)
    if this.dst is not None:
        this.dst = this._gwy.device_by_id.get(this.dst.id, this.dst)


def process_pkt(pkt: Packet) -> Optional[bool]:
    """Process the (valid) packet's metadata (but dont process the payload)."""

    if _LOGGER.getEffectiveLevel() == logging.INFO:  # i.e. don't log for DEBUG
        _LOGGER.info(pkt)

    if not pkt.is_valid or pkt._gwy.config.reduce_processing >= DONT_CREATE_ENTITIES:
        return False

    try:  # process the packet meta-data
        # TODO: This will need to be removed for HGI80-impersonation
        if pkt.src.type != "18":  # 18:/RQs are unreliable, but corresponding RPs?
            _create_devices(pkt)  # from pkt header & from pkt payload (e.g. 000C)

    except (AssertionError, NotImplementedError) as err:
        (_LOGGER.error if DEV_MODE else _LOGGER.warning)(
            "%s << %s", pkt._pkt, f"{err.__class__.__name__}({err})"
        )
        return False  # NOTE: use raise only when debugging

    except (AttributeError, LookupError, TypeError, ValueError) as err:
        (_LOGGER.exception if DEV_MODE else _LOGGER.error)(
            "%s << %s", pkt._pkt, f"{err.__class__.__name__}({err})"
        )
        return False  # NOTE: use raise only when debugging

    except CorruptStateError as err:  # TODO: add CorruptPacketError
        (_LOGGER.exception if DEV_MODE else _LOGGER.error)("%s << %s", pkt._pkt, err)
        return False  # TODO: bad pkt, or Schema

    pkt._gwy._prev_pkt = pkt
