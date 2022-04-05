#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

from types import SimpleNamespace

from .protocol.const import (  # noqa: F401
    _000C_DEVICE,
    _000C_DEVICE_TYPE,
    _0005_ZONE,
    ATTR_DATETIME,
    ATTR_DEVICES,
    ATTR_HEAT_DEMAND,
    ATTR_LANGUAGE,
    ATTR_NAME,
    ATTR_RELAY_DEMAND,
    ATTR_RELAY_FAILSAFE,
    ATTR_SETPOINT,
    ATTR_SYSTEM_MODE,
    ATTR_TEMP,
    ATTR_WINDOW_OPEN,
    ATTR_ZONE_IDX,
    BOOST_TIMER,
    DEFAULT_MAX_ZONES,
    DEV_KLASS,
    DEVICE_ID_REGEX,
    DEVICE_TYPES,
    DOMAIN_TYPE_MAP,
    FAN_MODE,
    HGI_DEVICE_ID,
    NON_DEVICE_ID,
    NUL_DEVICE_ID,
    SYSTEM_MODE,
    SZ_DEVICE_CLASS,
    SZ_DOMAIN_ID,
    SZ_ZONE_IDX,
    ZONE_MODE,
    ZONE_TYPE_MAP,
    ZONE_TYPE_SLUGS,
    SystemType,
)

# skipcq: PY-W2000
from .protocol import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
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
