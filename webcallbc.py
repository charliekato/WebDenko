#!/usr/bin/env python3

import sys
import threading
import asyncio
import json
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import pyodbc
import select
import xml.etree.ElementTree as ET
import aiohttp

from swlib.select_event import get_event_no

@dataclass(slots=True)
class LaneInfo:
    event_name:str
    zero_use: int
    start_lane: int
    end_lane: int



def get_lane_info(event_no) -> LaneInfo:
    row = execute("""
        select 
          大会名1 as eventName,
          使用水路予選 as maxLane,
          ゼロコース使用 as zeroUse ,
          タッチ板 as touchBoard
        from 大会設定
        where 大会番号=?
        """, event_no, fetch="one")
    event_name = row.eventName
    zero_use = row.zeroUse
    start_lane = 0 if zero_use else 1
    end_lane = row.maxLane-row.zeroUse
    return LaneInfo(event_name,zero_use,  start_lane, end_lane)



connections: list[WebSocket] = []


# ===== FastAPI =====

app = FastAPI()


# ===== WebSocket =====

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    await ws.accept()
    connections.append(ws)

    print("client connected")
    push_lane_order(False)

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




# ===== HTML =====
@app.get("/lane_order")
def lane_order():
    data = show_lane_order()
    return data

@app.get("/", response_class=HTMLResponse)
def index():

    return   f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{{
background:black;
color:white;
font-size:24px;
font-family:monospace;
}}

h2{{ 
font-size:24px;
font-family:monospace;
white-space: pre;
}}


table {{
  border-collapse: collapse;
}}

td {{
  border-bottom: 1px solid white; /* 横線だけ */
  padding-top: 3px;
  padding-bottom: 3px;
}}
</style>
<title>{lane_info.event_name} </title>
</head>
<body>


<h2 id="header"> 　</h2>
 <button class="next" onclick="send('next')">次の組</button>
 <button class="prev" onclick="send('prev')">前の組</button>


<table width="100%" id="t"></table>

<script>
const STARTLANE={lane_info.start_lane};
const ENDLANE={lane_info.end_lane};
const table=document.getElementById("t")
 
async function send(cmd) {{
    await fetch('/' + cmd)
}} 

for(let i = STARTLANE; i < ENDLANE+1; i++) {{

  const tr=document.createElement("tr")

  tr.innerHTML=
  `<td width="7%">${{i}}</td>
  <td width="16%" id="name${{i}}"></td>
  <td width="16%" id="team1${{i}}"></td>
  <td width="16%" id="team2${{i}}"></td>
  <td width="16%" id="team3${{i}}"></td>
  <td width="16%" id="team4${{i}}"></td>
  <td width="8%" id="mark${{i}}"></td>
  <td width="5%" id="padding${{i}}"></td>

  `

    table.appendChild(tr)
}}

function clearLaneOrder() {{
    for (let i=STARTLANE;i<ENDLANE+1;i++) {{
        document.getElementById("name"+i).textContent = "";
        document.getElementById("team1"+i).textContent = "";
        document.getElementById("team2"+i).textContent = "";
        document.getElementById("team3"+i).textContent = "";
        document.getElementById("team4"+i).textContent = "";
    }}
}}

const ws=new WebSocket("ws://"+location.host+"/ws")

ws.onmessage=(ev)=>{{

    const data=JSON.parse(ev.data)


        clearLaneOrder()

        document.getElementById("header").textContent = data.header
        data.lanes.forEach(lane=>{{
            document.getElementById("name"+lane.lane).textContent = lane.name
            document.getElementById("team1"+lane.lane).textContent = lane.team1
            document.getElementById("team2"+lane.lane).textContent = lane.team2
            document.getElementById("team3"+lane.lane).textContent = lane.team3
            document.getElementById("team4"+lane.lane).textContent = lane.team4
        }})

        return
       

}}

</script>

</body>
</html>
"""

@app.get("/prev")
async def show_prev():
    show_prev_race()

@app.get("/next")
async def show_next():
    show_next_race()

@app.on_event("startup")
async def startup():
    global loop
    loop = asyncio.get_running_loop()



# ===== SQL SERVER ====
def execute(sql, *params, fetch="all"):
    with pyodbc.connect(connectionStr) as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)

        if fetch == "one":
            return cur.fetchone()

        if fetch == "all":
            return cur.fetchall()

        conn.commit()

def get_max_kumi():   
    row = execute("""
        select max(組)
        from v記録
        where 大会番号=?
        and PRGNO=?
        """, eventNo,prgNo,fetch="one")
    return row[0] if row else 0

def get_max_prgno():

    row = execute("""
        select max(表示用競技番号)
        from プログラム
        where 大会番号=?
    """, eventNo,fetch="one")

    return row[0] if row else None

def get_prev_race():
    global kumi
    global prgNo
    while kumi>1:
        kumi -= 1
        if race_exist():
            return True
    while prgNo>1:
        prgNo -= 1
        kumi = get_max_kumi()
        if race_exist():
            return True
    return False

def get_next_race():   
    global kumi
    global prgNo
    while kumi<get_max_kumi():
        kumi += 1 
        if race_exist():
            return True
    kumi=1
    maxprgno = get_max_prgno()
    while prgNo<maxprgno:
        prgNo += 1
        if race_exist():
            return True
    return False


def race_exist():
    rows = execute("""
        select 
          選手番号 as swimmerid,
          表示用競技番号 as prgno,
          組
        from 記録
        inner join プログラム on プログラム.競技番号=記録.競技番号
               and プログラム.大会番号=記録.大会番号
        where 記録.大会番号=?
         and 表示用競技番号=?
         and 組=?
         """,eventNo,prgNo,kumi,fetch="all")
    for row in rows:
        if row.swimmerid > 0 :
            return True
    return False


def push_lane_order(flash):

    (header, lanes) = show_lane_order()

    payload = json.dumps({
        "header": header ,
        "lanes": lanes
    })

    if connections:
        asyncio.run_coroutine_threadsafe(
            broadcast(payload),
            loop
        )

def show_prev_race():
    if get_prev_race():
        push_lane_order(True)
    else:
        print("最初のレースです。")



def show_next_race():
    if get_next_race():
        push_lane_order(True)
    else:
        print("最終のレースです。")


def show_lane_order():
    rows = execute("""
         select 
           距離 as distance,
           種目 as stroke,
           種目コード as strokecode,
           予決 as phase,
           クラス名称 as className,
           性別 as gender,
           水路 as lane,
           MAXLANE,
           第１泳者 as swimmer1,
           第２泳者 as swimmer2,
           第３泳者 as swimmer3,
           第４泳者 as swimmer4,
           所属 as team,
           ゴール as goal,
           棄権印刷マーク as mark
         from v記録
           where 大会番号= ?
            and  PRGNO = ?
            and  組 = ?
          """, eventNo, prgNo, kumi,fetch="all")
    
    lanes = []
    for row in rows:
        header =  str(prgNo) + "  "   +\
                row.gender + row.className + row.distance + row.stroke + \
                " " + row.phase +" "+ str(kumi) + "組"
        lane = row.lane - lane_info.zero_use
        if lane>9 :
            continue
        if row.strokecode < 6:
            team1 = row.team or ""
            team2 =  ""
            team3 =  ""
            team4 =  ""
            name = row.swimmer1 or ""
        else:
            name = row.team or ""
            team1 = "1. " + (row.swimmer1 or "")
            team2 = "2. " + (row.swimmer2 or "")
            team3 = "3. " + (row.swimmer3 or "")
            team4 = "4. " + (row.swimmer4 or "")
            

        lanes.append({
            "lane": lane,
            "name": name,
            "team1": team1,
            "team2": team2,
            "team3": team3,
            "team4": team4,
            "mark": row.mark or ""
        })

    
    return header, lanes


# ===== main =====

prgNo = 1
kumi = 1

tree = ET.parse("webdenko.config")
root = tree.getroot()
server = root.find("Server").text
password = root.find("Password").text

eventNo = get_event_no(server,password)
print("\033[2J\033[H", end="")

def main():

    global connectionStr
    global lane_info

    connectionStr =  ("DRIVER=FreeTDS;" 
         f"SERVER={server};" 
          "PORT=1433;"
          "UID=sw;" 
          "DATABASE=sw;" 
         f"PWD={password};" 
          "TDS_Version=7.4;")

           
    # screen clear
    lane_info=get_lane_info(eventNo)
    show_lane_order()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5193)

if __name__ == "__main__":
    main()
