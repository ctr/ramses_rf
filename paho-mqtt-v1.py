#!/usr/bin/env python
# CTR attempt at forwarding packets via MQTT

import json
import paho.mqtt.client as mqtt
import re

# To decode packets
from ramses_tx.protocol import Packet
from ramses_tx.message import Message

# MQTT settings
BROKER = "flint.home"  # broker address
PORT = 1883
TOPIC_SUBSCRIBE = "RAMSES/GATEWAY/18:226396/rx"      # RX events from the ramses_esp
TOPIC_PUBLISH   = "RAMSES/GATEWAY/18:226396/tx"      # TX destination for ramses_esp (same one)

DEVICE_ID = "03:150994"

# Callback function when the client receives a CONNACK response from the server
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to the input topic
    client.subscribe(TOPIC_SUBSCRIBE)

# Callback function when a message is received
def on_message(client, userdata, msg):
    message = msg.payload.decode("utf-8")  # Decode the received message
    print(f"Message received: {message}")

    msg = json.loads(message)
    print(f"{msg=}")
    packet = Packet(msg["ts"], msg["msg"]) 
    print(packet)

    mm = Message(packet)
    print(mm)

    # Check if the message contains the DEVICE_ID to forward
    if DEVICE_ID in msg:
        print(f"Message from DEVICE_ID found: {msg=}")
        #client.publish(TOPIC_PUBLISH, "")
    else:
        print(f"Ignoring message: {msg=}")

# Create an MQTT client instance
client = mqtt.Client()

# Attach the callback functions
client.on_connect = on_connect
client.on_message = on_message

# Connect to the broker
client.connect(BROKER, PORT, 60)

# Start the MQTT loop to process incoming and outgoing messages
client.loop_forever()

