#!/usr/bin/env python
# CTR attempt at forwarding packets using a RAMSES_ESP device and MQTT transport.
# Forwards packets for selected devices only in an attempt to minimise impact on system.
#
# Usage:
# (evohome) ctr28@flint:~/evohome/ramses_rf$ ./paho-mqtt-v1.py | tee -a paho_-mqtt-v1.log

import json
import paho.mqtt.client as mqtt
from ramses_tx.protocol import Packet # To decode packets
from ramses_tx.message import Message # To decode packets
import re
import sys

# MQTT settings
BROKER = "flint.home"  # broker address
PORT = 1883
TOPIC_SUBSCRIBE = "RAMSES/GATEWAY/18:226396/rx"      # RX events from the ramses_esp
TOPIC_PUBLISH   = "RAMSES/GATEWAY/18:226396/tx"      # TX destination for ramses_esp (same one)

DEVICES_TO_FORWARD = [
            "03:150994", # SEN:LIVING (zone 05)
            "04:237332", # RAD:LIVING (zone 05)
            "04:243385", # RAD:GIRLS (zone 00)
            ]

# Callback function when the client receives a CONNACK response from the server
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc=}")
    # Subscribe to the input topic
    client.subscribe(TOPIC_SUBSCRIBE)

# Callback function when a message is received
def on_message(client, userdata, msg):
    message = msg.payload.decode("utf-8")  # Decode the received message
    #print(f"\n\nMessage received: {message}")

    msg = json.loads(message)
    #print(f"{msg=}")
    packet = Packet.from_file(msg["ts"], msg["msg"])
    #print(f"{packet=}")

    mm = Message(packet)
    # print(f"{str(mm)=}")
    # print(f"{repr(mm)=}")
    # print(mm)

    #print(f"{mm.dst=}")

    # Note. You can manually transmit a temperature packet with
    # 21.93C
    # (evohome) ctr28@flint:~/evohome/ramses_rf$ mosquitto_pub -m '{ "msg": " I --- 03:150994 --:------ 03:150994 30C9 003 000891" }' -t "RAMSES/GATEWAY/18:226396/tx"
    # 18.4C
    # (evohome) ctr28@flint:~/evohome/ramses_rf$ mosquitto_pub -m '{ "msg": " I --- 03:150994 --:------ 03:150994 30C9 003 000730" }' -t "RAMSES/GATEWAY/18:226396/tx"

    # Check if the message contains the DEVICE_ID to forward
    # Annoyingly transmitted packets are echoed to Rx BUT they have 000 as the RSSI which is impossible I think for normal packets.
    if packet._rssi == "000":
        print(f"IGNORE LOOPBACK || {str(mm)}")
    elif repr(mm.src) in DEVICES_TO_FORWARD or repr(mm.dst) in DEVICES_TO_FORWARD: # For whatever reason repr doesn't decode the names but str does.
        print(f"*REPEAT PACKET* || {str(mm)}\n--> {packet=}")
        client.publish(TOPIC_PUBLISH, f'{{ "msg": "{repr(mm)}" }}') # MQTT Tx needs to be in JSON format
        # Note that in python f-strings {{ gives a literal {, and }} gives a literal }.
    else:
        print(f"                || {str(mm)}")


### MAIN CODE HERE ##

# Disable buffering so output can be fed to `tee`
sys.stdout.reconfigure(line_buffering=True)

# Create an MQTT client instance
client = mqtt.Client()

# Attach the callback functions
client.on_connect = on_connect
client.on_message = on_message

# Connect to the broker
client.connect(BROKER, PORT, 60)

# Start the MQTT loop to process incoming and outgoing messages
client.loop_forever()

