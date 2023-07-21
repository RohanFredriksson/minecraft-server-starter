const child_process = require('child_process');

module.exports = {

    Proxy: class Proxy {

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
    
}