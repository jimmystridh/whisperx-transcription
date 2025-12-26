import AppKit
import Sparkle
import SwiftUI

@MainActor
struct MenuContent: View {
    @ObservedObject var transcriptionStore: TranscriptionStore
    @ObservedObject var historyStore: HistoryStore
    @ObservedObject var settings: SettingsStore
    let updater: SPUStandardUpdaterController

    private var autoUpdateBinding: Binding<Bool> {
        Binding(
            get: { self.updater.updater.automaticallyChecksForUpdates },
            set: { self.updater.updater.automaticallyChecksForUpdates = $0 })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Status Section
            StatusSection(
                status: self.transcriptionStore.status,
                progress: self.transcriptionStore.progress,
                stage: self.transcriptionStore.currentStage,
                queue: self.transcriptionStore.queue)

            Divider()

            // Recent Transcripts
            Text("Recent Transcripts")
                .font(.headline)
                .foregroundStyle(.secondary)

            if self.historyStore.transcripts.isEmpty {
                Text("No transcripts yet")
                    .foregroundStyle(.tertiary)
                    .padding(.vertical, 4)
            } else {
                ForEach(self.historyStore.transcripts.prefix(self.settings.maxRecentTranscripts)) { transcript in
                    TranscriptRow(transcript: transcript)
                }
            }

            Divider()

            // Folder Actions
            Button {
                NSWorkspace.shared.open(self.historyStore.transcriptsFolder)
            } label: {
                Label("Open Transcripts Folder", systemImage: "folder")
            }
            .buttonStyle(.plain)

            Button {
                NSWorkspace.shared.open(self.historyStore.incomingFolder)
            } label: {
                Label("Open Incoming Folder", systemImage: "tray.and.arrow.down")
            }
            .buttonStyle(.plain)

            Divider()

            // Settings Menu
            Menu("Settings") {
                Toggle("Notifications", isOn: self.$settings.notificationsEnabled)
                Toggle("Show Progress in Icon", isOn: self.$settings.showProgressInIcon)
                Toggle("Launch at Login", isOn: self.$settings.launchAtLogin)

                Divider()

                Toggle("Automatically check for updates", isOn: self.autoUpdateBinding)
                Button("Check for Updates...") {
                    self.updater.checkForUpdates(nil)
                }

                if self.settings.debugMenuEnabled {
                    Divider()
                    Button("Reload History") {
                        Task { await self.historyStore.refresh() }
                    }
                }
            }
            .buttonStyle(.plain)

            Button("Quit WhisperBar") {
                NSApp.terminate(nil)
            }
            .buttonStyle(.plain)
            .keyboardShortcut("q")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(minWidth: 300, alignment: .leading)
        .foregroundStyle(.primary)
    }
}

@MainActor
struct StatusSection: View {
    let status: TranscriptionStatus
    let progress: Double
    let stage: String?
    let queue: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            switch self.status {
            case .idle:
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("Ready")
                        .font(.headline)
                }
                Text("Drop audio files into incoming folder")
                    .font(.caption)
                    .foregroundStyle(.secondary)

            case let .transcribing(filename, stage):
                HStack {
                    Image(systemName: "waveform")
                        .symbolEffect(.variableColor.iterative.reversing)
                        .foregroundStyle(.blue)
                    Text("Transcribing")
                        .font(.headline)
                }

                Text(filename)
                    .lineLimit(1)
                    .truncationMode(.middle)

                HStack {
                    ProgressView(value: self.progress, total: 100)
                        .progressViewStyle(.linear)

                    Text("\(Int(self.progress))%")
                        .font(.caption)
                        .monospacedDigit()
                }

                Text(self.stageDescription(stage))
                    .font(.caption)
                    .foregroundStyle(.secondary)

            case let .error(message):
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                    Text("Error")
                        .font(.headline)
                }
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

            case .disconnected:
                HStack {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .foregroundStyle(.orange)
                    Text("Daemon Not Running")
                        .font(.headline)
                }
                Text("Start whisperxd to enable transcription")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !self.queue.isEmpty {
                Divider()
                Text("Queue: \(self.queue.count) file(s)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func stageDescription(_ stage: String) -> String {
        switch stage {
        case "loading": "Loading audio..."
        case "detecting": "Detecting language..."
        case "transcribing": "Transcribing speech..."
        case "aligning": "Aligning timestamps..."
        case "diarization": "Identifying speakers..."
        case "saving": "Saving output..."
        default: stage.capitalized
        }
    }
}
