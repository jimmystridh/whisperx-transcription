import AppKit
import SwiftUI

@MainActor
struct TranscriptRow: View {
    let transcript: Transcript
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 8) {
            // Status indicator
            if self.transcript.success {
                Text(self.transcript.languageFlag)
                    .font(.caption)
            } else {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundStyle(.red)
                    .font(.caption)
            }

            // Transcript info
            VStack(alignment: .leading, spacing: 2) {
                Text(self.transcript.displayName)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .fontWeight(self.isHovered ? .medium : .regular)

                HStack(spacing: 4) {
                    Text(self.transcript.formattedDuration)

                    if self.transcript.speakerCount > 0 {
                        Text("•")
                        Text("\(self.transcript.speakerCount) speaker\(self.transcript.speakerCount == 1 ? "" : "s")")
                    }

                    if let date = self.transcript.completedDate {
                        Text("•")
                        Text(self.relativeTime(from: date))
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()

            // Action buttons (shown on hover)
            if self.isHovered {
                Button {
                    self.copyTranscript()
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .help("Copy transcript to clipboard")

                Button {
                    self.openInEditor()
                } label: {
                    Image(systemName: "square.and.pencil")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .help("Open in editor")
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 4)
        .background(self.isHovered ? Color.primary.opacity(0.05) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .contentShape(Rectangle())
        .onHover { self.isHovered = $0 }
        .onTapGesture {
            self.openInEditor()
        }
    }

    private func relativeTime(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func copyTranscript() {
        let path = URL(fileURLWithPath: self.transcript.transcriptPath)

        guard FileManager.default.fileExists(atPath: path.path) else {
            // Try to find a .txt file with the same name in transcripts folder
            let homeDir = FileManager.default.homeDirectoryForCurrentUser
            let transcriptsDir = homeDir.appendingPathComponent("Documents/whisperx-transcription/transcripts")
            let txtPath = transcriptsDir.appendingPathComponent("\(self.transcript.displayName).txt")

            if FileManager.default.fileExists(atPath: txtPath.path),
               let content = try? String(contentsOf: txtPath, encoding: .utf8)
            {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(content, forType: .string)
            }
            return
        }

        if let content = try? String(contentsOf: path, encoding: .utf8) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(content, forType: .string)
        }
    }

    private func openInEditor() {
        let path = URL(fileURLWithPath: self.transcript.transcriptPath)
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let transcriptsDir = homeDir.appendingPathComponent("Documents/whisperx-transcription/transcripts")

        // First try the recorded path
        var targetPath = path

        // If it doesn't exist, try finding it in transcripts folder
        if !FileManager.default.fileExists(atPath: targetPath.path) {
            let txtPath = transcriptsDir.appendingPathComponent("\(self.transcript.displayName).txt")
            if FileManager.default.fileExists(atPath: txtPath.path) {
                targetPath = txtPath
            } else {
                // Can't find the file
                return
            }
        }

        // Check for EDITOR environment variable
        if let editor = ProcessInfo.processInfo.environment["EDITOR"], !editor.isEmpty {
            // Launch editor in Terminal
            let script = """
            tell application "Terminal"
                activate
                do script "\(editor) '\(targetPath.path)'"
            end tell
            """

            var error: NSDictionary?
            if let appleScript = NSAppleScript(source: script) {
                appleScript.executeAndReturnError(&error)
                if error == nil {
                    return
                }
            }
        }

        // Fallback to default app (usually TextEdit)
        NSWorkspace.shared.open(targetPath)
    }
}
