import socket
import json

from .packet import PacketReader, PacketWriter
from .protocol_server import FrameReader

TIMEOUT = 2.0

def ping(host, port):
    
    try:

        # Establish connection with server.
        with socket.create_connection((host, port), timeout=TIMEOUT) as sock:

            # Handshake Packet
            writer = PacketWriter()
            writer.write_varint(767)
            writer.write_string(host)
            writer.write_unsigned_short(port)
            writer.write_varint(1)
            data = writer.encode(0)
            sock.sendall(data)

            # Status Request
            writer = PacketWriter()
            data = writer.encode(0)
            sock.sendall(data)

            # Status Return, which takes several reads when it includes the server icon.
            data = FrameReader(sock).read(TIMEOUT)
            if data is None: raise Exception("Ping timed out.")

        # Convert packet to dict.
        reader = PacketReader(data)
        response = reader.read_string()
        result = json.loads(response)
        if type(result) != dict: raise Exception("JSON response of incorrect format.")
        result["online"] = True
        return result

    except Exception as e: 
        print(e)
        return {"online": False}
    
