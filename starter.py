import threading
import json
import time

from scripts.packet import PacketReader, PacketWriter
from scripts.minecraft_server import MinecraftServer
from scripts.protocol_server import ProtocolServer
from scripts.properties import Properties
from scripts.proxy import DynamicProxy
from scripts.ping import ping

WAITING = 0
STARTING = 1
STARTED = 2
STOPPED = 3

starter_properties = Properties('starter.properties')
server_properties = Properties('server.properties')

minecraft_server = MinecraftServer(starter_properties['command'])
protocol_server = ProtocolServer(starter_properties['starter-port'])
proxy = DynamicProxy(starter_properties['server-port'], starter_properties['starter-port'])
state = WAITING

def on_ping(args):
    
    global state, proxy, minecraft_server, starter_properties, server_properties
    conn, addr, packet = args

    # Depending on the state, we need to show different motds.
    description = starter_properties['waiting-motd']
    if state == STARTING: starter_properties['starting-motd']
    
    # Required response to client to show status to pinging clients.
    status_string = json.dumps({
        "version": { "name": starter_properties["version"], "protocol": starter_properties["protocol"] },
        "players": { "max": 20, "online": 0, "sample": [] },
        "description": { "text": description },
        "enforcesSecureChat": False
    })
    
    response = PacketWriter()
    response.write_string(status_string)
    data = response.encode(0)
    conn.send(data)

def on_pong(args):

    conn, addr, packet = args

    # Return the ping packet to the client.
    response = PacketWriter()
    response.write_long(packet.read_long())
    data = response.encode(1)
    conn.send(data)
    conn.close()

def on_login(args):

    global state, proxy, minecraft_server, starter_properties, server_properties
    conn, addr, packet = args

    # Send a disconnect packet to the client.
    response = PacketWriter()
    response.write_string(json.dumps({"text": starter_properties['starting-reason']}))
    data = response.encode(0)
    conn.send(data)
    conn.close()

    # If we are currently waiting, start the server.
    if state != WAITING: return

    print('Server is starting...')
    print('-'*80)

    minecraft_server.start()
    state = STARTING

protocol_server.on('ping', on_ping)
protocol_server.on('pong', on_pong)
protocol_server.on('login', on_login)

def on_ready():

    # Swap the proxy to the actual server.
    global state, proxy, minecraft_server, starter_properties, server_properties
    proxy.swap(server_properties['server-port'])
    state = STARTED

    # Inactivity timeout.
    def timeout():

        timeout_count = 0
        while state != STOPPED:

            # Ping the server once every minute.
            for i in range(600):
                if state == STOPPED: return
                time.sleep(0.1)
        
            # If there are players online reset the count, else increment.
            response = ping('127.0.0.1', server_properties['server-port'])
            if response['online'] == False: return
            if response['players']['online'] > 0: timeout_count = 0 
            else: timeout_count += 1

            # If we have passed the timeout threshold, we shut it down.
            if timeout_count < starter_properties['timeout']: continue
            minecraft_server.stop()
            return
        
    thread = threading.Thread(target=timeout, args=())
    thread.start()

    # Update the version name and protocol number in starter properties
    response = ping('127.0.0.1', server_properties['server-port'])
    if response["online"] == False: return

    starter_properties["protocol"] = response["version"]["protocol"]
    starter_properties["version"]  = response["version"]["name"]
    starter_properties.write()

def on_exit():

    # Swap the proxy to the protocol server.
    global state, proxy, minecraft_server, starter_properties, server_properties
    if state == STOPPED: return
    print('-'*80)
    print('Serving sleeping. Waiting for login attempt...')
    proxy.swap(starter_properties['starter-port'])
    state = WAITING

minecraft_server.on('ready', on_ready)
minecraft_server.on('exit', on_exit)

print('-'*80)
print('Serving sleeping. Waiting for login attempt...')

while True:
    
    try:
        line = input()
        minecraft_server.enter_command(f"{line}\n")
    
    except KeyboardInterrupt:
        print('-'*80)
        state = STOPPED
        minecraft_server.stop()
        protocol_server.stop()
        proxy.stop()
        break