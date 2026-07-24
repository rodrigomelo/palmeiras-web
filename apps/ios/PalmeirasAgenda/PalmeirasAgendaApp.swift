import SwiftUI
import BackgroundTasks
@preconcurrency import UserNotifications

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        BGTaskScheduler.shared.register(forTaskWithIdentifier: NativeNotificationSync.backgroundTaskIdentifier, using: nil) { task in
            guard let refresh = task as? BGAppRefreshTask else { return }
            NativeNotificationSync.scheduleBackgroundRefresh()
            let work = Task {
                await NativeNotificationSync.synchronize()
                refresh.setTaskCompleted(success: !Task.isCancelled)
            }
            refresh.expirationHandler = { work.cancel() }
        }
        NativeNotificationSync.scheduleBackgroundRefresh()
        Task { await NativeNotificationSync.synchronize() }
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        NativeNotificationSync.scheduleBackgroundRefresh()
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        guard let matchID = response.notification.request.content.userInfo["matchID"] as? String else { return }
        await MainActor.run {
            NotificationCenter.default.post(name: NativeDeepLink.notification, object: matchID)
        }
    }
}

@main
struct PalmeirasAgendaApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            AppRootView()
        }
    }
}
