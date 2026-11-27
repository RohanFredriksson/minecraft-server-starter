import subprocess
import threading
import re

class MinecraftServer:

    def __init__(self, command):
        
        self.command = command
        self.callbacks = {'start': [], 'binding': [], 'ready': [], 'exit': []}
        self.process = None
        self.lock = threading.Lock()

    def __del__(self):
        if self.process is not None: self.process.terminate()

    def start(self):

        with self.lock:
            if self.process is not None: raise Exception("Minecraft server has already started.")

            process = subprocess.Popen(
                self.command.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
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
            with self.lock:
                if process == self.process: self.process = None
            self._run_event('exit')

        thread = threading.Thread(target=routine, daemon=True)
        thread.start()

    def stop(self):
        with self.lock:
            process = self.process
        if process is None or process.poll() is not None: return
        try:
            process.stdin.write('stop\n')
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def stop_and_wait(self, timeout=10):
        with self.lock:
            process = self.process
        if process is None: return

        self.stop()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def enter_command(self, command):
        with self.lock:
            process = self.process
        if process is None or process.poll() is not None: return
        try:
            process.stdin.write(command)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _run_event(self, event):
        if event not in self.callbacks: return
        for callback in self.callbacks[event]: callback()

    def on(self, event, callback):
        if event not in self.callbacks: return
        self.callbacks[event].append(callback)
