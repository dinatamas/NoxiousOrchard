#!/usr/bin/env python3
import json
import shlex
import socket


class State:
    session = "disconnected"


def main():
    S = State()

    while True:
        print()
        print(f"┌──({S.session})")
        command = shlex.split(input("└─$ "))
        if not command:
            continue
        if command[0] in ["exit"]:
            break
        print()
        if command[0] in ["help", "?"]:
            tprint(
                ["Command", "Description"],
                ["exit",    "exit the script"],
                ["help",    "show this help message"],
            )
        elif command[0] == "session":
            if command[1] == "list":
                do_sessionlist(S)
            elif command[1] == "join":
                do_sessionjoin(S)
        else:
            print(f'Uknown command "{command[0]}"')


def do_sessionlist(S):
    cmd = {"cmd": "sessionlist"}
    with socket.create_connection(("127.0.0.1", 9999)) as sock:
        sock.sendall(json.dumps(cmd).encode() + b"\n")
        print(json.loads(sock.recv(4096))["sessions"])


def do_sessionjoin(S):
    cmd = {"cmd": "sessionjoin", "session": 1}
    with socket.create_connection(("127.0.0.1", 9999)) as sock:
        sock.sendall(json.dumps(cmd).encode() + b"\n")
        res = json.loads(sock.recv(4096))["res"]
        if res == "success":
            print("[+] Successfully joined session")
            S.session = 1
            import time
            time.sleep(30)
        else:
            print("[-] Failed to join session")


def tprint(*rows):
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for row in [rows[0], ["-" * len(header) for header in rows[0]], *rows[1:]]:
        print("   " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths)))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
