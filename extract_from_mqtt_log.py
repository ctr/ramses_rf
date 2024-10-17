#python

# USAGE:
# $ conda activate evohome
# $ cat mqtt_logs.json | python3 extract_from_mqtt_log.py  | python client.py parse

import sys
import re

def extract_data(file):
    ts_pattern = re.compile(r'"ts":\s*"([^"]+)"')
    msg_pattern = re.compile(r'"msg":\s*"([^"]+)"')

    current_ts = None

    for line in file:
        line = line.strip()
        
        # Extract timestamp
        ts_match = ts_pattern.search(line)
        if ts_match:
            current_ts = ts_match.group(1)

        # Extract message
        msg_match = msg_pattern.search(line)
        if msg_match and current_ts:
            msg = msg_match.group(1)
	    # Remove "+00:00" from the timestamp if present
            if current_ts.endswith("+00:00"):
                current_ts = current_ts[:-6]
            print(f"{current_ts} {msg}")
            current_ts = None  # Reset timestamp after using it

if __name__ == "__main__":
    extract_data(sys.stdin)


