#!/bin/bash
# [Define404] 미팅냥 앱 만들기: ~/Applications/미팅냥.app 을 만든다. 독에 끌어다 두면 원클릭으로 켜진다.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/미팅냥.app"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
osacompile -o "$APP" -e "do shell script quoted form of \"$ROOT/tools/launch.sh\" & \" > /dev/null 2>&1 &\""

# 아이콘: web/logo.svg 를 그려 icns 로
TMP="$(mktemp -d)"
cat > "$TMP/icon.swift" <<'SWIFT'
import AppKit
let src = NSImage(contentsOfFile: CommandLine.arguments[1])!
for s in [16, 32, 64, 128, 256, 512, 1024] {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: s, pixelsHigh: s, bitsPerSample: 8, samplesPerPixel: 4,
                               hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let pad = CGFloat(s) * 0.08
    src.draw(in: NSRect(x: pad, y: pad, width: CGFloat(s) - pad * 2, height: CGFloat(s) - pad * 2))
    NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(CommandLine.arguments[2])/\(s).png"))
}
SWIFT
mkdir -p "$TMP/png" "$TMP/icon.iconset"
swift "$TMP/icon.swift" "$ROOT/web/logo.svg" "$TMP/png"
for s in 16 32 128 256 512; do
  cp "$TMP/png/$s.png" "$TMP/icon.iconset/icon_${s}x${s}.png"
  cp "$TMP/png/$((s * 2)).png" "$TMP/icon.iconset/icon_${s}x${s}@2x.png"
done
iconutil -c icns "$TMP/icon.iconset" -o "$APP/Contents/Resources/applet.icns"
# 새 macOS는 Assets.car 아이콘을 먼저 쓰므로 지우고 applet.icns 를 쓰게 한다
rm -f "$APP/Contents/Resources/Assets.car"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleName 미팅냥" "$APP/Contents/Info.plist" 2>/dev/null || true
codesign --force --deep -s - "$APP" 2>/dev/null || true
rm -rf "$TMP"
touch "$APP"
echo "만들었어요: $APP  (독에 끌어다 두면 한 번에 켜져요)"
