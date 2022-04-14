#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

from types import SimpleNamespace

from .protocol.const import (  # noqa: F401
    ATTR_TEMP,
    ATTR_ZONE_IDX,
    BOOST_TIMER,
    DEFAULT_MAX_ZONES,
    DEVICE_ID_REGEX,
    DOMAIN_TYPE_MAP,
    FAN_MODE,
    SYSTEM_MODE,
    SZ_DATETIME,
    SZ_DEVICE_CLASS,
    SZ_DEVICES,
    SZ_DOMAIN_ID,
    SZ_ELECTRIC_HEAT,
    SZ_HEAT_DEMAND,
    SZ_LANGUAGE,
    SZ_MIXING_VALVE,
    SZ_NAME,
    SZ_RADIATOR_VALVE,
    SZ_RELAY_DEMAND,
    SZ_RELAY_FAILSAFE,
    SZ_SETPOINT,
    SZ_SYSTEM_MODE,
    SZ_UNDERFLOOR_HEATING,
    SZ_WINDOW_OPEN,
    SZ_ZONE_CLASS,
    SZ_ZONE_IDX,
    SZ_ZONE_MASK,
    SZ_ZONE_SENSOR,
    SZ_ZONE_TYPE,
    SZ_ZONE_VALVE,
    ZONE_MODE,
    SystemType,
)

# skipcq: PY-W2000
from .protocol import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    DEV_CLASS_MAP,
    DEV_CLASS,
    DEV_TYPE,
    DEV_TYPE_MAP,
    ZON_CLASS,
    ZON_CLASS_MAP,
)

# skipcq: PY-W2000
from .protocol import (  # noqa: F401, isort: skip, pylint: disable=unused-import
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
    _0150,
    _01D0,
    _01E9,
    _0404,
    _0418,
    _042F,
    _0B04,
    _1030,
    _1060,
    _1081,
    _1090,
    _1098,
    _10A0,
    _10B0,
    _10E0,
    _10E1,
    _1100,
    _11F0,
    _1260,
    _1280,
    _1290,
    _1298,
    _12A0,
    _12B0,
    _12C0,
    _12C8,
    _12F0,
    _1300,
    _1F09,
    _1F41,
    _1FC9,
    _1FCA,
    _1FD0,
    _1FD4,
    _2249,
    _22C9,
    _22D0,
    _22D9,
    _22F1,
    _22F3,
    _2309,
    _2349,
    _2389,
    _2400,
    _2401,
    _2410,
    _2420,
    _2D49,
    _2E04,
    _2E10,
    _30C9,
    _3110,
    _3120,
    _313F,
    _3150,
    _31D9,
    _31DA,
    _31E0,
    _3200,
    _3210,
    _3220,
    _3221,
    _3223,
    _3B00,
    _3EF0,
    _3EF1,
    _PUZZ,
)

__dev_mode__ = False
# DEV_MODE = __dev_mode__

Discover = SimpleNamespace(
    NOTHING=0, SCHEMA=1, PARAMS=2, STATUS=4, FAULTS=8, SCHEDS=16, ALL=(1 + 2 + 4)
)

DONT_CREATE_MESSAGES = 3
DONT_CREATE_ENTITIES = 2
DONT_UPDATE_ENTITIES = 1

# Status codes for Worcester Bosch boilers - OT|OEM diagnostic code
WB_STATUS_CODES = {
    "200": "CH system is being heated.",
    "201": "DHW system is being heated.",
    "202": "Anti rapid cycle mode. The boiler has commenced anti-cycle period for CH.",
    "203": "System standby mode.",
    "204": "System waiting, appliance waiting for heating system to cool.",
    "208": "Appliance in service Test mode (Min/Max)",
    "265": "EMS controller has forced stand-by-mode due to low heating load (power required is less than the minimum output)",
    "268": "Component test mode (is running the manual component test as activated in the menus).",
    "270": "Power up mode (appliance is powering up).",
    "283": "Burner starting. The fan and the pump are being controlled.",
    "284": "Gas valve(s) opened, flame must be detected within safety time. The gas valve is being controlled.",
    "305": "Anti fast cycle mode (DHW keep warm function). Diverter valve is held in DHW position for a period of time after DHW demand.",
    "357": "Appliance in air purge mode. Primary heat exchanger air venting program active - approximately 100 seconds.",
    "358": "Three way valve kick. If the 3-way valve hasn't moved in within 48 hours, the valve will operate once to prevent seizure",
}
