import select
import socket
import threading

class Proxy:

    def __init__(self):
        
        self.stop_flag = False
        self.external = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        def handle(conn, addr):

            internal = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            internal.connect(('127.0.0.1', 25567))

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

            self.external.bind(('127.0.0.1', 25565))
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

import time

proxy = Proxy()
while True:
    print("HELLO")
    try: time.sleep(1)
    except KeyboardInterrupt: 
        proxy.stop()
        break