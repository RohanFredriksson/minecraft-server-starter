"""End-to-end tests for starter.py against tests/FakeServer.java.

Each test runs the starter in a temporary folder with a fake server on a free port.
Requires Python 3.8+ and Java 11+ on the PATH. Run with:

    python -m unittest discover -s tests -v
"""
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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL = 767

WAITING_MOTD = 'Server currently sleeping. Please login to wake me up!'
STARTING_MOTD = 'Server is waking up. Please wait a few seconds.'


def varint(value):
    out = bytearray()
    while True:
        if value & ~0x7F == 0:
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


def handshake(port, next_state):
    return frame(0x00, varint(PROTOCOL) + string('localhost') + port.to_bytes(2, 'big') + varint(next_state))


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


def status(port, host='127.0.0.1'):
    """Returns the server list description, or None if nothing is listening."""
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(handshake(port, 1) + frame(0x00))
            packet_id, read = read_packet(sock)
            description = json.loads(read_string(read))['description']
            sock.sendall(frame(0x01, (1234).to_bytes(8, 'big')))
            pong_id, read = read_packet(sock)
            if pong_id != 0x01 or read(8) != (1234).to_bytes(8, 'big'): return 'bad pong'
            return description['text'] if isinstance(description, dict) else description
    except (ConnectionRefusedError, ConnectionResetError):
        return None


def login(port, name, timeout=60):
    """Logs in like a 1.20.2+ client, answering the starter's keep-alives.

    Returns the disconnect message, which is "Welcome <name>" when the fake server accepted the login.
    """
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        sock.sendall(handshake(port, 2) + frame(0x00, string(name) + uuid.uuid3(uuid.NAMESPACE_DNS, name).bytes))
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


class StarterTest(unittest.TestCase):

    def start_starter(self, command='java FakeServer.java', hold_timeout=60):
        self.port = free_port()
        self.folder = tempfile.mkdtemp(prefix='starter-test-')
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

        shutil.copy(os.path.join(REPO, 'starter.py'), self.folder)
        shutil.copytree(os.path.join(REPO, 'scripts'), os.path.join(self.folder, 'scripts'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy(os.path.join(REPO, 'tests', 'FakeServer.java'), self.folder)

        with open(os.path.join(REPO, 'starter.properties')) as file:
            lines = file.read().splitlines()
        settings = {'command': command, 'hold-timeout': hold_timeout}
        lines = [f'{line.split("=")[0]}={settings[line.split("=")[0]]}' if line.split('=')[0] in settings else line
                 for line in lines]
        with open(os.path.join(self.folder, 'starter.properties'), 'w') as file:
            file.write('\n'.join(lines) + '\n')
        with open(os.path.join(self.folder, 'server.properties'), 'w') as file:
            file.write(f'server-ip=\nserver-port={self.port}\n')

        self.log_path = os.path.join(self.folder, 'starter.log')
        self.log = open(self.log_path, 'w')
        self.starter = subprocess.Popen([sys.executable, '-u', 'starter.py'], cwd=self.folder,
                                        stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(self.stop_starter)
        self.assertTrue(wait_for(lambda: status(self.port), 10), 'starter did not start listening')

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
        self.assertTrue(wait_for(lambda: status(self.port) == WAITING_MOTD, 20), 'starter did not reclaim the port')

    def test_status_while_sleeping(self):
        self.start_starter()
        self.assertEqual(status(self.port, '127.0.0.1'), WAITING_MOTD)
        if ipv6_available():
            self.assertEqual(status(self.port, '::1'), WAITING_MOTD)

    def test_wake_up_hand_over_and_sleep_again(self):
        self.start_starter()

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

        with open(os.path.join(self.folder, 'starter.properties')) as file:
            properties = file.read()
        self.assertIn('version=Fake', properties)
        self.assertIn('protocol=767', properties)

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

    def test_hold_timeout(self):
        self.start_starter(command='java FakeServer.java slow', hold_timeout=2)
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
        self.assertTrue(wait_for(lambda: status(self.port) == WAITING_MOTD, 10), 'starter did not reclaim the port')

    def test_command_not_found(self):
        self.start_starter(command='minecraft-server-starter-missing-command')
        self.assertEqual(login(self.port, 'Unlucky'), 'The server failed to start.')
        self.assertEqual(status(self.port), WAITING_MOTD)

    @unittest.skipIf(sys.platform == 'win32', 'Ctrl+C cannot be sent to a single process on Windows')
    def test_ctrl_c_frees_the_port(self):
        self.start_starter()
        self.starter.send_signal(signal.SIGINT)
        self.assertEqual(self.starter.wait(10), 0)
        self.assertIsNone(status(self.port))


if __name__ == '__main__':
    unittest.main()
