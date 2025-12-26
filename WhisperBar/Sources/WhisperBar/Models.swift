import Foundation

enum TranscriptionStatus: Equatable, Sendable {
    case idle
    case transcribing(filename: String, stage: String)
    case error(String)
    case disconnected
}

struct TranscriptionProgress: Codable, Sendable {
    let filename: String
    let startedAt: String
    let durationSeconds: Double
    let progressPercent: Double
    let stage: String

    enum CodingKeys: String, CodingKey {
        case filename
        case startedAt = "started_at"
        case durationSeconds = "duration_seconds"
        case progressPercent = "progress_percent"
        case stage
    }
}

struct Transcript: Identifiable, Codable, Sendable {
    let id: String
    let originalFilename: String
    let transcriptPath: String
    let completedAt: String
    let durationSeconds: Double
    let language: String
    let speakerCount: Int
    let success: Bool
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id
        case originalFilename = "original_filename"
        case transcriptPath = "transcript_path"
        case completedAt = "completed_at"
        case durationSeconds = "duration_seconds"
        case language
        case speakerCount = "speaker_count"
        case success
        case error
    }

    var displayName: String {
        let url = URL(fileURLWithPath: self.originalFilename)
        return url.deletingPathExtension().lastPathComponent
    }

    var formattedDuration: String {
        let minutes = Int(self.durationSeconds / 60)
        let seconds = Int(self.durationSeconds.truncatingRemainder(dividingBy: 60))
        if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        }
        return "\(seconds)s"
    }

    var completedDate: Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: self.completedAt)
            ?? ISO8601DateFormatter().date(from: self.completedAt)
    }

    var languageFlag: String {
        switch self.language.lowercased() {
        case "sv": "🇸🇪"
        case "en": "🇺🇸"
        default: "🌐"
        }
    }
}

struct DaemonState: Codable, Sendable {
    let status: String
    let current: TranscriptionProgress?
    let queue: [String]
    let history: [Transcript]?
}

struct DaemonEvent: Codable, Sendable {
    let event: String
    let filename: String?
    let durationSeconds: Double?
    let percent: Double?
    let stage: String?
    let transcriptPath: String?
    let language: String?
    let speakerCount: Int?
    let error: String?
    let timestamp: String?
    let id: String?

    // For state event
    let status: String?
    let current: TranscriptionProgress?
    let queue: [String]?
    let history: [Transcript]?
    let transcripts: [Transcript]?

    enum CodingKeys: String, CodingKey {
        case event, filename, percent, stage, language, error, timestamp, id
        case durationSeconds = "duration_seconds"
        case transcriptPath = "transcript_path"
        case speakerCount = "speaker_count"
        case status, current, queue, history, transcripts
    }
}
