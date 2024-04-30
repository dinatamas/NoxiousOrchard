#!/usr/bin/env python3

import asyncio
import signal
import socket
import socketserver
import threading


LHOST = "127.0.0.1"
LPORT = 9999
RHOST = "127.0.0.1"
RPORT = 33443


SESSION_LOCK = threading.RLock()
SESSIONS = list()


class Session:
    NEXT_ID = 1

    def __init__(self):
        with SESSION_LOCK:
            self.id = self.NEXT_ID
            self.NEXT_ID += 1
            SESSIONS.append(self)
        self.local, self.llock = None, threading.RLock()
        self.remote, self.rlock = None, threading.RLock()
        self.local_buffer, self.remote_buffer = socket.socketpair()
        self.local_buffer.setblocking(False)
        self.remote_buffer.setblocking(False)
        self.log("[+]", "session opened")

    async def handle_local(self, local):
        if not self.llock.acquire(blocking=False):
            return -1
        with self.llock:
            await self.handle_peer("local", local, self.local_buffer)

    async def handle_remote(self, remote):
        if not self.rlock.acquire(blocking=False):
            return -1
        with self.rlock:
            await self.handle_peer("remote", remote, self.remote_buffer)

    async def handle_peer(self, name, peer, buffer):
        self.log("[+]", f"{name}: {peer.getsockname()}")
        peer.setblocking(False)
        ptask = asyncio.ensure_future(self.sock2sock(peer, buffer))
        btask = asyncio.ensure_future(self.sock2sock(buffer, peer))
        _, pending = await asyncio.wait([ptask, btask], return_when=asyncio.FIRST_COMPLETED)
        [task.cancel() for task in pending]
        peer.close()
        self.log("[-]", f"{name}: disconnected")

    async def sock2sock(self, src, dst):
        loop = asyncio.get_event_loop()
        while True:
            data = await loop.sock_recv(src, 4096)
            try:
                await loop.sock_sendall(dst, data)
            except:
                break  # dst closed for write
            if not data:
                break  # src closed for read

    def log(self, lvl, txt):
        print(f"{lvl} #{self.id} {txt}")


class LocalHandler(socketserver.BaseRequestHandler):

    def handle(self):
        session = 1  # normally: get this from protocol
        if not SESSIONS:
            _ = Session()
        code = asyncio.run(SESSIONS[session-1].handle_local(self.request))
        if code == -1:
            self.request.sendall(b"[-] could not connect\n")


class RemoteHandler(socketserver.BaseRequestHandler):

    def handle(self):
        session = 1  # normally: get this from protocol
        if not SESSIONS:
            _ = Session()
        code = asyncio.run(SESSIONS[session-1].handle_remote(self.request))
        if code == -1:
            self.request.sendall(b"[-] could not connect\n")


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    print()
    # "Local": This is where operators should connect.
    print(f"[+] LHOST = {LHOST}")
    print(f"[+] LPORT = {LPORT}")
    print()
    # "Remote": This is where implants should connect.
    print(f"[+] RHOST = {RHOST}")
    print(f"[+] RPORT = {RPORT}")
    print()

    lserver = TCPServer((LHOST, LPORT), LocalHandler)
    lthread = threading.Thread(target=lserver.serve_forever)
    lthread.start()

    rserver = TCPServer((RHOST, RPORT), RemoteHandler)
    rthread = threading.Thread(target=rserver.serve_forever)
    rthread.start()

    def sigint_handler(*_):
        print("\r", end="")  # Stop ^C from popping up in terminal.
        print("[-] Interrupt received, exiting...")
        raise KeyboardInterrupt
    def sigterm_handler(*_):
        print("[-] Terminated, exiting...")
        raise SystemExit
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        # Blocks ad infinitum.
        lthread.join()
        rthread.join()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        lserver.shutdown()
        lserver.server_close()
        lthread.join()
        rserver.shutdown()
        rserver.server_close()
        rthread.join()


if __name__ == "__main__":
    main()
