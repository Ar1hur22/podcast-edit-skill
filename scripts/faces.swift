// Face boxes for every image in a folder, via macOS Vision (built in, no install).
// Usage: swift scripts/faces.swift <folder>   -> prints JSON {filename: [[x, y, w, h], ...]} in pixels, origin top-left.
import Foundation
import Vision
import AppKit

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path).filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") }.sorted()
var out: [String: [[Int]]] = [:]
for f in files {
    guard let img = NSImage(contentsOf: dir.appendingPathComponent(f)),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNDetectFaceRectanglesRequest()
    try VNImageRequestHandler(cgImage: cg).perform([req])
    let W = Double(cg.width), H = Double(cg.height)
    out[f] = (req.results ?? []).map { r in
        let b = r.boundingBox  // normalised, origin bottom-left
        return [Int(b.minX * W), Int((1 - b.maxY) * H), Int(b.width * W), Int(b.height * H)]
    }
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
