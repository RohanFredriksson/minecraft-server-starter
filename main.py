import os
import time
import signal
import shutil

proxy_executable = shutil.which('redir')
proxy_pid = -1

def switch(state):

    # Kill any active proxies
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

    if proxy_executable == None: 
        print('redir is required')
        return


if __name__ == '__main__':
    main()