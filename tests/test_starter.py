"""End-to-end tests for starter.py against tests/FakeServer.java.

Each test runs the starter in a temporary folder with a fake server on a free port.
Requires Python 3.8+ and Java 11+ on the PATH. Run with:

    python -m unittest discover -s tests -v
"""
import base64
import contextlib
import errno
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock

from scripts.minecraft_server import BINDING_PATTERN
from scripts.packet import PacketReader, PacketWriter
from scripts.protocol_server import FrameReader, HeldPlayer, ProtocolServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL = 767

SLEEPING_MOTD = 'Server currently sleeping. Please login to wake me up!'
STARTING_MOTD = 'Server is waking up. Please wait a few seconds.'


def varint(value):
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        if value <= 0x7F:
            out.append(value)
            return bytes(out)
        out.append((value & 0x7F) | 0x80)
        value >>= 7


def string(text):
    data = text.encode()
    return varint(len(data)) + data


def frame(packet_id, payload=b''):
    body = varint(packet_id) + payload
    return varint(len(body)) + body


def handshake(port, next_state, protocol=PROTOCOL, address='localhost'):
    return frame(0x00, varint(protocol) + string(address) + port.to_bytes(2, 'big') + varint(next_state))


def png(width, height, padding=20):
    """The start of a PNG image, which is all the size checks read, padded to stand in for image data."""
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR' + width.to_bytes(4, 'big') + height.to_bytes(4, 'big') + bytes(padding)


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk: raise ConnectionError('Connection closed')
        data += chunk
    return data


def read_varint(read):
    value = 0
    for shift in range(0, 35, 7):
        current = read(1)[0]
        value |= (current & 0x7F) << shift
        if not current & 0x80: return value
    raise ValueError('VarInt is too big')


def read_packet(sock):
    body = recv_exact(sock, read_varint(lambda n: recv_exact(sock, n)))
    position = [0]

    def read(n):
        chunk = body[position[0]:position[0] + n]
        position[0] += n
        return chunk

    packet_id = read_varint(read)
    return packet_id, read


def read_string(read):
    return read(read_varint(read)).decode()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def ipv6_available():
    try:
        with socket.socket(socket.AF_INET6) as sock:
            sock.bind(('::1', 0))
        return True
    except OSError:
        return False


def status_response(port, host='127.0.0.1', protocol=PROTOCOL):
    """Returns the server list response, or None if nothing is listening."""
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(handshake(port, 1, protocol) + frame(0x00))
            packet_id, read = read_packet(sock)
            response = json.loads(read_string(read))
            sock.sendall(frame(0x01, (1234).to_bytes(8, 'big')))
            pong_id, read = read_packet(sock)
            if pong_id != 0x01 or read(8) != (1234).to_bytes(8, 'big'): return {'description': 'bad pong'}
            return response
    except (ConnectionRefusedError, ConnectionResetError):
        return None


def status(port, host='127.0.0.1'):
    """Returns the server list description, or None if nothing is listening."""
    response = status_response(port, host)
    if response is None: return None
    description = response['description']
    return description['text'] if isinstance(description, dict) else description


def login(port, name, timeout=60, intent=2):
    """Logs in like a 1.20.2+ client, answering the starter's keep-alives.

    Returns the disconnect message, which is "Welcome <name>" when the fake server accepted the login.
    """
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        sock.sendall(handshake(port, intent) + frame(0x00, string(name) + uuid.uuid3(uuid.NAMESPACE_DNS, name).bytes))
        while True:
            packet_id, read = read_packet(sock)
            if packet_id == 0x04:
                message_id = read_varint(read)
                sock.sendall(frame(0x02, varint(message_id) + b'\x00'))
            elif packet_id == 0x02:
                read(16)
                if read_string(read) != name: return 'wrong name in login success'
                sock.sendall(frame(0x03))
            elif packet_id == 0x00:
                return json.loads(read_string(read))['text']
            else:
                return f'unexpected packet 0x{packet_id:02x}'


def wait_for(condition, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = condition()
        if result: return result
        time.sleep(0.1)
    return None


class PacketProtocolTest(unittest.TestCase):

    def test_varints_round_trip_signed_32_bit_values(self):
        samples = {
            -0x80000000: bytes.fromhex('8080808008'),
            -1: bytes.fromhex('ffffffff0f'),
            0: b'\x00',
            0x7FFFFFFF: bytes.fromhex('ffffffff07'),
        }
        for value, expected in samples.items():
            with self.subTest(value=value):
                writer = PacketWriter()
                writer.write_varint(value)
                self.assertEqual(bytes(writer.stream), expected)

                packet = PacketReader(bytes([len(expected) + 1, 0]) + expected)
                self.assertEqual(packet.read_varint(), value)

    def test_varint_rejects_out_of_range_values_and_truncation(self):
        with self.assertRaises(ValueError):
            PacketWriter().write_varint(0x80000000)
        with self.assertRaises(ValueError):
            PacketReader(b'\x02\x00\x80').read_varint()

    def test_varint_drops_overflow_bits_like_vanilla(self):
        # The wiki's reader keeps only 32 bits of the fifth byte, but never reads a sixth.
        self.assertEqual(PacketReader(b'\x06\x00' + bytes.fromhex('ffffffff7f')).read_varint(), -1)
        with self.assertRaises(ValueError):
            PacketReader(b'\x07\x00' + bytes.fromhex('ffffffffff01')).read_varint()

    def test_packet_fields_reject_negative_lengths_and_truncation(self):
        for payload in (varint(-1) + b'abc', varint(5) + b'ab'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                PacketReader(frame(0, payload)).read_string()
        with self.assertRaises(ValueError):
            PacketReader(frame(0, b'\x00')).read_unsigned_short()

    def test_string_limits_count_utf16_code_units(self):
        for text in ('a' * 256, '\U0001f600' * 128):
            with self.subTest(text=text), self.assertRaises(ValueError):
                PacketReader(frame(0, string(text))).read_string(255)
        text = '\U0001f600' * 127 + 'a'
        self.assertEqual(PacketReader(frame(0, string(text))).read_string(255), text)

    def test_invalid_utf8_is_replaced_like_vanilla(self):
        self.assertEqual(PacketReader(frame(0, varint(3) + b'a\xffb')).read_string(), 'a\ufffdb')

    def test_frame_length_limit_matches_three_byte_protocol_limit(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        reader = FrameReader(left)

        reader.buffer = bytearray(varint(2_097_152))
        with self.assertRaises(ValueError):
            reader.read(0)

        reader.buffer = bytearray(b'\x80\x80\x80\x00')
        with self.assertRaises(ValueError):
            reader.read(0)

    def test_short_padded_frame_length_is_allowed(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        reader = FrameReader(left)
        reader.buffer = bytearray(b'\x80\x01\x00')
        self.assertIsNone(reader.read(0))

    def test_unanswered_plugin_response_prevents_handover(self):
        class NoResponseReader:
            buffer = bytearray()

            def read(self, timeout):
                return None

        player = HeldPlayer(None, None, NoResponseReader(), b'')
        player.outstanding.add(1)
        finished = threading.Event()
        finished.set()
        with mock.patch('scripts.protocol_server.PLUGIN_RESPONSE_DRAIN_TIMEOUT', 0.01):
            self.assertFalse(player.hold(finished, 1))

    def test_disconnect_sends_message_and_drains_pending_input(self):
        server, client = socket.socketpair()
        self.addCleanup(server.close)
        self.addCleanup(client.close)
        client.sendall(b'late plugin response')
        player = HeldPlayer(server, None, None, b'')
        worker = threading.Thread(target=player.disconnect, args=('Closed',))
        worker.start()
        packet_id, read = read_packet(client)
        self.assertEqual(packet_id, 0)
        self.assertEqual(json.loads(read_string(read))['text'], 'Closed')
        client.close()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_disconnect_drain_has_a_total_deadline(self):
        server, client = socket.socketpair()
        stop = threading.Event()

        def send_input():
            while not stop.is_set():
                try: client.sendall(b'ongoing input')
                except OSError: return
                stop.wait(0.02)

        sender = threading.Thread(target=send_input)
        worker = threading.Thread(target=HeldPlayer(server, None, None, b'').disconnect, args=('Closed',))
        sender.start()
        worker.start()
        try:
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive(), 'ongoing input extended the disconnect deadline')
        finally:
            stop.set()
            client.close()
            sender.join(timeout=2)
            worker.join(timeout=2)
            server.close()

    def test_proxy_forwarded_address_is_accepted(self):
        # BungeeCord's IP forwarding adds the player's address, UUID and profile to the handshake address,
        # which Spigot and Paper accept up to 32767 characters instead of vanilla's 255.
        properties = json.dumps([{'name': 'textures', 'value': 'e' * 600, 'signature': 's' * 684}])
        address = '\0'.join(('localhost', '203.0.113.5', uuid.uuid4().hex, properties))
        players = []
        server = ProtocolServer('', 0, None, players.append)
        conn, client = socket.socketpair()
        self.addCleanup(client.close)
        client.sendall(handshake(25565, 2, address=address) + frame(0x00, string('Proxied') + bytes(16)))
        server._handle(conn, ('proxy', 0))
        self.assertEqual(len(players), 1)
        players[0].close()

    def test_accept_continues_after_transient_errors(self):
        listener = socket.create_server(('127.0.0.1', 0))
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        # A client that reset before it was accepted, then running out of file descriptors.
        errors = [ConnectionAbortedError(errno.ECONNABORTED, 'Software caused connection abort'),
                  OSError(errno.EMFILE, 'Too many open files')]

        class FailingListener:
            def fileno(self):
                return listener.fileno()

            def accept(self):
                if errors: raise errors.pop(0)
                return listener.accept()

        server = ProtocolServer('', port, lambda protocol: json.dumps({'description': 'Up'}), None)
        server.listener = FailingListener()
        worker = threading.Thread(target=server._accept, args=(server.listener,))
        output = io.StringIO()
        with mock.patch('scripts.protocol_server.ACCEPT_RETRY_DELAY', 0.01), contextlib.redirect_stdout(output):
            worker.start()
            try:
                self.assertEqual(status(port), 'Up')
            finally:
                server.listener = None
                listener.close()
                worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertIn('Too many open files', output.getvalue())

    def test_old_legacy_ping_formats(self):
        status = json.dumps({
            'version': {'name': 'Unknown', 'protocol': 0},
            'players': {'online': 0, 'max': 20},
            'description': {'text': 'Test'},
        })
        expected_responses = {
            b'\xfe': 'Test\u00a70\u00a720',
            b'\xfe\x01': '\u00a71\0' + '\0'.join(('127', 'Unknown', 'Test', '0', '20')),
        }
        for ping, expected in expected_responses.items():
            with self.subTest(ping=ping):
                server_sock, client = socket.socketpair()
                # Pre-1.6 clients give up after 3 seconds.
                client.settimeout(3)
                server = ProtocolServer('', 0, lambda protocol: status, lambda player: None)
                worker = threading.Thread(target=server._handle, args=(server_sock, ('local', 0)))
                try:
                    worker.start()
                    client.sendall(ping)
                    self.assertEqual(recv_exact(client, 1), b'\xff')
                    size = int.from_bytes(recv_exact(client, 2), 'big')
                    response = recv_exact(client, size * 2).decode('utf-16-be')
                    self.assertEqual(response, expected)
                finally:
                    client.close()
                    worker.join(timeout=2)
                    server_sock.close()
                self.assertFalse(worker.is_alive())

    def test_legacy_truncation_preserves_player_fields_and_unicode(self):
        server = ProtocolServer('', 0, lambda protocol: json.dumps({
            'version': {'name': 'Unknown', 'protocol': 0},
            'players': {'online': 0, 'max': 20},
            'description': {'text': '\U0001f600' * 33000},
        }), lambda player: None)
        for extended, maximum in ((False, 256), (True, 32767)):
            with self.subTest(extended=extended), mock.patch('scripts.protocol_server._send_and_close') as send:
                server._serve_legacy_status(None, extended)
                packet = send.call_args[0][1]
                size = int.from_bytes(packet[1:3], 'big')
                text = packet[3:].decode('utf-16-be')
                self.assertLessEqual(size, maximum)
                self.assertEqual(len(packet[3:]), size * 2)
                if extended:
                    self.assertEqual(text.split('\0')[-2:], ['0', '20'])
                    self.assertEqual(len(text.split('\0')), 6)
                else:
                    self.assertTrue(text.endswith('\u00a70\u00a720'))

    def test_binding_pattern_only_matches_bind_log(self):
        self.assertIsNone(BINDING_PATTERN.search('Starting minecraft server version 1.21'))
        self.assertIsNotNone(BINDING_PATTERN.search('Starting Minecraft server on *:25565'))


class StarterTest(unittest.TestCase):

    def prepare(self, server_properties=''):
        """Creates a server folder with the starter, the fake server and a server.properties."""
        self.port = free_port()
        self.folder = tempfile.mkdtemp(prefix='starter-test-')
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

        shutil.copy(os.path.join(REPO, 'starter.py'), self.folder)
        shutil.copytree(os.path.join(REPO, 'scripts'), os.path.join(self.folder, 'scripts'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy(os.path.join(REPO, 'tests', 'FakeServer.java'), self.folder)
        self.write('server.properties', f'server-ip=\nserver-port={self.port}\n{server_properties}')

    def write(self, name, data):
        mode, encoding = ('wb', None) if isinstance(data, bytes) else ('w', 'utf-8')
        with open(os.path.join(self.folder, name), mode, encoding=encoding) as file:
            file.write(data)

    def read(self, name):
        with open(os.path.join(self.folder, name), encoding='utf-8', errors='replace') as file:
            return file.read()

    def launch(self):
        self.log_path = os.path.join(self.folder, 'starter.log')
        self.log = open(self.log_path, 'w')
        self.starter = subprocess.Popen([sys.executable, '-u', 'starter.py'], cwd=self.folder,
                                        stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(self.stop_starter)
        self.assertTrue(wait_for(lambda: status(self.port), 10), 'starter did not start listening')

    def start_starter(self, command='java FakeServer.java', settings=None):
        self.prepare()
        settings = {'command': command, **(settings or {})}
        self.write('starter.properties', ''.join(f'{key}={value}\n' for key, value in settings.items()))
        self.launch()

    def run_until_exit(self):
        """Runs a starter that should exit by itself, returning its exit code and output."""
        result = subprocess.run([sys.executable, '-u', 'starter.py'], cwd=self.folder, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        return result.returncode, result.stdout

    def stop_starter(self):
        if self.starter.poll() is None:
            self.starter.kill()
            self.starter.wait()
        self.starter.stdin.close()
        # Closing the starter's pipe makes the fake server exit too.
        time.sleep(0.5)
        self.log.close()
        with open(self.log_path) as file:
            self.output = file.read()

    def send(self, line):
        self.starter.stdin.write(line + '\n')
        self.starter.stdin.flush()

    def run(self, result=None):
        problems = len(result.failures) + len(result.errors) if result is not None else 0
        result = super().run(result)
        if result is not None and len(result.failures) + len(result.errors) > problems and hasattr(self, 'output'):
            print(f'\n--- starter output for {self.id()} ---\n{self.output}', file=sys.stderr)
        return result

    def stop_server_and_wait_until_sleeping(self):
        self.send('stop')
        self.assertTrue(wait_for(lambda: status(self.port) == SLEEPING_MOTD, 20), 'starter did not reclaim the port')

    def test_status_while_sleeping(self):
        self.start_starter()
        self.assertEqual(status(self.port, '127.0.0.1'), SLEEPING_MOTD)
        if ipv6_available():
            self.assertEqual(status(self.port, '::1'), SLEEPING_MOTD)

    def test_legacy_server_list_ping(self):
        self.start_starter()
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(b'\xfe\x01\xfa')
            self.assertEqual(recv_exact(sock, 1), b'\xff')
            size = int.from_bytes(recv_exact(sock, 2), 'big')
            response = recv_exact(sock, size * 2).decode('utf-16-be')
            self.assertEqual(response.split('\0')[0], '\u00a71')
            self.assertIn(SLEEPING_MOTD, response)

    def test_fragmented_long_hostname_is_not_a_legacy_ping(self):
        self.start_starter()
        address = '.'.join(('a' * 63, 'b' * 63, 'c' * 63, 'd' * 54))
        hello = handshake(self.port, 1, address=address)
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(hello[:2])
            time.sleep(0.05)
            sock.sendall(hello[2:] + frame(0))
            packet_id, read = read_packet(sock)
            self.assertEqual(packet_id, 0)
            self.assertEqual(json.loads(read_string(read))['description']['text'], SLEEPING_MOTD)

    def test_truncated_ping_is_rejected(self):
        self.start_starter()
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(handshake(self.port, 1) + frame(1, b'\x42'))
            self.assertEqual(sock.recv(1), b'')

    def test_negative_status_protocol_is_reported_as_signed(self):
        self.start_starter()
        self.assertEqual(status_response(self.port, protocol=-1)['version']['protocol'], -1)

    def test_unsupported_login_version_is_disconnected(self):
        self.start_starter()
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(handshake(self.port, 2, protocol=340) + frame(0x00, string('OldClient')))
            packet_id, read = read_packet(sock)
            self.assertEqual(packet_id, 0x00)
            self.assertIn('Minecraft 1.13 or newer is required.', json.loads(read_string(read))['text'])

    def test_transfer_login_is_forwarded_to_server(self):
        self.start_starter()
        self.assertEqual(login(self.port, 'Transfer', intent=3), 'Welcome Transfer')

    def test_wake_up_hand_over_and_sleep_again(self):
        self.start_starter()
        settings = self.read('starter.properties')

        descriptions = []
        done = threading.Event()

        def watch():
            while not done.is_set():
                try: description = status(self.port)
                except OSError: description = None
                if description and (not descriptions or descriptions[-1] != description):
                    descriptions.append(description)
                time.sleep(0.05)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            self.assertEqual(login(self.port, 'Waker'), 'Welcome Waker')
        finally:
            done.set()
            watcher.join()
        self.assertIn(STARTING_MOTD, descriptions)

        # The starter has stepped aside, so new players reach the server directly.
        self.assertEqual(status(self.port), 'Fake server')
        if ipv6_available():
            self.assertEqual(status(self.port, '::1'), 'Fake server')
        self.assertEqual(login(self.port, 'Direct', 10), 'Welcome Direct')

        self.stop_server_and_wait_until_sleeping()
        self.assertEqual(login(self.port, 'Again'), 'Welcome Again')
        self.stop_server_and_wait_until_sleeping()

        # The server's version is remembered for the server list, without touching the user's settings.
        self.assertEqual(status_response(self.port, protocol=776)['version'], {'name': 'Fake', 'protocol': 767})
        self.assertTrue(os.path.exists(os.path.join(self.folder, 'starter-cache.json')))
        self.assertEqual(self.read('starter.properties'), settings)

    def test_paper_style_log_format(self):
        self.start_starter(command='java FakeServer.java paper')
        self.assertEqual(login(self.port, 'PaperWaker'), 'Welcome PaperWaker')
        self.assertEqual(status(self.port), 'Fake server')
        self.assertEqual(login(self.port, 'PaperDirect', 10), 'Welcome PaperDirect')

        self.stop_server_and_wait_until_sleeping()

    def test_several_players_waiting(self):
        self.start_starter()
        results = {}

        def join(name):
            results[name] = login(self.port, name)

        threads = [threading.Thread(target=join, args=(f'Player{i}',)) for i in range(3)]
        for thread in threads:
            thread.start()
            time.sleep(0.1)
        for thread in threads:
            thread.join()

        self.assertEqual(results, {f'Player{i}': f'Welcome Player{i}' for i in range(3)})

    def test_join_timeout(self):
        self.start_starter(command='java FakeServer.java slow', settings={'join-timeout-seconds': 2})
        started = time.monotonic()
        message = login(self.port, 'Impatient')
        self.assertIn('taking longer than usual', message)
        self.assertLess(time.monotonic() - started, 5)

        # The server keeps booting, and a retry gets in once it is up.
        self.assertTrue(wait_for(lambda: status(self.port) == 'Fake server', 30), 'server did not finish starting')
        self.assertEqual(login(self.port, 'Retry', 10), 'Welcome Retry')

    def test_server_crashes_while_starting(self):
        self.start_starter(command='java FakeServer.java crash')
        self.assertEqual(login(self.port, 'Unlucky'), 'The server failed to start.')
        self.assertTrue(wait_for(lambda: status(self.port) == SLEEPING_MOTD, 10), 'starter did not reclaim the port')

    def test_command_not_found(self):
        self.start_starter(command='minecraft-server-starter-missing-command')
        self.assertEqual(login(self.port, 'Unlucky'), 'The server failed to start.')
        self.assertEqual(status(self.port), SLEEPING_MOTD)

    def test_first_run_creates_described_settings(self):
        self.prepare()
        self.launch()
        self.assertEqual(status(self.port), SLEEPING_MOTD)

        settings = self.read('starter.properties')
        keys = [line.split('=')[0] for line in settings.splitlines() if line and not line.startswith('#')]
        self.assertEqual(keys, ['command', 'stop-when-empty-seconds', 'join-timeout-seconds', 'sleeping-motd',
                                'starting-motd', 'join-timeout-message', 'start-failed-message'])
        for key in keys:
            self.assertRegex(settings, f'#.*\n{key}=', f'{key} is not described')

    def test_invalid_settings_stop_the_starter(self):
        self.prepare()
        self.write('starter.properties', 'stop-when-empty-seconds=-1\njoin-timeout-seconds=soon\ntimeout=3\n')
        code, output = self.run_until_exit()
        self.assertEqual(code, 1, output)
        self.assertIn("unknown setting 'timeout'", output)
        self.assertIn('stop-when-empty-seconds must be a whole number of seconds, at least 1 (not "-1")', output)
        self.assertIn('join-timeout-seconds must be a whole number of seconds, at least 1 (not "soon")', output)
        self.assertNotIn('Waiting for login attempt', output)

    def test_missing_server_properties(self):
        self.prepare()
        os.remove(os.path.join(self.folder, 'server.properties'))
        code, output = self.run_until_exit()
        self.assertEqual(code, 1, output)
        self.assertIn('server.properties was not found', output)
        self.assertFalse(os.path.exists(os.path.join(self.folder, 'starter.properties')))

    def test_stops_when_empty(self):
        self.start_starter(settings={'stop-when-empty-seconds': 1})
        # A typical icon makes the running server's status response longer than a single read.
        self.write('server-icon.png', png(64, 64, 8000))
        self.assertEqual(login(self.port, 'Visitor'), 'Welcome Visitor')
        self.assertTrue(wait_for(lambda: status(self.port) == SLEEPING_MOTD, 20), 'empty server was not stopped')
        self.assertIn('Server empty for 1 seconds, stopping it.', self.read('starter.log'))

    def test_hidden_player_count_keeps_server_running(self):
        self.start_starter(command='java FakeServer.java hidden-players', settings={'stop-when-empty-seconds': 1})
        self.assertEqual(login(self.port, 'Hidden'), 'Welcome Hidden')
        warning = 'The server does not report how many players are online, so it will not be stopped when empty.'
        self.assertTrue(wait_for(lambda: warning in self.read('starter.log'), 10), 'missing player count was not reported')
        self.assertEqual(status(self.port), 'Fake server')
        self.assertNotIn('Traceback', self.read('starter.log'))
        self.stop_server_and_wait_until_sleeping()

    def test_undecodable_server_output(self):
        self.start_starter(command='java FakeServer.java garbled', settings={'join-timeout-seconds': 15})
        self.assertEqual(login(self.port, 'Garbled'), 'Welcome Garbled')
        self.assertIn('<C> \\x81', self.read('starter.log'))
        self.stop_server_and_wait_until_sleeping()

    def test_sleeping_status_mirrors_server(self):
        self.prepare('max-players=7\n')
        self.write('starter.properties', 'command=java FakeServer.java\nsleeping-motd=Line one\\nLine two \\u00A7aGreen\n')
        icon = png(64, 64)
        self.write('server-icon.png', icon)
        self.launch()

        response = status_response(self.port, protocol=776)
        self.assertEqual(response['description']['text'], 'Line one\nLine two \u00a7aGreen')
        self.assertEqual(response['players']['max'], 7)
        self.assertEqual(response['favicon'], 'data:image/png;base64,' + base64.b64encode(icon).decode())
        # Before the server has run, its version is unknown, so any client is shown as compatible.
        self.assertEqual(response['version']['protocol'], 776)

        # Minecraft only uses 64x64 icons, so other sizes are left out.
        self.write('server-icon.png', png(32, 32))
        self.assertNotIn('favicon', status_response(self.port))

        # Clients reject server list responses over 32767 characters, so icons too large to fit are left out too.
        self.write('server-icon.png', png(64, 64, 26000))
        response = status_response(self.port)
        self.assertNotIn('favicon', response)
        self.assertEqual(response['description']['text'], 'Line one\nLine two \u00a7aGreen')

    def test_command_with_quoted_path(self):
        self.prepare()
        shutil.copy(os.path.join(self.folder, 'FakeServer.java'), os.path.join(self.folder, 'Fake Server.java'))
        self.write('starter.properties', 'command=java "Fake Server.java"\n')
        self.launch()
        self.assertEqual(login(self.port, 'Quoted'), 'Welcome Quoted')

    @unittest.skipIf(sys.platform == 'win32', 'Ctrl+C cannot be sent to a single process on Windows')
    def test_ctrl_c_frees_the_port(self):
        self.start_starter()
        self.starter.send_signal(signal.SIGINT)
        self.assertEqual(self.starter.wait(10), 0)
        self.assertIsNone(status(self.port))

    @unittest.skipIf(sys.platform == 'win32', 'Windows SIGTERM terminates the process without running handlers')
    def test_closed_stdin_keeps_starter_running_until_sigterm(self):
        self.start_starter()
        self.starter.stdin.close()
        time.sleep(0.5)
        self.assertIsNone(self.starter.poll())
        self.assertEqual(status(self.port), SLEEPING_MOTD)

        self.starter.send_signal(signal.SIGTERM)
        self.assertEqual(self.starter.wait(10), 0)
        self.assertIsNone(status(self.port))

    @unittest.skipIf(sys.platform == 'win32', 'Windows SIGTERM terminates the process without running handlers')
    def test_sigterm_stops_running_server(self):
        self.start_starter()
        self.assertEqual(login(self.port, 'Waker'), 'Welcome Waker')
        self.assertEqual(status(self.port), 'Fake server')

        self.starter.send_signal(signal.SIGTERM)
        self.assertEqual(self.starter.wait(15), 0)
        self.assertIsNone(status(self.port))


if __name__ == '__main__':
    unittest.main()
