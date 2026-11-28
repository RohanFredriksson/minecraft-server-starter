import base64
import threading
import json
import signal
import sys
import time

from scripts.minecraft_server import MinecraftServer
from scripts.protocol_server import ProtocolServer
from scripts.settings import SettingsError, load_server_settings, load_starter_settings
from scripts.ping import ping

SLEEPING = 0
STARTING = 1
RUNNING = 2
STOPPED = 3

IDLE_CHECK_INTERVAL = 5
# The longest server list response clients accept.
MAX_STATUS_LENGTH = 32767
CACHE_FILE = 'starter-cache.json'
ICON_FILE = 'server-icon.png'

# Read server.properties first, so nothing is created when run outside a server folder.
try:
    server_settings = load_server_settings('server.properties')
    settings = load_starter_settings('starter.properties')
except SettingsError as error:
    print(error, file=sys.stderr)
    sys.exit(1)

# The Minecraft server owns the public port while it runs, so the starter shares its address.
server_ip = server_settings['server-ip']
server_port = server_settings['server-port']
local_ip = server_ip if server_ip not in ('', '0.0.0.0', '::') else '127.0.0.1'

def checked_version(version):
    if isinstance(version, dict) and isinstance(version.get('name'), str) and isinstance(version.get('protocol'), int):
        return {'name': version['name'], 'protocol': version['protocol']}
    return None

def load_cached_version():
    """The version the server reported the last time it ran, if known."""
    try:
        with open(CACHE_FILE, encoding='utf-8') as file:
            cache = json.load(file)
    except (OSError, ValueError):
        return None
    return checked_version(cache.get('version')) if isinstance(cache, dict) else None

def server_icon():
    try:
        with open(ICON_FILE, 'rb') as file:
            icon = file.read()
    except OSError:
        return None

    # Like Minecraft, only use 64x64 PNG images.
    if icon[:8] != b'\x89PNG\r\n\x1a\n' or icon[16:24] != (64).to_bytes(4, 'big') * 2: return None
    return 'data:image/png;base64,' + base64.b64encode(icon).decode('ascii')

class Boot:

    def __init__(self):
        self.finished = threading.Event()
        self.ready = False

minecraft_server = MinecraftServer(settings['command'])
state = SLEEPING
boot = None
lock = threading.Lock()
cached_version = load_cached_version()

def status(client_protocol):

    # Depending on the state, we need to show different motds.
    description = settings['sleeping-motd']
    if state == STARTING: description = settings['starting-motd']

    # Until the server has run once its version is unknown, so show it as compatible.
    version = cached_version or {"name": "Unknown", "protocol": client_protocol}

    # Required response to client to show status to pinging clients.
    response = {
        "version": version,
        "players": { "max": server_settings["max-players"], "online": 0, "sample": [] },
        "description": { "text": description },
        "enforcesSecureChat": False
    }
    icon = server_icon()
    if icon: response["favicon"] = icon

    # The JSON escapes any non-ASCII text, so its length is what clients count. Leave out icons that do not fit.
    text = json.dumps(response)
    if len(text) > MAX_STATUS_LENGTH:
        response.pop("favicon", None)
        text = json.dumps(response)
    return text

def on_login(player):

    global state, boot

    with lock:

        if state == STOPPED:
            player.close()
            return

        if state == SLEEPING:
            print('Server is starting...')
            print('-'*80)
            boot = Boot()
            state = STARTING

            try: minecraft_server.start()
            except OSError as error:
                print(f'Could not start the server: {error}')
                state = SLEEPING
                boot.finished.set()

        player_boot = boot

    # Keep the player on the loading screen until the server is ready, then pass them over.
    if not player.hold(player_boot.finished, settings['join-timeout-seconds']):
        player.disconnect(settings['join-timeout-message'])
    elif not player_boot.ready:
        player.disconnect(settings['start-failed-message'])
    else:
        player.hand_over(local_ip, server_port)

protocol_server = ProtocolServer(server_ip, server_port, status, on_login)

def on_binding():
    # Free the port at the last moment so the server can take it over.
    protocol_server.release()

def on_ready():

    global state, cached_version
    with lock:
        state = RUNNING
        boot.ready = True
        boot.finished.set()

    # Stop the server once nobody has been online for long enough.
    def stop_when_empty():

        limit = settings['stop-when-empty-seconds']
        empty_since = None
        warned = False
        while True:

            deadline = time.monotonic() + min(IDLE_CHECK_INTERVAL, limit)
            while time.monotonic() < deadline:
                if state != RUNNING: return
                time.sleep(0.1)

            response = ping(local_ip, server_port)
            if not response['online']:
                print('Could not ping the server for its idle status; will retry.')
                continue

            # The player count is optional, and some plugins hide it. Never mistake an unknown count for empty.
            players = response.get('players')
            online = players.get('online') if isinstance(players, dict) else None
            if not isinstance(online, int):
                if not warned:
                    print('The server does not report how many players are online, so it will not be stopped when empty.')
                    warned = True
                empty_since = None
                continue

            # Count from the first empty check, since players may have only just left.
            now = time.monotonic()
            if online > 0: empty_since = None
            elif empty_since is None: empty_since = now
            elif now - empty_since >= limit:
                print(f'Server empty for {limit} seconds, stopping it.')
                minecraft_server.stop()
                return

    thread = threading.Thread(target=stop_when_empty, args=())
    thread.start()

    # Remember the version to show in the server list while the server sleeps.
    response = ping(local_ip, server_port)
    version = checked_version(response.get("version"))
    if version is None: return

    cached_version = version
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as file:
            json.dump({"version": version}, file)
    except OSError as error:
        print(f'Could not save {CACHE_FILE}: {error}')

def on_exit():

    global state
    with lock:
        if state == STOPPED: return
        state = SLEEPING
        boot.finished.set()

    print('-'*80)
    print('Server sleeping. Waiting for login attempt...')
    protocol_server.open()

minecraft_server.on('binding', on_binding)
minecraft_server.on('ready', on_ready)
minecraft_server.on('exit', on_exit)

protocol_server.open()
print('-'*80)
print('Server sleeping. Waiting for login attempt...')

def handle_shutdown_signal(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

def shutdown():
    global state
    with lock:
        state = STOPPED
    protocol_server.release()
    minecraft_server.stop_and_wait()

try:
    while True:
        try:
            line = input()
        except EOFError:
            print('Standard input is closed; waiting for a shutdown signal.')
            while state != STOPPED:
                time.sleep(1)
            break
        minecraft_server.enter_command(f"{line}\n")
except KeyboardInterrupt:
    print('-'*80)
finally:
    shutdown()
