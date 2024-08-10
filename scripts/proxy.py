import threading
import select
import socket
import time

class DynamicProxy:

    def __init__(self, host_port, connect_port):
        
        self.host_port = host_port
        self.connect_port = connect_port
        self.start()

    def start(self):

        self.external = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.external.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stop_flag = False

        def handle_connection(conn, addr):

            internal = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            internal.connect(('127.0.0.1', self.connect_port))

            while not self.stop_flag:

                r, w, err = select.select((conn, internal), (), (), 0.1)
                if not r: continue

                for readable in r:

                    data = readable.recv(4096)

                    if not data: 
                        internal.close()
                        conn.close()
                        return

                    if readable == conn: internal.send(data)
                    elif readable == internal: conn.send(data)

        def accept_connections():

            self.external.bind(('127.0.0.1', self.host_port))
            self.external.listen(1)

            while not self.stop_flag:

                r, w, err = select.select((self.external,), (), (), 0.1)
                if not r: continue

                for readable in r:
                    if self.stop_flag: return
                    conn, addr = self.external.accept()
                    conn_thread = threading.Thread(target=handle_connection, args=(conn, addr))
                    conn_thread.start()

            self.external.close()

        thread = threading.Thread(target=accept_connections, args=())
        thread.start()

    def swap(self, new_port):
        
        # Stop all threads.
        self.connect_port = new_port
        self.stop_flag = True
        time.sleep(0.15)
        
        # Close the external connection port.
        self.external.close()

        # Reset the proxy.
        self.start()

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True