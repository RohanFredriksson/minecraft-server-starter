import os
import time
import shutil
import signal
import socket

starter_executable = shutil.which('node')
proxy_executable = shutil.which('redir')
starter_pid = -1
proxy_pid = -1
close = False

def switch(state):

    # Kill any active proxies
    global proxy_pid
    if proxy_pid > 0: os.kill(proxy_pid, signal.SIGKILL)

    # Determine the ports the proxy needs to connect to.
    proxy_arguments = None
    if state == 'inactive': proxy_arguments = [proxy_executable] + ['--lport=25565', '--cport=25566']
    elif state == 'active': proxy_arguments = [proxy_executable] + ['--lport=25565', '--cport=25567']
    else: return

    # Start the proxy on a child process.
    proxy_pid = os.fork()
    if proxy_pid == 0: os.execv(proxy_executable, proxy_arguments)

def main():

    # Check if required executables exist
    if (starter_executable == None): 
        print("node is required to run the starter.")
        return
    if (proxy_executable == None): 
        print("redir is required to run the proxy.")
        return

    # Start up a TCP server for IPC.
    ipc_port = 25568
    ipc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ipc.bind(('127.0.0.1', ipc_port))

    # Start up the proxy.
    switch('inactive')

    # Start up the node process.
    starter_pid = os.fork()
    if starter_pid == 0: os.execv(starter_executable, [starter_executable, 'starter.js', str(ipc_port)])

    # Wait for the process to connect to the TCP server.
    ipc.listen(1)
    connection, address = ipc.accept()

    # Listen for messages from the node process.
    while not close:
        data = connection.recv(1024)
        print('Received:', data.decode())
        #break

    # Close the connection
    connection.close()
    ipc.close()

    # Kill all child processes
    os.kill(starter_pid, signal.SIGKILL)
    os.kill(proxy_pid, signal.SIGKILL)

if __name__ == '__main__':
    main()