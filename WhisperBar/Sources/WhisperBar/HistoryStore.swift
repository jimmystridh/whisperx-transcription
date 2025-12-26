import Combine
import Foundation

@MainActor
final class HistoryStore: ObservableObject {
    @Published var transcripts: [Transcript] = []
    @Published var isLoading = false

    private let connection: DaemonConnection
    private var eventTask: Task<Void, Never>?
    private var filePollingTask: Task<Void, Never>?

    let transcriptsFolder: URL
    let incomingFolder: URL

    init(connection: DaemonConnection) {
        self.connection = connection

        // Default folders - can be customized
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        self.transcriptsFolder = homeDir
            .appendingPathComponent("Documents/whisperx-transcription/transcripts")
        self.incomingFolder = homeDir
            .appendingPathComponent("Documents/whisperx-transcription/incoming")

        self.startListening()
        Task { await self.loadHistory() }
    }

    private func startListening() {
        self.eventTask = Task {
            for await event in self.connection.events {
                await MainActor.run {
                    self.handleEvent(event)
                }
            }
        }

        // Poll history file periodically
        self.filePollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(10))
                await self.loadHistoryFromFile()
            }
        }
    }

    private func handleEvent(_ event: DaemonEvent) {
        switch event.event {
        case "state":
            if let history = event.history {
                self.transcripts = history
            }

        case "history":
            if let transcripts = event.transcripts {
                self.transcripts = transcripts
            }

        case "completed":
            // A new transcript was completed - reload history
            Task { await self.loadHistory() }

        default:
            break
        }
    }

    func loadHistory() async {
        await self.connection.sendCommand(["command": "history"])
        // Also load from file as backup
        await self.loadHistoryFromFile()
    }

    private func loadHistoryFromFile() async {
        let historyFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".whisperx/history.json")

        guard FileManager.default.fileExists(atPath: historyFile.path) else { return }

        do {
            let data = try Data(contentsOf: historyFile)
            let decoded = try JSONDecoder().decode([String: [Transcript]].self, from: data)

            await MainActor.run {
                if let transcripts = decoded["transcripts"] {
                    // Merge with existing, preferring file data for completeness
                    let existingIds = Set(self.transcripts.map(\.id))
                    let newTranscripts = transcripts.filter { !existingIds.contains($0.id) }
                    self.transcripts = (self.transcripts + newTranscripts)
                        .sorted { ($0.completedDate ?? .distantPast) > ($1.completedDate ?? .distantPast) }
                }
            }
        } catch {
            // History file unreadable
        }
    }

    func refresh() async {
        self.isLoading = true
        await self.loadHistory()
        self.isLoading = false
    }

    deinit {
        self.eventTask?.cancel()
        self.filePollingTask?.cancel()
    }
}
