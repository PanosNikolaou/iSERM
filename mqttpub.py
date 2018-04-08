import paho.mqtt.client as mqtt
import time
import json
#import math
import random
#import numpy as np

def on_publish(client, userdata, mid):
    print("mid: "+str(mid))


mqttc = mqtt.Client()
mqttc.on_publish = on_publish
mqttc.connect("broker.hivemq.com", 1883)


while True:
    smoke = random.randrange(1000)
    hum = random.randrange(start=30,stop=80)
    temp = random.randrange(start=0 , stop=40)
    windspd = random.randrange(20)
    lpg = random.randrange(20)
    co = random.randrange(20)
    temperature = "'{\"smk\" : "+ str(smoke) +", \"lpg\" :" + str(lpg) +", \"co\" :" + str(co) +", \"hum\" :" + str(hum) + ", \"temp\":" + str(temp) + ", \"wndspd\":" + str(windspd)+ ", \"wnddir\":\"E\" }'"
    json.dumps(temperature)
    print(temperature)
    mqttc.publish("/SERM", temperature)
    time.sleep(1)
