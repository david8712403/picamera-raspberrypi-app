import paho.mqtt.client as mqtt
import time
import json
import datetime
import Config

# get pi host ip
from subprocess import check_output
import re
ip = str(check_output(['hostname','-I']))
ip = re.sub('[a-z\ \' ]', '', ip)
ip = ip[0:-1]
print(ip)

client_pub = mqtt.Client(client_id='david',
        clean_session=True,
        transport='tcp')

client_pub.username_pw_set(Config.mqtt_user, password=Config.mqtt_pwd)
client_pub.reconnect_delay_set(min_delay=1, max_delay=60)

client_pub.connect('localhost', port=1883, keepalive=999)

while True:
    i = eval(input("input:"))
    payload={'time': str(datetime.datetime.now()),'index':i}
    print(json.dumps(payload))
    client_pub.publish('david/test', i)
