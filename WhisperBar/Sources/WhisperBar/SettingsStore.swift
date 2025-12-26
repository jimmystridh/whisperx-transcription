import AppKit
import ServiceManagement
import SwiftUI

@MainActor
final class SettingsStore: ObservableObject {
    @AppStorage("launchAtLogin") var launchAtLogin: Bool = false {
        didSet { LaunchAtLoginManager.setEnabled(self.launchAtLogin) }
    }

    @AppStorage("notificationsEnabled") var notificationsEnabled: Bool = true

    @AppStorage("showProgressInIcon") var showProgressInIcon: Bool = true

    @AppStorage("maxRecentTranscripts") var maxRecentTranscripts: Int = 8

    @AppStorage("debugMenuEnabled") var debugMenuEnabled: Bool = false

    init() {
        LaunchAtLoginManager.setEnabled(self.launchAtLogin)
    }
}

enum LaunchAtLoginManager {
    @MainActor
    static func setEnabled(_ enabled: Bool) {
        guard #available(macOS 13, *) else { return }
        let service = SMAppService.mainApp
        if enabled {
            try? service.register()
        } else {
            try? service.unregister()
        }
    }
}
