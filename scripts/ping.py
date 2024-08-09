import select
import socket
import json

from .packet import PacketReader, PacketWriter

def ping(host, port):
    
    try:

        # Establish connection with server.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))

        # Handshake Packet
        writer = PacketWriter()
        writer.write_varint(767)
        writer.write_string(host)
        writer.write_unsigned_short(port)
        writer.write_varint(1)
        data = writer.encode(0)
        sock.send(data)

        # Status Request
        writer = PacketWriter()
        data = writer.encode(0)
        sock.send(data)

        # Status Return
        r, w, err = select.select((sock,), (), (), 2.0)
        if not r: raise Exception("Ping timed out.")
        data = False
        data = sock.recv(4096)
        if not data: raise Exception("Connected terminated.")
        sock.close()

        # Convert packet to dict.
        reader = PacketReader(data)
        response = reader.read_string()
        result = json.loads(response)
        if type(result) != dict: raise Exception("JSON response of incorrect format.")
        result["online": True]
        return result

    except: return {"online": False}
    
