$sourcePath = "D:\☆股票\台股開盤預測儀表板"
$zipPath = "D:\☆股票\台股開盤預測儀表板\taiwan-stock-dashboard.zip"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Write-Host "Creating Production Build ZIP: taiwan-stock-dashboard.zip..."
# Exclude folders that shouldn't be in the production deployment
$exclude = @(".venv", ".git", "__pycache__", "logs", "taiwan-stock-dashboard.zip")

Get-ChildItem -Path $sourcePath -Exclude $exclude | Compress-Archive -DestinationPath $zipPath -Force

Write-Host "Build and ZIP completed successfully."
