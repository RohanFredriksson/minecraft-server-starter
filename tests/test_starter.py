"""End-to-end tests for starter.py against tests/FakeServer.java.

Each test runs the starter in a temporary folder with a fake server on a free port.
Requires Python 3.8+ and Java 11+ on the PATH. Run with:

    python -m unittest discover -s tests -v
"""
import base64
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

SLEEPING_MOTD = 'Server currently sleeping. Please login to wake me up!'
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


def handshake(port, next_state, protocol=PROTOCOL):
    return frame(0x00, varint(protocol) + string('localhost') + port.to_bytes(2, 'big') + varint(next_state))


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

    def write(self, name, text):
        with open(os.path.join(self.folder, name), 'w', encoding='utf-8') as file:
            file.write(text)

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
        self.assertEqual(login(self.port, 'Visitor'), 'Welcome Visitor')
        self.assertTrue(wait_for(lambda: status(self.port) == SLEEPING_MOTD, 20), 'empty server was not stopped')
        self.assertIn('Server empty for 1 seconds, stopping it.', self.read('starter.log'))

    def test_sleeping_status_mirrors_server(self):
        self.prepare('max-players=7\n')
        self.write('starter.properties', 'command=java FakeServer.java\nsleeping-motd=Line one\\nLine two \\u00A7aGreen\n')
        icon = b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR' + (64).to_bytes(4, 'big') * 2 + bytes(20)
        with open(os.path.join(self.folder, 'server-icon.png'), 'wb') as file:
            file.write(icon)
        self.launch()

        response = status_response(self.port, protocol=776)
        self.assertEqual(response['description']['text'], 'Line one\nLine two \u00a7aGreen')
        self.assertEqual(response['players']['max'], 7)
        self.assertEqual(response['favicon'], 'data:image/png;base64,' + base64.b64encode(icon).decode())
        # Before the server has run, its version is unknown, so any client is shown as compatible.
        self.assertEqual(response['version']['protocol'], 776)

        # Minecraft only uses 64x64 icons, so other sizes are left out.
        with open(os.path.join(self.folder, 'server-icon.png'), 'wb') as file:
            file.write(icon[:16] + (32).to_bytes(4, 'big') * 2 + icon[24:])
        self.assertNotIn('favicon', status_response(self.port))

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
