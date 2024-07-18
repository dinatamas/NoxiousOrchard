#!/usr/bin/env python3

import asyncio
import json
import select
import signal
import socketserver
import threading

from sck import SocketBuffer


LHOST = "127.0.0.1"
LPORT = 9999
RHOST = "127.0.0.1"
RPORT = 33443


#
# Todo:
#  - Use it to create / assign sessions
#  - Log a lot more (include colors & log files!)
#  - Log all incoming / outgoing data
#

class Session(threading.Thread):
    def __init__(self, name):
        super().__init__(daemon=True)
        self.name = name
        self.buffers = dict()
        self.local = self.buffers["local"] = SocketBuffer()
        self.remote = self.buffers["remote"] = SocketBuffer()

    def run(self):
        asyncio.run(self._run())

    async def _run(self):
        while True:
            readable, _, _ = select.select([self.local, self.remote], [], [])
            if self.remote in readable:
                print(self.remote.ready())
                print(await self.remote.readuntil(b"\n"))

    async def handle_peer(self, name, peer):
        buffer = self.buffers[name]
        if buffer.lock.acquire(blocking=False):
            with buffer.lock:
                print_success("peer accepted")
                res = {"res": "success"}
                peer.sendall(json.dumps(res).encode())
                await buffer.sync(peer)
                print_warning("peer disconnected")
                return True
        print_error("peer rejected")
        res = {"res": "failed"}
        peer.sendall(json.dumps(res).encode())
        return False


SESSION = Session("main")
SESSION.start()


def run_server(name, host, port):

    class TCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    # TODO: Add numbers for local and remote connections too!
    # TODO: Introduce global state with (proper locking)!
    class PeerHandler(socketserver.BaseRequestHandler):
        def handle(self):
            print_info(f"{name}: {self.client_address}")
            cmd = json.loads(self.request.recv(4096))
            if cmd["cmd"] == "sessionlist":
                print_info(f"{name}: requested sessions")
                res = {"sessions": [1]}
                self.request.sendall(json.dumps(res).encode())
                return
            if cmd["cmd"] == "sessionjoin":
                asyncio.run(SESSION.handle_peer(name, self.request))

    print_success(f"{name.upper()} HOST = {host}")
    print_success(f"{name.upper()} PORT = {port}")
    print()
    server = TCPServer((host, port), PeerHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def main():
    def sigint_handler(*_):
        print("\x08\x08  ")  # Stop ^C from popping up.
        print_error("Interrupt received, exiting...")
        raise KeyboardInterrupt
    def sigterm_handler(*_):
        print_error("Terminated, exiting...")
        raise SystemExit
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    print()
    lserver, lthread = run_server("local", LHOST, LPORT)
    rserver, rthread = run_server("remote", RHOST, RPORT)
    try:
        lthread.join()
        rthread.join()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        lserver.shutdown()
        rserver.shutdown()


BOLD    = "\033[1m"
BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"
RESET   = "\033[0m"
def print_error(msg):   l33t_pR1N7(msg, RED,    "-")
def print_warning(msg): l33t_pR1N7(msg, YELLOW, "!")
def print_success(msg): l33t_pR1N7(msg, GREEN,  "+")
def print_info(msg):    l33t_pR1N7(msg, BLUE,   "*")
def l33t_pR1N7(msg, color, symbol):
    print(f"{color}[{symbol}]{RESET} {msg}")


if __name__ == "__main__":
    main()


#
# TODO:
#  - How should locals / remotes identify themselves?
#    - One idea would definitely be the IP address (src port is random)
#  - Even before a session, should connections be persisted?
#  - That might require buffers to be initiated by not by the sessions,
#    but by the external handler threads... not a good idea, since from
#    the session's point of view the buffers should be "transparent"
#    throughout reconnections...
#
#
