#!/usr/bin/env python3

import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
import time
import datetime
import math
import json

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


# Received: {'from': 530607104, 'to': 131047185, 'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'payload': b'G', 'bitfield': 1, 'text': 'G'}, 'id': 103172025, 'rxTime': 1745376860, 'rxSnr': 7.0, 'hopLimit': 7, 'wantAck': True, 'rxRssi': -14, 'hopStart': 7, 'publicKey': 'Jn89K4tEsX2fKYy+NUu3J8EJ/gjXjxP1SQCHm3A8Wms=', 'pkiEncrypted': True, 'raw': from: 530607104, to: 131047185, [...], 'fromId': '!1fa06c00', 'toId': '!07cf9f11'}

def onReceive(packet, interface):
    #print(f"Received: {packet}")
    try:
        if packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP' and packet['to'] == 131047185:
            print(f"rx msg: {packet['decoded']['payload']}")
            rx_time = datetime.datetime.fromtimestamp(packet['rxTime']).time()

            msg = f"KD9PRC 🎈 node. "
            msg += f"I ack your msg at {rx_time} SNR {packet['rxSnr']} RSSI {packet['rxRssi']}. My alt {round(pos['altitude'],0)}m, lat {round(pos['latitude'],3)} lon {round(pos['longitude'],3)}. "
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
            msg += "Thanks for QSO!"
            interface.sendText(msg, packet['from'])
            print(f"sent reply, {len(msg)}")
    except Exception:
        print('unhandled packet')

pub.subscribe(onReceive, "meshtastic.receive")
interface = meshtastic.tcp_interface.TCPInterface(hostname='127.0.0.1')

while True:
    my = interface.getMyNodeInfo()
    pos = my['position']
    pay = {
        'alt': round(my['position']['altitude'],0),
        'lat': round(my['position']['latitude'],4),
        'lon': round(my['position']['longitude'],4),
        'chUtil': round(my['deviceMetrics']['channelUtilization'], 2),
        'airUtilTx': round(my['deviceMetrics']['channelUtilization'], 2),
        'uptime': my['deviceMetrics']['uptimeSeconds'],
# TODO: linux uptime, Pi cpu temp?, some voltage?
    }
    pay_json = json.dumps(pay)
    msg = f"mtf:{pay_json}"
    interface.sendText(msg, '!d9efdb3d')
    print(msg)
    print(f"sent downlink len {len(msg)} sleeping...")
    # do clever things based on altitude???
    time.sleep(60)


interface.close()
