import threading
import select
import socket

from .packet import PacketReader

HANDSHAKING = 0
STATUS = 1
LOGIN = 2

class ProtocolServer:

    def __init__(self, host_port):
        
        self.host_port = host_port
        self.callbacks = {'handshake': [], 'ping': [], 'pong': [], 'login': []}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stop_flag = False

        def handle(conn, addr):

            protocol_state = HANDSHAKING

            while not self.stop_flag:
                
                try: 

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

                except: break

            try: conn.close()
            except: pass

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