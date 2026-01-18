import AppKit
import Foundation
import UserNotifications

final class NotificationManager: NSObject, @unchecked Sendable {
    static let shared = NotificationManager()

    private var center: UNUserNotificationCenter?

    // Action identifiers
    static let openAction = "OPEN_TRANSCRIPT"
    static let copyAction = "COPY_TRANSCRIPT"
    static let showInFinderAction = "SHOW_IN_FINDER"
    static let transcriptCategory = "TRANSCRIPT_COMPLETE"

    override private init() {
        super.init()
        // Only initialize if running in a proper bundle
        if Bundle.main.bundleIdentifier != nil {
            self.center = UNUserNotificationCenter.current()
            self.center?.delegate = self
            self.setupCategories()
        }
    }

    private func setupCategories() {
        let openAction = UNNotificationAction(
            identifier: Self.openAction,
            title: "Open",
            options: [.foreground]
        )

        let copyAction = UNNotificationAction(
            identifier: Self.copyAction,
            title: "Copy Text",
            options: []
        )

        let showInFinderAction = UNNotificationAction(
            identifier: Self.showInFinderAction,
            title: "Show in Finder",
            options: [.foreground]
        )

        let transcriptCategory = UNNotificationCategory(
            identifier: Self.transcriptCategory,
            actions: [openAction, copyAction, showInFinderAction],
            intentIdentifiers: [],
            options: []
        )

        self.center?.setNotificationCategories([transcriptCategory])
    }

    func requestAuthorization() {
        self.center?.requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error {
                print("Notification authorization error: \(error)")
            }
        }
    }

    func notifyStarted(filename: String, duration: TimeInterval) {
        guard UserDefaults.standard.bool(forKey: "notificationsEnabled") else { return }

        let content = UNMutableNotificationContent()
        content.title = "Transcription Started"
        content.body = "\(filename) (\(self.formatDuration(duration)))"
        content.sound = nil // Silent for start

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil)

        self.center?.add(request)
    }

    func notifyCompleted(
        filename: String,
        transcriptPath: String?,
        language: String,
        speakerCount: Int
    ) {
        guard UserDefaults.standard.bool(forKey: "notificationsEnabled") else { return }

        let content = UNMutableNotificationContent()
        content.title = "Transcription Complete"

        var bodyParts = [filename]
        bodyParts.append(self.languageFlag(language))
        if speakerCount > 0 {
            bodyParts.append("\(speakerCount) speaker\(speakerCount == 1 ? "" : "s")")
        }
        content.body = bodyParts.joined(separator: " • ")

        content.sound = UNNotificationSound(named: UNNotificationSoundName("Glass"))
        content.categoryIdentifier = "TRANSCRIPT_COMPLETE"

        if let path = transcriptPath {
            content.userInfo = ["transcriptPath": path]
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil)

        self.center?.add(request)
    }

    func notifyFailed(filename: String, error: String) {
        guard UserDefaults.standard.bool(forKey: "notificationsEnabled") else { return }

        let content = UNMutableNotificationContent()
        content.title = "Transcription Failed"
        content.body = "\(filename): \(error)"
        content.sound = UNNotificationSound.default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil)

        self.center?.add(request)
    }

    func notifyFilesAdded(count: Int) {
        guard UserDefaults.standard.bool(forKey: "notificationsEnabled") else { return }

        let content = UNMutableNotificationContent()
        content.title = "Files Added for Transcription"
        content.body = count == 1 ? "1 file added to queue" : "\(count) files added to queue"
        content.sound = nil

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil)

        self.center?.add(request)
    }

    func notifyError(title: String, message: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = message
        content.sound = UNNotificationSound.default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil)

        self.center?.add(request)
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        let minutes = Int(seconds / 60)
        let secs = Int(seconds.truncatingRemainder(dividingBy: 60))
        if minutes > 0 {
            return "\(minutes)m \(secs)s"
        }
        return "\(secs)s"
    }

    private func languageFlag(_ language: String) -> String {
        switch language.lowercased() {
        case "sv": "🇸🇪 Swedish"
        case "en": "🇺🇸 English"
        default: "🌐 \(language.uppercased())"
        }
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    func userNotificationCenter(
        _: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        guard let path = response.notification.request.content.userInfo["transcriptPath"] as? String else {
            completionHandler()
            return
        }

        let url = URL(fileURLWithPath: path)

        switch response.actionIdentifier {
        case UNNotificationDefaultActionIdentifier, Self.openAction:
            // Open the transcript with default app
            NSWorkspace.shared.open(url)

        case Self.copyAction:
            // Copy transcript contents to clipboard
            if let content = try? String(contentsOf: url, encoding: .utf8) {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(content, forType: .string)
            }

        case Self.showInFinderAction:
            // Reveal in Finder
            NSWorkspace.shared.selectFile(url.path, inFileViewerRootedAtPath: url.deletingLastPathComponent().path)

        default:
            break
        }

        completionHandler()
    }

    func userNotificationCenter(
        _: UNUserNotificationCenter,
        willPresent _: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Show notifications even when app is in foreground
        completionHandler([.banner, .sound])
    }
}
