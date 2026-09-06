param([ValidateSet('Setup','Start','Stop','Reset-Demo','Apply-Retention','Test','Status')][string]$Command='Start')
$ErrorActionPreference='Stop'
$ProjectRoot=$PSScriptRoot
$Python=Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$PgBin='C:\Program Files\PostgreSQL\18\bin'
$DataRoot=Join-Path $env:LOCALAPPDATA 'Ternfold'
$PgData=Join-Path $DataRoot 'postgres'
$LogDir=Join-Path $DataRoot 'logs'
$PidFile=Join-Path $DataRoot 'web.pid'
$env:TERNFOLD_CONFIG_FILE=Join-Path $DataRoot '.env'
$WebLog=Join-Path $LogDir 'web.log'
$PgCtl=Join-Path $PgBin 'pg_ctl.exe'
$PgExe=Join-Path $PgBin 'postgres.exe'
$env:TERNFOLD_STORAGE_ROOT=Join-Path $DataRoot 'storage'
$env:TERNFOLD_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/ternfold'

function Ensure-Dirs { New-Item -ItemType Directory -Force -Path $DataRoot,$LogDir | Out-Null }
function Pg-Status { if(Test-Path $PgData){ $null=& (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 2>$null; return ($LASTEXITCODE -eq 0) }; return $false }
function Start-Pg {
  Ensure-Dirs
  if(-not (Test-Path (Join-Path $PgData 'PG_VERSION'))){ throw 'Local database is not initialized. Run .\ternfold.ps1 Setup once.' }
  if(-not (Pg-Status)){
    Start-Process -FilePath $PgExe -ArgumentList '-D',$PgData,'-h','127.0.0.1','-p','55432' -RedirectStandardOutput (Join-Path $LogDir 'postgres-stdout.log') -RedirectStandardError (Join-Path $LogDir 'postgres.log') -WindowStyle Hidden | Out-Null
    $Ready=$false
    1..20 | ForEach-Object { if(-not $Ready){ Start-Sleep -Milliseconds 500; $null=& (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432; $Ready=($LASTEXITCODE -eq 0) } }
    if(-not $Ready){ throw 'The isolated PostgreSQL server could not start. See %LOCALAPPDATA%\Ternfold\logs\postgres.log.' }
  }
}

Set-Location $ProjectRoot
if($Command -eq 'Setup'){
  Ensure-Dirs
  if(-not (Test-Path $env:TERNFOLD_CONFIG_FILE)){ Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $env:TERNFOLD_CONFIG_FILE }
  if(-not (Test-Path $Python)){ throw 'Python environment is missing. Create .venv and install requirements.txt.' }
  if(-not (Test-Path (Join-Path $PgData 'PG_VERSION'))){ & (Join-Path $PgBin 'initdb.exe') -D $PgData -U postgres -A trust -E UTF8 --locale=C | Out-Null }
  Start-Pg
  & (Join-Path $PgBin 'createdb.exe') -h 127.0.0.1 -p 55432 -U postgres ternfold 2>$null
  & $Python -m ternfold.cli init
  & $Python -m ternfold.cli seed
  Write-Output 'Setup complete. Run .\ternfold.ps1 Start and open http://127.0.0.1:8000/login'
  exit
}
if($Command -eq 'Start'){
  Start-Pg
  if(Test-Path $PidFile){ $Existing=[int](Get-Content $PidFile); if(Get-Process -Id $Existing -ErrorAction SilentlyContinue){ Write-Output 'Ternfold is already running at http://127.0.0.1:8000/login'; exit } }
  $Process=Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','ternfold.app:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $ProjectRoot -RedirectStandardOutput $WebLog -RedirectStandardError (Join-Path $LogDir 'web-error.log') -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $PidFile -Value $Process.Id
  $Health=$null
  1..20 | ForEach-Object { if(-not $Health){ Start-Sleep -Milliseconds 500; try { $Health=Invoke-RestMethod 'http://127.0.0.1:8000/health' } catch {} } }
  if($Health){
    $Listener=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if($Listener){ Set-Content -LiteralPath $PidFile -Value $Listener.OwningProcess }
    Write-Output "Ternfold running: http://127.0.0.1:8000/login (database=$($Health.database), live AI=$($Health.ai))"
  } else { Get-Content (Join-Path $LogDir 'web-error.log') -Tail 30; throw 'Ternfold did not start.' }
  exit
}
if($Command -eq 'Stop'){
  if(Test-Path $PidFile){ $Id=[int](Get-Content $PidFile); Stop-Process -Id $Id -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $PidFile -Force }
  if(Pg-Status){ & $PgCtl stop -D $PgData -m fast -w | Out-Null }
  Write-Output 'Ternfold local processes stopped.'; exit
}
if($Command -eq 'Reset-Demo'){ Start-Pg; & $Python -m ternfold.cli reset-demo; exit }
if($Command -eq 'Apply-Retention'){ Start-Pg; & $Python -m ternfold.cli apply-retention; exit $LASTEXITCODE }
if($Command -eq 'Test'){
  Start-Pg
  & (Join-Path $PgBin 'createdb.exe') -h 127.0.0.1 -p 55432 -U postgres ternfold_test 2>$null
  $env:TERNFOLD_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/ternfold_test'
  $env:TERNFOLD_STORAGE_ROOT=Join-Path $ProjectRoot 'tmp\test-storage'
  & $Python -m pytest -q -p no:cacheprovider
  exit $LASTEXITCODE
}
if($Command -eq 'Status'){
  $Running=$false; if(Test-Path $PidFile){ $Id=[int](Get-Content $PidFile); $Running=[bool](Get-Process -Id $Id -ErrorAction SilentlyContinue) }
  Write-Output "Web running: $Running"; Write-Output "PostgreSQL running: $(Pg-Status)"; exit
}
