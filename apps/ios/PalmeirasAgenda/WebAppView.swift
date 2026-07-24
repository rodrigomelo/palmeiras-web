import SwiftUI
import WebKit

@MainActor
final class WebAppController: ObservableObject {
    weak var webView: WKWebView?
    private(set) var selectedWebTab = "home"
    private(set) var selectedTheme = "light"
    private(set) var teamScope = "men"
    private(set) var spoilerFree = false

    func attach(_ webView: WKWebView) {
        self.webView = webView
    }

    func selectWebTab(_ tab: String) {
        selectedWebTab = tab
        evaluate("window.nativeSelectTab?.('\(tab)')")
    }

    func setTheme(_ theme: String) {
        selectedTheme = theme == "dark" ? "dark" : "light"
        evaluate("window.nativeSetTheme?.('\(selectedTheme)')")
    }

    func refreshData() {
        evaluate("window.refreshAllData?.()")
    }

    func setTeamScope(_ scope: String) {
        teamScope = scope == "women" ? "women" : "men"
        evaluate("if(localStorage.getItem('pa-team-scope') !== '\(teamScope)'){localStorage.setItem('pa-team-scope','\(teamScope)');location.reload()}")
    }

    func setSpoilerFree(_ enabled: Bool) {
        spoilerFree = enabled
        let value = enabled ? "true" : "false"
        evaluate("if(localStorage.getItem('pa-spoiler-free') !== '\(value)'){localStorage.setItem('pa-spoiler-free','\(value)');location.reload()}")
    }

    func setNativeNotificationState(active: Bool, permission: String, preferences: [String: Bool] = [:]) {
        var prefEntries = preferences.map { "'\($0.key)': \($0.value ? "true" : "false")" }.joined(separator: ", ")
        if preferences.isEmpty { prefEntries = "" }
        evaluate("""
            window.PalmeirasFeatures?.setNativeNotificationState({
                active: \(active ? "true" : "false"),
                permission: '\(permission)',
                preferences: { \(prefEntries) }
            })
            """)
    }

    func openMatch(_ matchID: String) {
        guard let encodedID = matchID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return }
        let baseURL = AppConfiguration.production.webAppURL.absoluteString
        evaluate("location.href='\(baseURL)?match=\(encodedID)'")
    }

    func restoreNativeState() {
        selectWebTab(selectedWebTab)
        setTheme(selectedTheme)
        setTeamScope(teamScope)
        setSpoilerFree(spoilerFree)
    }

    private func evaluate(_ script: String) {
        webView?.evaluateJavaScript(script)
    }
}

struct WebAppView: UIViewRepresentable {
    let url: URL
    let controller: WebAppController
    @Binding var isLoading: Bool
    @Binding var errorMessage: String?
    let onOpenNotificationSettings: () -> Void
    let onRequestNotificationState: () -> Void
    let onToggleNotifications: (Bool) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(
            allowedHost: url.host,
            isLoading: $isLoading,
            errorMessage: $errorMessage,
            onOpenNotificationSettings: onOpenNotificationSettings,
            onRequestNotificationState: onRequestNotificationState,
            onToggleNotifications: onToggleNotifications
        )
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.applicationNameForUserAgent = "PalmeirasAgendaiOS/\(AppConfiguration.appVersion)"
        configuration.userContentController.add(context.coordinator, name: "palmeirasNative")

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsLinkPreview = true
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 243 / 255, green: 245 / 255, blue: 239 / 255, alpha: 1)
        webView.scrollView.backgroundColor = webView.backgroundColor
        webView.scrollView.contentInsetAdjustmentBehavior = .always
        webView.scrollView.alwaysBounceHorizontal = false
        webView.scrollView.showsHorizontalScrollIndicator = false
        webView.scrollView.isDirectionalLockEnabled = true

        context.coordinator.webView = webView
        context.coordinator.controller = controller
        controller.attach(webView)

        var request = URLRequest(url: url)
        request.cachePolicy = .useProtocolCachePolicy
        request.timeoutInterval = 30
        webView.load(request)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(
            forName: "palmeirasNative"
        )
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        weak var controller: WebAppController?

        private let allowedHost: String?
        private var isLoading: Binding<Bool>
        private var errorMessage: Binding<String?>
        private let onOpenNotificationSettings: () -> Void
        private let onRequestNotificationState: () -> Void
        private let onToggleNotifications: (Bool) -> Void

        init(
            allowedHost: String?,
            isLoading: Binding<Bool>,
            errorMessage: Binding<String?>,
            onOpenNotificationSettings: @escaping () -> Void,
            onRequestNotificationState: @escaping () -> Void,
            onToggleNotifications: @escaping (Bool) -> Void
        ) {
            self.allowedHost = allowedHost
            self.isLoading = isLoading
            self.errorMessage = errorMessage
            self.onOpenNotificationSettings = onOpenNotificationSettings
            self.onRequestNotificationState = onRequestNotificationState
            self.onToggleNotifications = onToggleNotifications
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard message.name == "palmeirasNative",
                  let payload = message.body as? [String: Any],
                  let action = payload["action"] as? String
            else {
                return
            }
            if action == "openNotificationSettings" {
                onOpenNotificationSettings()
            } else if action == "requestNotificationState" {
                onRequestNotificationState()
            } else if action == "toggleNotifications" {
                let enable = payload["enable"] as? Bool ?? true
                onToggleNotifications(enable)
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            guard let destination = navigationAction.request.url else {
                return .cancel
            }

            if shouldOpenExternally(destination, navigationAction: navigationAction) {
                _ = await UIApplication.shared.open(destination)
                return .cancel
            }

            return .allow
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation?) {
            errorMessage.wrappedValue = nil
            isLoading.wrappedValue = true
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation?) {
            isLoading.wrappedValue = false
            controller?.restoreNativeState()
            onRequestNotificationState()
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation?,
            withError error: Error
        ) {
            handle(error, in: webView)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation?, withError error: Error) {
            handle(error, in: webView)
        }

        private func shouldOpenExternally(
            _ destination: URL,
            navigationAction: WKNavigationAction
        ) -> Bool {
            guard let scheme = destination.scheme?.lowercased() else { return true }
            if scheme != "http" && scheme != "https" { return true }
            if destination.path.hasSuffix(".ics") { return true }
            if destination.host != allowedHost { return true }
            return navigationAction.targetFrame == nil && navigationAction.navigationType == .linkActivated
        }

        private func handle(_ error: Error, in webView: WKWebView) {
            isLoading.wrappedValue = false

            let nsError = error as NSError
            guard nsError.code != NSURLErrorCancelled else { return }
            errorMessage.wrappedValue = "Verifique sua conexão e tente novamente."
        }
    }
}
