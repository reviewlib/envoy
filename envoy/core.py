# -*- coding: utf-8 -*-

"""
envoy.core
~~~~~~~~~~

This module provides envoy awesomeness.
"""

import os
import sys
'''split shell commends into correct tokens'''
import shlex
'''supportance of Linux Signals'''
import signal
'''actual subprocess module'''
import subprocess
'''create a thread to work, but why?'''
import threading
'''traceback exeception'''
import traceback


__version__ = '0.0.3'
__license__ = 'MIT'
__author__ = 'Kenneth Reitz'


def _terminate_process(process):
    if sys.platform == 'win32':
        import ctypes
        PROCESS_TERMINATE = 1
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, process.pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)
    else:
        os.kill(process.pid, signal.SIGTERM)


def _kill_process(process):
    if sys.platform == 'win32':
        _terminate_process(process)
    else:
        os.kill(process.pid, signal.SIGKILL)


def _is_alive(thread):
    if hasattr(thread, "is_alive"):
        return thread.is_alive()
    else:
        return thread.isAlive()


class Command(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None
        self.out = None
        self.err = None
        self.returncode = None
        self.data = None
        self.exc = None

    def run(self, data, timeout, kill_timeout, env, cwd):
        self.data = data
        environ = dict(os.environ)
        environ.update(env or {})

        def target():

            try:
                self.process = subprocess.Popen(self.cmd,
                    universal_newlines=True,
                    shell=False,
                    env=environ,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    cwd=cwd,
                )

                if sys.version_info[0] >= 3:
                    self.out, self.err = self.process.communicate(
                        input = bytes(self.data, "UTF-8") if self.data else None
                    )
                else:
                    self.out, self.err = self.process.communicate(self.data)
            except Exception as exc:
                self.exc = exc


        '''actually do the task(target)'''
        thread = threading.Thread(target=target)
        thread.start()

        thread.join(timeout)
        if self.exc:
            '''got exception, raise it'''
            raise self.exc
        if _is_alive(thread) :
            '''do not get exception but alive, timeout, terminate it'''
            _terminate_process(self.process)
            thread.join(kill_timeout)
            if _is_alive(thread):
                _kill_process(self.process)
                thread.join()
        '''everything is okay, get ready to return'''
        self.returncode = self.process.returncode
        return self.out, self.err


class ConnectedCommand(object):
    def __init__(self,
        process=None,
        std_in=None,
        std_out=None,
        std_err=None):

        self._process = process
        self.std_in = std_in
        self.std_out = std_out
        self.std_err = std_out
        self._status_code = None

    '''good guy! a class with __enter__ and __exit__ can be used with context manager (with ... as ...:)'''
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.kill()

    '''no setter, means read only attrib.'''
    @property
    def status_code(self):
        """The status code of the process.
        If the code is None, assume that it's still running.
        """
        return self._status_code

    @property
    def pid(self):
        """The process' PID."""
        return self._process.pid

    def kill(self):
        """Kills the process."""
        return self._process.kill()

    def expect(self, bytes, stream=None):
        """Block until given bytes appear in the stream."""
        if stream is None:
            stream = self.std_out

    def send(self, str, end='\n'):
        """Sends a line to std_in."""
        return self._process.stdin.write(str+end)

    def block(self):
        """Blocks until command finishes. Returns Response instance."""
        self._status_code = self._process.wait()



class Response(object):
    """A command's response"""

    def __init__(self, process=None):
        super(Response, self).__init__()

        self._process = process
        self.command = None
        self.std_err = None
        self.std_out = None
        self.status_code = None
        self.history = []


    def __repr__(self):
        if len(self.command):
            return '<Response [{0}]>'.format(self.command[0])
        else:
            return '<Response>'


def expand_args(command):
    """Parses command strings and returns a Popen-ready list."""

    # Prepare arguments.
    if isinstance(command, (str, unicode)):
        splitter = shlex.shlex(command.encode('utf-8'))
        splitter.whitespace = '|'
        splitter.whitespace_split = True
        command = []

        while True:
            token = splitter.get_token()
            if token:
                command.append(token)
            else:
                break

        '''map: map func to each element in iter'''
        command = list(map(shlex.split, command))

    return command


def run(command, data=None, timeout=None, kill_timeout=None, env=None, cwd=None):
    """Executes a given commmand and returns Response.

    Blocks until process is complete, or timeout is reached.
    """

    command = expand_args(command)

    history = []
    for c in command:

        if len(history):
            # due to broken pipe problems pass only first 10 KiB
            data = history[-1].std_out[0:10*1024]

        cmd = Command(c)
        try:
            out, err = cmd.run(data, timeout, kill_timeout, env, cwd)
            status_code = cmd.returncode
        except OSError as e:
            out, err = '', u"\n".join([e.strerror, traceback.format_exc()])
            status_code = 127

        r = Response(process=cmd)

        r.command = c
        r.std_out = out
        r.std_err = err
        r.status_code = status_code

        history.append(r)

    r = history.pop()
    r.history = history

    return r


def connect(command, data=None, env=None, cwd=None):
    """Spawns a new process from the given command."""

    # TODO: support piped commands
    command_str = expand_args(command).pop()
    environ = dict(os.environ)
    environ.update(env or {})

    process = subprocess.Popen(command_str,
        universal_newlines=True,
        shell=False,
        env=environ,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        cwd=cwd,
    )

    return ConnectedCommand(process=process)
