const mc = require('minecraft-protocol');
const child_process = require('child_process');

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

var state = 'waiting';

async function ping() {
    try {result = await mc.ping({host: '127.0.0.1', port: 25567}); result.online = true; return result;} 
    catch {result = {online: false}; return result;}
}

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

    data = await ping();
    if (!data.online) {
        
        client.end("Server waking up, please rejoin in a minute :)");
        if (state == 'waiting') {
        
            // Start the server.
            state = 'starting';
            //p = child_process.spawn('screen', ['-dmS', 'minecraft', 'java', '-Xms1G', '-Xmx1G', '-jar', 'server.jar', 'nogui']);
            child_process.spawn('java', ['-Xms1G', '-Xmx1G', '-jar', 'server.jar', 'nogui']);

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

    client.end("Server is already up.");
});
