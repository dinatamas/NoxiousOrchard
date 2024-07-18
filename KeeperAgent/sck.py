import array
import asyncio
import fcntl
import socket
import termios
import threading


#
# Convenience functions for sockets (without buffering).
#
class SocketWrapper:

    def __init__(self, sock):
        self.sock = sock

    @property
    def loop(self):
        return asyncio.get_event_loop()

    ###################################################
    # selectable / awaitabe regular socket operations #
    ###################################################

    def fileno(self): return self.sock.fileno()
    def recv(self, size): return self.loop.sock_recv(self.sock, size)
    def send(self, data): return self.loop.sock_sendall(self.sock, data)
    def sendall(self, data): return self.send(data)

    ###########################################
    # inspectable / awaitable internal buffer #
    ###########################################

    async def wait(self, what="RD"):
        event = asyncio.Event()
        update = lambda: event.set()
        if what == "RD":
            self.loop.add_reader(self.sock, update)
        if what == "WR":
            self.loop.add_writer(self.sock, update)
        await event.wait()

    def ready(self):
        size = array.array("i", [0])
        fcntl.ioctl(self.sock, termios.FIONREAD, size)
        return size[0]

    ###############################################
    # immediately returning read-write operations #
    ###############################################

    def peek(self):
        return self._recv(self.ready(), socket.MSG_PEEK)

    def read(self):
        return self._recv(self.ready())

    def write(self, data):
        return self._send(data)

    ###########################################
    # awaitable advanced buffering operations #
    ###########################################

    async def readexact(self, size):
        data = b""
        while True:
            data += await self.recv(size)
            size = size - len(data)
            if not size:
                return data

    async def readuntil(self, *delims):
        def _find(data):
            found = [(data.find(d), len(d)) for d in delims]
            found = sorted(found, key=lambda f: (f[0],-f[1]))
            offsets = [f[0]+f[1] for f in found if f[0] != -1]
            return offsets[0] if offsets else 0
        data = b""
        while True:
            chunk = self.peek()
            offset = _find(data + chunk)
            amount = (offset or len(data)+len(chunk)) - len(data)
            data += self._recv(amount)
            if offset:
                return data
            await self.wait()

    ################################################
    # non-blocking / non-raising internal wrappers #
    ################################################

    def _recv(self, *args, **kwargs):
        try:
            return self.sock.recv(*args, **kwargs)
        except BlockingIOError:
            return b""

    def _send(self, *args, **kwargs):
        try:
            self.sock.sendall(*args, **kwargs)
        except BlockingIOError:
            return False
        return True



#
# Instead of having a direct local-remote connection, this
# class provides the sock2sock() function, which can be
# run in a separate thread to buffer all in-between data:
#   local (sockint) <-> sockext <-> remote
#
# Benefits:
#  - Provides async peek behavior.
#  - Unlike regular byte buffers, this socketpair-based
#    solution supports select() on all platforms.
#  - Applications can disregard connection establishment
#    They can use regular socket operations without having
#    to handle error cases like remote disconnects. Data
#    will be sent as soon as the connection is reestablished.
#    - This is useful when there's a higher level application
#      session protocol, making the TCP layer mechanisms a
#      pain rather than an ease. Application layer ACKs will
#      also be more authoritative than their TCP counterparts.
#
class SocketBuffer(SocketWrapper):
    # See also: Boltons > socketutils.py

    def __init__(self):
        self.sockint, self.sockext = socket.socketpair()
        self.sockint.setblocking(False)
        self.sockext.setblocking(False)
        self.lock = threading.RLock()
        self.peekable = asyncio.Event()
        self.peeklock = threading.RLock()
        super().__init__(self.sockint)

    ###########################################
    # awaitable advanced buffering operations #
    ###########################################

    async def peekexact(self, size):
        while True:
            await self.peekable.wait()
            with self.peeklock:
                self.peekable.clear()
            data = self.peek()
            if len(data) >= size:
                return data[:size]

    async def peekuntil(self, *delims):
        def _find(data):
            found = [(data.find(d), len(d)) for d in delims]
            found = sorted(found, key=lambda f: (f[0],-f[1]))
            offsets = [f[0]+f[1] for f in found if f[0] != -1]
            return offsets[0] if offsets else 0
        while True:
            await self.peekable.wait()
            with self.peeklock:
                self.peekable.clear()
            data = self.peek()
            if offset := _find(data):
                return data[:offset]

    #####################################
    # underlying socket synchronisation #
    #####################################

    async def sync(self, sock):
        sock.setblocking(False)
        t1 = asyncio.ensure_future(self.sock2sock(sock, self.sockext))
        t2 = asyncio.ensure_future(self.sock2sock(self.sockext, sock))
        _, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        [task.cancel() for task in pending]

    async def sock2sock(self, src, dst):
        event = asyncio.Event()
        reader = lambda: event.set()
        self.loop.add_reader(src, reader)
        while True:
            try:
                await event.wait()
                data = src.recv(2**16, socket.MSG_PEEK)
                if not data:
                    break
                await self.loop.sock_sendall(dst, data)
                src.recv(len(data))
                event.clear()
                with self.peeklock:
                    self.peekable.set()
            except:
                break


#
# Tasks:
# - Create wait / ready for write operations!
# - Provide buffer_socket() function to sync!
# - Add names + more logging!
# - Handle close / shutdown!
#
