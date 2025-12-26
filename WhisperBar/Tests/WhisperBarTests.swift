import Foundation
import Testing

@testable import WhisperBar

@Suite
struct ModelTests {
    @Test
    func transcriptDisplayName() {
        let transcript = Transcript(
            id: "abc123",
            originalFilename: "meeting-2024-01-15.m4a",
            transcriptPath: "/path/to/transcripts/meeting-2024-01-15.txt",
            completedAt: "2024-01-15T10:30:00Z",
            durationSeconds: 3600,
            language: "sv",
            speakerCount: 3,
            success: true,
            error: nil)

        #expect(transcript.displayName == "meeting-2024-01-15")
    }

    @Test
    func transcriptFormattedDuration() {
        let transcript = Transcript(
            id: "abc123",
            originalFilename: "test.m4a",
            transcriptPath: "/path/to/test.txt",
            completedAt: "2024-01-15T10:30:00Z",
            durationSeconds: 125,
            language: "en",
            speakerCount: 1,
            success: true,
            error: nil)

        #expect(transcript.formattedDuration == "2m 5s")
    }

    @Test
    func transcriptLanguageFlag() {
        let swedish = Transcript(
            id: "1",
            originalFilename: "a.m4a",
            transcriptPath: "/a.txt",
            completedAt: "2024-01-15T10:30:00Z",
            durationSeconds: 60,
            language: "sv",
            speakerCount: 1,
            success: true,
            error: nil)

        let english = Transcript(
            id: "2",
            originalFilename: "b.m4a",
            transcriptPath: "/b.txt",
            completedAt: "2024-01-15T10:30:00Z",
            durationSeconds: 60,
            language: "en",
            speakerCount: 1,
            success: true,
            error: nil)

        #expect(swedish.languageFlag == "🇸🇪")
        #expect(english.languageFlag == "🇺🇸")
    }

    @Test
    func daemonEventDecoding() throws {
        let json = """
        {
            "event": "started",
            "filename": "test.m4a",
            "duration_seconds": 120.5,
            "timestamp": "2024-01-15T10:30:00Z"
        }
        """

        let data = json.data(using: .utf8)!
        let event = try JSONDecoder().decode(DaemonEvent.self, from: data)

        #expect(event.event == "started")
        #expect(event.filename == "test.m4a")
        #expect(event.durationSeconds == 120.5)
    }

    @Test
    func progressEventDecoding() throws {
        let json = """
        {
            "event": "progress",
            "percent": 45.5,
            "stage": "transcribing"
        }
        """

        let data = json.data(using: .utf8)!
        let event = try JSONDecoder().decode(DaemonEvent.self, from: data)

        #expect(event.event == "progress")
        #expect(event.percent == 45.5)
        #expect(event.stage == "transcribing")
    }
}
