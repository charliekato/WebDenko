#!/usr/bin/env python3
import sys
import time
import serial
import threading
from fastapi import FastAPI
import uvicorn
from queue import Queue

event_queue = Queue()

# ===== 引数チェック =====
if len(sys.argv) < 2:
    port_name = "/dev/ttyUSB0"
else :
    port_name = sys.argv[1]
print(f"Using Serial Port: {port_name}")

ser = serial.Serial(
    port=port_name,
    baudrate=9600,
    parity=serial.PARITY_EVEN,
    bytesize=serial.SEVENBITS,
    timeout=None
)

# ===== タイマー状態 =====
running = False
elapsed_base = 0.0
start_time = time.time()
lock = threading.Lock()

# ===== FastAPI =====
app = FastAPI()
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def control_panel():
    return """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PT Timer Control</title>
<style>
body {
    background-color: #111;
    color: white;
    text-align: center;
    font-family: Arial, sans-serif;
}
h1 {
    font-size: 3em;
}
button {
    width: 28%;
    padding: 15;
    margin: 8px;
    font-size: 1.5em;
    border-radius: 20px;
    border: none;
}
.start { background-color: green; }
.reset { background-color: orange; }
.status {
    font-size: 2em;
    margin-top: 20px;
}
.keypad {
    margin-top: 20px;
}
.keypad button {
    width: 7%;
}
</style>
<script>
async function send(cmd) {
    await fetch('/' + cmd);
    updateStatus();
}

async function updateStatus() {
    const res = await fetch('/status');
    const data = await res.json();
    document.getElementById("status").innerText =
        "Running: " + data.running +
        "  Time: " + data.elapsed_sec.toFixed(1) + " sec";
}

setInterval(updateStatus, 500);
</script>
</head>
<body onload="updateStatus()">
<h1>PT TIMER</h1>

<button class="start" onclick="send('start')">START</button>
<button class="reset" onclick="send('reset')">RESET</button>
<div class="keypad">
<button onclick="send('num/0')">0</button>
<button onclick="send('num/1')">1</button>
<button onclick="send('num/2')">2</button>
<button onclick="send('num/3')">3</button>
<button onclick="send('num/4')">4</button>
<button onclick="send('num/5')">5</button>
<button onclick="send('num/6')">6</button>
<button onclick="send('num/7')">7</button>
<button onclick="send('num/8')">8</button>
<button onclick="send('num/9')">9</button><br>
<button onclick="send('num/10')">G</button>
<button onclick="send('num/11')">G</button>
<button onclick="send('num/12')">G</button>
<button onclick="send('num/13')">G</button>
<button onclick="send('num/14')">G</button>
<button onclick="send('num/15')">G</button>
<button onclick="send('num/16')">G</button>
<button onclick="send('num/17')">G</button>
<button onclick="send('num/18')">G</button>
<button onclick="send('num/19')">G</button><br>
<button align="center" onclick="send('reaction')">REACTION</button><br>
</div>



<div id="status" class="status"></div>

</body>
</html>
"""


@app.get("/num/{digit}")
def receive_number(digit: int):
    if 0 <= digit <= 19:
        event_queue.put(digit)

    return {"received" :digit}
    
@app.get("/reaction")
def reaction():
    event_queue.put(30)
    return {"received" : 30}


@app.get("/start")
def start_timer():
    global running, start_time
    with lock:
        if not running:
            start_time = time.time()
            running = True
    return {"status": "started"}

@app.get("/reset")
def reset_timer():
    global running, elapsed_base, start_time
    with lock:
        elapsed_base = 0.0
        start_time = time.time()
        running = False
    return {"status": "reset", "time": "00:00.00"}

@app.get("/status")
def status():
    with lock:
        if running:
            elapsed = elapsed_base + (time.time() - start_time)
        else:
            elapsed = elapsed_base
    return {
        "running": running,
        "elapsed_sec": round(elapsed, 2)
    }

# ===== シリアル送信ループ =====
def serial_loop():
    global running, elapsed_base
    oldtenth = 0

    reactionlane=0
    while True:
        with lock:
            if running:
                elapsed = elapsed_base + (time.time() - start_time)
            else:
                elapsed = elapsed_base

        total_minutes = int(elapsed // 60) % 100
        seconds = int(elapsed % 60)
        tenth = int((elapsed * 10) % 10)
        hundred = int((elapsed * 100 ) % 10)
        if tenth != oldtenth:
            oldtenth=tenth
            frame = bytearray(16)

            frame[0]  = 0x02
            frame[1]  = ord('A')
            frame[2]  = ord('R')
            frame[3]  = 0x20
            frame[4]  = 0x20
            frame[5]  = 0x20
            ten_minutes = total_minutes // 10
            if (ten_minutes==0) :
                frame[6] = 0x20
            else :
                frame[6]  = ord('0') + ten_minutes
            minutes = total_minutes % 10
            if (total_minutes == 0) :
                frame[7] = 0x20
                frame[8] = 0x20
            else :
                frame[7]  = ord('0') + minutes
                frame[8]  = ord(':')
            ten_seconds = seconds // 10
            if ((ten_seconds == 0) and (total_minutes == 0)):
                frame[9] = 0x20
            else :
                frame[9]  = ord('0') + ten_seconds
            frame[10] = ord('0') + seconds % 10

            frame[11] = ord('.')
            frame[12] = ord('0') + tenth

            frame[13] = 0x20
            frame[14] = 0x20
            frame[15] = 0x03

            ser.write(frame)

        while not event_queue.empty():
            key_frame = bytearray(16)
            key_frame[0] = 0x02
            key_frame[15] = 0x03
            key_frame[1]  = ord('A')
            digit = event_queue.get()
            if digit==30:
                #.. reaction
                key_frame[14]=ord('J')
                key_frame[2]=0x20
                key_frame[3]=ord('0')+reactionlane
                reactionlane += 1
                if reactionlane>9:
                    reactionlane=0
                key_frame[4]= 0x20
                key_frame[5]= 0x20
                key_frame[6]= ord('S')
                key_frame[7]= ord('0')
                key_frame[8]= ord('S')
                key_frame[9]= ord('0')
                key_frame[10]= ord('.')
                key_frame[11]= ord('5')
                key_frame[12]= ord('9')  # reactiontime is always 0.59
                key_frame[13]= ord(' ') 
            else:
                if digit>9:
                    digit-=10
                    key_frame[14]=ord('G')
                else:
                    key_frame[14]=ord('L')
                key_frame[2]  = ord('1')
                key_frame[3]  = ord('0') + digit     # 押された番号
                key_frame[4]  = ord('1')             # 仮の着順
                key_frame[5]  = ord(' ')
                ten_minutes = total_minutes // 10
                if ( ten_minutes == 0 ) :
                    key_frame[6] = 0x20
                else :
                    key_frame[6]  = ord('0') + ten_minutes
                minutes = total_minutes % 10
                if ( total_minutes == 0 ) :
                    key_frame[7] = 0x20
                    key_frame[8] = 0x20
                else :
                    key_frame[7]  = ord('0') + minutes
                    key_frame[8]  = ord(':')
                ten_seconds = seconds // 10
                if ( ten_seconds == 0 ) and (total_minutes == 0) :
                    key_frame[9] = 0x20
                else :
                    key_frame[9]  = ord('0') + ten_seconds
                key_frame[10] = ord('0') + seconds % 10
                key_frame[11] = ord('.')
                key_frame[12] = ord('0') + tenth
                key_frame[13] = ord('0') + hundred
            ser.write(key_frame)
            print(key_frame)

        time.sleep(0.01)

# ===== メイン =====
if __name__ == "__main__":
    t = threading.Thread(target=serial_loop, daemon=True)
    t.start()

    #app = FastAPI(root_path="/flash")
    # 0.0.0.0 にバインド → LAN内の他PC/スマホからアクセス可能
    uvicorn.run(app, host="0.0.0.0", port=8000)

