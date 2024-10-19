#!/usr/bin/env python

# Use:
# (evohome) ctr28@flint:~/evohome/ramses_rf$ ./discover_schema.py  | jq
#
# Print the auto-discovered schema.

import asyncio
from ramses_rf import Gateway
from tests.tests.helpers import load_test_gwy
import json

# Async function to run schema discovery and dump it
async def dump_schema():
    # Setup serial port or other connection method (depends on your setup)
    # Replace 'COM3' or '/dev/ttyUSB0' with the correct port for your system
    #port = "/dev/ttyUSB0"  # or the relevant port for your system
    
    # Create the RAMSES RF Gateway object
    #gateway = Gateway(port)
    gateway: Gateway = await load_test_gwy(".") # Reads ./packet.log (and ./config.json but that's not defined?)
    
    # Once discovery is done, dump the schema
    schema = gateway.schema

    # Print or log the discovered schema
    print(json.dumps(schema))

    # Close the gateway when done
    await gateway.stop()

# Run the async function
asyncio.run(dump_schema())


