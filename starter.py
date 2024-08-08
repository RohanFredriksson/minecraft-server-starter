import re
import json
import time
import select
import socket
import threading
import subprocess

# Variable Int Masks
SEGMENT_BITS = 0x7F
CONTINUE_BIT = 0x80

# Minecraft Protocol States
HANDSHAKING = 0
STATUS = 1
LOGIN = 2
class PacketReader:

    def __init__(self, stream: bytes):
        self.stream = stream
        self.size = self.read_varint()
        self.id = self.read_varint()

    def read_byte(self) -> bytes:
        return self.read_bytes(1)
    
    def read_bytes(self, size: int) -> bytes:
        result = self.stream[:size]
        self.stream = self.stream[size:]
        return result
    
    def read_string(self) -> str:
        size = self.read_varint()
        return self.read_bytes(size).decode("utf-8")

    def read_varint(self) -> int:

        value = 0
        position = 0
        
        while True:
            current = int.from_bytes(self.read_byte(), byteorder='big')
            value |= (current & SEGMENT_BITS) << position
            if (current & CONTINUE_BIT) == 0: break
            position += 7
            if position >= 32: raise Exception("VarInt is too big")

        return value
    
    def read_unsigned_short(self) -> int:
        return int.from_bytes(self.read_bytes(2), byteorder='big', signed=False)
    
    def read_long(self) -> int:
        return int.from_bytes(self.read_bytes(8), byteorder='big', signed=True)

class PacketWriter:

    def __init__(self):
        self.stream = bytearray()

    def write_byte(self, value: int):
        self.stream.append(value)

    def write_bytes(self, stream: bytes):
        self.stream = self.stream + stream

    def write_string(self, string: str):
        self.write_varint(len(string))
        self.stream = self.stream + string.encode()

    def write_long(self, value: int):
        self.write_bytes(value.to_bytes(8, byteorder='big', signed=True))

    def write_varint(self, value: int):
        
        while True:
            
            if (value & ~SEGMENT_BITS) == 0:
                self.write_byte(value)
                return
            
            self.write_byte((value & SEGMENT_BITS) | CONTINUE_BIT)
            value = (value >> 7) & 4294967295 # Unsigned right shift operator

    def encode(self, packet_id) -> bytes:

        def size_varint(value: int):
            count = 0
            while True:
                count += 1
                if (value & ~SEGMENT_BITS) == 0: return count
                value = (value >> 7) & 4294967295 # Unsigned right shift operator

        header = PacketWriter()
        header.write_varint(size_varint(packet_id) + len(self.stream))
        header.write_varint(packet_id)

        self.stream = header.stream + self.stream
        return bytes(self.stream)

class MinecraftServer:

    def __init__(self, command):
        
        self.command = command
        self.callbacks = {'start': [], 'ready': [], 'exit': []}
        self.process = None

    def __del__(self):
        if self.process != None: self.process.terminate()

    def start(self):

        if self.process != None: raise Exception("Minecraft server has already started.")

        def routine():

            self.process = subprocess.Popen(["java", "-Xms1G", "-Xmx1G", "-jar", "server.jar", "nogui"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._run_event('start')

            def waiter(p):
                p.wait()
                self._run_event('exit')
                if p == self.process: self.process = None

            thread = threading.Thread(target=waiter, args=(self.process,))
            thread.start()

            while self.process != None:
                
                line = self.process.stdout.readline()
                if not line: break
                print(line, end="")

                pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread/INFO\]: Done.*")
                result = pattern.match(line)
                if result: self._run_event('ready')

        thread = threading.Thread(target=routine, args=())
        thread.start()

    def stop(self):
        if self.process == None: return
        self.process.stdin.write('stop\n')
        self.process.stdin.flush()

    def enter_command(self, command):
        if self.process == None: return
        self.process.stdin.write(command)
        self.process.stdin.flush()

    def _run_event(self, event):
        if event not in self.callbacks: return
        for callback in self.callbacks[event]: callback()

    def on(self, event, callback):
        if event not in self.callbacks: return
        self.callbacks[event].append(callback)

class Proxy:

    def __init__(self, host_port, connect_port):
        
        self.host_port = host_port
        self.connect_port = connect_port
        self.external = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stop_flag = False

        def handle(conn, addr):

            internal = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            internal.connect(('127.0.0.1', self.connect_port))

            while not self.stop_flag:

                r, w, err = select.select((conn, internal), (), (), 0.1)
                if not r: continue

                for readable in r:
                    data = readable.recv(4096)
                    if not data: break
                    if readable == conn: internal.send(data)
                    elif readable == internal: conn.send(data)

            conn.close()
            internal.close()

        def start():

            self.external.bind(('127.0.0.1', self.host_port))
            self.external.listen()

            while not self.stop_flag:

                r, w, err = select.select((self.external,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    conn, addr = self.external.accept()
                    conn_thread = threading.Thread(target=handle, args=(conn, addr))
                    conn_thread.start()

        thread = threading.Thread(target=start, args=())
        thread.start()

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True

class ServerStarter:

    def __init__(self, host_port):
        
        self.host_port = host_port
        self.callbacks = {'handshake': [], 'ping': [], 'pong': [], 'login': []}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stop_flag = False

        def handle(conn, addr):

            protocol_state = HANDSHAKING

            while not self.stop_flag:

                r, w, err = select.select((conn,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    
                    data = readable.recv(4096)
                    if not data: 
                        conn.close()
                        return

                    packet = PacketReader(data)
                
                    if protocol_state == HANDSHAKING and packet.id == 0:

                        protocol_number = packet.read_varint()
                        server_address = packet.read_string()
                        server_port = packet.read_unsigned_short()
                        next_state = packet.read_varint()

                        protocol_state = next_state
                        
                    elif protocol_state == STATUS and packet.id == 0: self._run_event('ping',  conn, addr, packet)
                    elif protocol_state == STATUS and packet.id == 1: self._run_event('pong',  conn, addr, packet)
                    elif protocol_state == LOGIN  and packet.id == 0: self._run_event('login', conn, addr, packet)

        def start():

            self.socket.bind(('127.0.0.1', self.host_port))
            self.socket.listen()

            while not self.stop_flag:

                r, w, err = select.select((self.socket,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    conn, addr = self.socket.accept()
                    conn_thread = threading.Thread(target=handle, args=(conn, addr))
                    conn_thread.start()

        thread = threading.Thread(target=start, args=())
        thread.start()

    def _run_event(self, event, *args):
        if event not in self.callbacks: return
        for callback in self.callbacks[event]: callback(args)

    def on(self, event, callback):
        if event not in self.callbacks: return
        self.callbacks[event].append(callback)

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True

minecraft_server = MinecraftServer('java -Xms1G -Xmx1G -jar server.jar nogui')
server_starter = ServerStarter(25566)
proxy = Proxy(25565, 25566)

def on_ping(args):
    
    conn, addr, packet = args
    
    status_string = json.dumps({
        "version": {
            "name": "1.20.1",
            "protocol": 767
        },
        "players": {
            "max": 100,
            "online": 0,
            "sample": []
        },
        "description": {
            "text": "Hello, world!"
        },
        "enforcesSecureChat": False
    })
    
    response = PacketWriter()
    response.write_string(status_string)
    data = response.encode(0)
    conn.send(data)

def on_pong(args):

    conn, addr, packet = args

    response = PacketWriter()
    response.write_long(packet.read_long())
    data = response.encode(1)
    conn.send(data)

def on_login(args):

    conn, addr, packet = args

    reason_string = json.dumps({
        "text": "Server is waking up. Please wait a few seconds."
    })

    response = PacketWriter()
    response.write_string(reason_string)
    data = response.encode(0)
    conn.send(data)

    #minecraft_server.stop()

server_starter.on('ping', on_ping)
server_starter.on('pong', on_pong)
server_starter.on('login', on_login)

def on_start():
    print("START")

def on_ready():
    print("READY")

def on_exit():
    print("EXIT")

minecraft_server.on('start', on_start)
minecraft_server.on('ready', on_ready)
minecraft_server.on('exit', on_exit)
minecraft_server.start()

while True:
    try: time.sleep(0.1)
    except KeyboardInterrupt:
        minecraft_server.stop()
        server_starter.stop()
        proxy.stop()
        break
