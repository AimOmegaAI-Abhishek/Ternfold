param([ValidateSet('Setup','Start','Stop','Status')][string]$Command='Start')
$ErrorActionPreference='Stop'
$ProjectRoot=$PSScriptRoot
$Python=Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$DataRoot=Join-Path $env:LOCALAPPDATA 'Ternfold'
$LogDir=Join-Path $DataRoot 'logs'
$PidFile=Join-Path $DataRoot 'web.pid'
$env:TERNFOLD_CONFIG_FILE=Join-Path $DataRoot '.env'
$env:TERNFOLD_STORAGE_ROOT=Join-Path $DataRoot 'storage'
Remove-Item Env:TERNFOLD_DATABASE_URL -ErrorAction SilentlyContinue

function Ensure-Config {
  New-Item -ItemType Directory -Force -Path $DataRoot,$LogDir | Out-Null
  if(-not (Test-Path $env:TERNFOLD_CONFIG_FILE)){ Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $env:TERNFOLD_CONFIG_FILE }
  if(-not (Select-String -LiteralPath $env:TERNFOLD_CONFIG_FILE -Pattern '^SUPABASE_DATABASE_URL=.+')){ throw 'Add the Supabase session-pooler connection string to %LOCALAPPDATA%\Ternfold\.env first.' }
}

Set-Location $ProjectRoot
if($Command -eq 'Setup'){
  Ensure-Config
  & $Python -m ternfold.cli init
  if($LASTEXITCODE -ne 0){ throw 'Supabase migration failed. No synthetic seeding was attempted.' }
  & $Python -m ternfold.cli seed
  if($LASTEXITCODE -ne 0){ throw 'Supabase migration succeeded, but synthetic seeding failed.' }
  Write-Output 'Supabase schema and synthetic demonstration are ready.'
  exit
}
if($Command -eq 'Start'){
  Ensure-Config
  if(Test-Path $PidFile){ $Existing=[int](Get-Content $PidFile); if(Get-Process -Id $Existing -ErrorAction SilentlyContinue){ Write-Output 'Ternfold is already running at http://127.0.0.1:8000/login'; exit } }
  $Process=Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','ternfold.app:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $ProjectRoot -RedirectStandardOutput (Join-Path $LogDir 'web.log') -RedirectStandardError (Join-Path $LogDir 'web-error.log') -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $PidFile -Value $Process.Id
  $Health=$null
  1..30 | ForEach-Object { if(-not $Health){ Start-Sleep -Milliseconds 500; try { $Health=Invoke-RestMethod 'http://127.0.0.1:8000/health' } catch {} } }
  if(-not $Health){ Get-Content (Join-Path $LogDir 'web-error.log') -Tail 30; throw 'Ternfold did not connect to Supabase.' }
  $Listener=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($Listener){ Set-Content -LiteralPath $PidFile -Value $Listener.OwningProcess }
  Write-Output "Ternfold running with Supabase: http://127.0.0.1:8000/login (live AI=$($Health.ai))"
  exit
}
if($Command -eq 'Stop'){
  if(Test-Path $PidFile){ $Id=[int](Get-Content $PidFile); Stop-Process -Id $Id -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $PidFile -Force }
  Write-Output 'Ternfold web process stopped.'; exit
}
if($Command -eq 'Status'){
  $Running=$false; if(Test-Path $PidFile){ $Id=[int](Get-Content $PidFile); $Running=[bool](Get-Process -Id $Id -ErrorAction SilentlyContinue) }
  Write-Output "Web running: $Running"; exit
}

