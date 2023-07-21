const mc = require('minecraft-protocol');
const { MinecraftServer } = require('./src/minecraft-server');
const { Proxy } = require('./src/proxy');
const { properties } = require('./src/properties');
const { ping, line } = require('./src/util');

console.log(line);
console.log('Server sleeping. Waiting for login attempt...')

var state = 'waiting';
const proxy = new Proxy(properties['server-port'], properties['minecraft-server-starter-port']);
const server = new MinecraftServer(properties['minecraft-server-port'], properties['command']);

server.on('start', (server) => {
    console.log(line);
    process.stdin.pipe(server.process.stdin);
    server.process.stdout.pipe(process.stdout);
    server.process.stderr.pipe(process.stderr);
});

server.on('ready', async (server) => {
    
    state = 'started';
    proxy.set(properties['server-port'], properties['minecraft-server-port']);

    // See if we can sleep the server.
    var count = 0
    while (true) {
        data = await ping('127.0.0.1', properties['minecraft-server-port']);
        if (!data.online) {break;}
        if (data.players.online == 0) {count++;}
        else {count = 0;}
        if (count >= properties['timeout']) {server.stop(); break;}
        await new Promise((resolve) => setTimeout(resolve, 60000));
    }

});

server.on('exit', (server) => {
    console.log(line);
    console.log('Server sleeping. Waiting for login attempt...')
    state = 'waiting';
    process.stdin.unpipe(server.process.stdin);
    proxy.set(properties['server-port'], properties['minecraft-server-starter-port']);
});

const starter = mc.createServer({
    'online-mode': true,
    encryption: true,
    host: '0.0.0.0',
    port: properties['minecraft-server-starter-port'],
    version: properties['version'],
    motd: properties['motd']
});

starter.on('connection', function(client) {

});

starter.on('login', async function(client) {

    client.end("Server waking up... Please rejoin in few seconds.");

    const data = await ping('127.0.0.1', properties['minecraft-server-port']);
    if (!data.online && state == 'waiting') {
        console.log(`${client.username} started the server.`);
        state = 'starting';
        server.start();
    } 

});