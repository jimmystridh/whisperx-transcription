import AppKit
import SwiftUI

@MainActor
struct MenuContent: View {
    @ObservedObject var transcriptionStore: TranscriptionStore
    @ObservedObject var historyStore: HistoryStore
    @ObservedObject var settings: SettingsStore
    @ObservedObject var daemonController: DaemonController

    @State private var searchQuery = ""

    private var filteredTranscripts: [Transcript] {
        guard !self.searchQuery.isEmpty else {
            return Array(self.historyStore.transcripts.prefix(self.settings.maxRecentTranscripts))
        }
        return self.historyStore.transcripts
            .filter { $0.originalFilename.localizedCaseInsensitiveContains(self.searchQuery) }
            .prefix(self.settings.maxRecentTranscripts)
            .map { $0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Add Files Button
            AddFilesButton()

            // Status Section
            StatusSection(
                status: self.transcriptionStore.status,
                progress: self.transcriptionStore.progress,
                stage: self.transcriptionStore.currentStage,
                detail: self.transcriptionStore.currentDetail,
                queue: self.transcriptionStore.queue,
                daemonRunning: self.daemonController.isRunning,
                onClearError: { self.clearErrorState() })

            Divider()

            // Recent Transcripts
            HStack {
                Text("Recent Transcripts")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                Spacer()
                if self.historyStore.transcripts.count > 3 {
                    Text("\(self.historyStore.transcripts.count)")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                        .padding(.horizontal, 6)
                        .background(Capsule().fill(.quaternary))
                }
            }

            // Search field
            if self.historyStore.transcripts.count > 3 {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                    TextField("Search transcripts...", text: self.$searchQuery)
                        .textFieldStyle(.plain)
                        .font(.caption)
                    if !self.searchQuery.isEmpty {
                        Button {
                            self.searchQuery = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .background(RoundedRectangle(cornerRadius: 4).fill(.quaternary))
            }

            if self.historyStore.transcripts.isEmpty {
                Text("No transcripts yet")
                    .foregroundStyle(.tertiary)
                    .padding(.vertical, 4)
            } else if self.filteredTranscripts.isEmpty {
                Text("No matching transcripts")
                    .foregroundStyle(.tertiary)
                    .padding(.vertical, 4)
            } else {
                ForEach(self.filteredTranscripts) { transcript in
                    TranscriptRow(transcript: transcript)
                }
            }

            Divider()

            // Daemon Control
            DaemonControlSection(controller: self.daemonController)

            Divider()

            // Quick Actions
            if let latest = self.historyStore.transcripts.first, latest.success {
                Button {
                    self.openLatestTranscript()
                } label: {
                    Label("Open Latest Transcript", systemImage: "doc.text")
                }
                .buttonStyle(.plain)
                .keyboardShortcut("o", modifiers: [.command])
            }

            // Folder Actions
            Button {
                NSWorkspace.shared.open(self.historyStore.transcriptsFolder)
            } label: {
                Label("Open Transcripts Folder", systemImage: "folder")
            }
            .buttonStyle(.plain)
            .keyboardShortcut("t", modifiers: [.command, .shift])

            Button {
                NSWorkspace.shared.open(self.historyStore.incomingFolder)
            } label: {
                Label("Open Incoming Folder", systemImage: "tray.and.arrow.down")
            }
            .buttonStyle(.plain)
            .keyboardShortcut("i", modifiers: [.command, .shift])

            Divider()

            Button {
                LogWindowController.shared.showLogWindow()
            } label: {
                Label("View Daemon Log", systemImage: "doc.text.magnifyingglass")
            }
            .buttonStyle(.plain)
            .keyboardShortcut("l", modifiers: [.command])

            // Settings Menu
            Menu("Settings") {
                Toggle("Notifications", isOn: self.$settings.notificationsEnabled)
                Toggle("Show Progress in Icon", isOn: self.$settings.showProgressInIcon)
                Toggle("Launch at Login", isOn: self.$settings.launchAtLogin)

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

    private func openLatestTranscript() {
        guard let latest = self.historyStore.transcripts.first,
              latest.success else { return }

        let transcriptURL = URL(fileURLWithPath: latest.transcriptPath)
        NSWorkspace.shared.open(transcriptURL)
    }

    private func clearErrorState() {
        let stateFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".whisperx/state.json")

        do {
            let data = try Data(contentsOf: stateFile)
            if var json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                json["status"] = "idle"
                json["error_message"] = nil
                json["last_updated"] = ISO8601DateFormatter().string(from: Date())
                let newData = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted])
                try newData.write(to: stateFile)
            }
        } catch {
            // Silently ignore errors
        }
    }
}

@MainActor
struct StatusSection: View {
    let status: TranscriptionStatus
    let progress: Double
    let stage: String?
    let detail: String?
    let queue: [String]
    var daemonRunning: Bool = true
    var onClearError: (() -> Void)?

    private func clearErrorState() {
        self.onClearError?()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Override disconnected status if daemon is actually running
            if !self.daemonRunning {
                HStack {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .foregroundStyle(.orange)
                    Text("Daemon Not Running")
                        .font(.headline)
                }
                Text("Start daemon to enable transcription")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                self.statusContent
            }

            if !self.queue.isEmpty {
                Divider()
                QueueSection(queue: self.queue)
            }
        }
    }

    @ViewBuilder
    private var statusContent: some View {
        switch self.status {
        case .idle, .disconnected:
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
                        .animation(nil, value: self.progress)

                    Text("\(Int(self.progress))%")
                        .font(.caption)
                        .monospacedDigit()
                        .contentTransition(.identity)
                }

                if let detail = self.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text(self.stageDescription(stage))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

            case let .error(message):
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text("Last Transcription Failed")
                        .font(.headline)
                }
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                Button {
                    self.clearErrorState()
                } label: {
                    Label("Dismiss", systemImage: "xmark.circle")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .padding(.top, 2)

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

@MainActor
struct DaemonControlSection: View {
    @ObservedObject var controller: DaemonController
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: self.controller.isRunning ? "circle.fill" : "circle")
                    .foregroundStyle(self.controller.isRunning ? .green : .secondary)
                    .font(.caption)
                Text(self.controller.isRunning ? "Daemon Running" : "Daemon Stopped")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let pid = self.controller.pid, self.controller.isRunning {
                    Text("(PID \(pid))")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            if self.isLoading {
                HStack {
                    ProgressView()
                        .scaleEffect(0.6)
                    Text("Please wait...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                HStack(spacing: 12) {
                    if self.controller.isRunning {
                        Button {
                            self.stopDaemon()
                        } label: {
                            Label("Stop", systemImage: "stop.fill")
                        }
                        .buttonStyle(.plain)

                        Button {
                            self.restartDaemon()
                        } label: {
                            Label("Restart", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(.plain)
                    } else {
                        Button {
                            self.startDaemon()
                        } label: {
                            Label("Start Daemon", systemImage: "play.fill")
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if let error = self.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
        }
    }

    private func startDaemon() {
        self.isLoading = true
        self.errorMessage = nil
        Task {
            do {
                try await self.controller.startDaemon()
            } catch {
                self.errorMessage = error.localizedDescription
            }
            self.isLoading = false
        }
    }

    private func stopDaemon() {
        self.isLoading = true
        self.errorMessage = nil
        Task {
            do {
                try await self.controller.stopDaemon()
            } catch {
                self.errorMessage = error.localizedDescription
            }
            self.isLoading = false
        }
    }

    private func restartDaemon() {
        self.isLoading = true
        self.errorMessage = nil
        Task {
            do {
                try await self.controller.restartDaemon()
            } catch {
                self.errorMessage = error.localizedDescription
            }
            self.isLoading = false
        }
    }
}

@MainActor
struct QueueSection: View {
    let queue: [String]
    @State private var isExpanded: Bool = false

    private var incomingFolder: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Documents/whisperx-transcription/incoming")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    self.isExpanded.toggle()
                }
            } label: {
                HStack {
                    Image(systemName: "list.bullet")
                        .foregroundStyle(.blue)
                    Text("Queue")
                        .font(.caption)
                    Text("\(self.queue.count)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .background(Capsule().fill(.quaternary))
                    Spacer()
                    Image(systemName: self.isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }
            }
            .buttonStyle(.plain)

            if self.isExpanded {
                ForEach(Array(self.queue.prefix(5).enumerated()), id: \.offset) { index, filename in
                    HStack {
                        Text("\(index + 1).")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .frame(width: 16, alignment: .trailing)
                        Text(filename)
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Spacer()
                        Button {
                            self.removeFromQueue(filename)
                        } label: {
                            Image(systemName: "xmark.circle")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("Remove from queue")
                    }
                    .padding(.leading, 4)
                }

                if self.queue.count > 5 {
                    Text("... and \(self.queue.count - 5) more")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .padding(.leading, 20)
                }

                HStack {
                    Button {
                        self.clearQueue()
                    } label: {
                        Label("Clear Queue", systemImage: "trash")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.red)
                }
                .padding(.top, 4)
            }
        }
    }

    private func removeFromQueue(_ filename: String) {
        let fileURL = self.incomingFolder.appendingPathComponent(filename)
        try? FileManager.default.removeItem(at: fileURL)
    }

    private func clearQueue() {
        for filename in self.queue {
            let fileURL = self.incomingFolder.appendingPathComponent(filename)
            try? FileManager.default.removeItem(at: fileURL)
        }
    }
}
