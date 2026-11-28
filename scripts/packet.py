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
        if size < 0 or size > len(self.stream):
            raise ValueError(f"Invalid packet field size: {size} ({len(self.stream)} bytes remain)")
        result = self.stream[:size]
        self.stream = self.stream[size:]
        return result
    
    def read_string(self, max_characters: int = 32767) -> str:
        size = self.read_varint()
        if size > max_characters * 3:
            raise ValueError("String exceeds its maximum encoded length")
        # Like Minecraft, replace invalid UTF-8 rather than rejecting it.
        text = self.read_bytes(size).decode("utf-8", errors="replace")
        if len(text.encode("utf-16-be")) // 2 > max_characters:
            raise ValueError("String exceeds its maximum character count")
        return text

    def read_varint(self) -> int:

        value = 0

        for position in range(0, 35, 7):
            data = self.read_byte()
            current = data[0]
            value |= (current & SEGMENT_BITS) << position
            if current & CONTINUE_BIT == 0:
                # Like Minecraft, drop the bits of a fifth byte that do not fit in 32.
                value &= 0xFFFFFFFF
                if value & 0x80000000: value -= 0x100000000
                return value

        raise ValueError("VarInt is too big")
    
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
        data = string.encode()
        self.write_varint(len(data))
        self.stream = self.stream + data

    def write_unsigned_short(self, value: int):
        self.write_bytes(value.to_bytes(2, byteorder='big', signed=False))

    def write_long(self, value: int):
        self.write_bytes(value.to_bytes(8, byteorder='big', signed=True))

    def write_varint(self, value: int):

        if not -0x80000000 <= value <= 0x7FFFFFFF:
            raise ValueError("VarInt must fit in a signed 32-bit integer")

        value &= 0xFFFFFFFF
        while True:

            if value <= SEGMENT_BITS:
                self.write_byte(value)
                return

            self.write_byte((value & SEGMENT_BITS) | CONTINUE_BIT)
            value >>= 7

    def encode(self, packet_id) -> bytes:

        encoded_id = PacketWriter()
        encoded_id.write_varint(packet_id)
        header = PacketWriter()
        header.write_varint(len(encoded_id.stream) + len(self.stream))

        self.stream = header.stream + encoded_id.stream + self.stream
        return bytes(self.stream)