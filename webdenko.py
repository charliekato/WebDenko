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
import xml.etree.ElementTree as ET

import aiohttp

from swlib.select_event import get_event_no

async def forward():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://192.168.100.180:5000/f5") as res:
                text = await res.text()
    except Exception as e:
        print("forward error:" , e)

async def backward():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://192.168.100.180:5000/f1") as res:
                text = await res.text()
    except Exception as e:
        print("forward error:" , e)



def reset_time():
    global lasttime
    global lapcount
    global finish
    global place
    place = [0]*60
    lasttime = [0]*10
    lapcount = [0]*10
    finish = [1]*10




def timestr2int(mytime) -> int :
    try:
        return int(mytime.replace(":", "").replace(".", ""))
    except ValueError:
        return 0


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
    place: int

@dataclass(slots=True)
class LaneInfo:
    event_name:str
    zero_use: int
    lap_unit: int
    start_lane: int
    end_lane: int

def get_lap_unit(touchBoard) -> int :
    if touchBoard == 3:
        return 25
    if touchBoard == 2:
        return 100
    # touchBoard = 1,4
    return 50


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
    lap_unit = get_lap_unit(row.touchBoard)
    return LaneInfo(event_name,zero_use, lap_unit, start_lane, end_lane)


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

place = [0]*60
last_sent='99:99.9'
def parse_packet(buf):
    global last_sent
    global place
    timer = format_running_time(buf[5:13].decode("ascii"))

    if buf[0:2] == b'AR':
        timer = timer[:-1]
        if last_sent != timer:
            last_sent = timer
            return TimeRecord(timer, 0, False, True,"","",0)
        else:
            return None



    if not (ord('0') <= buf[2] <= ord('9')):
        return None
    lane = buf[2] - ord('0')

    if buf[13:14] == b'G':
        this_time = timestr2int(timer)
        lap_time = timeint2str(substract_time(this_time,lasttime[lane]))
        lapcount[lane] += 1
        lasttime[lane]=this_time
        place[lapcount[lane]] +=1
        myplace = place[lapcount[lane]]

        return TimeRecord(timer, lane, True, False,lap_time,"Goal",myplace)

    if buf[13:14] == b'L':
        this_time = timestr2int(timer)
        lap_time = timeint2str(substract_time(this_time,lasttime[lane]))
        lapcount[lane] += 1
        lasttime[lane]=this_time
        intdistance = lane_info.lap_unit * lapcount[lane]
        if intdistance < race_distance:
            distance = str(lane_info.lap_unit * lapcount[lane]) + "m"
            place[lapcount[lane]] += 1
            myplace = place[lapcount[lane]]
            return TimeRecord(timer, lane, False, False,lap_time,distance,myplace)

    return None



#queue = asyncio.Queue()
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


# ===== broadcaster =====
reset=True

async def broadcaster():

    global reset
    while True:

        rec = await asyncio.to_thread(queue.get)
        strdistance = rec.distance
        if relay_flag:
            if strdistance != "":
                if strdistance[-1]=="m":
                    intdistance = int(strdistance[:-1])
                    swimmer_index = int(intdistance*4/race_distance)
                    lane_no = rec.lane_no + lane_info.zero_use
                    if swimmers[lane_no] and swimmer_index < len(swimmers[lane_no]):
                        name = swimmers[lane_no][swimmer_index]
                    else:
                        name = ""
                    payload = json.dumps({"type": "sc",
                          "lane_no": rec.lane_no,
                          "swimmer": str(swimmer_index+1)+ " : " + name})
                    await broadcast(payload)
        inttime = timestr2int(rec.str_time)
        if inttime==0:
            if reset:
                reset_time()
                reset=False
        else:
            reset=True

        if rec.is_running_timer:
            payload = json.dumps({"type": "rt",
              "time": rec.str_time})
            await broadcast(payload)
        else:
            payload = json.dumps({"type": "lt",
                  "lane_no":rec.lane_no,
                  "time": rec.str_time,
                  "lap_time": rec.lap_time,
                  "distance": strdistance ,
                  "place": rec.place})
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

    buf = bytearray(19)
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
#timer{{
position:fixed;
top:20px;
right:30px;
color:yellow;
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

<div id="timer">0.00</div>

<h2 id="header"> 　</h2>
<table width="100%" id="t"></table>


<script>
const STARTLANE={lane_info.start_lane};
const ENDLANE={lane_info.end_lane};
const table=document.getElementById("t")
const clearTimers = {{}}
 
for(let i = STARTLANE; i < ENDLANE+1; i++) {{

  const tr=document.createElement("tr")

  tr.innerHTML=
  `<td width="5%">${{i}}</td>
  <td width="20%" id="name${{i}}"></td>
  <td width="29%" id="team${{i}}"></td>
  <td width="11%" align="right" id="lap${{i}}" ></td>
  <td width="14%" align="right" id="time${{i}}"></td>
  <td width="10%" align="right" id="note${{i}}"></td>
  <td width="7%" align="right" id="place${{i}}"></td>
  <td width="4%" id="padding${{i}}"></td>

  `

    table.appendChild(tr)
}}
function clearLaneTime() {{
    for (let i=STARTLANE;i<ENDLANE+1;i++) {{
        document.getElementById("lap"+i).textContent = "";
        document.getElementById("time"+i).textContent = "";
        document.getElementById("note"+i).textContent = "";
        document.getElementById("place"+i).textContent = "";
    }}
}}

function clearLaneOrder() {{
    for (let i=STARTLANE;i<ENDLANE+1;i++) {{
        document.getElementById("name"+i).textContent = "";
        document.getElementById("team"+i).textContent = "";
    }}
}}

const ws=new WebSocket("ws://"+location.host+"/ws")

ws.onmessage=(ev)=>{{

    const data=JSON.parse(ev.data)

    if(data.type=="lo"){{

        clearLaneOrder()
        if (data.flash) {{
            clearLaneTime()
        }}

        document.getElementById("header").textContent = data.header
        data.lanes.forEach(lane=>{{
            document.getElementById("name"+lane.lane).textContent = lane.name
            document.getElementById("team"+lane.lane).textContent = lane.team
        }})

        return
    }}
    if(data.type=="sc"){{
        document.getElementById("team"+data.lane_no).textContent = data.swimmer
    }}

    if(data.type=="rt"){{
        document.getElementById("timer").textContent=data.time
    }}
    if(data.type=="lt"){{
        const lane = data.lane_no
        

        const ids = ["time", "lap", "note", "place"]

        // 表示更新 + フェードリセット
        ids.forEach(id=>{{
            const el = document.getElementById(id+lane)
            el.textContent = data[id === "note" ? "distance" : id === "time" ? "time" : id === "lap" ? "lap_time" : "place"]

            // 初期化
            el.style.transition = "none"
            el.style.opacity = "1"
            el.style.color = "red"  //まず赤

        }})
        // === 点滅処理 ===
        let blinkCount = 0
        const blinkMax = 8  // 4回点滅 (on/off で4回)

        const blinkInterval = setInterval(() => {{
            ids.forEach(id=> {{
                const el = document.getElementById(id+lane)
                el.style.opacity = (el.style.opacity === "0" ? "1" : "0")
            }})
            blinkCount++

            if (blinkCount >= blinkMax) {{
                clearInterval(blinkInterval)
                ids.forEach(id=>{{
                    const el = document.getElementById(id+lane)
                    el.style.opacity = "1"
                    el.style.color = "white"
                }})
            }}
        }}, 200) // 200->点滅速度　(200ms)
        

        // 既存タイマー削除
        if(clearTimers[lane]){{
            clearTimeout(clearTimers[lane])
        }}

        if(data.distance !== "Goal"){{

            // フェード開始（9秒後）
            setTimeout(()=>{{
                ids.forEach(id=>{{
                    const el = document.getElementById(id+lane)
                    el.style.transition = "opacity 1s"
                    el.style.opacity = "0"
                }})
            }}, 9000)

            // 完全クリア（10秒後）
            clearTimers[lane] = setTimeout(()=>{{
                ids.forEach(id=>{{
                    const el = document.getElementById(id+lane)
                    el.textContent = ""
                }})
            }}, 10000)
        }}
    }}
}}

</script>

</body>
</html>
"""

@app.get("/control/p")
async def show_prev():
    show_prev_race()
    ##-- send prev command to seiko swimv6
    await backward()

@app.get("/control/n")
async def show_next():
    show_next_race()
    ##-- send next command to seiko swimv6
    await forward()


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
        "type": "lo",
        "header": header ,
        "lanes": lanes,
        "flash": flash
    })

    if connections:
        asyncio.run_coroutine_threadsafe(
            broadcast(payload),
            loop
        )

def show_prev_race():
    if get_prev_race():
        reset_time()
        push_lane_order(True)
    else:
        print("最初のレースです。")



def show_next_race():
    if get_next_race():
        reset_time()
        push_lane_order(True)
    else:
        print("最終のレースです。")

race_distance=100
swimmers = [None]*11
relay_flag = False

def show_lane_order():
    global race_distance
    global relay_flag
    global swimmers
    swimmers = [None]*11
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
    first = True
    for row in rows:
        if first:
            relay_flag = row.strokecode >5
            distance = row.distance
            race_distance = int(distance[:-1])
            header =  str(prgNo) + "  "   +\
                    row.gender + row.className + distance + row.stroke + \
                    " " + row.phase +" "+ str(kumi) + "組"
            first=False
        swimmers[row.lane] = [
            row.swimmer1 or "",
            row.swimmer2 or "",
            row.swimmer3 or "",
            row.swimmer4 or "",
            ]

        lane = row.lane - lane_info.zero_use
        if lane>9 :
            continue
        if row.strokecode < 6:
            team = row.team or ""
            name = row.swimmer1 or ""
        else:
            name = row.team or ""
            team = "1 : " + (row.swimmer1 or "")
            
        if row.mark:
            goal=row.mark
        else:
            goal=row.goal

        lanes.append({
            "lane": lane,
            "name": name,
            "team": team,
            "time": goal
        })
            
    
    return header, lanes


# ===== main =====

prgNo = 1
kumi = 1
reset_time()

tree = ET.parse("webdenko.config")
root = tree.getroot()
server = root.find("Server").text
password = root.find("Password").text

eventNo = get_event_no(server,password)
print("\033[2J\033[H", end="")
serial_port = serial.Serial(
    port="/dev/ttyUSB0",
    baudrate=9600,
    parity=serial.PARITY_EVEN,
    bytesize=7,
    timeout=None
)


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
    t = threading.Thread(target=serial_thread, daemon=True)
    t.start()
    lane_info=get_lane_info(eventNo)
    show_lane_order()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5192)

if __name__ == "__main__":
    main()
