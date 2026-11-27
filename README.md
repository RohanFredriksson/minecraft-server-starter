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
5. Stop the Minecraft server after initial setup. Keep its normal public `server-port` in **server.properties** (usually `25565`); no separate proxy or starter ports are needed. Check that `command` in **starter.properties** starts your server jar, then run the starter from that folder:
```bash
python3 starter.py
```
The starter waits in sleep mode on the server's own address and port, taken from `server-ip` and `server-port` in **server.properties**, so players connect exactly as they would to the server itself. When a player joins, the starter starts the server and keeps them on the loading screen until it is ready. It releases the listening port for the server to take over, then relays the waiting player's connection. New connections go directly to the running server. After a period with nobody online the server is stopped and the starter takes the port back.

Players held during startup remain connected through the starter for that session and appear to the server as connecting from the starter's local address. Players who join after startup connect directly with their own addresses.

Commands typed into the starter are forwarded to the Minecraft server while it is running. Press Ctrl+C to stop both. When running as a background service, closed standard input does not stop the starter; send it a shutdown signal (such as SIGTERM on Linux or macOS) to stop it cleanly.

If `server-ip` is blank, the starter listens on all network interfaces (IPv4 and IPv6). To connect from another device, allow the port through the host firewall; internet connections may also require port forwarding on your router.

### Settings
The starter is configured with **starter.properties**:

| Setting | Description |
| --- | --- |
| `command` | Command used to start the Minecraft server. |
| `timeout` | Empty-server checks before stopping, performed once per minute while the server runs. Timing is approximate; a check with players online resets the count. |
| `hold-timeout` | Seconds a joining player is kept waiting for the server to start before being disconnected with `starting-reason`. Minecraft clients give up after 30 seconds without traffic, so the starter keeps them connected while they wait. |
| `waiting-motd` | Server list message shown while the server is asleep. |
| `starting-motd` | Server list message shown while the server is starting. |
| `starting-reason` | Message shown to a player if the server does not start within `hold-timeout`. |
| `version`, `protocol` | Version shown in the server list while asleep. Updated automatically each time the server starts. |

### Compatibility
- Python 3.8 or newer is required.
- Players must use Minecraft 1.13 or newer to be held while the server starts.
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
