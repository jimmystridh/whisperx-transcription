import AppKit
import SwiftUI

@MainActor
final class LogStore: ObservableObject {
    @Published var entries: [LogEntry] = []
    @Published var isLoading: Bool = false

    private let logFile = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".whisperx/daemon.log")

    private var refreshTask: Task<Void, Never>?

    struct LogEntry: Identifiable {
        let id = UUID()
        let timestamp: String
        let level: LogLevel
        let message: String

        enum LogLevel: String {
            case info = "INFO"
            case warning = "WARNING"
            case error = "ERROR"
            case unknown = ""

            var color: Color {
                switch self {
                case .info: .primary
                case .warning: .orange
                case .error: .red
                case .unknown: .secondary
                }
            }
        }
    }

    func startAutoRefresh() {
        self.refreshTask = Task {
            while !Task.isCancelled {
                await self.loadLogs()
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    func stopAutoRefresh() {
        self.refreshTask?.cancel()
        self.refreshTask = nil
    }

    func loadLogs() async {
        guard FileManager.default.fileExists(atPath: self.logFile.path) else {
            await MainActor.run {
                self.entries = []
            }
            return
        }

        do {
            let content = try String(contentsOf: self.logFile, encoding: .utf8)
            let lines = content.components(separatedBy: .newlines)
                .filter { !$0.isEmpty }
                .suffix(200) // Keep last 200 lines

            let parsed = lines.map { self.parseLine($0) }
            await MainActor.run {
                self.entries = Array(parsed)
            }
        } catch {
            // Silently ignore read errors
        }
    }

    private func parseLine(_ line: String) -> LogEntry {
        // Format: 2025-12-26 12:00:00 [INFO] Message
        let pattern = #"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$"#

        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: line, range: NSRange(line.startIndex..., in: line))
        {
            let timestamp = String(line[Range(match.range(at: 1), in: line)!])
            let levelStr = String(line[Range(match.range(at: 2), in: line)!])
            let message = String(line[Range(match.range(at: 3), in: line)!])
            let level = LogEntry.LogLevel(rawValue: levelStr) ?? .unknown

            return LogEntry(timestamp: timestamp, level: level, message: message)
        }

        return LogEntry(timestamp: "", level: .unknown, message: line)
    }

    func clearLogs() {
        try? FileManager.default.removeItem(at: self.logFile)
        self.entries = []
    }

    func openInEditor() {
        NSWorkspace.shared.open(self.logFile)
    }

    func revealInFinder() {
        NSWorkspace.shared.selectFile(
            self.logFile.path,
            inFileViewerRootedAtPath: self.logFile.deletingLastPathComponent().path)
    }
}

struct LogViewerWindow: View {
    @StateObject private var logStore = LogStore()
    @State private var filterText = ""
    @State private var showErrorsOnly = false

    private var filteredEntries: [LogStore.LogEntry] {
        var entries = self.logStore.entries

        if self.showErrorsOnly {
            entries = entries.filter { $0.level == .error || $0.level == .warning }
        }

        if !self.filterText.isEmpty {
            entries = entries.filter {
                $0.message.localizedCaseInsensitiveContains(self.filterText)
            }
        }

        return entries
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("Filter logs...", text: self.$filterText)
                        .textFieldStyle(.plain)
                }
                .padding(6)
                .background(RoundedRectangle(cornerRadius: 6).fill(.quaternary))

                Toggle("Errors only", isOn: self.$showErrorsOnly)
                    .toggleStyle(.checkbox)

                Spacer()

                Button {
                    self.logStore.openInEditor()
                } label: {
                    Image(systemName: "doc.text")
                }
                .help("Open in editor")

                Button {
                    self.logStore.revealInFinder()
                } label: {
                    Image(systemName: "folder")
                }
                .help("Show in Finder")

                Button {
                    self.logStore.clearLogs()
                } label: {
                    Image(systemName: "trash")
                }
                .help("Clear logs")
            }
            .padding(8)
            .background(.bar)

            Divider()

            // Log content
            if self.logStore.entries.isEmpty {
                VStack {
                    Spacer()
                    Image(systemName: "doc.text")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text("No log entries")
                        .foregroundStyle(.secondary)
                    Text("Daemon logs will appear here")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(self.filteredEntries) { entry in
                                LogEntryRow(entry: entry)
                                    .id(entry.id)
                            }
                        }
                        .padding(8)
                    }
                    .onChange(of: self.logStore.entries.count) { _, _ in
                        if let last = self.filteredEntries.last {
                            withAnimation {
                                proxy.scrollTo(last.id, anchor: .bottom)
                            }
                        }
                    }
                }
            }
        }
        .frame(minWidth: 600, minHeight: 400)
        .onAppear {
            Task {
                await self.logStore.loadLogs()
            }
            self.logStore.startAutoRefresh()
        }
        .onDisappear {
            self.logStore.stopAutoRefresh()
        }
    }
}

struct LogEntryRow: View {
    let entry: LogStore.LogEntry

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            if !self.entry.timestamp.isEmpty {
                Text(self.entry.timestamp)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .frame(width: 140, alignment: .leading)
            }

            if self.entry.level != .unknown {
                Text(self.entry.level.rawValue)
                    .font(.caption.monospaced().bold())
                    .foregroundStyle(self.entry.level.color)
                    .frame(width: 60, alignment: .leading)
            }

            Text(self.entry.message)
                .font(.caption.monospaced())
                .foregroundStyle(self.entry.level.color)
                .textSelection(.enabled)

            Spacer()
        }
        .padding(.vertical, 2)
    }
}

@MainActor
final class LogWindowController {
    static let shared = LogWindowController()
    private var window: NSWindow?

    func showLogWindow() {
        if let existingWindow = self.window, existingWindow.isVisible {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let contentView = LogViewerWindow()
        let hostingController = NSHostingController(rootView: contentView)

        let window = NSWindow(contentViewController: hostingController)
        window.title = "Daemon Log"
        window.setContentSize(NSSize(width: 700, height: 500))
        window.styleMask = [.titled, .closable, .resizable, .miniaturizable]
        window.center()
        window.makeKeyAndOrderFront(nil)

        NSApp.activate(ignoringOtherApps: true)

        self.window = window
    }
}
