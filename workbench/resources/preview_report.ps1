param([string]$Path)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $file = (Resolve-Path -LiteralPath $Path).Path
    $document = $word.Documents.Open([ref]$file, [ref]$false, [ref]$true, [ref]$false)
    $document.ExportAsFixedFormat([System.IO.Path]::ChangeExtension($file, '.pdf'), 17)
} finally {
    if ($document) { $document.Close([ref]0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($word) { $word.Quit([ref]0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
}
