const fs = require('fs');
const properties_parser = require('properties-parser');

// Load the properties files.
const server = properties_parser.parse(fs.readFileSync('server.properties', 'utf-8'));
const starter = properties_parser.parse(fs.readFileSync('starter.properties', 'utf-8'));

// Check if all required fields are present.
if (!('version' in starter)) {throw new Error('Version number not specified in starter.properties!');}
if (!('command' in starter)) {throw new Error('Start command not specified in starter.properties!');}
if (!('server-port' in server)) {throw new Error('Server port not specified in server.properties!');}
if (!('server-port' in starter)) {throw new Error('Server port not specified in starter.properties!');}
if (!('starter-port' in starter)) {throw new Error('Starter port not specified in starter.properties!');}

// Fill in default values for optional properties
if (!('timeout' in starter)) {starter['timeout'] = 5;}
if (!('waiting-motd' in starter)) {starter['waiting-motd'] = 'Server currently sleeping.\nPlease login to wake me up!';}
if (!('starting-motd' in starter)) {starter['starting-motd'] = 'Server is waking up.\nPlease wait a few seconds.';}
if (!('starting-reason' in starter)) {starter['starting-reason'] = 'Server is waking up. Please wait a few seconds.';}

// Type cast the numbers to number types.
server['server-port'] = parseInt(server['server-port'], 10);
starter['server-port'] = parseInt(starter['server-port'], 10);
starter['starter-port'] = parseInt(starter['starter-port'], 10);
starter['timeout'] = parseInt(starter['timeout'], 10);

// Check if all required numbers were parsed successfully.
if (isNaN(server['server-port'])) {throw new Error('Server port in server.properties is not an integer!');}
if (isNaN(starter['server-port'])) {throw new Error('Server port in starter.properties is not an integer!');}
if (isNaN(starter['starter-port'])) {throw new Error('Server port in starter.properties is not an integer!');}

// Create the properties object.
const properties = {};
properties['server-port'] = starter['server-port'];
properties['minecraft-server-port'] = server['server-port'];
properties['minecraft-server-starter-port'] = starter['starter-port'];
properties['version'] = starter['version'];
properties['command'] = starter['command'];
properties['timeout'] = starter['timeout'];
properties['waiting-motd'] = starter['waiting-motd'];
properties['starting-motd'] = starter['starting-motd'];
properties['starting-reason'] = starter['starting-reason'];

module.exports = { properties: properties};