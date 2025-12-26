import Combine
import Foundation

@MainActor
final class TranscriptionStore: ObservableObject {
    @Published var status: TranscriptionStatus = .disconnected
    @Published var progress: Double = 0
    @Published var currentFilename: String?
    @Published var currentStage: String?
    @Published var queue: [String] = []
    @Published var isConnected: Bool = false

    private let connection: DaemonConnection
    private var eventTask: Task<Void, Never>?
    private var statePollingTask: Task<Void, Never>?

    init(connection: DaemonConnection) {
        self.connection = connection
        self.startConnection()
    }

    private func startConnection() {
        self.eventTask = Task {
            await self.connection.connect()

            for await event in self.connection.events {
                await MainActor.run {
                    self.handleEvent(event)
                }
            }
        }

        // Poll for state file if socket fails
        self.statePollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2))
                if !self.isConnected {
                    await self.loadStateFromFile()
                }
            }
        }
    }

    private func handleEvent(_ event: DaemonEvent) {
        self.isConnected = true

        switch event.event {
        case "state":
            if let current = event.current {
                self.status = .transcribing(filename: current.filename, stage: current.stage)
                self.progress = current.progressPercent
                self.currentFilename = current.filename
                self.currentStage = current.stage
            } else if event.status == "idle" {
                self.status = .idle
                self.progress = 0
                self.currentFilename = nil
                self.currentStage = nil
            } else if event.status == "error", let errorMsg = event.error {
                self.status = .error(errorMsg)
            }
            self.queue = event.queue ?? []

        case "started":
            if let filename = event.filename {
                self.status = .transcribing(filename: filename, stage: "loading")
                self.progress = 0
                self.currentFilename = filename
                self.currentStage = "loading"
                NotificationManager.shared.notifyStarted(
                    filename: filename,
                    duration: event.durationSeconds ?? 0)
            }

        case "progress":
            self.progress = event.percent ?? 0
            if let stage = event.stage {
                self.currentStage = stage
                if let filename = self.currentFilename {
                    self.status = .transcribing(filename: filename, stage: stage)
                }
            }

        case "completed":
            self.status = .idle
            self.progress = 0
            self.currentFilename = nil
            self.currentStage = nil
            if let filename = event.filename {
                NotificationManager.shared.notifyCompleted(
                    filename: filename,
                    transcriptPath: event.transcriptPath,
                    language: event.language ?? "unknown",
                    speakerCount: event.speakerCount ?? 0)
            }

        case "failed":
            self.status = .error(event.error ?? "Unknown error")
            self.currentFilename = nil
            self.currentStage = nil
            if let filename = event.filename {
                NotificationManager.shared.notifyFailed(
                    filename: filename,
                    error: event.error ?? "Unknown error")
            }

        default:
            break
        }
    }

    private func loadStateFromFile() async {
        let stateFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".whisperx/state.json")

        guard FileManager.default.fileExists(atPath: stateFile.path) else {
            await MainActor.run {
                self.status = .disconnected
                self.isConnected = false
            }
            return
        }

        do {
            let data = try Data(contentsOf: stateFile)
            let state = try JSONDecoder().decode(DaemonState.self, from: data)

            await MainActor.run {
                if let current = state.current {
                    self.status = .transcribing(filename: current.filename, stage: current.stage)
                    self.progress = current.progressPercent
                    self.currentFilename = current.filename
                    self.currentStage = current.stage
                } else if state.status == "idle" {
                    self.status = .idle
                    self.progress = 0
                } else if state.status == "error" {
                    self.status = .error("Check daemon logs")
                }
                self.queue = state.queue
            }
        } catch {
            // State file unreadable
        }
    }

    func requestStatus() async {
        await self.connection.sendCommand(["command": "status"])
    }

    deinit {
        self.eventTask?.cancel()
        self.statePollingTask?.cancel()
    }
}
