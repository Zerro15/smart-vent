
# Каркас симулятора датчиков по MQTT (теоретический)
import json, time, random, paho.mqtt.client as mqtt
BROKER="localhost"; TOPIC="school/classA/window1/telemetry"
def main():
    co2=650.0; t=21.5; rh=44.0; pm25_out=15.0
    c=mqtt.Client(); c.connect(BROKER,1883,60)
    while True:
        co2 += random.uniform(5, 12)
        payload={"co2":round(co2,1),"t":round(t,1),"rh":round(rh,1),"pm25_out":round(pm25_out,1)}
        c.publish(TOPIC, json.dumps(payload)); time.sleep(2)
if __name__=="__main__": main()
