# Puts PurrOS on the Windows Desktop and in the Start menu. Run from WSL:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w ~/purros/host/install-windows.ps1)"
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $env:LOCALAPPDATA 'PurrOS'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item -Force (Join-Path $here 'purros.ico') (Join-Path $dir 'purros.ico')
# wscript runs wsl hidden, so no console window sits behind the PurrOS window
$vbs = Join-Path $dir 'purros.vbs'
Set-Content -Encoding ASCII -Path $vbs -Value 'CreateObject("WScript.Shell").Run "wsl.exe -d Ubuntu-24.04 -e /Users/joshwald/purros/host/purros", 0, False'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $lnk = $shell.CreateShortcut((Join-Path $folder 'PurrOS.lnk'))
  $lnk.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
  $lnk.Arguments = '"' + $vbs + '"'
  $lnk.IconLocation = (Join-Path $dir 'purros.ico') + ',0'
  $lnk.Description = 'PurrOS, a small cozy computer'
  $lnk.WorkingDirectory = $dir
  $lnk.Save()
  Write-Output ('made ' + (Join-Path $folder 'PurrOS.lnk'))
}
