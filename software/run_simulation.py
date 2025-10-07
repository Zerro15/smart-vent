
import numpy as np, pandas as pd, matplotlib.pyplot as plt, os
from dataclasses import dataclass
np.random.seed(3)
HOURS=8; N=HOURS*60
# people timeline
people=np.zeros(N); t=0
for L,b in zip([45,45,45,45,45,45],[10,10,30,10,10,0]):
    e=min(t+L,N); people[t:e]=29; t=e
    if b and t<N: e=min(t+b,N); people[t:e]=2+np.random.randint(0,4,e-t); t=e
if t<N: people[t:]=2
# outdoor
m=np.arange(N)
t_out=12+5*np.sin(2*np.pi*(m-180)/(12*60))+np.random.normal(0,0.4,N)
pm_out=np.clip(12+8*np.exp(-((m-240)/90.0)**2)+np.random.normal(0,1.5,N),5,80)
@dataclass
class S: co2:float; t:float; rh:float; pm:float
@dataclass
class A: fan:float; valve:float; mode:str
ROOM=180.0; CO2_OUT=420.0; GEN=0.5; MAX=110.0; INF=0.3; HEPA=0.92
def step(s,p,a,to,po):
    af=(a.fan/100)*(a.valve/100); m3h=af*MAX; ach=(m3h/ROOM+INF)/60
    co2=max(CO2_OUT, s.co2 + GEN*p - (s.co2-CO2_OUT)*ach)
    t=s.t + (to-s.t)*0.0035 + (to-s.t)*0.015*af + 0.002*(max(0,p-5))
    pm=max(0, s.pm + (po*(m3h/ROOM)/60)*(1-HEPA) - s.pm*0.002)
    rh=min(75, max(20, s.rh + (45-s.rh)*0.01 + 0.008*max(0,p-5)))
    return S(co2,t,rh,pm)
def run(ctrl):
    s=S(600,21,45,8); rows=[]
    fan=25; valve=15
    for i in range(N):
        if ctrl:
            if s.co2>1200: fan=min(100,fan+30); valve=min(100,valve+30)
            elif s.co2>1000: fan=min(100,fan+20); valve=min(100,valve+15)
            elif s.co2<700: fan=max(15,fan-10); valve=max(5,valve-10)
            if pm_out[i]>40: fan=min(fan,40); valve=min(valve,40)
            a=A(fan,valve,"auto")
        else:
            a=A(0,0,"stop")
        s=step(s,people[i],a,t_out[i],pm_out[i])
        rows.append(dict(minute=i,hour=i/60,people=people[i],t_out=t_out[i],pm25_out=pm_out[i],
                         co2=s.co2,temp=s.t,rh=s.rh,pm25=s.pm,fan=a.fan,valve=a.valve,mode=a.mode))
    return pd.DataFrame(rows)
base=run(False); ctrl=run(True)
df=ctrl.rename(columns={"co2":"co2_ctrl","temp":"temp_ctrl","pm25":"pm25_ctrl"})
df["co2_base"]=base["co2"]; df["temp_base"]=base["temp"]; df["pm25_base"]=base["pm25"]
os.makedirs("docs",exist_ok=True)
plt.figure(figsize=(10,5)); plt.plot(df.hour,df.co2_base,label="CO₂ без управления"); plt.plot(df.hour,df.co2_ctrl,label="CO₂ с управлением"); plt.axhline(1000,linestyle="--",label="Порог 1000 ppm"); plt.xlabel("часы"); plt.ylabel("ppm"); plt.title("CO₂"); plt.legend(); plt.tight_layout(); plt.savefig("docs/sim_co2.png",dpi=160); plt.close()
plt.figure(figsize=(10,5)); plt.plot(df.hour,df.temp_ctrl,label="Внутри"); plt.plot(df.hour,df.t_out,label="Снаружи"); plt.xlabel("часы"); plt.ylabel("°C"); plt.title("Температура"); plt.legend(); plt.tight_layout(); plt.savefig("docs/sim_temp.png",dpi=160); plt.close()
plt.figure(figsize=(10,5)); plt.plot(df.hour,df.pm25_ctrl,label="Внутри"); plt.plot(df.hour,df.pm25_out,label="Снаружи"); plt.xlabel("часы"); plt.ylabel("µg/m³"); plt.title("PM2.5"); plt.legend(); plt.tight_layout(); plt.savefig("docs/sim_pm.png",dpi=160); plt.close()
plt.figure(figsize=(10,5)); plt.plot(df.hour,df.fan,label="Вентилятор"); plt.plot(df.hour,df.valve,label="Клапан"); plt.xlabel("часы"); plt.ylabel("%"); plt.title("Действия контроллера"); plt.legend(); plt.tight_layout(); plt.savefig("docs/sim_actions.png",dpi=160); plt.close()
plt.figure(figsize=(10,4)); plt.plot(df.hour,df.people,label="Людей"); plt.xlabel("часы"); plt.ylabel("чел"); plt.title("Заполняемость"); plt.legend(); plt.tight_layout(); plt.savefig("docs/sim_people.png",dpi=160); plt.close()
df.to_csv("docs/simulation.csv",index=False)
print("DONE")
