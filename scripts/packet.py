SEGMENT_BITS = 0x7F
CONTINUE_BIT = 0x80

class PacketReader:

    def __init__(self, stream: bytes):
        self.stream = stream
        self.size = self.read_varint()
        self.id = self.read_varint()

    def read_byte(self) -> bytes:
        return self.read_bytes(1)
    
    def read_bytes(self, size: int) -> bytes:
        result = self.stream[:size]
        self.stream = self.stream[size:]
        return result
    
    def read_string(self) -> str:
        size = self.read_varint()
        return self.read_bytes(size).decode("utf-8")

    def read_varint(self) -> int:

        value = 0
        position = 0
        
        while True:
            current = int.from_bytes(self.read_byte(), byteorder='big')
            value |= (current & SEGMENT_BITS) << position
            if (current & CONTINUE_BIT) == 0: break
            position += 7
            if position >= 32: raise Exception("VarInt is too big")

        return value
    
    def read_unsigned_short(self) -> int:
        return int.from_bytes(self.read_bytes(2), byteorder='big', signed=False)
    
    def read_long(self) -> int:
        return int.from_bytes(self.read_bytes(8), byteorder='big', signed=True)

class PacketWriter:

    def __init__(self):
        self.stream = bytearray()

    def write_byte(self, value: int):
        self.stream.append(value)

    def write_bytes(self, stream: bytes):
        self.stream = self.stream + stream

    def write_string(self, string: str):
        self.write_varint(len(string))
        self.stream = self.stream + string.encode()

    def write_unsigned_short(self, value: int):
        self.write_bytes(value.to_bytes(2, byteorder='big', signed=False))

    def write_long(self, value: int):
        self.write_bytes(value.to_bytes(8, byteorder='big', signed=True))

    def write_varint(self, value: int):
        
        while True:
            
            if (value & ~SEGMENT_BITS) == 0:
                self.write_byte(value)
                return
            
            self.write_byte((value & SEGMENT_BITS) | CONTINUE_BIT)
            value = (value >> 7) & 4294967295 # Unsigned right shift operator

    def encode(self, packet_id) -> bytes:

        def size_varint(value: int):
            count = 0
            while True:
                count += 1
                if (value & ~SEGMENT_BITS) == 0: return count
                value = (value >> 7) & 4294967295 # Unsigned right shift operator

        header = PacketWriter()
        header.write_varint(size_varint(packet_id) + len(self.stream))
        header.write_varint(packet_id)

        self.stream = header.stream + self.stream
        return bytes(self.stream)