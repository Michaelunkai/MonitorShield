' MonitorShield - Silent VBS Launcher
' Launches MonitorShield invisibly (no console window).
' Double-click to run silently in the background.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory of this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Launch Python silently
WshShell.Run "cmd /c cd /d """ & scriptDir & "\src"" && python -m monitor_shield", 0, False

Set WshShell = Nothing
Set fso = Nothing
