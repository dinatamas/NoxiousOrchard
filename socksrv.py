#!/usr/bin/env python3

#
# Stupid simple sessioned socket server.
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
    (3) L <-> R works, L off, R off -> L auto-off (do not read EOF from R)
    (4) L <-> R works, R off -> L auto-off (no more data to read from R)
    (5) L <-> R works, L off, R send -> L on, L read, L <-> R works
    (6) L <-> R works, L off, R send, R off -> L on, L read, L auto-off
"""

import asyncio
import os
import signal
import socket
import socketserver
import threading


LHOST = "127.0.0.1"
LPORT = 33443

SESSION = 1
SESSIONS = 0


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
        print(f"[+] (#{self.session}) remote: {self.client_address}")
        self.loop = asyncio.get_event_loop()
        self.remote = self.request
        self.remote.setblocking(False)
        self.proxy = socket.create_server(("127.0.0.1", 0), reuse_port=True)
        self.proxy.setblocking(False)
        PHOST, PPORT = self.proxy.getsockname()
        print(f"[+] (#{self.session}) proxy: nc {PHOST} {PPORT}")

        self.local_buffer, self.remote_buffer = socket.socketpair()
        self.local_buffer.setblocking(False)
        self.remote_buffer.setblocking(False)
        self.accept_task = None
        task_local = asyncio.ensure_future(self.handle_local())
        task_remote = asyncio.ensure_future(self.handle_remote())
        await asyncio.gather(task_remote)
        try:
            leftover = self.local_buffer.recv(4096, socket.MSG_PEEK)
        except:
            leftover = None
        if leftover:
            print(f"[!] (#{self.session}) session: unread local data")
        else:
            if self.accept_task:
                self.accept_task.cancel()
        await asyncio.gather(task_local)
        print(f"[-] (#{self.session}) session: closed")

    async def handle_local(self):
        while True:
            try:
                # Waits until connection is received or cancelled.
                self.accept_task = self.loop.sock_accept(self.proxy)
                self.local, local_address = await self.accept_task
            except asyncio.CancelledError:
                break
            self.accept_task = None
            self.local.setblocking(False)
            print(f"[+] (#{self.session}) local: {local_address}")
            self.local.sendall(f"\n[+] (#{self.session}) peer: {self.client_address}\n\n".encode())
            task_read = asyncio.ensure_future(self.sock2sock(self.local, self.local_buffer))
            task_write = asyncio.ensure_future(self.sock2sock(self.local_buffer, self.local))
            done, _ = await asyncio.wait([task_read, task_write], return_when=asyncio.FIRST_COMPLETED)
            print(f"[-] (#{self.session}) local: disconnected")
            self.local.close()
            self.local = None
            if task_write in done:
                # remote_buffer closed -> no reconnect
                task_read.cancel()
                break
            if task_read in done:
                # local closed -> allow reconnect
                task_write.cancel()
        if self.local_buffer:
            self.local_buffer.close()
            self.local_buffer = None

    async def handle_remote(self):
        task_read = asyncio.ensure_future(self.sock2sock(self.remote, self.remote_buffer))
        task_write = asyncio.ensure_future(self.sock2sock(self.remote_buffer, self.remote))
        await asyncio.gather(task_read)  # remote closed
        task_write.cancel()
        print(f"[-] (#{self.session}) remote: disconnected")
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


class MainServer(socketserver.ThreadingTCPServer):

    allow_reuse_address = True
    daemon_threads = True


def main():
    # Todo: Commented out until cross-platform implementation.
    # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    #     packed = struct.pack("256s", LIFNAME.encode())
    #     LHOST = fcntl.ioctl(s.fileno(), 0x8915, packed)  # SIOCGIFADDR
    #     LHOST = socket.inet_ntoa(LHOST[20:24])
    print()
    print(f"[+] LHOST = {LHOST}")
    print(f"[+] LPORT = {LPORT}")
    print()

    listener = MainServer((LHOST, LPORT), ProxyHandler)
    lthread = threading.Thread(target=listener.serve_forever)
    lthread.start()

    def sigint_handler(*_):
        print("\r", end="")  # Stop ^C from popping up in terminal.
        if SESSIONS:
            print(f"[!] There are open sessions, please kill me: {os.getpid()}")
        else:
            print("[-] Interrupt received, exiting...")
            raise KeyboardInterrupt
    def sigterm_handler(*_):
        print("[-] Terminated, exiting...")
        raise SystemExit
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        lthread.join()  # blocks ad infinitum
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        listener.shutdown()
        listener.server_close()


if __name__ == "__main__":
    main()
