import subprocess
import threading
import re

class MinecraftServer:

    def __init__(self, command):
        
        self.command = command
        self.callbacks = {'start': [], 'binding': [], 'ready': [], 'exit': []}
        self.process = None

    def __del__(self):
        if self.process != None: self.process.terminate()

    def start(self):

        if self.process != None: raise Exception("Minecraft server has already started.")

        process = subprocess.Popen(self.command.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.process = process
        self._run_event('start')

        def routine():

            binding = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread/INFO\]: Starting minecraft server version")
            ready = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread/INFO\]: Done.*")

            while True:
                
                line = process.stdout.readline()
                if not line: break
                print(line, end="")

                # Logged shortly before the server binds its port.
                if binding.match(line): self._run_event('binding')
                if ready.match(line): self._run_event('ready')

            process.wait()
            if process == self.process: self.process = None
            self._run_event('exit')

        thread = threading.Thread(target=routine, args=())
        thread.start()

    def stop(self):
        if self.process == None: return
        self.process.stdin.write('stop\n')
        self.process.stdin.flush()

    def enter_command(self, command):
        if self.process == None: return
        self.process.stdin.write(command)
        self.process.stdin.flush()

    def _run_event(self, event):
        if event not in self.callbacks: return
        for callback in self.callbacks[event]: callback()

    def on(self, event, callback):
        if event not in self.callbacks: return
        self.callbacks[event].append(callback)
