import SwiftUI

@main
struct WhisperBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var settings = SettingsStore()
    @StateObject private var transcriptionStore: TranscriptionStore
    @StateObject private var historyStore: HistoryStore
    @StateObject private var daemonController = DaemonController()
    @State private var isInserted = true

    init() {
        let connection = DaemonConnection()
        _transcriptionStore = StateObject(wrappedValue: TranscriptionStore(connection: connection))
        _historyStore = StateObject(wrappedValue: HistoryStore(connection: connection))
    }

    var body: some Scene {
        MenuBarExtra(isInserted: self.$isInserted) {
            MenuContent(
                transcriptionStore: self.transcriptionStore,
                historyStore: self.historyStore,
                settings: self.settings,
                daemonController: self.daemonController)
                .onAppear {
                    self.daemonController.startMonitoring()
                }
        } label: {
            IconView(
                status: self.transcriptionStore.status,
                progress: self.transcriptionStore.progress,
                stage: self.transcriptionStore.currentStage)
        }
        .menuBarExtraStyle(.window)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_: Notification) {
        NotificationManager.shared.requestAuthorization()
    }
}
