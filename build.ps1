# 打包成 dist\外设电量\外设电量.exe
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$env:PYTHONIOENCODING = "utf-8"

# 图标（多尺寸 .ico），缺了才重建
if (-not (Test-Path "app.ico")) {
  $env:PYTHONPATH = $root
  python tools\make_ico.py app.ico
}

$webviewLib = python -c "import webview,os;print(os.path.join(os.path.dirname(webview.__file__),'lib'))"

python -m PyInstaller --noconfirm --onedir --windowed `
  --name "外设电量" `
  --icon "app.ico" `
  --add-data "ui/index.html;ui" `
  --add-data "$webviewLib;webview/lib" `
  --hidden-import webview.platforms.winforms `
  --hidden-import clr `
  --collect-all webview `
  --collect-all clr_loader `
  --collect-all pythonnet `
  periph_battery.py

Write-Host ""
Write-Host "完成： dist\外设电量\外设电量.exe"
