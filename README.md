# Minecraft Server Starter

## Description
This is a cross-platform Minecraft Java Edition server tool that can automatically start and stop a Minecraft server depending on user activity. This allows for an energy-efficient approach to running Minecraft Servers which have 24/7 uptime and inconsistent user activity. When players are not on the server, the server sleeps and when a player decides to join, the server starts back up and is running within 30 seconds.

## Requirements
This codebase has the requires the following programs to function:
- [java](https://www.java.com/en/)
- [python3](https://www.python.org/)

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
5. Next we will need to modify the actual Minecraft server port number to something that is not the final port that we will be hosting the server on, since we will be using a TCP proxy. In this case, I changed the port number for the server to 25567. To change the port number change the following lines indicated with an arrow below in the **server.properties** file.
```
#Minecraft server properties
#Wed Jul 19 23:53:54 AEST 2023
.
.
.
query.port=25567 <--
.
.
.
server-ip=
server-port=25567 <--
.
.
.
```
6. Now we should be able to run the server using the default parameters. To run the server run the following command:
```bash
python3 starter.py
```
This will start the server in sleep mode. To start the playing start up Minecraft, then log in to the server using the Minecraft Client. This will then start the server. Log in to the server again and it should be running ready to play on! Feel free to tune the parameters to your liking by altering the values in the **.properties** files.
## Screenshots


## Contributions
Contributions are welcome! If you find any bugs or have suggestions for improvements, feel free to open an issue or submit a pull request on GitHub.
