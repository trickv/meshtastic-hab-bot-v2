#!/usr/bin/env python3

import meshtastic
from pubsub import pub
import time
import datetime
import math
import json
import traceback
import subprocess
import re

from config import interface, my_name, my_node_user_id

# WGS84 ellipsoid constants
a = 6378137.0          # semi-major axis in meters
e2 = 6.69437999014e-3  # first eccentricity squared

def geodetic_to_ecef(lat, lon, alt):
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    N = a / math.sqrt(1 - e2 * (math.sin(lat_rad) ** 2))

    x = (N + alt) * math.cos(lat_rad) * math.cos(lon_rad)
    y = (N + alt) * math.cos(lat_rad) * math.sin(lon_rad)
    z = (N * (1 - e2) + alt) * math.sin(lat_rad)

    return x, y, z

def distance_between_geodetic_points(p1, p2):
    x1, y1, z1 = geodetic_to_ecef(*p1)
    x2, y2, z2 = geodetic_to_ecef(*p2)

    dx = x2 - x1
    dy = y2 - y1
    dz = z2 - z1

    distance_meters = math.sqrt(dx**2 + dy**2 + dz**2)
    return round(distance_meters / 1000.0, 1)  # convert to kilometers

def parse_recent_gps_from_journalctl():
    # Only get logs from the last 1 minute
    result = subprocess.run(
        ["journalctl", "-u", "meshtasticd", "--no-pager", "--output=short", "--since", "1 min ago"],
        capture_output=True, text=True
    )
    
    logs = result.stdout

    # Pattern to find GPS events
    gps_event_pattern = re.compile(
        r'^(?P<month>\w{3}) (?P<day>\d{1,2}) (?P<time>\d{2}:\d{2}:\d{2}).*New GPS pos.*lat=(?P<lat>-?\d+\.\d+) lon=(?P<lon>-?\d+\.\d+) alt=(?P<alt>-?\d+).*sats=(?P<sats>\d+)',
        re.MULTILINE
    )

    matches = list(gps_event_pattern.finditer(logs))

    if not matches:
        print("No GPS in log!")
        return None

    latest_match = matches[-1]  # Get the most recent match
    data = latest_match.groupdict()

    # Parse the time into a UTC timestamp
    now = datetime.datetime.utcnow()
    log_dt = datetime.datetime.strptime(f"{now.year} {data['month']} {data['day']} {data['time']}", "%Y %b %d %H:%M:%S")
    log_dt = log_dt.replace(tzinfo=datetime.timezone.utc)
    timestamp = int(log_dt.timestamp())

    # Build the dictionary
    gps_data = {
        "lat": float(data['lat']),
        "lon": float(data['lon']),
        "alt": int(data['alt']),
        "sats": int(data['sats']),
        "timestamp": timestamp
    }

    return gps_data

# Received: {'from': 530607104, 'to': 131047185, 'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'payload': b'G', 'bitfield': 1, 'text': 'G'}, 'id': 103172025, 'rxTime': 1745376860, 'rxSnr': 7.0, 'hopLimit': 7, 'wantAck': True, 'rxRssi': -14, 'hopStart': 7, 'publicKey': 'Jn89K4tEsX2fKYy+NUu3J8EJ/gjXjxP1SQCHm3A8Wms=', 'pkiEncrypted': True, 'raw': from: 530607104, to: 131047185, [...], 'fromId': '!1fa06c00', 'toId': '!07cf9f11'}

def onReceive(packet, interface):
    print("packet") # FIXME: debug packets so we can trace stuff we receive in flight
    #print(f"Received: {packet}")
    try:
        if packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP' and packet['to'] == my_node_user_id:
            print(f"rx msg: {packet['decoded']['payload']} from {packet['fromId']}")
            rx_time = datetime.datetime.fromtimestamp(packet['rxTime']).time()

            msg = f"{my_name} node. "

            msg += f"I ack your msg at {rx_time}. "
            try:
                msg += f"SNR {packet['rxSnr']} RSSI {packet['rxRssi']}. "
            except Exception:
                print("failed to get SNR?")
                traceback.print_exc()
            if pos is not None and {'latitude', 'longitude', 'altitude'}.issubset(pos):
                print("I have local position")
                msg += f"My alt {round(pos['altitude'],0)}m, lat {round(pos['latitude'],3)} lon {round(pos['longitude'],3)}. "
                if packet['fromId'] in interface.nodes:
                    print("fromId is in")
                    if 'position' in interface.nodes[packet['fromId']]:
                        print("it has position")
                        remote_position = interface.nodes[packet['fromId']]['position']
                        if {'latitude', 'longitude', 'altitude'}.issubset(remote_position):
                            print("it has attrs")
                            distance_km = distance_between_geodetic_points(
                                (remote_position['latitude'], remote_position['longitude'], remote_position['altitude']),
                                (pos['latitude'], pos['longitude'], pos['altitude']))
                            msg += f"We are {distance_km}km apart! "
                    else:
                        print("No remote position available")
            else:
                print("No local GPS fix")
                msg += "My GPS has no lock at the moment. "
            msg += "Thanks for QSO!"
            interface.sendText(msg, packet['from'])
            print(f"sent reply, {len(msg)}")
    except Exception as e:
        print('unhandled exception')
        traceback.print_exc()

pub.subscribe(onReceive, "meshtastic.receive")

iteration = 0

max_alt = 0
burst = False

while True:
    iteration += 1
    my = interface.getMyNodeInfo()
    print(f"my:{my}")
    #pos = my['position']
    pos = parse_recent_gps_from_journalctl()
    pay = {
        'chUtil': round(my['deviceMetrics']['channelUtilization'], 2),
        'airUtilTx': round(my['deviceMetrics']['airUtilTx'], 2),
        'uptime': my['deviceMetrics']['uptimeSeconds'],
        }
    if pos:
        pay.update({
            'alt': round(pos['alt'],0),
            'lat': round(pos['lat'],6),
            'lon': round(pos['lon'],6),
            'sats': pos['sats'],
            'gpstime': pos['timestamp'],
        })
        msg = None
        alt = pos['alt']
        if alt > 1000 and max_alt < alt:
            max_alt = alt
        if alt > 1000 and alt < 1360:
            # we're finally in flight!
            msg = f"{my_name} has lifted off! Altitude is {alt}m"
        if (alt > 5000 and alt < 5360) or (alt > 10000 and alt < 10360) or (alt > 15000 and alt < 15360) or (alt > 20000 and alt < 20360) or (alt > 25000 and alt < 25360) or (alt > 30000 and alt < 30360):
            msg = f"{my_name} at altitude {alt}m. DM me for stats, ChiMesh.org for Discord, follow path on amateur.sondehub.org"
        if alt < max_alt - 100 and not burst:
            burst = True
            msg = f"{my_name} balloon has burst at {max_alt}! I'll be landing in about 30 minutes, wish me luck!"
        if msg:
            print(f"Sending broadcast {msg}")
            interface.sendText(msg, destinationId='^all')
    else:
        if iteration % 30 == 0:
            msg = "Hi from {my_name}. DM me for stats, ChiMesh.org for Discord, follow path on amateur.sondehub.org"
            print(f"Sending broadcast {msg}")
            interface.sendText(msg, destinationId='^all')
    with open("/proc/uptime", "r") as f:
        uptime_str = f.readline().split()[0]
        pay.update({'uptime': int(float(uptime_str))})
    # TODO: Pi cpu temp?, some voltage?
    pay_json = json.dumps(pay, separators=(',', ':'))
    msg = f"mtf1:{pay_json}"
    # BalloonData channel idx=1 key vSHBJpTtJU3VvpQX3DYfAZUEfaHy4uYXVbHTVrx0ItA=
    #interface.sendPosition(destinationId='^all', channelIndex=1)# NB: this seems to send a position packet without any lat/long??? weird.
    interface.sendText(msg, destinationId='^all', channelIndex=1)
    print(msg)
    print(f"sent downlink len {len(msg)} sleeping...")
    #interface.showNodes() # for later analysis
    print(repr(interface.nodes))
    time.sleep(60)


interface.close()
