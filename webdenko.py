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
import select


from swlib.select_event import get_event_no


eventNo=1
prgNo=1
kumi=1
lapunit=50
lasttime = [0]*10
lapcount = [0]*10

def resettime():
    global lasttime
    global lapcount
    lasttime = [0]*10
    lapcount = [0]*10


def set_lapunit():
    global lapunit
    row = execute("""
        select
          タッチ板 as touchBoard
        from 大会設定
        where 大会番号=?
        """, eventNo,fetch="one")
    if row.touchBoard == 4:
        lapunit=50
    if row.touchBoard == 3:
        lapunit=25
    if row.touchBoard == 2:
        lapunit=100

    if row.touchBoard == 1:
        lapunit=50
    return

def timestr2int(mytime):
    return int(mytime.replace(":", "").replace(".", ""))


def timeint2str(mytime: int) -> str:
    minutes = mytime // 10000
    temps = mytime % 10000
    seconds = temps // 100
    centiseconds = temps % 100

    if minutes > 0:
        return f"{minutes:2}:{seconds:02}.{centiseconds:02}"
    else:
        return f"   {seconds:2}.{centiseconds:02}"

# ===== データ =====

@dataclass(slots=True)
class TimeRecord:
    str_time: str
    lane_no: int
    goal: bool
    is_running_timer: bool
    lap_time: str
    distance: str

def substract_time(current_time: int, last_time: int) -> int:
    minute = (current_time // 10000) - (last_time // 10000)
    second = ((current_time % 10000) // 100) - ((last_time % 10000) // 100)
    centi_second = (current_time % 100) - (last_time % 100)

    if centi_second < 0:
        second -= 1
        centi_second += 100

    if second < 0:
        minute -= 1
        second += 60
    answer= minute * 10000 + second * 100 + centi_second



    return answer

def parse_packet(buf):

    timer = format_running_time(buf[5:13].decode("ascii"))

    if buf[0:2] == b'AR':
        return TimeRecord(timer, 0, False, True,"","")

    lane = buf[2] - ord('0')

    if buf[13:14] == b'G':
        this_time = timestr2int(timer)
        lap_time = timeint2str(substract_time(this_time,lasttime[lane]))
        lapcount[lane] += 1
        lasttime[lane]=this_time
        return TimeRecord(timer, lane, True, False,lap_time,"G")

    if buf[13:14] == b'L':
        this_time = timestr2int(timer)
        lap_time = timeint2str(substract_time(this_time,lasttime[lane]))
        lapcount[lane] += 1
        lasttime[lane]=this_time
        distance = str(lapunit * lapcount[lane]) + "m"



        return TimeRecord(timer, lane, False, False,lap_time,distance)

    return None



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
    push_lane_order()

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
reset=True;

async def broadcaster():

    global reset
    while True:

        rec = await asyncio.to_thread(queue.get)
        inttime = timestr2int(rec.str_time)
        if inttime==0:
            if reset:
                show_next_race()
                resettime()
                reset=False
        else:
            reset=True


        payload = json.dumps({
            "str_time": rec.str_time,
            "lane_no": rec.lane_no,
            "goal": rec.goal,
            "is_running_timer": rec.is_running_timer,
            "lap_time": rec.lap_time,
            "distance": rec.distance,
        })

        await broadcast(payload)


@app.on_event("startup")
async def startup():
    global loop
    loop = asyncio.get_running_loop()

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
    data = show_lane_order()
    return data
@app.post("/command")
async def command(data: dict):
    cmd = data["cmd"]
    if cmd == "n":
        show_next_race()
    elif cmd == "p":
        show_prev_race()
    elif cmd == "r":
        show_lane_order()
    return {"ok": True}

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

<div id="timer">0.00</div>

<h2 id="header"> 　</h2>
<table width="100%" id="t"></table>


<script>

const table=document.getElementById("t")

for(let i=0;i<10;i++){

  const tr=document.createElement("tr")

  tr.innerHTML=
  `<td width="5%">${i}</td>
  <td width="23%" id="name${i}">name</td>
  <td width="28%" id="team${i}">team</td>
  <td width="15%" align="right" id="lap${i}" >lap </td>
  <td width="16%" align="right" id="time${i}">time</td>
  <td width="13%" align="right" id="note${i}">dist</td>
  `

table.appendChild(tr)
}
function clearLaneOrder() {
    for (let i=0;i<10;i++) {
        document.getElementById("name"+i).textContent = "";
        document.getElementById("team"+i).textContent = "";
        document.getElementById("lap"+i).textContent = "";
        document.getElementById("time"+i).textContent = "";
        document.getElementById("note"+i).textContent = "";
    }
}
async function loadLaneOrder(){

    const res = await fetch("/lane_order");
    const lanes = await res.json();


    lanes.forEach(lane => {

        document.getElementById("header").textContent = lane.header;
        document.getElementById("name"+lane.lane).textContent = lane.name;

        document.getElementById("team"+lane.lane).textContent = lane.team;

    });
}
clearLaneOrder();
loadLaneOrder();


const ws=new WebSocket("ws://"+location.host+"/ws")

ws.onmessage=(ev)=>{

    const data=JSON.parse(ev.data)

    if(data.type=="lane_order"){

        clearLaneOrder()

        data.lanes.forEach(lane=>{
            document.getElementById("header").textContent = lane.header
            document.getElementById("name"+lane.lane).textContent = lane.name
            document.getElementById("team"+lane.lane).textContent = lane.team
            document.getElementById("time"+lane.lane).textContent = lane.time
            document.getElementById("note"+lane.lane).textContent = lane.time
        })

        return
    }

    if(data.is_running_timer){
        document.getElementById("timer").textContent=data.str_time
    }else{
        document.getElementById("time"+data.lane_no).textContent=data.str_time
        document.getElementById("lap"+data.lane_no).textContent=data.lap_time
        document.getElementById("note"+data.lane_no).textContent=data.distance
    }
}

</script>

</body>
</html>
"""

@app.get("/control", response_class=HTMLResponse)
def control():

    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body{
background:black;
color:white;
font-size:30px;
font-family:monospace;
text-align:center;
}
input{
font-size:30px;
width:200px;
text-align:center;
}
</style>
</head>
<body>

<h1>Race Control</h1>

<input id="cmd" autofocus placeholder="n / p / r" >

<script>
document.getElementById("cmd").addEventListener("keydown", async (e)=>{

    if(e.key==="Enter"){

        const cmd=e.target.value

        await fetch("/command",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({cmd:cmd})
        })

        e.target.value=""
    }
})


</script>

</body>
</html>
"""
#document.addEventListener("keydown", async (e)=>{
#
#    if(e.key==="n" || e.key==="p" || e.key==="r"){
#
#        await fetch("/command",{
#            method:"POST",
#            headers:{"Content-Type":"application/json"},
#            body:JSON.stringify({cmd:e.key})
#        })
#    }
#})

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


def push_lane_order():

    lanes = show_lane_order()

    payload = json.dumps({
        "type": "lane_order",
        "lanes": lanes
    })

    if connections:
        asyncio.run_coroutine_threadsafe(
            broadcast(payload),
            loop
        )
def show_prev_race():
    if get_prev_race():
        push_lane_order()
    else:
        print("最初のレースです。")



def show_next_race():
    if get_next_race():
        push_lane_order()
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
        lane = row.lane
        mark = row.mark
        if row.strokecode < 6:
            team = row.team or ""
            name = row.swimmer1 or ""
        else:
            if row.swimmer1:
                team = "1: " + str(row.swimmer1)
            else:
                team = ""
            name = row.team or ""
        if mark:
            goal=mark
        else:
            goal=row.goal

        lanes.append({
            "lane": lane,
            "name": name,
            "team": team,
            "header" : str(prgNo) + "  " + "   " +\
                    row.gender + row.className + row.distance + row.stroke + \
                    " " + row.phase +" "+ str(kumi) + "組",
            "time": goal
        })
            
    
    return lanes





# ===== main =====

def main():

    global serial_port
    global eventNo
    global prgNo
    global kumi
    global connectionStr
    server = input("Server Name: ")
    if server == "":
        server = "olivia.local"

    password = input("password: ")
    if password == "":
        if server == "olivia.local":
            password = "StrongPassword123!"
        if server == "madoka.local":
            password = "StrongPassword123!"

    connectionStr =  ("DRIVER=FreeTDS;" 
         f"SERVER={server};" 
          "PORT=1433;"
          "UID=sw;" 
          "DATABASE=sw;" 
         f"PWD={password};" 
          "TDS_Version=7.4;")



    eventNo = get_event_no(server,password)
    prgNo=1
    kumi=1
    

           
    # screen clear
    print("\033[2J\033[H", end="")
    serial_port = serial.Serial(
        port="/dev/ttyUSB0",
        baudrate=9600,
        parity=serial.PARITY_EVEN,
        bytesize=7,
        timeout=None
    )

    t = threading.Thread(target=serial_thread, daemon=True)
    t.start()
    set_lapunit()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5192)

if __name__ == "__main__":
    main()
