const mc = require('minecraft-protocol');
const child_process = require('child_process');

class MinecraftServer {

    constructor() {
        this.process = null;
    }

    start() {
        this.stop();
        this.process = child_process.spawn('java', ['-Xms1G', '-Xmx1G', '-jar', 'server.jar', 'nogui']);
    }

    stop() {
        if (this.process != null) {this.process.stdin.write('stop\n'); this.process.stdin.end();}
    }

}

class Proxy {

    constructor(input, output) {
        this.process = null;
        this.set(input, output);
    }

    set(input, output) {
        this.destroy();
        this.process = child_process.spawn('redir', [`--lport=${input}`, `--cport=${output}`]);
    }

    destroy() {
        if (this.process != null) {this.process.kill();}
    }

}

const proxy = new Proxy(25565, 25566);
const minecraft = new MinecraftServer();
var state = 'waiting';

function handle(signal) {
    minecraft.process.on('exit', (c, s) => {process.exit(0);});   
    minecraft.stop();
}

process.on('SIGINT', () => handle('SIGINT'));
process.on('SIGTERM', () => handle('SIGTERM'));

const server = mc.createServer({
    'online-mode': true,
    encryption: true,
    host: '0.0.0.0',
    port: 25566,
    version: '1.20.1'
});

server.on('connection', function(client) {

});

server.on('login', async function(client) {

    async function ping() {
        try {result = await mc.ping({host: '127.0.0.1', port: 25567}); result.online = true; return result;} 
        catch {result = {online: false}; return result;}
    }

    data = await ping();
    if (!data.online) {
        
        client.end("Server waking up... Please rejoin in few seconds.");
        if (state == 'waiting') {
        
            // Start the server.
            state = 'starting';
            minecraft.start();

            // Wait for the server to start.
            while (true) {
                data = await ping();
                if (data.online) {break;}
                await new Promise((resolve) => setTimeout(resolve, 5000));
            }

            // Swap the proxy to the server.
            state = 'started';
            proxy.set(25565, 25567);

            // See if we can sleep the server.

        }

    } 
    
    else {
        client.end("Server has already started.");
        state = 'started';
        proxy.set(25565, 25567);
    }

});
