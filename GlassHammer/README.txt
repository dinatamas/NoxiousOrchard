OSCP Post-Exploitation Workflow
===============================


Initial Compromise
------------------

We get initial code execution on the public-facing target of the network.
This could be either SSH, RDP, bind / reverse / web shell...

To make this tool cross-platform and usable in all situations, we don't
presume anything about the initial connection, only that we have some
sort of code execution (bash / powershell / etc.)


Required Capabilities
---------------------

(1) RCE : We need to be able to execute commands and see their output.
These could be either simple shell commands, executables, etc.
Similar to DoublePulsar / KillSuit loading DLLs and EXEs into memory.

(2) Exfiltration : Files, verbose command outputs should be transferred
out-of-band to not mess up the active connections and for later analysis.

(3) File Transfer : Upload files and executables for compromise.

(4) AV Evasion : The implant ideally should not be flagged by PSPs.

(5) Privilege Escalation : It doesn't need to do privesc (like mimikatz)
but should aid in the multi-user workflow that comes with it.

(6) Persistence : The C&C channel should not be flimsy, re-exploitation
should not be necessary for lost connections (and later: even reboots).

(7) Lateral Movement : These implants should also function as a one-stop-shop
for pivot tunneling-proxying with DPI evasion capabilities.

(8) C&C RPC : Execute remote procedure calls on the C&C server to analyze
certain artifacts and to print that information to the console (but not
necessarily send the results back to the implant).


Installing the Implant
----------------------

I'm not a nation state level adversary, so I don't have custom exploits
that somehow corrupt OS kernel process memory space and give root or
Administrator privileges with carefully crafted in-memory DLL implants.

What I usually have is an unreliable PowerShell / Bash shell session.
I need to extend that with a process running my custom implant:

  1. I need to transfer my implant's executable code to the system,
     preferably without touching disk -> this is a system-dependent
     process which differs if I have CMD / PowerShell / Bash access,
     but standard injection commands should be prepared for all
     environments I might happen to encounter.
  2. Ideally, step (1) is the only command I need to run through the
     raw shell connection. Preferably I wouldn't need to copy-paste
     the command, instead I could write a general infector-listener
     which "poisons" any system initiating shell connections to it
     by recognizing the environment / shell type and executing the
     required specialized payload to insert the implant.
  3. Steps (1) and (2) are essentially what distinguishes me from an
     adversary who has DLL / EXE execution as their initial foothold.
     Initially I have standard tools / shell only, and not custom
     injection payloads, but these steps should take care of that and
     transfer execution to my custom implant process.
  4. Methods like metasploit's execute / migrate commands could also
     be considered, as well as evasion techniques similar to Shellter,
     but initially stealth should not be a major focus, as that is a
     super complicated process and I don't have the time / resources for it.

https://github.com/PowerShellMafia/PowerSploit/tree/master/CodeExecution

https://www.securonix.com/blog/hiding-the-powershell-execution-flow/

https://www.youtube.com/watch?v=WJlqQYyzGi8
