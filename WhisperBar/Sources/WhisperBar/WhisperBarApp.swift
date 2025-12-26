import Sparkle
import SwiftUI

@main
struct WhisperBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var settings = SettingsStore()
    @StateObject private var transcriptionStore: TranscriptionStore
    @StateObject private var historyStore: HistoryStore
    @State private var isInserted = true

    init() {
        let settings = SettingsStore()
        let connection = DaemonConnection()
        _settings = StateObject(wrappedValue: settings)
        _transcriptionStore = StateObject(wrappedValue: TranscriptionStore(connection: connection))
        _historyStore = StateObject(wrappedValue: HistoryStore(connection: connection))
    }

    var body: some Scene {
        MenuBarExtra(isInserted: self.$isInserted) {
            MenuContent(
                transcriptionStore: self.transcriptionStore,
                historyStore: self.historyStore,
                settings: self.settings,
                updater: self.appDelegate.updaterController)
        } label: {
            IconView(
                status: self.transcriptionStore.status,
                progress: self.transcriptionStore.progress)
        }
        .menuBarExtraStyle(.window)
        Settings {
            EmptyView()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let updaterController = SPUStandardUpdaterController(
        startingUpdater: true,
        updaterDelegate: nil,
        userDriverDelegate: nil)

    func applicationDidFinishLaunching(_: Notification) {
        NotificationManager.shared.requestAuthorization()
    }
}
