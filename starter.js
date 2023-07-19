const mc = require('minecraft-protocol');
const net = require('net');
const parent = parseInt(process.argv[2]);

const server = mc.createServer({
    'online-mode': true,
    encryption: true,
    host: '0.0.0.0',
    port: 25566,
    version: '1.20.1'
});

server.on('connection', function(client) {
    console.log("CONNECTION");
});

server.on('login', function(client) {
    console.log(client.uuid);
    client.end("closed connection");
});

const client = net.createConnection(parent, '127.0.0.1', () => {
    console.log("Connected");
    client.write(`Hello from client!`);
});

client.on("data", (data) => {
    console.log(`Received: ${data}`);
});

client.on("error", (error) => {
    console.log(`Error: ${error.message}`);
});

client.on("close", () => {
    console.log("Connection closed");
});