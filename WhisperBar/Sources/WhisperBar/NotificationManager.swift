import AppKit
import Foundation
import UserNotifications

final class NotificationManager: NSObject, @unchecked Sendable {
    static let shared = NotificationManager()

    private let center = UNUserNotificationCenter.current()

    override private init() {
        super.init()
        self.center.delegate = self
    }

    func requestAuthorization() {
        self.center.requestAuthorization(options: [.alert, .sound]) { granted, error in
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

        self.center.add(request)
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

        self.center.add(request)
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

        self.center.add(request)
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
        if response.actionIdentifier == UNNotificationDefaultActionIdentifier {
            // User tapped the notification - open the transcript
            if let path = response.notification.request.content.userInfo["transcriptPath"] as? String {
                let url = URL(fileURLWithPath: path)
                NSWorkspace.shared.open(url)
            }
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
