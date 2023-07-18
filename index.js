const mc = require('minecraft-protocol');
const server = mc.createServer({
    'online-mode': true,   // optional
    encryption: true,      // optional
    host: '0.0.0.0',       // optional
    port: 25565,           // optional
    version: '1.20.1'
});

server.on('connection', function(client) {
    console.log("CONNECTION");
});

server.on('login', function(client) {
    console.log("LOGIN");
    client.end("hes cheeeeeating");
});