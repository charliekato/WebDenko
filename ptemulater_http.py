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

while True:
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=9600,
            parity=serial.PARITY_EVEN,
            bytesize=serial.SEVENBITS,
            timeout=None
        )
        print(f"Serial port opened: {port_name}")
        break
    except serial.SerialException as e:
        print(f"Serial port not available: {port_name}")
        print("Waiting for USB serial device.")
        time.sleep(5)

# ===== タイマー状態 =====
running = False
elapsed_base = 0.0
start_time = time.time()
reset_pending = False
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
    global running, elapsed_base, start_time, reset_pending
    with lock:
        elapsed_base = 0.0
        start_time = time.time()
        running = False
        reset_pending = True
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

def send_lap(lane,mytime,order):
    ser.write(bytearray(f"\x02A{order}{lane}{order} ","ascii")+mytime+bytearray("L\x03","ascii"))

def send_goal(lane,mytime,order):
    ser.write(bytearray(f"\x02A{order}{lane}{order} ","ascii")+mytime+bytearray("G\x03","ascii"))

def send_reset():
    ser.write(bytearray("\x02AR       0.00 \x03","ascii"))

def send_exchange(lane):
    ser.write(bytearray(f"\x02A0{lane}02 0-0.00 K\x03","ascii"))


def send_running_timer(time):
    ser.write(bytearray(f"\x02AR   ","ascii") + time + bytearray("  \x03","ascii"))

def send_reaction(lane):
    ser.write(bytearray(f"\x02A{lane}  S0S0.59 J\x03","ascii"))


oldtenth = 99
def parse_time(elapsed) -> bytearray(8):
    global oldtenth
    mytime= bytearray(8)
    total_minutes = int(elapsed // 60) % 100
    ten_minutes = total_minutes // 10
    if ten_minutes==0 :
        mytime[0] = ord(' ')
    else:
        mytime[0] = ord('0') + ten_minutes
    if total_minutes==0 :
        mytime[1] = ord(' ')
        mytime[2] = ord(' ')
    else :
        mytime[1] = ord('0') + total_minutes % 10
        mytime[2] = ord(':')

    tseconds = int(elapsed % 60)       # 秒
    ten_seconds = tseconds //10
    if (total_minutes==0) and (ten_seconds==0) :
        mytime[3] = ord(' ')
    else:
        mytime[3] = ord('0') + ten_seconds

    seconds = tseconds % 10
    mytime[4] = ord('0') + seconds
    mytime[5] = ord('.')
    tenth = int((elapsed * 10) % 10)  # 1/10 秒
    mytime[6] = ord('0') + tenth
    hundred = int((elapsed * 100) % 10)
    mytime[7] = ord('0') + hundred
    if oldtenth!= tenth:
        oldtenth=tenth
        send_running_timer(mytime[:7])
    return mytime

# ===== シリアル送信ループ =====
def serial_loop():
    global running, elapsed_base, reset_pending
    exchange_counter = [0]*10

    mytime=bytearray(8)
    while True:
        with lock:
            if running:
                elapsed = elapsed_base + (time.time() - start_time)
            else:
                elapsed = elapsed_base
        mytime = parse_time(elapsed)
        if reset_pending:
            with lock:
                reset_pending = False
            send_reset()
        while not event_queue.empty():
            digit = event_queue.get()
            if digit>9:
                digit-=10
                send_goal(digit,mytime,"1")
            else:
                exchange_counter[digit]=50
                send_lap(digit,mytime,"1")
        for i in range(10):
            if exchange_counter[i] == 1:
                send_exchange(i) #引継ぎ
            if exchange_counter[i]>0:
                exchange_counter[i] -= 1

        time.sleep(0.01)

# ===== メイン =====
if __name__ == "__main__":
    t = threading.Thread(target=serial_loop, daemon=True)
    t.start()

    #app = FastAPI(root_path="/flash")
    # 0.0.0.0 にバインド → LAN内の他PC/スマホからアクセス可能
    uvicorn.run(app, host="0.0.0.0", port=8000)

