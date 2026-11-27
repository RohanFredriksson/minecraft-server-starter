import os
import re

from . import properties
from .minecraft_server import split_command

# Written to starter.properties when it does not exist. The defaults are read from it too.
DEFAULT_FILE = r"""# Minecraft Server Starter settings, described in more detail in README.md.
# The starter reads this file when it starts, so restart it after making changes.
# Delete this file to recreate it with the default settings.

# Command that starts the Minecraft server, run from this folder without a shell.
# Set the memory (-Xms/-Xmx) and jar name here; quote paths that contain spaces.
# The server must run in the foreground with its console attached: the starter
# reads it to see when the server is ready and types "stop" to shut it down.
command=java -Xms1G -Xmx1G -jar server.jar nogui

# Seconds the server must be empty before it is stopped.
stop-when-empty-seconds=180

# Seconds a player who wakes the server waits for it to finish starting. If it
# takes longer, they are disconnected with join-timeout-message, and the server
# keeps starting so they can join again shortly.
join-timeout-seconds=120

# The messages below may use \n for a new line and \u00A7 for the section sign
# used by formatting codes, like the motd in server.properties.

# Server list message while the server is stopped.
sleeping-motd=Server currently sleeping. Please login to wake me up!

# Server list message while the server is starting.
starting-motd=Server is waking up. Please wait a few seconds.

# Shown to a waiting player who is disconnected after join-timeout-seconds.
join-timeout-message=The server is taking longer than usual to wake up. Please try again in a moment.

# Shown to waiting players if the server exits or cannot be run before it is ready.
start-failed-message=The server failed to start.
"""

DEFAULTS = properties.parse(DEFAULT_FILE)
DURATIONS = ('stop-when-empty-seconds', 'join-timeout-seconds')
MESSAGES = ('sleeping-motd', 'starting-motd', 'join-timeout-message', 'start-failed-message')
ESCAPE = re.compile(r'\\(?:u([0-9a-fA-F]{4})|(.))')


class SettingsError(Exception):
    pass


def unescape(text):
    """Applies the \\n, \\uXXXX and \\\\ escapes that server.properties supports."""

    def replace(match):
        if match.group(1): return chr(int(match.group(1), 16))
        return {'n': '\n', '\\': '\\'}.get(match.group(2), match.group(0))

    return ESCAPE.sub(replace, text)


def number(value, default):
    try: return int(value)
    except (TypeError, ValueError): return default


def read(path):
    try: return properties.load(path)
    except OSError as error: raise SettingsError(f'Could not read {path}: {error}')


def load_starter_settings(path):
    """Reads the starter's settings, creating the file with the defaults if it is missing."""
    if not os.path.exists(path):
        try:
            with open(path, 'w', encoding='utf-8') as file:
                file.write(DEFAULT_FILE)
        except OSError as error:
            raise SettingsError(f'Could not create {path}: {error}')
        print(f'Created {path} with the default settings.')

    values = read(path)
    unknown = [key for key in values if key not in DEFAULTS]
    for key in unknown:
        print(f"Warning: ignoring unknown setting '{key}' in {path}.")
    if unknown:
        print(f'Delete {path} to recreate it with every available setting described.')

    settings = {key: values.get(key, default) for key, default in DEFAULTS.items()}
    problems = []

    for key in DURATIONS:
        value = settings[key]
        settings[key] = number(value, 0)
        if settings[key] < 1:
            problems.append(f'{key} must be a whole number of seconds, at least 1 (not "{value}").')

    if not settings['command'].strip():
        problems.append('command must not be empty.')
    else:
        try: split_command(settings['command'])
        except ValueError as error: problems.append(f'command could not be read: {error}.')

    for key in MESSAGES:
        settings[key] = unescape(settings[key])

    if problems:
        raise SettingsError('\n  '.join([f'Invalid settings in {path}:'] + problems))
    return settings


def load_server_settings(path):
    """Reads what the starter needs from the Minecraft server's own settings."""
    if not os.path.exists(path):
        raise SettingsError(f'{path} was not found. Run the starter from the Minecraft server folder, '
                            'after starting the server once to create it.')
    values = read(path)

    # Like Minecraft, use the default port if the value is not a number.
    port = number(values.get('server-port'), 25565)
    if not 0 < port < 65536:
        raise SettingsError(f'server-port in {path} must be between 1 and 65535 (not "{port}").')

    if values.get('enable-status', 'true').lower() != 'true':
        print(f'Warning: enable-status is off in {path}. The starter counts players with status '
              'requests, so the server will not be stopped when it is empty.')
    if (values.get('prevent-proxy-connections', 'false').lower() == 'true'
            and values.get('online-mode', 'true').lower() == 'true'):
        print(f'Warning: prevent-proxy-connections is on in {path}. Players who wake the server are '
              'connected through the starter, so Minecraft will reject their logins.')

    return {
        'server-ip': values.get('server-ip', ''),
        'server-port': port,
        'max-players': number(values.get('max-players'), 20),
    }
