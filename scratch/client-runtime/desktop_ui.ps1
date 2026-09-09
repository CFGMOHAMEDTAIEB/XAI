param([int]$ClickX=-1,[int]$ClickY=-1,[string]$Text='', [string]$ImageName='desktop-runtime.png')
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ReleaseUi {
 [StructLayout(LayoutKind.Sequential)] public struct RECT {public int Left,Top,Right,Bottom;}
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
}
"@
if ($ClickX -ge 0) {
 $point=[IntPtr](($ClickY -shl 16) -bor $ClickX)
 [ReleaseUi]::SendMessage([IntPtr]461280,0x201,[IntPtr]1,$point) | Out-Null
 [ReleaseUi]::SendMessage([IntPtr]461280,0x202,[IntPtr]0,$point) | Out-Null
}
foreach($character in $Text.ToCharArray()) { [ReleaseUi]::SendMessage([IntPtr]461280,0x102,[IntPtr][int]$character,[IntPtr]0) | Out-Null }
Start-Sleep -Milliseconds 750
$rect=New-Object ReleaseUi+RECT
[ReleaseUi]::GetWindowRect([IntPtr]197242,[ref]$rect) | Out-Null
$bitmap=New-Object System.Drawing.Bitmap(($rect.Right-$rect.Left),($rect.Bottom-$rect.Top))
$graphics=[System.Drawing.Graphics]::FromImage($bitmap); $dc=$graphics.GetHdc()
[ReleaseUi]::PrintWindow([IntPtr]197242,$dc,2) | Out-Null
$graphics.ReleaseHdc($dc)
$bitmap.Save((Join-Path $PSScriptRoot $ImageName)); $graphics.Dispose(); $bitmap.Dispose()

