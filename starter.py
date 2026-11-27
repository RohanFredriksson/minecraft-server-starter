import threading
import json
import signal
import time

from scripts.minecraft_server import MinecraftServer
from scripts.protocol_server import ProtocolServer
from scripts.properties import Properties
from scripts.ping import ping

SLEEPING = 0
STARTING = 1
RUNNING = 2
STOPPED = 3

starter_properties = Properties('starter.properties')
server_properties = Properties('server.properties')

# The Minecraft server owns the public port while it runs, so the starter shares its address.
server_ip = server_properties.get('server-ip', '')
server_port = server_properties.get('server-port', 25565)
local_ip = server_ip if server_ip not in ('', '0.0.0.0', '::') else '127.0.0.1'

class Boot:

    def __init__(self):
        self.finished = threading.Event()
        self.ready = False

minecraft_server = MinecraftServer(starter_properties['command'])
state = SLEEPING
boot = None
lock = threading.Lock()

def status():

    # Depending on the state, we need to show different motds.
    description = starter_properties['waiting-motd']
    if state == STARTING: description = starter_properties['starting-motd']
    
    # Required response to client to show status to pinging clients.
    return json.dumps({
        "version": { "name": starter_properties["version"], "protocol": starter_properties["protocol"] },
        "players": { "max": 20, "online": 0, "sample": [] },
        "description": { "text": description },
        "enforcesSecureChat": False
    })

def on_login(player):

    global state, boot

    with lock:

        if state == STOPPED:
            player.close()
            return

        if state == SLEEPING:
            print('Server is starting...')
            print('-'*80)
            boot = Boot()
            state = STARTING

            try: minecraft_server.start()
            except OSError as error:
                print(f'Could not start the server: {error}')
                state = SLEEPING
                boot.finished.set()

        player_boot = boot

    # Keep the player on the loading screen until the server is ready, then pass them over.
    if not player.hold(player_boot.finished, starter_properties['hold-timeout']):
        player.disconnect(starter_properties['starting-reason'])
    elif not player_boot.ready:
        player.disconnect('The server failed to start.')
    else:
        player.hand_over(local_ip, server_port)

protocol_server = ProtocolServer(server_ip, server_port, status, on_login)

def on_binding():
    # Free the port at the last moment so the server can take it over.
    protocol_server.release()

def on_ready():

    global state
    with lock:
        state = RUNNING
        boot.ready = True
        boot.finished.set()

    # Inactivity timeout.
    def timeout():

        timeout_count = 0
        while state == RUNNING:

            # Ping the server once every minute.
            for i in range(600):
                if state != RUNNING: return
                time.sleep(0.1)
        
            # If there are players online reset the count, else increment.
            response = ping(local_ip, server_port)
            if not response['online']:
                print('Could not ping the server for its idle status; will retry.')
                continue
            if response['players']['online'] > 0: timeout_count = 0
            else: timeout_count += 1

            # If we have passed the timeout threshold, we shut it down.
            if timeout_count < starter_properties['timeout']: continue
            minecraft_server.stop()
            return
        
    thread = threading.Thread(target=timeout, args=())
    thread.start()

    # Update the version name and protocol number in starter properties
    response = ping(local_ip, server_port)
    if response["online"] == False: return

    starter_properties["protocol"] = response["version"]["protocol"]
    starter_properties["version"]  = response["version"]["name"]
    starter_properties.write()

def on_exit():

    global state
    with lock:
        if state == STOPPED: return
        state = SLEEPING
        boot.finished.set()

    print('-'*80)
    print('Server sleeping. Waiting for login attempt...')
    protocol_server.open()

minecraft_server.on('binding', on_binding)
minecraft_server.on('ready', on_ready)
minecraft_server.on('exit', on_exit)

protocol_server.open()
print('-'*80)
print('Server sleeping. Waiting for login attempt...')

def handle_shutdown_signal(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

def shutdown():
    global state
    with lock:
        state = STOPPED
    protocol_server.release()
    minecraft_server.stop_and_wait()

try:
    while True:
        try:
            line = input()
        except EOFError:
            print('Standard input is closed; waiting for a shutdown signal.')
            while state != STOPPED:
                time.sleep(1)
            break
        minecraft_server.enter_command(f"{line}\n")
except KeyboardInterrupt:
    print('-'*80)
finally:
    shutdown()
