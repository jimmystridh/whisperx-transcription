import AppKit
import Foundation

@MainActor
final class DaemonController: ObservableObject {
    @Published var isRunning: Bool = false
    @Published var pid: Int?

    private let pidFile = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".whisperx/daemon.pid")
    private let watcherScript: URL
    private let venvPython: URL
    private var checkTimer: Timer?

    init() {
        let whisperxDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Documents/whisperx-transcription")
        self.watcherScript = whisperxDir.appendingPathComponent("watcher.py")
        self.venvPython = whisperxDir.appendingPathComponent(".venv/bin/python3")
    }

    func startMonitoring() {
        guard self.checkTimer == nil else { return }
        self.checkDaemonStatus()
        self.checkTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.checkDaemonStatus()
            }
        }
    }

    func checkDaemonStatus() {
        guard FileManager.default.fileExists(atPath: self.pidFile.path) else {
            self.isRunning = false
            self.pid = nil
            return
        }

        do {
            let pidString = try String(contentsOf: self.pidFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            guard let daemonPid = Int(pidString) else {
                self.isRunning = false
                self.pid = nil
                return
            }

            self.pid = daemonPid

            // Check if process is actually running
            let task = Process()
            task.executableURL = URL(fileURLWithPath: "/bin/kill")
            task.arguments = ["-0", String(daemonPid)]

            try task.run()
            task.waitUntilExit()

            self.isRunning = task.terminationStatus == 0
        } catch {
            self.isRunning = false
            self.pid = nil
        }
    }

    func startDaemon() async throws {
        guard !self.isRunning else { return }

        // Check if venv python exists
        guard FileManager.default.fileExists(atPath: self.venvPython.path) else {
            throw DaemonError.venvNotFound
        }

        guard FileManager.default.fileExists(atPath: self.watcherScript.path) else {
            throw DaemonError.scriptNotFound
        }

        // Start the daemon in background
        let task = Process()
        task.executableURL = self.venvPython
        task.arguments = [self.watcherScript.path]
        task.currentDirectoryURL = self.watcherScript.deletingLastPathComponent()

        // Redirect output to log file
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".whisperx")
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)

        let logFile = logDir.appendingPathComponent("daemon.log")
        FileManager.default.createFile(atPath: logFile.path, contents: nil)
        let fileHandle = try FileHandle(forWritingTo: logFile)
        task.standardOutput = fileHandle
        task.standardError = fileHandle

        // Detach from terminal
        task.qualityOfService = .utility

        try task.run()

        // Wait a moment for the daemon to start
        try await Task.sleep(for: .seconds(1))
        self.checkDaemonStatus()
    }

    func stopDaemon() async throws {
        guard self.isRunning, let daemonPid = self.pid else { return }

        // Send SIGTERM to the daemon
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/kill")
        task.arguments = ["-TERM", String(daemonPid)]

        try task.run()
        task.waitUntilExit()

        // Wait for process to stop
        try await Task.sleep(for: .seconds(1))
        self.checkDaemonStatus()
    }

    func restartDaemon() async throws {
        try await self.stopDaemon()
        try await Task.sleep(for: .seconds(1))
        try await self.startDaemon()
    }

    func stopMonitoring() {
        self.checkTimer?.invalidate()
        self.checkTimer = nil
    }
}

enum DaemonError: LocalizedError {
    case venvNotFound
    case scriptNotFound
    case startFailed(String)

    var errorDescription: String? {
        switch self {
        case .venvNotFound:
            "Python virtual environment not found at expected location"
        case .scriptNotFound:
            "watcher.py script not found"
        case let .startFailed(reason):
            "Failed to start daemon: \(reason)"
        }
    }
}
