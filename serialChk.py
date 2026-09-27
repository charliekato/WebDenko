import serial

serial_port = serial.Serial(
    port="COM5",  
    baudrate=9600,
    parity=serial.PARITY_EVEN,
    bytesize=7,
    timeout=None
)


#serial_port = None
while True:
    data = serial_port.read(16)
    print(data) 

