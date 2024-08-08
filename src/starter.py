import select
import socket
import threading

class Starter:

    def __init__(self):
        
        self.stop_flag = False
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        def handle(conn, addr):

            while not self.stop_flag:

                r, w, err = select.select((conn,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    data = readable.recv(4096)
                    if not data: break

            conn.close()

        def start():

            self.socket.bind(('127.0.0.1', 25566))
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

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True