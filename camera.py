#Based on: https://nostarch.com/RaspberryPiProject

import io
import os
import pigpio
import picamera
import logging
import time
import datetime
import threading

import paho.mqtt.client as mqtt  
import socketserver
from threading import Condition
from http import server
from google.cloud import storage
from firebase import firebase
import firebase_admin
from firebase_admin import db, credentials
import requests
from requests import get, post
import json

import Config

PWM_CONTROL_PIN = 18
PWM_CONTROL_PIN_1 = 19
PWM_FREQ = 50
STEP = 15
pi = pigpio.pi()

#get pi host ip
from subprocess import check_output
import re
ip = str(check_output(['hostname', '-I']).decode('utf-8')).replace('\n', '').rstrip()
print(ip)

version = "1.0"

PAGE="""\
<html>
    <head>
        <style>
            p.serif {
              font-family: "Times New Roman", Times, serif;
            }
            p.sansserif {
              font-family: Arial, Helvetica, sans-serif;
            }
            body {
              background-color: white;
            }
        </style>
    </head>
    <body>
        <center><img src="stream.mjpg" width="640" height="340"></center>
    </body>
</html>
"""

def angle_to_duty_cycle(angle=0):
    duty_cycle = int((500 * PWM_FREQ + (1900 * PWM_FREQ * angle / 180)))
    return duty_cycle

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            #new frame, copy the existing buffer's content and notify all
            #clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class DBThread(threading.Thread):
    def __init__(self, picamera):
        threading.Thread.__init__(self)
        self.picamera = picamera
    
    def run(self):
        dbUrl = Config.dbUrl
        postRef = Config.postRef
        imgUrl = Config.imgUrl
        if not firebase_admin._apps:
            cred = credentials.Certificate(Config.CerficateRef)
            default_app = firebase_admin.initialize_app(cred, {'databaseURL': dbUrl, 'storageBucket':imgUrl})
    
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"]=Config.CerficateRef
        firebase.FirebaseApplication(dbUrl + '.json')
        screenshotRef = db.reference('device/home/screenshot')
        client = storage.Client()
        bucket = client.get_bucket(imgUrl)

        t = time.time()
        date = datetime.datetime.fromtimestamp(t).strftime('%Y%m%d%H%M%S')
        self.picamera.capture('/home/pi/Desktop/images/'+ str(date) +'.jpg')
        print("capture")
        imgPath = '/home/pi/Desktop/images/'+ str(date) +'.jpg'
        imgBlob = bucket.blob('images/'+ str(date) + '.jpg')
        imgBlob.upload_from_filename(imgPath)
        imgData = {'createAt':str(datetime.datetime.fromtimestamp(t)),
                   'name': str(date)+'.jpg',
                   'url': imgUrl + '/' + str(date) + '.jpg'}
        result = requests.post(postRef, data=json.dumps(imgData))
        print("response:" + result.text)
        self.picamera.annotate_text = "picture saved!"

           
class LabelThread(threading.Thread):
    def __init__(self, camera, mqtt_client):
        threading.Thread.__init__(self)
        self.camera = camera
        self.mqtt_client = mqtt_client
        self.camera.annotate_background = picamera.color.Color('black')
        self.angle = 0
        pi.hardware_PWM(PWM_CONTROL_PIN, PWM_FREQ, angle_to_duty_cycle(self.angle))
        self.clockwise = False
        #self.camera.brightness = 0
        
    def run(self):
        while True:
            self.mqtt_client.loop()
            #time.sleep(0.1)
            if self.angle == 60:
                self.clockwise = False
                time.sleep(1)
            if self.angle == 0:
                self.clockwise = True
                time.sleep(1)

            if self.clockwise == True:
                self.angle += 1
            else:
                self.angle -= 1
            self.camera.annotate_text = "ip:" + ip + " " +  datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " v:" + version
            self.camera.annotate_text_size = 30
            #pi.hardware_PWM(PWM_CONTROL_PIN, PWM_FREQ, angle_to_duty_cycle(self.angle))
            #self.camera.brightness += 5

camera =  picamera.PiCamera(resolution='1280x720', framerate=40)

client_sub = mqtt.Client(client_id='chen',
        clean_session=True,
        transport='tcp')

def on_connect(client, userdata, flag, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("device/angle")
    client.subscribe("device/zoom")
    client.subscribe("device/screenshot")

def on_message(client, userdata, msg):
    
    if msg.topic == 'device/angle':
        print(msg.topic+" "+str(msg.payload.decode("utf-8")))
        angle = int(msg.payload.decode("utf-8"))
        pi.hardware_PWM(PWM_CONTROL_PIN,
                        PWM_FREQ,
                        angle_to_duty_cycle(angle))
    elif msg.topic == 'device/zoom':
        print(msg.topic+" "+str(msg.payload.decode("utf-8")))
        zoom = int(msg.payload.decode("utf-8"))
        camera.zoom=((50.-zoom/2.)/100.,(50.-zoom/2.)/100.,zoom/100.,zoom/100.)
    
    elif msg.topic == 'device/screenshot':
        print(msg.topic+" "+str(msg.payload.decode("utf-8")))
        dbThread = DBThread(camera)
        dbThread.start()
        
        

client_sub.on_connect = on_connect
client_sub.on_message = on_message

client_sub.username_pw_set(Config.mqtt_user, password=Config.mqtt_pwd)
client_sub.connect(ip, port=1883, keepalive=60)

pi.hardware_PWM(PWM_CONTROL_PIN,PWM_FREQ,angle_to_duty_cycle(0))
time.sleep(1)
pi.hardware_PWM(PWM_CONTROL_PIN,PWM_FREQ,angle_to_duty_cycle(170))



output = StreamingOutput()
camera.rotation = 180
camera.start_recording(output, format='mjpeg')
labelThread = LabelThread(camera, client_sub)
labelThread.start()
    
try:
    address = (ip, 8000)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()
except KeyboardInterrupt:
    camera.stop_recording()
finally:
    camera.stop_recording()
