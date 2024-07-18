#!/usr/bin/env python3
from rpc import RPC

a = RPC.parse('{"a": }')
print(a)

b = RPC.parse(a[0])
print(b)

c = RPC.parse('{"state": "notification", "message": "its a notification"}')
print(c)
