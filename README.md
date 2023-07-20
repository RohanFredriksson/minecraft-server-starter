# Minecraft Server Starter

## Description
This is a Minecraft Java Edition server tool built for POSIX systems, that can automatically start and stop a Minecraft server depending on user activity. 

## Requirements
This codebase has the requires the following programs to function:
- [java](https://www.java.com/en/)
- [redir](https://linux.die.net/man/1/redir)
- [nodejs](https://nodejs.org/en)
- [npm](https://www.npmjs.com/)

## Getting Started
1. Ensure the required programs are installed. These programs are listed above.
2. Clone or download this repository. This can be achieved with the following command.
```bash
git clone https://github.com/RohanFredriksson/minecraft-server-starter.git
```
3. Install all required node modules using the following command.
```
npm install
```
4. Download the Minecraft Server jar file for the version you wish to use. This can be done through the Minecraft Launcher or through the official [Minecraft Website](https://www.minecraft.net/en-us). Place the server.jar file into the root of this repository.
5. Run the server.jar file to initialise the server. You will also have to agree to the Minecraft End User License Agreement by altering the **eula.txt** file. Your eula.txt file should look something like this.
```
#By changing the setting below to TRUE you are indicating your agreement to our EULA (https://aka.ms/MinecraftEULA).
#Wed Jul 19 18:00:07 AEST 2023
eula=true
```
6. Next we will need to modify the actual Minecraft server port number to something that is not the final port that we will be hosting the server on, since we will be using a TCP proxy. In this case I changed the port number for the server to 25567. To change the port number change the following lines indicated with an arrow below in the **server.properties** file.
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
## Example
```javascript
```

## Features
Minecraft Server Starter provides the following features:
- tmp

## Contributions
Contributions are welcome! If you find any bugs or have suggestions for improvements, feel free to open an issue or submit a pull request on GitHub.
