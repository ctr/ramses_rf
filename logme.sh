#!/bin/bash

# Log using MQTT subscription over wifi
mosquitto_sub -v -t "RAMSES/GATEWAY/18:226396/+" >> mqtt_logs.json


