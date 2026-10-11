param([string]$Path, [string]$OwnerPath)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
$probe = $null
$owned = $false
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class WordOwner { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }'
$previous = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
try {
    $word = New-Object -ComObject Word.Application
    $missing = [Type]::Missing
    # Word exposes Hwnd on Window, rather than Application. A hidden temporary
    # document gives us the owning process before changing application settings.
    $probe = $word.Documents.Add($missing, $false, 0, $false)
    [uint32]$wordPid = 0
    [void][WordOwner]::GetWindowThreadProcessId([IntPtr]$probe.ActiveWindow.Hwnd, [ref]$wordPid)
    if (!$wordPid -or $previous -contains $wordPid) { throw 'Word returned an existing instance. It was not modified or closed.' }
    $process = Get-Process -Id $wordPid
    $owned = $true
    @{pid=$wordPid; creation_time=[string]$process.StartTime.ToUniversalTime().ToFileTimeUtc(); owned=$true} | ConvertTo-Json | Set-Content -LiteralPath $OwnerPath -Encoding UTF8
    $probe.Close(0);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($probe);$probe=$null
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $file = (Resolve-Path -LiteralPath $Path).Path
    $document = $word.Documents.Open($file, $false, $true, $false)
    $document.ExportAsFixedFormat([System.IO.Path]::ChangeExtension($file, '.pdf'), 17)
} finally {
    if ($probe) { $probe.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($probe) }
    if ($document) { $document.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($word) {
        if ($owned) { $word.Quit([ref]0) }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
}
