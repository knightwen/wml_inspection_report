param([string]$Path, [string]$OwnerPath, [string]$LogoPath)
$ErrorActionPreference = 'Stop'
$excel = $null
$book = $null
$owned = $false
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class ExcelOwner { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }'
$previous = @(Get-Process -Name EXCEL -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
try {
    $excel = New-Object -ComObject Excel.Application
    [uint32]$excelPid = 0
    [void][ExcelOwner]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$excelPid)
    if (!$excelPid -or $previous -contains $excelPid) { throw 'Excel returned an existing instance. It was not modified or closed.' }
    if ($excel.Workbooks.Count -ne 0) { throw 'Excel opened with other workbooks. This instance was not modified or closed.' }
    $process = Get-Process -Id $excelPid
    $owned = $true
    @{pid=$excelPid; creation_time=[string]$process.StartTime.ToUniversalTime().ToFileTimeUtc(); owned=$true} | ConvertTo-Json | Set-Content -LiteralPath $OwnerPath -Encoding UTF8
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AutomationSecurity = 3
    $excel.AskToUpdateLinks = $false
    $file = (Resolve-Path -LiteralPath $Path).Path
    $book = $excel.Workbooks.Open($file, 0, $false)
    # Header images repeat on every page, including long modules.
    foreach ($name in @('Cover','Contents','Report')) {
        $sheet = $book.Worksheets.Item($name)
        $sheet.PageSetup.LeftHeaderPicture.Filename = (Resolve-Path -LiteralPath $LogoPath).Path
        $sheet.PageSetup.LeftHeaderPicture.Height = 44
        $sheet.PageSetup.LeftHeaderPicture.Width = 42
        $sheet.PageSetup.LeftHeader = '&G'
    }
    $report = $book.Worksheets.Item('Report')
    $contents = $book.Worksheets.Item('Contents')
    $outline = $book.Worksheets.Item('_Outline')
    $pdf = [System.IO.Path]::ChangeExtension($file, '.pdf')
    # HPageBreaks omits automatic breaks with FitToPagesWide on some Excel
    # versions. The parent reads the actual printed report instead.
    $book.ExportAsFixedFormat(0, $pdf, 0, $true, $false)
    $report.ExportAsFixedFormat(0, [System.IO.Path]::ChangeExtension($file, '.report.pdf'), 0, $true, $false)
    $headings = @()
    for ($row=2; $row -le $outline.UsedRange.Rows.Count; $row++) {
        $headings += @{row=[int]$outline.Cells.Item($row,2).Value2; title=[string]$outline.Cells.Item($row,3).Value2}
    }
    @{headings=$headings} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ([System.IO.Path]::ChangeExtension($file, '.toc-request.json')) -Encoding UTF8
    $tocPath = [System.IO.Path]::ChangeExtension($file, '.toc.json')
    $started = Get-Date
    while (!(Test-Path -LiteralPath $tocPath)) {
        if (((Get-Date)-$started).TotalSeconds -gt 45) { throw 'Timed out waiting for printed-page directory.' }
        Start-Sleep -Milliseconds 100
    }
    $numbers = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $tocPath -Raw -Encoding UTF8)
    foreach ($entry in $numbers) {
        $contents.Cells.Item([int]$entry.row,19).Value2 = [string]$entry.page
    }
    $book.Worksheets.Item('Cover').Activate()
    $book.Save()
    $book.ExportAsFixedFormat(0, $pdf, 0, $true, $false)
} finally {
    if ($book) { try { $book.Close($false) } catch { Write-Warning $_ }; try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) } catch {} }
    if ($excel) {
        if ($owned) { try { $excel.Quit() } catch { Write-Warning $_ } }
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) } catch {}
    }
}
