#!/usr/bin/env python3

#
# Stupid simple multiplexer socket server.
#   1. Remote reverse shell connects to MainServer.
#   2. MainServer opens local ProxyHandler.
#   3. Local client connects to ProxyHandler.
#   4. ProxyHandler transfers between local and remote clients.
#
# Why?
#   - MainServer can continue listening on same port.
#   - ProxyHandler keeps remote open if local disconnects.
#

import asyncio
import errno
import fcntl
import os
import select
import shlex
import signal
import socket
import socketserver
import struct
import threading


LIFNAME = "tun0"
LPORT = 443

SESSION = 1
SESSIONS = 0


class MainServer(socketserver.ThreadingTCPServer):

    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(socketserver.BaseRequestHandler):

    def setup(self):
        global SESSION, SESSIONS
        self.session = SESSION
        SESSION += 1
        SESSIONS += 1

    def finish(self):
        global SESSIONS
        SESSIONS -= 1

    def handle(self):
        asyncio.run(self.handle_async())

    async def handle_async(self):
        print(f"(+) [#{self.session}] Remote : {self.client_address}")
        self.loop = asyncio.get_event_loop()
        self.remote = self.request
        self.remote.setblocking(False)
        self.proxy = socket.create_server(("127.0.0.1", 0), reuse_port=True)
        self.proxy.setblocking(False)
        PHOST, PPORT = self.proxy.getsockname()
        print(f"(+) [#{self.session}] Proxy  : nc {PHOST} {PPORT}")

        self.local_buffer, self.remote_buffer = socket.socketpair()
        self.local_buffer.setblocking(False)
        self.remote_buffer.setblocking(False)
        task_local = asyncio.ensure_future(self.handle_local())
        task_remote = asyncio.ensure_future(self.handle_remote())
        await asyncio.gather(task_remote)
        task_local.cancel()
        print(f"(-) [#{self.session}] session closed")
        # Todo: Do not cancel task_local until all buffered data is read.

    async def handle_local(self):
        while True:
            self.local, local_address = await self.loop.sock_accept(self.proxy)
            self.local.setblocking(False)
            print(f"(+) [#{self.session}] Local  : {local_address}")
            task_read = asyncio.ensure_future(self.sock2sock(self.local, self.local_buffer))
            task_write = asyncio.ensure_future(self.sock2sock(self.local_buffer, self.local))
            await asyncio.gather(task_read)
            task_write.cancel()
            print(f"(!) [#{self.session}] Local : disconnected")

    async def handle_remote(self):
        task_read = asyncio.ensure_future(self.sock2sock(self.remote, self.remote_buffer))
        task_write = asyncio.ensure_future(self.sock2sock(self.remote_buffer, self.remote))
        await asyncio.gather(task_read)
        task_write.cancel()
        print(f"(!) [#{self.session}] Remote : disconnected")

    async def sock2sock(self, src, dst):
        while True:
            data = await self.loop.sock_recv(src, 4096)
            if not data:
                break
            await self.loop.sock_sendall(dst, data)
            # Todo: Error handling for read-write operations.


def main():
    print()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        packed = struct.pack("256s", LIFNAME.encode())
        LHOST = fcntl.ioctl(s.fileno(), 0x8915, packed)  # SIOCGIFADDR
        LHOST = socket.inet_ntoa(LHOST[20:24])
    print(f"(+) LHOST = {LHOST} ({LIFNAME})")
    print(f"(+) LPORT = {LPORT}")
    print()

    listener = MainServer((LHOST, LPORT), ProxyHandler)
    lthread = threading.Thread(target=listener.serve_forever)
    lthread.start()

    def handler(signum, frame):
        if signum == signal.SIGINT:
            print("\r", end="")  # Stop ^C from popping up in terminal.
            if SESSIONS:
                print(f"(>) There are still open sessions, please kill me : {os.getpid()}")
            else:
                print("(>) Keyboard interrupt received, exiting...")
                raise KeyboardInterrupt
        if signum == signal.SIGTERM:
            print("(!) Terminated, exiting...")
            raise SystemExit
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    while True:
        try:
            lthread.join()  # Blocks ad infinitum.
        except (KeyboardInterrupt, SystemExit):
            break
        finally:
            listener.shutdown()
            listener.server_close()


if __name__ == "__main__":
    main()
