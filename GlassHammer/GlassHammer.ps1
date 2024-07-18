<#
.SYNOPSIS
  GlassHammer will break Windows for you!

.DESCRIPTION
  A subset of winPEAS.ps1 until I write a complete Win32 implant in C.

  Check the original at:
  https://github.com/peass-ng/PEASS-ng/blob/master/winPEAS/winPEASps1/winPEAS.ps1

.EXAMPLE
  # No need to overthink - one size fits all!
  .\GlassHammer.ps1

.NOTES
  Version:       1.0
  Version Date:  28th April, 2024
  Author:        @dinatamaspal
  Website:       https://github.com/dinatamas

  TESTED: unknown
  UNTESTED: unknown
  NOT FULLY COMPATIBLE: unknown
#>


# ===============================================
# Add extra features:
#   - Upload command results as files to C&C
#   - Run checks like wesng on results
#   - Add color and [+] [-] output
#   - Print timestamps for cmd executions
# ===============================================


#################################################
# -- ENTRYPOINT --
#################################################

$stopwatch = [system.diagnostics.stopwatch]::StartNew()

Add-Type -AssemblyName System.Management

#################################################
# -- SYSTEM INFORMATION --
#################################################

systeminfo.exe  # -> wesng -> display vulns only!

Get-ComputerInfo  # -> list only relevant info!

Get-PSDrive -PSProvider FileSystem  # -> display drive letters where volume > 0

# AntiVirus checks -> format minimalistically (e.g. only names + versions) + interesting exclusions
WMIC /Node:localhost /Namespace:\\root\SecurityCenter2 Path AntiVirusProduct Get displayName
Get-ChildItem 'registry::HKLM\SOFTWARE\Microsoft\Windows Defender\Exclusions' -ErrorAction SilentlyContinue

# local user accounts -> format minimalistically (e.g. only names + who is admin) -> any other interesting info?
net accounts

#################################################
# -- REGISTRY SETTINGS --
#################################################

