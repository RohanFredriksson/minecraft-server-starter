import os
import shlex
import subprocess
import threading
import re

BINDING_PATTERN = re.compile(r'\bStarting minecraft server on\b', re.IGNORECASE)
READY_PATTERN = re.compile(r'\bDone \([^)]*\)!', re.IGNORECASE)

def split_command(command):
    """Splits a command line the way a terminal would, so quoted paths may contain spaces."""
    # Windows programs split their own command line, so it is passed on whole.
    if os.name == 'nt': return command
    return shlex.split(command)

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
                split_command(self.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                # Output the console encoding cannot decode must not stop the console being read, or the
                # server would stall once the pipe fills. Commands it cannot encode are escaped instead.
                errors='backslashreplace'
            )
            self.process = process
        self._run_event('start')

        def routine():

            while True:
                
                line = process.stdout.readline()
                if not line: break
                print(line, end="")

                if BINDING_PATTERN.search(line): self._run_event('binding')
                if READY_PATTERN.search(line): self._run_event('ready')

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
