import json

from scripts.packet import PacketReader, PacketWriter
from scripts.minecraft_server import MinecraftServer
from scripts.protocol_server import ProtocolServer
from scripts.properties import Properties
from scripts.proxy import Proxy
from scripts.ping import ping

WAITING = 0
STARTING = 1
STARTED = 2

starter_properties = Properties('starter.properties')
server_properties = Properties('server.properties')


#print(server_properties.properties)


#minecraft_server = MinecraftServer(properties['command'])
#protocol_server = ProtocolServer(properties['starter-port'])
#proxy = Proxy(properties['server-port'], properties['starter-port'])

def on_ping(args):
    
    conn, addr, packet = args
    
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
            "text": "Hello, world!"
        },
        "enforcesSecureChat": False
    })
    
    response = PacketWriter()
    response.write_string(status_string)
    data = response.encode(0)
    conn.send(data)

def on_pong(args):

    conn, addr, packet = args

    response = PacketWriter()
    response.write_long(packet.read_long())
    data = response.encode(1)
    conn.send(data)

def on_login(args):

    conn, addr, packet = args

    reason_string = json.dumps({
        "text": "Server is waking up. Please wait a few seconds."
    })

    response = PacketWriter()
    response.write_string(reason_string)
    data = response.encode(0)
    conn.send(data)

    #minecraft_server.stop()

#protocol_server.on('ping', on_ping)
#protocol_server.on('pong', on_pong)
#protocol_server.on('login', on_login)

def on_start():
    print("START")

def on_ready():
    print("READY")
    ping('127.0.0.1', 25567)

def on_exit():
    print("EXIT")

#minecraft_server.on('start', on_start)
#minecraft_server.on('ready', on_ready)
#minecraft_server.on('exit', on_exit)
#minecraft_server.start()

"""
while True:
    
    try:
        line = input()
        print(f"INPUT: {line}")
    
    except KeyboardInterrupt:
        minecraft_server.stop()
        protocol_server.stop()
        proxy.stop()
        break
"""