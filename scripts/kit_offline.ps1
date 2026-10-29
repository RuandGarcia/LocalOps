# Kit offline do estande (plano B, D22): o painel inteiro sem internet.
# Sem API, o chat responde em modo demonstração, com a base real agregada (inclui o relatório em CSV).
# Uso (PowerShell, na raiz do repo):  powershell -ExecutionPolicy Bypass -File scripts\kit_offline.ps1
# Abre http://localhost:8080/#/apresentacao. Ctrl+C encerra.
$raiz = Split-Path $PSScriptRoot -Parent
$web = Join-Path $raiz "apps\web"
$saida = Join-Path $web "dist-offline"
if (-not (Test-Path (Join-Path $saida "index.html"))) {
    npm --prefix $web run build -- --mode offline --outDir dist-offline
}
Start-Process "http://localhost:8080/#/apresentacao"
& (Join-Path $raiz ".venv\Scripts\python.exe") -m http.server 8080 --bind 127.0.0.1 -d $saida
