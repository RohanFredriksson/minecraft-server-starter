import json
import time
import select
import socket
import threading

SEGMENT_BITS = 0x7F
CONTINUE_BIT = 0x80

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
    
    def read_string(self, size: int) -> str:
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
        return int.from_bytes(self.read_bytes(2), byteorder='big')
    
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
    
class ServerStarter:

    def __init__(self, host_port):
        
        self.host_port = host_port
        self.events = {'ping': [], 'login': []}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stop_flag = False

        def handle(conn, addr):

            while not self.stop_flag:

                r, w, err = select.select((conn,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    
                    data = readable.recv(4096)
                    if not data: 
                        conn.close()
                        return

                    packet = PacketReader(data)
                    if packet.size < 5: continue
                    if packet.id != 0: continue

                    protocol_number = packet.read_varint()
                    server_address_size = packet.read_varint()
                    server_address = packet.read_string(server_address_size)
                    server_port = packet.read_unsigned_short()
                    next_state = packet.read_varint()

                    if   next_state == 1: self._run_event('ping',  conn, addr, packet.size, packet.id, protocol_number, server_address, server_port)
                    elif next_state == 2: self._run_event('login', conn, addr, packet.size, packet.id, protocol_number, server_address, server_port)

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

server_starter = ServerStarter(25566)
proxy = Proxy(25565, 25566)

def on_ping(args):

    conn, addr, packet_size, packet_id, protocol_number, server_address, server_port = args
    
    status_string = json.dumps({
        "version": {
            "name": "1.19.4",
            "protocol": 762
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


def on_login(args):
    conn, addr, packet_size, packet_id, protocol_number, server_address, server_port = args
    
server_starter.on('ping', on_ping)
server_starter.on('login', on_login)

while True:
    try: time.sleep(0.1)
    except KeyboardInterrupt:
        server_starter.stop()
        proxy.stop()
        break