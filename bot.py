#!/usr/bin/env python3

import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
import time
import datetime


#Received: {'from': 3656375101, 'to': 131047185, 'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'payload': b'G', 'bitfield': 1, 'text': 'G'}, 'id': 291278309, 'rxTime': 1745373565, 'rxSnr': 6.25, 'hopLimit': 7, 'wantAck': True, 'rxRssi': -39, 'hopStart': 7, 'publicKey':
def onReceive(packet, interface):
    #print(f"Received: {packet}")
    try:
        if packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP' and packet['to'] == 131047185:
            print(f"rx msg: {packet['decoded']['payload']}")
            rx_time = datetime.datetime.fromtimestamp(packet['rxTime']).time()
            msg = f"KD9PRC balloon node here, I ack your message at {rx_time}, SNR {packet['rxSnr']} RSSI {packet['rxRssi']}. My altitude is {pos['altitude']}m, lat {pos['latitude']} lon {pos['longitude']}. Thanks for QSO!"
            interface.sendText(msg, packet['from'])
            print('sent reply')
    except Exception:
        print('unhandled packet')

pub.subscribe(onReceive, "meshtastic.receive")
interface = meshtastic.tcp_interface.TCPInterface(hostname='172.16.17.185')

while True:
    my = interface.getMyNodeInfo()
    pos = my['position']
    msg = f"mtflyer: {pos['latitude']} {my['deviceMetrics']['channelUtilization']}"
    interface.sendText(msg, '!d9efdb3d')
    print('sent downlink, sleeping...')
    # do clever things based on altitude???
    time.sleep(60)



interface.close()
