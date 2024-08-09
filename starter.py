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

starter_properties = Properties('starter.properties')
server_properties = Properties('server.properties')

minecraft_server = MinecraftServer(starter_properties['command'])
protocol_server = ProtocolServer(starter_properties['starter-port'])
proxy = DynamicProxy(starter_properties['server-port'], starter_properties['starter-port'])
proxy.start()

state = WAITING

def on_ping(args):
    
    conn, addr, packet = args

    description = starter_properties['waiting-motd']
    if state == STARTING: starter_properties['starting-motd']
    
    # Required response to client to show status to pinging clients.
    status_string = json.dumps({
        "version": {
            "name": "1.20.1",
            "protocol": 767
        },
        "players": {
            "max": 100,
            "online": 0,
            "sample": []
        },
        "description": {
            "text": description
        },
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
    minecraft_server.start()
    state = STARTING

protocol_server.on('ping', on_ping)
protocol_server.on('pong', on_pong)
protocol_server.on('login', on_login)

def on_ready():

    # Swap the proxy to the actual server.
    global state, proxy, minecraft_server, starter_properties, server_properties
    #proxy.swap(server_properties['server-port'])
    proxy.update_forwarding(server_properties['server-port'])
    time.sleep(1)
    
    ping('127.0.0.1', 25565)

    state = STARTED

def on_exit():

    # Swap the proxy to the protocol server.
    global state, proxy, minecraft_server, starter_properties, server_properties
    print('Serving sleeping. Waiting for login attempt...')
    proxy.swap(starter_properties['starter-port'])

    

    state = WAITING

minecraft_server.on('ready', on_ready)
minecraft_server.on('exit', on_exit)

while True:
    
    try:
        line = input()
        minecraft_server.enter_command(f"{line}\n")
    
    except KeyboardInterrupt:
        minecraft_server.stop()
        protocol_server.stop()
        proxy.stop()
        break