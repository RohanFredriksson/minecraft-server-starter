import threading
import select
import socket

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