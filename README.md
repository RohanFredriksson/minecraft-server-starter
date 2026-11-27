# Minecraft Server Starter

## Description
This is a cross-platform Minecraft Java Edition server tool that automatically starts and stops a Minecraft server depending on player activity. When nobody is online, it stops the server process; when a player joins, it starts the server and keeps them waiting until it is ready. Startup time depends on the server and hardware. The host computer must stay awake to receive connections.

## Requirements
The following programs are required; no third-party Python packages are needed:
- [Java](https://www.java.com/en/) compatible with your Minecraft server version.
- [Python 3.8 or newer](https://www.python.org/).

## Getting Started
1. Ensure the required programs are installed. These programs are listed above.
2. Clone or download this repository. This can be achieved with the following command.
```bash
git clone https://github.com/RohanFredriksson/minecraft-server-starter.git
```
3. Download the Minecraft Server jar file for the version you wish to use. This can be done through the Minecraft Launcher or through the official [Minecraft Website](https://www.minecraft.net/en-us). Place the server.jar file into the root of this repository.
4. Run the server.jar file to initialise the server. You will also have to agree to the Minecraft End User License Agreement by altering the **eula.txt** file. Your eula.txt file should look something like this.
```
#By changing the setting below to TRUE you are indicating your agreement to our EULA (https://aka.ms/MinecraftEULA).
#Wed Jul 19 18:00:07 AEST 2023
eula=true
```
5. Stop the Minecraft server after initial setup. Keep its normal public `server-port` in **server.properties** (usually `25565`); no separate proxy or starter ports are needed. Then run the starter from the server folder:
```bash
python3 starter.py
```
On its first run, the starter creates **starter.properties** with the default settings, each described by a comment (see [Settings](#settings)). The default `command` runs `server.jar` with 1 GB of memory. To change it, stop the starter with Ctrl+C, edit **starter.properties**, and run the starter again.

The starter waits in sleep mode on the server's own address and port, taken from `server-ip` and `server-port` in **server.properties**, so players connect exactly as they would to the server itself. When a player joins, the starter starts the server and keeps them on the loading screen until it is ready. It releases the listening port for the server to take over, then relays the waiting player's connection. New connections go directly to the running server. After a period with nobody online the server is stopped and the starter takes the port back.

Players held during startup remain connected through the starter for that session and appear to the server as connecting from the starter's local address. Players who join after startup connect directly with their own addresses.

Commands typed into the starter are forwarded to the Minecraft server while it is running. Press Ctrl+C to stop both. When running as a background service, closed standard input does not stop the starter; send it a shutdown signal (such as SIGTERM on Linux or macOS) to stop it cleanly.

If `server-ip` is blank, the starter listens on all network interfaces (IPv4 and IPv6). To connect from another device, allow the port through the host firewall; internet connections may also require port forwarding on your router.

### Settings
The starter reads its settings from **starter.properties** in the server folder when it starts, so restart it after making changes. The file is created with the defaults on the first run and the starter never changes it, so your edits and comments are kept. Delete it to get a fresh copy with every setting described.

| Setting | Default | Description |
| --- | --- | --- |
| `command` | `java -Xms1G -Xmx1G -jar server.jar nogui` | Command that starts the Minecraft server in the server folder. Set the memory (`-Xms`, `-Xmx`) and jar name here, and quote paths that contain spaces. It is run directly rather than through a shell, so shell features such as `&&`, pipes and variables are not available. The server must run in the foreground: the starter reads its console to see when it is ready and types `stop` to shut it down. |
| `stop-when-empty-seconds` | `180` | Seconds the server must be empty before the starter stops it. Players are counted every 5 seconds, so it stops up to about 10 seconds after this. |
| `join-timeout-seconds` | `120` | Seconds a player who wakes the server is kept on the loading screen while it starts. If it takes longer, they are disconnected with `join-timeout-message` and can join again once it is running, as the server keeps starting. Minecraft clients give up after 30 seconds without traffic, so the starter keeps them connected while they wait. |
| `sleeping-motd` | `Server currently sleeping. Please login to wake me up!` | Server list message while the server is stopped. |
| `starting-motd` | `Server is waking up. Please wait a few seconds.` | Server list message while the server is starting. |
| `join-timeout-message` | `The server is taking longer than usual to wake up. Please try again in a moment.` | Disconnect message for a player still waiting after `join-timeout-seconds`. |
| `start-failed-message` | `The server failed to start.` | Disconnect message for waiting players if the server stops, or cannot be run, before it is ready. |

- Each setting is written as `name=value` on its own line. Lines starting with `#` are comments, and spaces around names and values are ignored. Messages do not need quotes; any quotes are shown as written.
- `stop-when-empty-seconds` and `join-timeout-seconds` must be whole numbers of at least 1.
- Messages can use `\n` to start a second line and `\u00A7` for the `§` sign of [formatting codes](https://minecraft.wiki/w/Formatting_codes), like the `motd` in **server.properties**. For example, `sleeping-motd=\u00A7eAsleep\n\u00A77Join to wake the server up`. The file is read as UTF-8, so `§` can also be typed directly.
- Settings that are left out use their defaults. Unknown settings, such as names from older versions, are reported when the starter starts, and invalid values stop it with a message explaining the problem.

### Server settings
The starter also reads these settings from the Minecraft server's **server.properties** when it starts:

| Setting | How the starter uses it |
| --- | --- |
| `server-ip`, `server-port` | The address the starter listens on while the server is stopped, so players always use the server's normal address. |
| `max-players` | Shown in the server list while the server is stopped. |
| `enable-status` | Must be `true`, the default. The starter asks the running server how many players are online, so without it the server is never stopped. |
| `prevent-proxy-connections` | Must be `false`, the default, when `online-mode` is `true`. Players who wake the server are connected through the starter, so Minecraft would reject their logins. |

While the server is stopped, the server list also shows its **server-icon.png** and the version it reported the last time it ran, which the starter keeps in **starter-cache.json**. Until the server has run once, every client version is shown as compatible.

Minecraft's own `pause-when-empty-seconds` (1.21.2 and newer) pauses the game while the server keeps running. It works alongside the starter, which stops the server entirely.

### Updating from an older version
Older versions kept **starter.properties** in the repository and rewrote it on every run, so `git pull` refuses to remove it. Rename it before pulling, and the starter will create a new one on its next run:
```bash
mv starter.properties starter.properties.old
git pull
```
Then copy any values you changed into the new file. The starter no longer needs a port of its own, so set `server-port` in **server.properties** back to the port players connect to. `timeout` (in minutes) is now `stop-when-empty-seconds`, `waiting-motd` is now `sleeping-motd`, and `starting-reason` is now `join-timeout-message`. `server-port`, `starter-port`, `version` and `protocol` were removed.

### Compatibility
- Python 3.8 or newer is required.
- Players must use Minecraft 1.13 or newer to be held while the server starts; older login attempts are disconnected with a message. Transfer-originated logins are passed to the server for its transfer policy.
- Modern and legacy server-list pings are supported. Pre-1.6 pings may wait up to 10 seconds because their prefixes overlap modern packet framing.
- The starter detects startup progress from console messages, independently of logger prefixes. Vanilla and Paper-style formats are covered by the tests; other forks may need verification.

## Testing
The tests run the starter against a small fake server (`tests/FakeServer.java`), so no Minecraft download is needed. They need Python and Java 11 or newer:
```bash
python3 -m unittest discover -s tests -v
```
GitHub Actions runs them on Linux (x64 and ARM), Windows and macOS for every push and pull request.

## Screenshots


## Contributions
Contributions are welcome! If you find any bugs or have suggestions for improvements, feel free to open an issue or submit a pull request on GitHub.

Have a question about using it? Ask in [Discussions](https://github.com/RohanFredriksson/minecraft-server-starter/discussions/categories/q-a).
