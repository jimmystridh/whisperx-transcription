import Foundation

actor DaemonConnection {
    private let socketPath: URL
    private var inputStream: InputStream?
    private var outputStream: OutputStream?
    private var isConnected = false
    private var buffer = Data()
    private var reconnectTask: Task<Void, Never>?

    private var eventContinuation: AsyncStream<DaemonEvent>.Continuation?
    nonisolated let events: AsyncStream<DaemonEvent>

    init(socketPath: URL? = nil) {
        self.socketPath = socketPath ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".whisperx/whisperxd.sock")

        var continuation: AsyncStream<DaemonEvent>.Continuation!
        self.events = AsyncStream { continuation = $0 }
        self.eventContinuation = continuation
    }

    func connect() async {
        guard !self.isConnected else { return }

        guard FileManager.default.fileExists(atPath: self.socketPath.path) else {
            self.scheduleReconnect()
            return
        }

        var readStream: Unmanaged<CFReadStream>?
        var writeStream: Unmanaged<CFWriteStream>?

        CFStreamCreatePairWithSocketToHost(
            nil,
            self.socketPath.path as CFString,
            0,
            &readStream,
            &writeStream)

        // For Unix sockets, we use a different approach
        let socket = socket(AF_UNIX, SOCK_STREAM, 0)
        guard socket >= 0 else {
            self.scheduleReconnect()
            return
        }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)

        let pathBytes = self.socketPath.path.utf8CString
        withUnsafeMutablePointer(to: &addr.sun_path) { ptr in
            let bound = ptr.withMemoryRebound(to: CChar.self, capacity: 104) { $0 }
            for (i, byte) in pathBytes.enumerated() where i < 103 {
                bound[i] = byte
            }
        }

        let connectResult = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockPtr in
                Darwin.connect(socket, sockPtr, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }

        guard connectResult == 0 else {
            close(socket)
            self.scheduleReconnect()
            return
        }

        self.inputStream = InputStream(fileAtPath: "/dev/fd/\(socket)")
        self.outputStream = OutputStream(toFileAtPath: "/dev/fd/\(socket)", append: false)

        // Use CFSocket-based streams for Unix sockets
        CFStreamCreatePairWithSocket(
            nil,
            Int32(socket),
            &readStream,
            &writeStream)

        guard let input = readStream?.takeRetainedValue(),
              let output = writeStream?.takeRetainedValue()
        else {
            close(socket)
            self.scheduleReconnect()
            return
        }

        self.inputStream = input as InputStream
        self.outputStream = output as OutputStream

        CFReadStreamSetProperty(input, CFStreamPropertyKey(kCFStreamPropertyShouldCloseNativeSocket), kCFBooleanTrue)
        CFWriteStreamSetProperty(output, CFStreamPropertyKey(kCFStreamPropertyShouldCloseNativeSocket), kCFBooleanTrue)

        self.inputStream?.open()
        self.outputStream?.open()
        self.isConnected = true

        Task { await self.readLoop() }
    }

    func disconnect() {
        self.reconnectTask?.cancel()
        self.reconnectTask = nil
        self.inputStream?.close()
        self.outputStream?.close()
        self.inputStream = nil
        self.outputStream = nil
        self.isConnected = false
    }

    func sendCommand(_ command: [String: Any]) async {
        guard self.isConnected, let output = self.outputStream else { return }

        do {
            let data = try JSONSerialization.data(withJSONObject: command)
            var dataWithNewline = data
            dataWithNewline.append(contentsOf: [UInt8(ascii: "\n")])

            dataWithNewline.withUnsafeBytes { ptr in
                if let baseAddress = ptr.baseAddress {
                    _ = output.write(baseAddress.assumingMemoryBound(to: UInt8.self), maxLength: dataWithNewline.count)
                }
            }
        } catch {
            // Ignore serialization errors
        }
    }

    private func readLoop() async {
        guard let input = self.inputStream else { return }

        var buffer = [UInt8](repeating: 0, count: 4096)

        while self.isConnected {
            let bytesRead = input.read(&buffer, maxLength: buffer.count)

            if bytesRead <= 0 {
                self.isConnected = false
                self.scheduleReconnect()
                break
            }

            self.buffer.append(contentsOf: buffer[0 ..< bytesRead])

            // Process complete lines
            while let newlineIndex = self.buffer.firstIndex(of: UInt8(ascii: "\n")) {
                let lineData = self.buffer[..<newlineIndex]
                self.buffer.removeSubrange(...newlineIndex)

                if let event = try? JSONDecoder().decode(DaemonEvent.self, from: Data(lineData)) {
                    self.eventContinuation?.yield(event)
                }
            }

            // Small delay to prevent busy loop
            try? await Task.sleep(for: .milliseconds(10))
        }
    }

    private func scheduleReconnect() {
        self.reconnectTask?.cancel()
        self.reconnectTask = Task {
            try? await Task.sleep(for: .seconds(5))
            if !Task.isCancelled {
                await self.connect()
            }
        }
    }

    var connectionStatus: Bool {
        self.isConnected
    }
}
