const fs = require('fs');
const mc = require('minecraft-protocol');
const child_process = require('child_process');
const properties_parser = require('properties-parser');

// Read server properties
const server_properties = properties_parser.parse(fs.readFileSync('server.properties', 'utf-8'));
const starter_properties = properties_parser.parse(fs.readFileSync('starter.properties', 'utf-8'));
server_properties['server-port'] = Number(server_properties['server-port']);
starter_properties['server-port'] = Number(starter_properties['server-port']);
starter_properties['starter-port'] = Number(starter_properties['starter-port']);
starter_properties['timeout'] = Number(starter_properties['timeout']);

// Prints a line.
function line() {
    try {console.log('-'.repeat(process.stdout.columns));}
    catch {console.log('-'.repeat(80));}
}

// Class that handles TCP proxy child process.
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

// Class that handles Minecraft Server child process.
class MinecraftServer {

    constructor() {
        this.process = null;
    }

    start() {
        
        this.stop();
        line();

        const args = starter_properties['start-command'].split(/\s+/);
        const command = args.shift();
        this.process = child_process.spawn(command, args);
        
        process.stdin.pipe(this.process.stdin);
        this.process.stdout.pipe(process.stdout);
        this.process.stderr.pipe(process.stderr);

        this.process.on('exit', (c, s) => {
            line();
            console.log('Server sleeping. Waiting for login attempt...')
            state = 'waiting';
            process.stdin.unpipe(this.process.stdin);
            proxy.set(starter_properties['server-port'], starter_properties['starter-port']);
        });   

    }

    stop() {
        if (this.process != null) {
            this.process.stdin.write('stop\n'); 
            this.process.stdin.end();
        }
    }

    destroy() {
        if (this.process != null) {this.process.kill();}
    }

}

// Destroy all children on termination.
async function handle(signal) {
    proxy.destroy();
    minecraft.destroy();
    process.exit(0);
}

process.on('SIGINT', () => handle('SIGINT'));
process.on('SIGTERM', () => handle('SIGTERM'));

// Initialise the state.
line();
console.log('Server sleeping. Waiting for login attempt...')
var state = 'waiting';
const proxy = new Proxy(starter_properties['server-port'], starter_properties['starter-port']);
const minecraft = new MinecraftServer();

// Configure the server starter.
const server = mc.createServer({
    'online-mode': true,
    encryption: true,
    host: '0.0.0.0',
    port: starter_properties['starter-port'],
    version: starter_properties['version']
});

server.on('connection', function(client) {

});

server.on('login', async function(client) {

    async function ping() {
        try {result = await mc.ping({host: '127.0.0.1', port: server_properties['server-port']}); result.online = true; return result;} 
        catch {result = {online: false}; return result;}
    }

    data = await ping();
    if (!data.online) {
        
        client.end("Server waking up... Please rejoin in few seconds.");
        if (state != 'starting') {
        
            // Log the start up.
            console.log(`${client.username} started the server.`);

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
            proxy.set(starter_properties['server-port'], server_properties['server-port']);

            // See if we can sleep the server.
            count = 0
            while (true) {
                data = await ping();
                if (!data.online) {break;}
                if (data.players.online == 0) {count++;}
                else {count = 0;}
                if (count >= starter_properties['timeout']) {minecraft.stop(); break;}
                await new Promise((resolve) => setTimeout(resolve, 60000));
            }

        }

    } 
    
    else {
        client.end("Server has already started.");
        state = 'started';
        proxy.set(starter_properties['server-port'], server_properties['server-port']);
    }

});

server['motd'] = starter_properties['motd'];