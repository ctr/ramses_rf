#!/usr/bin/env python

# ChatGPT code to discover schema.

import asyncio
from ramses_rf import Gateway, RamsesRf

# Async function to run schema discovery and dump it
async def dump_schema():
    # Setup serial port or other connection method (depends on your setup)
    # Replace 'COM3' or '/dev/ttyUSB0' with the correct port for your system
    port = "/dev/ttyUSB0"  # or the relevant port for your system
    
    # Create the RAMSES RF Gateway object
    gateway = Gateway(port)
    
    # Create a RamsesRf object for handling communication
    rf = RamsesRf(gateway)

    # Start discovery (this might take a while)
    await rf.start_discovery()

    # Wait for discovery to complete (you can specify a timeout)
    await asyncio.sleep(30)  # Adjust time according to your needs

    # Once discovery is done, dump the schema
    schema = rf.schema

    # Print or log the discovered schema
    print(schema)

    # Close the gateway when done
    await rf.stop()

# Run the async function
asyncio.run(dump_schema())


