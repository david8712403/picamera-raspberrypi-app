import paho.mqtt.client as mqtt  
import time  
import json
import threading
import random
import Config
import pigpio

# get pi host ip
from subprocess import check_output
import re
ip = str(check_output(['hostname','-I']))
ip = re.sub('[a-z\ \' ]', '', ip)
ip = ip[0:-1]
print(ip)

PWM_CONTROL_PIN = 18
PWM_FREQ = 50
STEP = 15
pi = pigpio.pi()

def angle_to_duty_cycle(angle=0):
    duty_cycle = int((500 * PWM_FREQ + (1900 * PWM_FREQ * angle / 180)))
    return duty_cycle

class MqttThread(threading.Thread):
    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.connect('localhost', port=1883, keepalive=60)

    def run(self):
        print("test")

client_sub = mqtt.Client(client_id='chen',
        clean_session=True,
        transport='tcp')

def on_connect(client, userdata, flag, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("david/test")

def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload.decode("utf-8")))
    angle = int(msg.payload.decode("utf-8"))
    pi.hardware_PWM(PWM_CONTROL_PIN,
            PWM_FREQ,
            angle_to_duty_cycle(angle))
    

client_sub.on_connect = on_connect
client_sub.on_message = on_message

client_sub.username_pw_set(Config.mqtt_user, password=Config.mqtt_pwd)
client_sub.connect(ip, port=1883, keepalive=60)

pi.hardware_PWM(PWM_CONTROL_PIN,PWM_FREQ,angle_to_duty_cycle(0))
time.sleep(1)
pi.hardware_PWM(PWM_CONTROL_PIN,PWM_FREQ,angle_to_duty_cycle(180))


while True:
    client_sub.loop()
