import AppKit
import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct AddFilesButton: View {
    private static let supportedExtensions = Set(["m4a", "mp4", "mov", "wav", "mp3", "flac", "ogg"])
    private static let supportedTypes: [UTType] = [.audio, .movie, .mpeg4Audio, .wav, .mp3]

    private var incomingFolder: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Documents/whisperx-transcription/incoming")
    }

    var body: some View {
        Button {
            self.openFilePicker()
        } label: {
            Label("Add Files to Transcribe...", systemImage: "plus.circle")
        }
        .buttonStyle(.plain)
        .keyboardShortcut("n", modifiers: [.command])
    }

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = Self.supportedTypes
        panel.message = "Select audio files to transcribe"
        panel.prompt = "Add to Queue"

        // Bring panel to front
        NSApp.activate(ignoringOtherApps: true)

        if panel.runModal() == .OK {
            self.handleFiles(panel.urls)
        }
    }

    private func handleFiles(_ urls: [URL]) {
        let audioFiles = urls.filter { Self.isAudioFile($0) }
        guard !audioFiles.isEmpty else { return }

        do {
            try FileManager.default.createDirectory(at: self.incomingFolder, withIntermediateDirectories: true)

            for file in audioFiles {
                let destination = self.incomingFolder.appendingPathComponent(file.lastPathComponent)
                if FileManager.default.fileExists(atPath: destination.path) {
                    try FileManager.default.removeItem(at: destination)
                }
                try FileManager.default.copyItem(at: file, to: destination)

                // Create marker so daemon knows to delete instead of archive
                // (file already exists elsewhere on disk)
                let marker = self.incomingFolder.appendingPathComponent(file.lastPathComponent + ".noarchive")
                FileManager.default.createFile(atPath: marker.path, contents: nil)
            }

            NotificationManager.shared.notifyFilesAdded(count: audioFiles.count)
        } catch {
            NotificationManager.shared.notifyError(title: "Failed to Add Files", message: error.localizedDescription)
        }
    }

    private static func isAudioFile(_ url: URL) -> Bool {
        Self.supportedExtensions.contains(url.pathExtension.lowercased())
    }
}
