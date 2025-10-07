
# Каркас контроллера по MQTT (теоретический)
import json, paho.mqtt.client as mqtt
BROKER="localhost"; TELE="school/classA/window1/telemetry"; CMD="school/classA/window1/cmd"
state={"fan":25,"valve":15,"mode":"auto","co2":600,"temp":21,"pm_out":12}
def decide():
    co2, temp, pm_out = state["co2"], state["temp"], state["pm_out"]
    fan, valve = state["fan"], state["valve"]
    if co2>1200: fan=min(100,fan+30); valve=min(100,valve+30)
    elif co2>1000: fan=min(100,fan+20); valve=min(100,valve+15)
    elif co2<700: fan=max(15,fan-10); valve=max(5,valve-10)
    if pm_out>40: fan=min(fan,40); valve=min(valve,40)
    state["fan"],state["valve"]=fan,valve
    return {"mode":"auto","fan":fan,"valve":valve}
def on_message(client,userdata,msg):
    data=json.loads(msg.payload.decode()); state.update({"co2":data.get("co2",state["co2"]),"temp":data.get("t",state["temp"]),"pm_out":data.get("pm25_out",state["pm_out"])})
    client.publish(CMD, json.dumps(decide()))
def main():
    c=mqtt.Client(); c.on_message=on_message; c.connect(BROKER,1883,60); c.subscribe(TELE); c.loop_forever()
if __name__=="__main__": main()
