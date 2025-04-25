#!/usr/bin/env python3

import serial
import struct
import argparse
import sys
import time

def __ubx_checksum(prefix_and_payload):
    """
    Calculates a UBX binary packet checksum.
    Algorithm comes from the u-blox M8 Receiver Description manual section "UBX Checksum"
    This is an implementation of the 8-Bit Fletcher Algorithm,
        so there may be a standard library for this.
    """
    checksum_a = 0
    checksum_b = 0
    for byte in prefix_and_payload:
        checksum_a = checksum_a + byte
        checksum_b = checksum_a + checksum_b
    checksum_a %= 256
    checksum_b %= 256
    return bytearray((checksum_a, checksum_b))


def ubx_assemble_packet(class_id, message_id, payload):
    """
    Assembles and returns a UBX packet from a class id,
    message id and payload bytearray.
    """
    # UBX protocol constants:
    ubx_packet_header = bytearray.fromhex("B5 62") # constant
    length_field_bytes = 2 # constant

    prefix = bytearray((class_id, message_id))
    length = len(payload).to_bytes(length_field_bytes, byteorder='little')
    return ubx_packet_header \
        + prefix \
        + length \
        + payload \
        + __ubx_checksum(prefix + length + payload) # fixme use other def?

# --- Utility Functions ---
def ubx_checksum(payload):
    ck_a = 0
    ck_b = 0
    for b in payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return bytes([ck_a, ck_b])

def dynamic_model_name(dyn_model):
    models = {
        0: "Portable",
        1: "Stationary",
        2: "Pedestrian",
        3: "Automotive",
        4: "Sea",
        5: "Airborne <4g",
        6: "Airborne <1g",
        7: "Airborne <2g",
        8: "Wrist",
        9: "Bike"
    }
    return models.get(dyn_model, "Unknown")

# --- UBX Interaction Functions ---
def read_ack(serial_port, msg_class, msg_id, timeout=2):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if serial_port.read(1) == b'\xB5':
            if serial_port.read(1) == b'\x62':
                header = serial_port.read(2)
                length = struct.unpack('<H', serial_port.read(2))[0]
                payload = serial_port.read(length)
                serial_port.read(2)  # checksum
                if header == b'\x05\x01' and payload[:2] == bytes([msg_class, msg_id]):
                    return True
                if header == b'\x05\x00' and payload[:2] == bytes([msg_class, msg_id]):
                    return False
    return None


def send_ubx_cfg_nav5(serial_port, dyn_model):
    # 36-byte payload with all fields (some zeroed)
    payload = struct.pack('<HBBLLLLLLLLLHHHHHH',
        0x0001,    # mask: only apply dynModel
        dyn_model, # dynamic model (0-8)
        2,         # fixMode (2 = auto)
        0, 0, 0,   # fixedAlt, fixedAltVar, minElev
        0, 0, 0,   # drLimit, pDop, tDop
        0, 0, 0,   # pAcc, tAcc, staticHoldThresh
        0,         # dgpsTimeout
        0,         # cnoThreshNumSVs
        0,         # cnoThresh
        0,         # reserved1
        0          # reserved2
    )

    msg = b'\xB5\x62\x06\x24' + struct.pack('<H', len(payload)) + payload
    msg += ubx_checksum(b'\x06\x24' + struct.pack('<H', len(payload)) + payload)

    serial_port.write(msg)
    return read_ack(serial_port, 0x06, 0x24)

def query_dynamic_model(serial_port):
    msg = b'\xB5\x62\x06\x24\x00\x00'
    msg += ubx_checksum(b'\x06\x24\x00\x00')

    serial_port.write(msg)

    while True:
        if serial_port.read(1) == b'\xB5':
            if serial_port.read(1) == b'\x62':
                header = serial_port.read(2)
                length = struct.unpack('<H', serial_port.read(2))[0]
                payload = serial_port.read(length)
                serial_port.read(2)  # checksum
                if header == b'\x06\x24' and length >= 2:
                    dyn_model = payload[2]
                    return dyn_model

def send_ubx_reset(serial_port, reset_type=0x00, nav_bbr_mask=0xFFFF):
    """
    Send a UBX-CFG-RST reset command.

    nav_bbr_mask:
      0x0000 = Hot start
      0x0001 = Warm start
      0xFFFF = Cold start (clear everything)

    reset_type:
      0x00 = Hardware reset (controlled by nav_bbr_mask)
      0x01 = Controlled software reset
      0x08 = Hardware reset (immediate)
    """
    payload = struct.pack('<HBb', nav_bbr_mask, reset_type, 0)
    msg = b'\xB5\x62\x06\x04' + struct.pack('<H', len(payload)) + payload
    msg += ubx_checksum(b'\x06\x04' + struct.pack('<H', len(payload)) + payload)
    serial_port.write(msg)

# --- CLI Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Query or set uBlox GPS dynamic model mode.")
    parser.add_argument('--port', required=True, help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument('--baud', type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument('--get-model', action='store_true', help="Query current dynamic model")
    parser.add_argument('--set-model', type=int, help="Set dynamic model (e.g. 6 for Airborne <1g)")
    parser.add_argument('--reset-gps', action='store_true', help="Send cold-start reset (equivalent to power cycle)")

    args = parser.parse_args()

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            if args.reset_gps:
                send_ubx_reset(ser, reset_type=0x00, nav_bbr_mask=0xFFFF)
                print("Cold reset sent. GPS is rebooting...")
                return  # Don't do anything else after reset
            if args.get_model:
                model = query_dynamic_model(ser)
                print(f"Current Dynamic Model: {model} ({dynamic_model_name(model)})")

            if args.set_model is not None:
                print(f"Setting Dynamic Model to {args.set_model} ({dynamic_model_name(args.set_model)})...")
                result = send_ubx_cfg_nav5(ser, args.set_model)
                if result is True:
                    print("Model set successfully (ACK received).")
                elif result is False:
                    print("Failed to set model (NAK received).")
                else:
                    print("No response from GPS (timeout).")
    except serial.SerialException as e:
        print(f"Serial error: {e}")
        sys.exit(1)



if __name__ == '__main__':
    main()
