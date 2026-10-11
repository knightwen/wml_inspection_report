param([string[]]$Paths = @(
    'workbench/resources/report_template.docx',
    '.build/qa/generated-sample.docx',
    '.build/qa/legacy-template-regression.docx',
    '.build/qa/photo-names.docx',
    '.build/qa/edited-photo.docx'
))

# Developer/CI verification only; the portable application does not need this SDK.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$cache = Join-Path $root '.build/openxml-validator'
$archive = Join-Path $cache 'sdk.zip'
$expectedHash = '053312E1A2A606DCC5BCFCFF6CC9F37235A1F43B3745AC907283D3122CE9F768'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
if (!(Test-Path -LiteralPath $archive)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri 'https://api.nuget.org/v3-flatcontainer/documentformat.openxml/2.20.0/documentformat.openxml.2.20.0.nupkg' -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Open XML SDK checksum mismatch. Cached download must be reviewed.'
}
$dll = Join-Path $cache 'sdk/lib/net46/DocumentFormat.OpenXml.dll'
if (!(Test-Path -LiteralPath $dll)) {
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $cache 'sdk') -Force
}
Add-Type -AssemblyName WindowsBase
Add-Type -Path $dll
if ([DocumentFormat.OpenXml.Validation.OpenXmlValidator].Assembly.GetName().Version -ne [Version]'2.20.0.0') {
    throw 'Unexpected Open XML SDK version in cache.'
}
$validator = New-Object DocumentFormat.OpenXml.Validation.OpenXmlValidator([DocumentFormat.OpenXml.FileFormatVersions]::Office2019)
$errorCount = 0
foreach ($path in $Paths) {
    $file = if ([IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $root $path }
    $document = [DocumentFormat.OpenXml.Packaging.WordprocessingDocument]::Open((Resolve-Path -LiteralPath $file).Path, $false)
    try {
        $errors = @($validator.Validate($document))
        Write-Output "$path : $($errors.Count) Open XML errors"
        foreach ($error in $errors) {
            Write-Output "$($error.Part.Uri) $($error.Path.XPath): $($error.Description)"
        }
        $errorCount += $errors.Count
    } finally { $document.Dispose() }
}
if ($errorCount -gt 0) { throw "$errorCount Open XML errors found. Reports must not be distributed." }
