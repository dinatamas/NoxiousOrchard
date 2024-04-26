#!/usr/bin/env python3

#
# Stupid simple multiplexer socket server.
#   1. Remote reverse shell connects to MainServer.
#   2. MainServer opens local ProxyHandler.
#   3. Local client connects to ProxyHandler.
#   4. ProxyHandler transfers between local and remote clients.
#
# Why?
#   - MainServer can continue listening on the same port.
#   - ProxyHandler keeps remote open if local disconnects.
#

"""
Behavior at local / remote client disconnects:
    (1) R on, R send, R off -> L on, L read, L auto-off
    (2) R on, R send, L on -> L read, L <-> R works
    (3) L <-> R works, L off, R off -> L on, L read (final EOF from R), L auto-off
    (4) L <-> R works, R off -> L auto-off (no more data to read from R)
    (5) L <-> R works, L off, R send -> L on, L read, L <-> R works
    (6) L <-> R works, L off, R send, R off -> L on, L read, L auto-off
"""

import asyncio
import fcntl
import os
import signal
import socket
import socketserver
import struct
import threading


LIFNAME = "lo"
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
        print(f"[+] (#{self.session}) remote : {self.client_address}")
        self.loop = asyncio.get_event_loop()
        self.remote = self.request
        self.remote.setblocking(False)
        self.proxy = socket.create_server(("127.0.0.1", 0), reuse_port=True)
        self.proxy.setblocking(False)
        PHOST, PPORT = self.proxy.getsockname()
        print(f"[+] (#{self.session}) proxy  : nc {PHOST} {PPORT}")

        self.local_buffer, self.remote_buffer = socket.socketpair()
        self.local_buffer.setblocking(False)
        self.remote_buffer.setblocking(False)
        task_local = asyncio.ensure_future(self.handle_local())
        task_remote = asyncio.ensure_future(self.handle_remote())
        await asyncio.gather(task_local, task_remote)
        print(f"[-] (#{self.session}) session closed")

    async def handle_local(self):
        while True:
            self.local, local_address = await self.loop.sock_accept(self.proxy)
            self.local.setblocking(False)
            print(f"[+] (#{self.session}) local  : {local_address}")
            self.local.sendall(f"\n[+] (#{self.session}) peer : {self.client_address}\n\n".encode())
            task_read = asyncio.ensure_future(self.sock2sock(self.local, self.local_buffer))
            task_write = asyncio.ensure_future(self.sock2sock(self.local_buffer, self.local))
            done, _ = await asyncio.wait([task_read, task_write], return_when=asyncio.FIRST_COMPLETED)
            self.local.close()
            self.local = None
            if task_write in done:
                # remote_buffer closed -> no reconnect
                task_read.cancel()
                break
            if task_read in done:
                # local closed -> allow reconnect
                task_write.cancel()
            print(f"[-] (#{self.session}) local  : disconnected")
        if self.local_buffer:
            self.local_buffer.close()
            self.local_buffer = None

    async def handle_remote(self):
        task_read = asyncio.ensure_future(self.sock2sock(self.remote, self.remote_buffer))
        task_write = asyncio.ensure_future(self.sock2sock(self.remote_buffer, self.remote))
        await asyncio.gather(task_read)  # remote closed
        task_write.cancel()
        print(f"[-] (#{self.session}) remote : disconnected")
        if self.remote:
            self.remote.close()
            self.remote = None
        if self.remote_buffer:
            self.remote_buffer.close()
            self.remote_buffer = None

    async def sock2sock(self, src, dst):
        while True:
            data = await self.loop.sock_recv(src, 4096)
            try:
                await self.loop.sock_sendall(dst, data)
            except:
                break  # dst closed for write
            if not data:
                break  # src closed for read

def main():
    print()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        packed = struct.pack("256s", LIFNAME.encode())
        LHOST = fcntl.ioctl(s.fileno(), 0x8915, packed)  # SIOCGIFADDR
        LHOST = socket.inet_ntoa(LHOST[20:24])
    print(f"[+] LHOST = {LHOST} ({LIFNAME})")
    print(f"[+] LPORT = {LPORT}")
    print()

    listener = MainServer((LHOST, LPORT), ProxyHandler)
    lthread = threading.Thread(target=listener.serve_forever)
    lthread.start()

    def handler(signum, frame):
        if signum == signal.SIGINT:
            print("\r", end="")  # Stop ^C from popping up in terminal.
            if SESSIONS:
                print(f"[!] There are open sessions, please kill me : {os.getpid()}")
            else:
                print("[!] Keyboard interrupt received, exiting...")
                raise KeyboardInterrupt
        if signum == signal.SIGTERM:
            print("[!] Terminated, exiting...")
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
