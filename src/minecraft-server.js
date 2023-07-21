const child_process = require('child_process');

module.exports = {

    MinecraftServer : class MinecraftServer {

        constructor(port, command) {
            this.port = port;
            this.command = command;
            this.process = null;
            this.startCallbacks = [];
            this.readyCallbacks = [];
            this.exitCallbacks = [];
        }
    
        start() {

            if (this.process != null) {throw new Error("Minecraft server has already started.");}

            const a = this.command.split(/\s+/);
            const c = a.shift();
            this.process = child_process.spawn(c, a);
            this.startCallbacks.forEach(callback => callback(this));
            this.process.on('exit', (c, s) => {this.exitCallbacks.forEach(callback => callback(this)); this.process = null;});

            this.process.stdout.on('data', (data) => {
                
                const output = data.toString();
                const lines = output.split('\n');
                const pattern = /^\[\d{2}:\d{2}:\d{2}\] \[Server thread\/INFO\]: Done.*/;
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    if (pattern.test(line)) {
                        this.readyCallbacks.forEach(callback => callback(this));
                        break;
                    }   
                }

            });

        }
    
        on(state, callback) {
            if (state.toLowerCase() == 'start') {this.startCallbacks.push(callback);}
            if (state.toLowerCase() == 'ready') {this.readyCallbacks.push(callback);}
            if (state.toLowerCase() == 'exit') {this.exitCallbacks.push(callback);}
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

}