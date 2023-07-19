const mc = require('minecraft-protocol');
const server = mc.createServer({
    'online-mode': true,   // optional
    encryption: true,      // optional
    host: '0.0.0.0',       // optional
    port: 25566,           // optional
    version: '1.20.1'
});

server.on('connection', function(client) {
    console.log("CONNECTION");
});

server.on('login', function(client) {
    console.log(client.uuid);
    client.end("closed connection");
});