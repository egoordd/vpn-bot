// Одна строка текста → PNG с прозрачным фоном, системным шрифтом macOS (CoreText).
// Нужна генератору баннеров для фарси: PIL без libraqm не соединяет арабские буквы
// и не переворачивает строку справа налево, а CoreText делает это сам.
//
//   render_text <текст> <размер px> <вес: regular|medium|semibold|bold|heavy|black> <#RRGGBB> <out.png>
import AppKit

let args = CommandLine.arguments
guard args.count == 6, let size = Double(args[2]) else {
    FileHandle.standardError.write("usage: render_text TEXT SIZE WEIGHT #RRGGBB OUT.png\n".data(using: .utf8)!)
    exit(2)
}
let weights: [String: NSFont.Weight] = [
    "regular": .regular, "medium": .medium, "semibold": .semibold, "bold": .bold, "heavy": .heavy, "black": .black,
]
let font = NSFont.systemFont(ofSize: CGFloat(size), weight: weights[args[3]] ?? .bold)
let hex = Int(args[4].dropFirst(), radix: 16) ?? 0xFFFFFF
let color = NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                    blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
let text = NSAttributedString(string: args[1], attributes: [.font: font, .foregroundColor: color])
let bounds = text.boundingRect(with: NSSize(width: 10000, height: 2000), options: [.usesLineFragmentOrigin])
let pad = 6
let width = Int(ceil(bounds.width)) + pad * 2
let height = Int(ceil(bounds.height)) + pad * 2
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
                                 samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                 bytesPerRow: 0, bitsPerPixel: 0) else { exit(1) }
rep.size = NSSize(width: width, height: height)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
text.draw(with: NSRect(x: pad, y: pad, width: width - pad * 2, height: height - pad * 2), options: [.usesLineFragmentOrigin])
NSGraphicsContext.restoreGraphicsState()
guard let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: args[5]))
