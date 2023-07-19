const mc = require('minecraft-protocol');
const which = require('which');
const child_process = require('child_process');

let redir; try {redir = which.sync('redir');} catch (error) {console.error('redir executable not found.'); process.exit(1);}
//let java;  try {java = which.sync('java');}   catch (error) {console.error('java executable not found.');  process.exit(1);}

class Proxy {

    constructor(input, output) {
        this.process = null;
        this.set(input, output);
    }

    set(input, output) {
        this.destroy();
        this.process = child_process.spawn(redir, [`--lport=${input}`, `--cport=${output}`]);
    }

    destroy() {
        if (this.process != null) {this.process.kill();}
    }

}

const proxy = new Proxy(25565, 25566);

const server = mc.createServer({
    'online-mode': true,
    encryption: true,
    host: '0.0.0.0',
    port: 25566,
    version: '1.20.1'
});

server.on('connection', function(client) {

});

server.on('login', function(client) {
    client.end("Disconnected");
});



