import socket
import threading

class DynamicProxy:

    def __init__(self, listen_port, forward_port):

        self.listen_host = '0.0.0.0'
        self.listen_port = listen_port
        self.forward_host = '0.0.0.0'
        self.forward_port = forward_port
        self.lock = threading.Lock()
        self.server_socket = None
        self.server_thread = None
        self.running = True

    def start(self):

        self.server_thread = threading.Thread(target=self.start_server)
        self.server_thread.start()

    def start_server(self):

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.listen_host, self.listen_port))
        self.server_socket.listen(5)

        print(f"[*] Listening on {self.listen_host}:{self.listen_port}")

        while self.running:

            try:
                client_socket, addr = self.server_socket.accept()
                print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
                client_handler = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_handler.start()

            except socket.error as e:
                print(f"[-] Socket error: {e}")
                break

    def handle_client(self, client_socket):

        remote_socket = None

        try:

            with self.lock:
                current_forward_host = self.forward_host
                current_forward_port = self.forward_port

            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.connect((current_forward_host, current_forward_port))

            send_thread = threading.Thread(target=self.forward, args=(client_socket, remote_socket))
            receive_thread = threading.Thread(target=self.forward, args=(remote_socket, client_socket))

            send_thread.start()
            receive_thread.start()

            send_thread.join()
            receive_thread.join()

        except Exception as e:
            print(f"[-] Connection error: {e}")

        finally:
            if client_socket: client_socket.close()
            if remote_socket: remote_socket.close()

    def forward(self, source, destination):

        try:
            while True:
                data = source.recv(4096)
                if len(data) == 0: break
                destination.sendall(data)

        except socket.error as e:
            print(f"[-] Socket error during forwarding: {e}")

        finally:
            source.close()
            destination.close()

    def update_forwarding(self, new_port):

        with self.lock: self.forward_port = new_port
        print(f"[+] Forwarding updated to {self.forward_host}:{new_port}")

    def stop(self):
        if self.server_socket: self.server_socket.close()
        if self.server_thread: self.server_thread.join()

"""
import threading
import select
import socket
import time

class Proxy:

    def __init__(self, host_port, connect_port):
        
        self.host_port = host_port
        self.connect_port = connect_port
        self.start()

    def start(self):

        self.external = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.external.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.stop_flag = False

        def handle_connection(conn, addr):

            print(" + HANDLE CONNECTION")
            internal = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            internal.connect(('127.0.0.1', self.connect_port))

            while not self.stop_flag:

                r, w, err = select.select((conn, internal), (), (), 0.1)
                if not r: continue

                close_flag = False
                for readable in r:

                    data = readable.recv(4096)

                    if not data: 
                        close_flag = True
                        break

                    if readable == conn: internal.send(data)
                    elif readable == internal: conn.send(data)

                if close_flag: break

            conn.close()
            internal.close()
            print(" - HANDLE CONNECTION")

        def accept_connections():

            print(" + ACCEPT CONNECTIONS")
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
            print(" - ACCEPT CONNECTIONS")

        thread = threading.Thread(target=accept_connections, args=())
        thread.start()

    def swap(self, new_port):
        
        # Stop all threads.
        self.connect_port = new_port
        self.stop_flag = True
        time.sleep(0.2)
        
        # Close the external connection port.
        self.external.close()
        time.sleep(0.1)
        
        # Reset the proxy.
        self.start()

    def __del__(self):
        self.stop_flag = True

    def stop(self):
        self.stop_flag = True
"""