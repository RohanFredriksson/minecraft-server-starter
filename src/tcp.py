import socket
from packet import PacketReader, PacketWriter

p = PacketWriter()
p.write_varint(2097151)
p.write_string("Hello World!")
print(p.stream)

HOST = "127.0.0.1"
PORT = 25567

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    
s.bind((HOST, PORT))
s.listen()

conn, add = s.accept()
    
while True:
    
    data = conn.recv(1024)
    if not data: break
    
    packet = PacketReader(data)
    protocol_number = packet.read_varint()
    server_address_size = packet.read_varint()
    server_address = packet.read_string(server_address_size)
    server_port = packet.read_unsigned_short()
    next_state = packet.read_varint()

    print("PACKET SIZE: ", packet.size)
    print("PACKET ID: ", packet.id)
    print("PROTOCOL NO: ", protocol_number)
    print("SERVER ADDRESS SIZE: ", server_address_size)
    print("SERVER ADDRESS: ", server_address)
    print("SERVER PORT: ", server_port)
    print("NEXT STATE: ", next_state)

    conn.send("Hello world".encode())

    exit()