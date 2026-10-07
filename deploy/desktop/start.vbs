Option Explicit
Dim shell, files, root, role, exeName, executable, python, command, versionFile, builtVersion, useExe, expectedVersion
Set shell=CreateObject("WScript.Shell")
Set files=CreateObject("Scripting.FileSystemObject")
root=files.GetParentFolderName(files.GetParentFolderName(files.GetParentFolderName(WScript.ScriptFullName)))
If WScript.Arguments.Count<>1 Then WScript.Quit 1
role=WScript.Arguments(0)
If role="pilot" Then
  exeName="SpotterPilot"
ElseIf role="viewer" Then
  exeName="SpotterViewer"
Else
  WScript.Quit 1
End If
shell.CurrentDirectory=root
executable=files.BuildPath(root,"dist\" & exeName & "\" & exeName & ".exe")
versionFile=files.BuildPath(root,"deploy\desktop\VERSION.txt")
expectedVersion=Trim(files.OpenTextFile(versionFile,1).ReadAll)
builtVersion=files.BuildPath(root,"dist\" & exeName & "\CLIENT_VERSION.txt")
useExe=False
If files.FileExists(executable) And files.FileExists(builtVersion) Then
  useExe=(Trim(files.OpenTextFile(builtVersion,1).ReadAll)=expectedVersion)
End If
If useExe Then
  command=Chr(34) & executable & Chr(34)
Else
  python=files.BuildPath(root,".gui-" & role & "\Scripts\pythonw.exe")
  If Not files.FileExists(python) Then
    MsgBox "Run SETUP_WINDOWS.cmd or BUILD_WINDOWS.cmd once. An older EXE will not be launched by this shortcut.",48,"Remote Spotter"
    WScript.Quit 1
  End If
  command=Chr(34) & python & Chr(34) & " -m remote.desktop." & role & "_entry"
End If
shell.Run command,1,False
