// Read the text lines in chat screenshots with Apple's Vision framework (macOS only, nothing to install).
//
//   swift tools/ocr_vision.swift shot1.png shot2.png
//
// Prints JSON: [{"image": path, "width": px, "height": px,
//                "lines": [{"text": "...", "x0": 0-1, "x1": 0-1, "y0": 0-1, "y1": 0-1}]}]
// Coordinates are fractions of the image, measured from the top-left corner.
// tools/screenshot_parser.py compiles this once into a cache folder so later runs are fast.
import AppKit
import Foundation
import Vision

var pages: [[String: Any]] = []
for path in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOfFile: path),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("cannot read image: \(path)\n".data(using: .utf8)!)
        exit(2)
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
    } catch {
        FileHandle.standardError.write("vision failed on \(path): \(error)\n".data(using: .utf8)!)
        exit(3)
    }
    var lines: [[String: Any]] = []
    for observation in request.results ?? [] {
        guard let best = observation.topCandidates(1).first else { continue }
        let box = observation.boundingBox  // normalized, origin bottom-left
        lines.append([
            "text": best.string,
            "x0": box.minX, "x1": box.maxX,
            "y0": 1 - box.maxY, "y1": 1 - box.minY,
        ])
    }
    pages.append(["image": path, "width": cg.width, "height": cg.height, "lines": lines])
}
let data = try JSONSerialization.data(withJSONObject: pages)
FileHandle.standardOutput.write(data)
