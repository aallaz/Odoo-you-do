' Raccourci Windows : lance launcher.py sans fenêtre de console.
' Nécessite Python installé (pyw = lanceur Python officiel ; pythonw en secours).
Option Explicit

Dim fso, shell, scriptDir, launcher
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = """" & scriptDir & "\launcher.py"""
shell.CurrentDirectory = scriptDir

On Error Resume Next
shell.Run "pyw " & launcher, 0, False
If Err.Number <> 0 Then
  Err.Clear
  shell.Run "pythonw " & launcher, 0, False
  If Err.Number <> 0 Then
    MsgBox "Python est introuvable. Installez-le depuis https://www.python.org/downloads/ " & _
           "(cochez ""Add python.exe to PATH"")."
  End If
End If
