#!/usr/bin/env python3

import sys
import threading
import asyncio
import json
from queue import Queue
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import pyodbc
import serial


# ===== データ =====

@dataclass(slots=True)
class TimeRecord:
    str_time: str
    lane_no: int
    goal: bool
    is_running_timer: bool


queue = Queue()
connections: list[WebSocket] = []


# ===== FastAPI =====

app = FastAPI()


# ===== WebSocket =====

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    await ws.accept()
    connections.append(ws)

    print("client connected")

    try:
        while True:
            await asyncio.sleep(3600)

    except WebSocketDisconnect:
        connections.remove(ws)
        print("client disconnected")


async def broadcast(payload: str):

    dead = []

    for ws in connections:
        try:
            await ws.send_text(payload)
        except:
            dead.append(ws)

    for ws in dead:
        connections.remove(ws)


# ===== broadcaster =====

async def broadcaster():

    while True:

        rec = await asyncio.to_thread(queue.get)

        payload = json.dumps({
            "str_time": rec.str_time,
            "lane_no": rec.lane_no,
            "goal": rec.goal,
            "is_running_timer": rec.is_running_timer
        })

        await broadcast(payload)


@app.on_event("startup")
async def startup():

    asyncio.create_task(broadcaster())


# ===== serial parser =====

STX = 2
ETX = 3

serial_port = None


def format_running_time(src: str) -> str:

    s = list(src)

    if s[0] == '0':
        s[0] = ' '

        if s[1] == '0':
            s[1] = ' '
            s[2] = ' '

            if s[3] == '0':
                s[3] = ' '

    return "".join(s)


def parse_packet(buf):

    timer = format_running_time(buf[5:13].decode("ascii"))

    if buf[0:2] == b'AR':

        return TimeRecord(timer, 0, False, True)

    lane = buf[2] - ord('0')

    if buf[13:14] == b'G':
        return TimeRecord(timer, lane, True, False)

    if buf[13:14] == b'L':
        return TimeRecord(timer, lane, False, False)

    return None


# ===== serial thread =====

def serial_thread():

    buf = bytearray(20)
    counter = -1

    while True:

        data = serial_port.read(18)

        for b in data:

            if b == STX:
                counter = 0

            elif b == ETX:

                counter = -1

                rec = parse_packet(buf)

                if rec:
                    queue.put(rec)

            elif counter >= 0:

                buf[counter] = b
                counter += 1

                if counter >= len(buf):
                    counter = -1


# ===== HTML =====
@app.get("/lane_order")
def lane_order():
    global eventNo
    data = show_lane_order(11,1,1)
    return data


@app.get("/", response_class=HTMLResponse)
def index():

    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{
background:black;
color:white;
font-size:24px;
font-family:monospace;
}
#timer{
position:fixed;
top:20px;
right:30px;
color:yellow;
}
h2{ 
font-size:24px;
font-family:monospace;
}
</style>
</head>
<body>

<div id="timer">00:00</div>

<h2> 　性別・種目・距離</h2>
<table width="100%" id="t"></table>


<script>

const table=document.getElementById("t")

for(let i=0;i<10;i++){

  const tr=document.createElement("tr")

  tr.innerHTML=
  `<td width="5%">${i}</td>
  <td width=20%" id="name${i}">name</td>
  <td width=20%" id="team${i}">team</td>
  <td width=20%" id="lap${i}" >lap </td>
  <td width=20%" id="time${i}">time</td>
  <td width=15%" id="note${i}">time</td>
  `

table.appendChild(tr)
}
async function loadLaneOrder(){

    const res = await fetch("/lane_order");
    const lanes = await res.json();

    lanes.forEach(lane => {

        document.getElementById("name"+lane.lane).textContent = lane.name;

        document.getElementById("team"+lane.lane).textContent = lane.team;

    });
}
loadLaneOrder();


const ws=new WebSocket("ws://"+location.host+"/ws")

ws.onmessage=(ev)=>{

    const data=JSON.parse(ev.data)

    if(data.is_running_timer){

    document.getElementById("timer").textContent=data.str_time

    }else{

        document.getElementById("time"+data.lane_no).textContent=data.str_time

    }

}
</script>

</body>
</html>
"""
# ===== SQL SERVER ====
connectionStr = """
          DRIVER={ODBC Driver 18 for SQL Server};
          SERVER=olivia.local,1433;
          UID=sw;
          DATABASE=sw;
          PWD=StrongPassword123!;
          Encrypt=no;
          TrustServerCertificate=yes;
          """
 
def show_lane_order(eventNo, prgno, kumi):
    with pyodbc.connect(connectionStr) as conn:
        cursor = conn.cursor()
        query = """
             select 
               距離 as distance,
               種目 as stroke,
               種目コード as strokecode,
               クラス名称 as class,
               性別 as gender,
               水路 as lane,
               第１泳者 as swimmer1,
               第２泳者 as swimmer2,
               第３泳者 as swimmer3,
               第４泳者 as swimmer4,
               所属 as team,
               棄権印刷マーク as mark
             from v記録
               where 大会番号= ?
                and  PRGNO = ?
                and  組 = ?
              """
        cursor.execute(query,eventNo,prgno,kumi)
        ## ここで、 種目コードが6未満のときは個人競技　6,7 はリレー
        ## 個人競技の時は第2泳者～第4泳者までは使用しない。row.第1泳者 を　
        ## <table>のname(laneNo)にいれる。 row.所属 は team(laneNo)にいれる。
        ## リレーの時はname(laneNo)には row.第1泳者 から 第4泳者までを"・" で
        ## 連結して　name(laneNo)にいれる。
        lanes = []
        for row in cursor:
            lane = row.lane
            if row.strokecode < 6:
                name = row.swimmer1
            else:
                name = "・".join([
                    row.swimmer1,
                    row.swimmer2,
                    row.swimmer3,
                    row.swimmer4
                ])

            lanes.append({
                "lane": lane,
                "name": name,
                "team": row.team
            })

    conn.close()
    
    return lanes





# ===== main =====

def main():

    global serial_port

    if len(sys.argv) < 2:
        print("usage: server.py /dev/ttyUSB0")
        return

    port = sys.argv[1]

    serial_port = serial.Serial(
        port=port,
        baudrate=9600,
        parity=serial.PARITY_EVEN,
        bytesize=7,
        timeout=None
    )

    t = threading.Thread(target=serial_thread, daemon=True)
    t.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5192)


if __name__ == "__main__":
    main()
