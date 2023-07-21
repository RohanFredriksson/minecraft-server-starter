const mc = require('minecraft-protocol');
const line = ("columns" in process.stdout) ? '-'.repeat(process.stdout.columns) : '-'.repeat(80);

module.exports = {

    ping: async (host, port) => {
        try {result = await mc.ping({host: host, port: port}); result.online = true; return result;} 
        catch {result = {online: false}; return result;}
    },

    line: line,
    
}