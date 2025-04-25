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

def enable_flight_mode(serial_port):
    """
    Sends a CFG-NAV5 UBX message which enables "flight mode", which allows
    operation at higher altitudes than defaults.
    Should read up more on this sentence, I'm just copying this
    byte string from other tracker projects.
    See for example string:
        https://github.com/Chetic/Serenity/blob/master/Serenity.py#L10
        https://github.com/PiInTheSky/pits/blob/master/tracker/gps.c#L423
    """
    print("radio_flyer GPS: enabling flight mode")
    cfg_nav5_class_id = 0x06
    cfg_nav5_message_id = 0x24
    payload = bytearray.fromhex("FF FF 06 03 00 00 00 00 10 27 00 00 05 00 FA 00 FA 00 64 00 2C 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00") # pylint: disable=line-too-long
    ack_ok = __send_and_confirm_ubx_packet(serial_port, cfg_nav5_class_id, cfg_nav5_message_id, payload)
    if not ack_ok:
        raise Exception("Failed to configure GPS for flight mode.")
    print("GPS: flight mode enabled.")

def __send_and_confirm_ubx_packet(serial_port, class_id, message_id, payload):
    """
    Constructs, sends, and waits for an ACK packet for a UBX "binary" packet.
    User only needs to specify the class & message IDs, and the payload as a bytearray;
        the header, length and checksum are calculated automatically.
    Then constructs the corresponding CFG-ACK packet expected, and waits for it.
    If the ACK packet is not received, returns False.
    """

    send_packet = ubx_assemble_packet(class_id, message_id, payload)
    serial_port.write(send_packet)
    print("UBX packet built: {}".format(send_packet))

    return read_ack(serial_port, class_id, message_id)

def reboot_my_gps(serial_port):
    return __send_and_confirm_ubx_packet(serial_port, 0x06, 0x04, bytearray.fromhex("FF 87 00 00"))

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

# --- CLI Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Query or set uBlox GPS dynamic model mode.")
    parser.add_argument('--port', required=True, help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument('--baud', type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument('--get-model', action='store_true', help="Query current dynamic model")
    parser.add_argument('--set-flight-mode', action='store_true', help="Set dynamic model to 6 for airborne 1g use")
    parser.add_argument('--reset-gps', action='store_true', help="Send reboot")

    args = parser.parse_args()

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            if args.reset_gps:
                reboot_my_gps(ser)
                print("Cold reset sent. GPS is rebooting...")
                return  # Don't do anything else after reset
            if args.get_model:
                model = query_dynamic_model(ser)
                print(f"Current Dynamic Model: {model} ({dynamic_model_name(model)})")

            if args.set_model is not None:
                print(f"Setting Dynamic Model to {args.set_model} ({dynamic_model_name(args.set_model)})...")
                result = enable_flight_mode(ser)
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
