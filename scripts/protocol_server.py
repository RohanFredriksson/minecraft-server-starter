import json
import select
import socket
import threading
import time

from .packet import PacketReader, PacketWriter

STATUS = 1
LOGIN = 2

MAX_PACKET_SIZE = 2_097_151
CONNECTION_TIMEOUT = 10
# Pre-1.6 clients send only FE or FE 01, which can also begin a modern packet, and give up after 3 seconds.
LEGACY_PING_TIMEOUT = 1
# Like asyncio, pause after errors such as running out of file descriptors, which accepting again would repeat.
ACCEPT_RETRY_DELAY = 1
DISCONNECT_TIMEOUT = 1
KEEPALIVE_INTERVAL = 5
PLUGIN_RESPONSE_DRAIN_TIMEOUT = 3
KEEPALIVE_CHANNEL = 'starter:keepalive'
LOGIN_PLUGIN_REQUEST = 0x04
LOGIN_PLUGIN_RESPONSE = 0x02
LEGACY_PING = 0xFE
MIN_SUPPORTED_PROTOCOL = 393
TRANSFER = 3


def _read_varint(data, offset):
    value = 0

    for position in range(0, 21, 7):
        if offset >= len(data):
            return None

        current = data[offset]
        offset += 1
        value |= (current & 0x7F) << position

        if current & 0x80 == 0:
            return value, offset

    raise ValueError("VarInt is too big")


def create_listener(host, port):
    if host:
        family = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][0]
        return socket.create_server((host, port), family=family)

    # Accept IPv6 clients too; "localhost" resolves to ::1 first on many systems.
    if socket.has_dualstack_ipv6():
        return socket.create_server(('', port), family=socket.AF_INET6, dualstack_ipv6=True)
    return socket.create_server(('', port))


def _send_and_close(conn, data):
    deadline = time.monotonic() + DISCONNECT_TIMEOUT
    try:
        conn.settimeout(DISCONNECT_TIMEOUT)
        conn.sendall(data)
        conn.shutdown(socket.SHUT_WR)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: return
            conn.settimeout(remaining)
            if not conn.recv(4096): return
    except OSError:
        pass
    finally:
        conn.close()


def _truncate_utf16(text, code_units):
    if code_units < 0: raise ValueError("Legacy status fields exceed the maximum string length")
    encoded = text.encode("utf-16-be")[:code_units * 2]
    if encoded and 0xD800 <= int.from_bytes(encoded[-2:], "big") <= 0xDBFF:
        encoded = encoded[:-2]
    return encoded.decode("utf-16-be")


def relay(a, b):
    try:
        a.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        b.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        a.close()
        b.close()
        raise

    try:
        while True:
            r, w, err = select.select((a, b), (), ())
            for source in r:
                data = source.recv(65536)
                if not data: return
                (b if source is a else a).sendall(data)
    except OSError:
        pass
    finally:
        a.close()
        b.close()


class FrameReader:

    def __init__(self, conn):
        self.conn = conn
        self.buffer = bytearray()

    def _receive(self, timeout):
        r, w, err = select.select((self.conn,), (), (), timeout)
        if not r: return False
        data = self.conn.recv(4096)
        if not data: raise ConnectionError("Connection closed")
        self.buffer.extend(data)
        return True

    def peek_bytes(self, size, timeout):
        """Returns up to `size` bytes without consuming them."""
        deadline = time.monotonic() + timeout
        while len(self.buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._receive(remaining): break
        return bytes(self.buffer[:size])

    def read(self, timeout):
        """Returns the next complete packet frame, or None if none arrives in time."""
        deadline = time.monotonic() + timeout

        while True:
            header = _read_varint(self.buffer, 0)
            if header is not None:
                size, offset = header
                if size < 1 or size > MAX_PACKET_SIZE:
                    raise ValueError(f"Invalid packet size: {size}")
                end = offset + size
                if len(self.buffer) >= end:
                    frame = bytes(self.buffer[:end])
                    del self.buffer[:end]
                    return frame

            remaining = deadline - time.monotonic()
            if remaining <= 0: return None
            if not self._receive(remaining): return None


class HeldPlayer:
    """A client that tried to log in while the server was asleep, kept on the loading screen."""

    def __init__(self, conn, addr, reader, login_frames):
        self.conn = conn
        self.addr = addr
        self.reader = reader
        self.login_frames = login_frames
        self.outstanding = set()
        self.next_query_id = 0

    def hold(self, finished, timeout):
        """Waits until `finished` is set. Returns False if `timeout` seconds pass first."""
        deadline = time.monotonic() + timeout
        next_keepalive = time.monotonic()

        while not finished.is_set():
            now = time.monotonic()
            if now >= deadline: return False

            # Clients time out after 30 seconds of silence. Unknown login plugin
            # requests are answered with "not understood", which keeps them waiting.
            if now >= next_keepalive:
                self._send_keepalive()
                next_keepalive = now + KEEPALIVE_INTERVAL

            self._read_answer(min(0.25, deadline - now))

        # Answers forwarded to the real server would break its login sequence.
        drain_deadline = time.monotonic() + PLUGIN_RESPONSE_DRAIN_TIMEOUT
        while self.outstanding and time.monotonic() < drain_deadline:
            self._read_answer(0.25)

        return not self.outstanding

    def hand_over(self, host, port):
        """Replays the client's login to the real server and relays the session."""
        upstream = socket.create_connection((host, port))
        upstream.sendall(self.login_frames + bytes(self.reader.buffer))
        relay(self.conn, upstream)

    def disconnect(self, reason):
        response = PacketWriter()
        response.write_string(json.dumps({'text': reason}))
        _send_and_close(self.conn, response.encode(0))

    def close(self):
        self.conn.close()

    def _send_keepalive(self):
        self.next_query_id += 1
        self.outstanding.add(self.next_query_id)
        request = PacketWriter()
        request.write_varint(self.next_query_id)
        request.write_string(KEEPALIVE_CHANNEL)
        self.conn.sendall(request.encode(LOGIN_PLUGIN_REQUEST))

    def _read_answer(self, timeout):
        frame = self.reader.read(max(timeout, 0))
        if frame is None: return
        packet = PacketReader(frame)
        if packet.id == LOGIN_PLUGIN_RESPONSE:
            self.outstanding.discard(packet.read_varint())


class ProtocolServer:
    """Answers on the public port while the Minecraft server is not running."""

    def __init__(self, host, port, status, on_login):

        self.host = host
        self.port = port
        self.status = status
        self.on_login = on_login
        self.listener = None
        self.lock = threading.Lock()

    def open(self, attempts=50):
        """Starts accepting connections, retrying while the port is still being released."""
        with self.lock:
            if self.listener is not None: return

        for attempt in range(attempts):
            try:
                listener = create_listener(self.host, self.port)
                break
            except OSError:
                if attempt == attempts - 1: raise
                time.sleep(0.1)

        with self.lock: self.listener = listener
        threading.Thread(target=self._accept, args=(listener,), daemon=True).start()

    def release(self):
        """Frees the public port immediately. Accepted connections stay open."""
        with self.lock: listener, self.listener = self.listener, None
        if listener is None: return

        # close() alone leaves the port bound while another thread is waiting on it.
        try: listener.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        listener.close()

    def _accept(self, listener):
        while self.listener is listener:
            try:
                r, w, err = select.select((listener,), (), (), 0.5)
                if not r: continue
                conn, addr = listener.accept()
            except ConnectionAbortedError:
                # The client disconnected before it was accepted.
                continue
            except (OSError, ValueError) as error:
                # Releasing the port closes the listener, which also ends up here.
                if self.listener is not listener: return
                print(f"Could not accept a connection: {error}")
                time.sleep(ACCEPT_RETRY_DELAY)
                continue
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn, addr):

        reader = FrameReader(conn)
        player = None

        try:
            deadline = time.monotonic() + CONNECTION_TIMEOUT
            first_byte = reader.peek_bytes(1, CONNECTION_TIMEOUT)
            if not first_byte: return
            if first_byte[0] == LEGACY_PING:
                prefix = reader.peek_bytes(3, LEGACY_PING_TIMEOUT)
                # FE 01 can also be a modern packet's length; wait for its packet ID.
                if prefix in (b'\xfe', b'\xfe\x01', b'\xfe\x01\xfa'):
                    self._serve_legacy_status(conn, extended=len(prefix) > 1)
                    return

            handshake = reader.read(max(0, deadline - time.monotonic()))
            if handshake is None: return

            packet = PacketReader(handshake)
            if packet.id != 0: return
            protocol = packet.read_varint()
            # Vanilla allows 255 characters, but proxies forward player details in the address,
            # which Spigot and Paper accept up to the usual string limit.
            packet.read_string()
            packet.read_unsigned_short()
            next_state = packet.read_varint()

            if next_state == STATUS:
                self._serve_status(conn, reader, protocol)
                return

            if next_state not in (LOGIN, TRANSFER): return

            login = reader.read(CONNECTION_TIMEOUT)
            if login is None or PacketReader(login).id != 0: return

            player = HeldPlayer(conn, addr, reader, handshake + login)
            conn = None
            if protocol < MIN_SUPPORTED_PROTOCOL:
                player.disconnect("Minecraft 1.13 or newer is required.")
                return
            self.on_login(player)

        except Exception as error:
            print(f"Connection from {addr[0]} closed: {error}")
            if player is not None: player.close()

        finally:
            if conn is not None: conn.close()

    def _serve_status(self, conn, reader, protocol):

        while True:
            frame = reader.read(CONNECTION_TIMEOUT)
            if frame is None: return
            packet = PacketReader(frame)

            if packet.id == 0:
                response = PacketWriter()
                response.write_string(self.status(protocol))
                conn.sendall(response.encode(0))

            elif packet.id == 1:
                response = PacketWriter()
                response.write_bytes(packet.read_bytes(8))
                conn.sendall(response.encode(1))
                return

    def _serve_legacy_status(self, conn, extended):
        status = json.loads(self.status(0))
        version = status.get("version", {})
        players = status.get("players", {})
        description = status.get("description", {})
        motd = description.get("text", "") if isinstance(description, dict) else str(description)
        online = str(players.get("online", 0))
        maximum = str(players.get("max", 0))
        if extended:
            prefix = "\u00a71\0" + "127\0"
            suffix = f"\0{online}\0{maximum}"
            budget = 32767 - len((prefix + "\0" + suffix).encode("utf-16-be")) // 2
            name = _truncate_utf16(str(version.get("name", "Unknown")), budget)
            motd = _truncate_utf16(motd, budget - len(name.encode("utf-16-be")) // 2)
            response = prefix + name + "\0" + motd + suffix
        else:
            suffix = f"\u00a7{online}\u00a7{maximum}"
            budget = 256 - len(suffix.encode("utf-16-be")) // 2
            response = _truncate_utf16(motd, budget) + suffix
        encoded = response.encode("utf-16-be")
        _send_and_close(conn, b"\xff" + (len(encoded) // 2).to_bytes(2, "big") + encoded)
