$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Raw = Join-Path $Here 'raw'
New-Item -ItemType Directory -Force -Path $Raw | Out-Null
$Url = 'https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/LPC-EGEE-2004-1.2-cln.swf.gz'
$Dest = Join-Path $Raw 'LPC-EGEE-2004-1.2-cln.swf.gz'
if (-not (Test-Path -LiteralPath $Dest)) {
    & curl.exe --fail -sS --proxy http://127.0.0.1:7897 -L --max-time 90 -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' -H 'Accept-Language: en-US,en;q=0.9' -H 'Sec-Fetch-Dest: document' -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Site: none' -H 'Upgrade-Insecure-Requests: 1' $Url -o $Dest
    if ($LASTEXITCODE -ne 0) { throw 'Download failed' }
}
$Info = Get-Item -LiteralPath $Dest
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Dest).Hash.ToLower()
@{url=$Url; retrieved_utc=(Get-Date).ToUniversalTime().ToString('o'); bytes=$Info.Length; sha256=$Hash} | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Here 'download.json')
Get-Content -LiteralPath (Join-Path $Here 'download.json') | Tee-Object -FilePath (Join-Path $Here 'out_download.txt')
