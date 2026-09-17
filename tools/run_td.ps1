param([int]$ShotAfter = 30, [int]$MaxWait = 120, [string]$Toe = "C:\Users\NORWAY_PC\Documents\RAYTRACER\tools\RayTest.toe")
$log = "C:\Users\NORWAY_PC\Documents\RAYTRACER\tools\td_log.txt"
$shot = "C:\Users\NORWAY_PC\AppData\Local\Temp\claude\C--Users-NORWAY-PC-Documents-RAYTRACER\7ae50c37-1956-4e5e-840a-dccfeb7d7607\scratchpad\td_screen.png"
if (Test-Path $log) { Clear-Content $log }
$p = Start-Process -FilePath "C:\Program Files\Derivative\TouchDesigner\bin\TouchDesigner.exe" -ArgumentList ('"' + $Toe + '"') -PassThru
$t0 = Get-Date; $shotDone = $false
while (-not $p.HasExited -and ((Get-Date) - $t0).TotalSeconds -lt $MaxWait) {
  Start-Sleep -Seconds 2
  if (-not $shotDone -and ((Get-Date) - $t0).TotalSeconds -ge $ShotAfter) {
    Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png); "screenshot $($b.Width)x$($b.Height)"
    Get-Process | Where-Object { $_.Name -like "Touch*" } | Select-Object Id, Name, MainWindowTitle | Format-Table | Out-String
    $shotDone = $true
  }
}
"exited: $($p.HasExited) after $([int]((Get-Date)-$t0).TotalSeconds)s"
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; "killed" }
"--- LOG ---"; if (Test-Path $log) { Get-Content $log } else { "NO LOG FILE" }
