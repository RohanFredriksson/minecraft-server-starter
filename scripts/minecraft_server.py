import subprocess
import threading
import re

class MinecraftServer:

    def __init__(self, command):
        
        self.command = command
        self.callbacks = {'start': [], 'ready': [], 'exit': []}
        self.process = None

    def __del__(self):
        if self.process != None: self.process.terminate()

    def start(self):

        if self.process != None: raise Exception("Minecraft server has already started.")

        def routine():

            self.process = subprocess.Popen(["java", "-Xms1G", "-Xmx1G", "-jar", "server.jar", "nogui"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._run_event('start')

            def waiter(p):
                p.wait()
                self._run_event('exit')
                if p == self.process: self.process = None

            thread = threading.Thread(target=waiter, args=(self.process,))
            thread.start()

            while self.process != None:
                
                line = self.process.stdout.readline()
                if not line: break
                print(line, end="")

                pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread/INFO\]: Done.*")
                result = pattern.match(line)
                if result: self._run_event('ready')

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
