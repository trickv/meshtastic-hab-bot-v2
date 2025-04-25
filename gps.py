#!/usr/bin/env python3

import ublox


def handle_gps_data(gps_data):
    print("got some gps data")
    print(gps_data)

def debug_ptr_callback(foo):
    print(f"GPS Debug: {foo}")

gps = ublox.UBloxGPS(port='/dev/ttyACM0',
    #dynamic_model = ublox.DYNAMIC_MODEL_AIRBORNE1G,
    baudrate= 9600,
    update_rate_ms = 1000,
    debug_ptr = debug_ptr_callback,
    callback = handle_gps_data,
    log_file = 'gps_data.log'
    )

