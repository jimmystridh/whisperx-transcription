import SwiftUI

@MainActor
struct IconView: View {
    let status: TranscriptionStatus
    let progress: Double
    let stage: String?

    private var stableKey: String {
        switch self.status {
        case .idle: "idle"
        case let .transcribing(_, currentStage): "transcribing-\(currentStage)"
        case .error: "error"
        case .disconnected: "disconnected"
        }
    }

    var body: some View {
        Group {
            switch self.status {
            case .idle:
                Image(systemName: "waveform")
                    .symbolRenderingMode(.hierarchical)

            case let .transcribing(_, currentStage):
                self.iconForStage(currentStage)

            case .error:
                Image(systemName: "waveform.badge.exclamationmark")
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(.red)

            case .disconnected:
                Image(systemName: "waveform.slash")
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(.secondary)
            }
        }
        .imageScale(.medium)
        .id(self.stableKey)
    }

    @ViewBuilder
    private func iconForStage(_ stage: String) -> some View {
        // Keep all icons waveform-based for consistency
        switch stage {
        case "loading":
            Image(systemName: "waveform.path.ecg")
                .symbolEffect(.pulse)

        case "detecting":
            Image(systemName: "waveform.badge.magnifyingglass")
                .symbolEffect(.pulse)

        case "transcribing":
            Image(systemName: "waveform")
                .symbolEffect(.variableColor.iterative.reversing)

        case "aligning":
            Image(systemName: "waveform.path")
                .symbolEffect(.pulse)

        case "diarization":
            Image(systemName: "waveform.and.person.filled")
                .symbolEffect(.variableColor.iterative)

        case "saving":
            Image(systemName: "waveform.circle")
                .symbolEffect(.pulse)

        case "complete":
            Image(systemName: "waveform.badge.checkmark")
                .symbolEffect(.pulse)

        default:
            Image(systemName: "waveform")
                .symbolEffect(.variableColor.iterative.reversing)
        }
    }
}

// Custom icon renderer for more detailed progress display (optional)
enum IconRenderer {
    static func makeIcon(
        status: TranscriptionStatus,
        progress: Double,
        stale: Bool = false
    ) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size)
        image.lockFocus()

        let trackColor = NSColor.labelColor.withAlphaComponent(stale ? 0.35 : 0.5)
        let fillColor = NSColor.labelColor.withAlphaComponent(stale ? 0.55 : 1.0)

        // Draw waveform bars
        let barCount = 5
        let barWidth: CGFloat = 2
        let spacing: CGFloat = 1.5
        let totalWidth = CGFloat(barCount) * barWidth + CGFloat(barCount - 1) * spacing
        let startX = (size.width - totalWidth) / 2

        let heights: [CGFloat] = [0.4, 0.7, 1.0, 0.7, 0.4]

        for i in 0 ..< barCount {
            let x = startX + CGFloat(i) * (barWidth + spacing)
            let maxHeight: CGFloat = 12
            let height = maxHeight * heights[i]
            let y = (size.height - height) / 2

            let barRect = CGRect(x: x, y: y, width: barWidth, height: height)
            let barPath = NSBezierPath(roundedRect: barRect, xRadius: barWidth / 2, yRadius: barWidth / 2)

            switch status {
            case .idle:
                trackColor.setFill()
                barPath.fill()

            case .transcribing:
                // Fill based on progress
                let progressFill = progress / 100.0
                trackColor.setFill()
                barPath.fill()

                let fillHeight = height * progressFill
                let fillRect = CGRect(x: x, y: y, width: barWidth, height: fillHeight)
                let fillPath = NSBezierPath(roundedRect: fillRect, xRadius: barWidth / 2, yRadius: barWidth / 2)
                fillColor.setFill()
                fillPath.fill()

            case .error:
                NSColor.systemRed.withAlphaComponent(0.7).setFill()
                barPath.fill()

            case .disconnected:
                NSColor.secondaryLabelColor.withAlphaComponent(0.3).setFill()
                barPath.fill()
            }
        }

        image.unlockFocus()
        image.isTemplate = true
        return image
    }
}
