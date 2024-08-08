import json
import time
import select
import socket
import threading

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
        self.events = {'handshake': [], 'ping': [], 'pong': [], 'login': []}
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
                        
                        self._run_event('handshake', conn, addr, packet.size, packet.id, protocol_number, server_address, server_port, next_state)

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
        if event not in self.events: return
        for function in self.events[event]: function(args)

    def on(self, event, function):
        if event not in self.events: return
        self.events[event].append(function)

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True

server_starter = ServerStarter(25566)
proxy = Proxy(25565, 25566)

def on_handshake(args):

    conn, addr, packet_size, packet_id, protocol_number, server_address, server_port, next_state = args
    print("HANDSHAKE")

def on_ping(args):
    
    conn, addr, packet = args
    print("PING")
    
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
    print("PONG")

    response = PacketWriter()
    response.write_long(packet.read_long())
    data = response.encode(1)
    conn.send(data)

def on_login(args):

    conn, addr, packet = args
    print("LOGIN")

    reason_string = json.dumps({
        "text": "Server is waking up. Please wait a few seconds."
    })

    response = PacketWriter()
    response.write_string(reason_string)
    data = response.encode(0)
    conn.send(data)

server_starter.on('handshake', on_handshake)
server_starter.on('ping', on_ping)
server_starter.on('pong', on_pong)
server_starter.on('login', on_login)

while True:
    try: time.sleep(0.1)
    except KeyboardInterrupt:
        server_starter.stop()
        proxy.stop()
        break
