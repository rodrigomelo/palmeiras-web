import SwiftUI
import UserNotifications

private enum NativeColors {
    static let green950 = Color(red: 4 / 255, green: 53 / 255, blue: 34 / 255)
    static let green900 = Color(red: 6 / 255, green: 65 / 255, blue: 43 / 255)
    static let green800 = Color(red: 7 / 255, green: 92 / 255, blue: 59 / 255)
    static let green700 = Color(red: 10 / 255, green: 122 / 255, blue: 74 / 255)
    static let green100 = Color(red: 231 / 255, green: 241 / 255, blue: 233 / 255)
    static let gold500 = Color(red: 201 / 255, green: 154 / 255, blue: 61 / 255)
    static let ivory = Color(red: 255 / 255, green: 253 / 255, blue: 243 / 255)
    static let mist = Color(red: 243 / 255, green: 245 / 255, blue: 239 / 255)
    static let darkCanvas = Color(red: 7 / 255, green: 17 / 255, blue: 12 / 255)
    static let darkSurface = Color(red: 15 / 255, green: 30 / 255, blue: 22 / 255)
    static let ink = Color(red: 16 / 255, green: 35 / 255, blue: 26 / 255)
    static let muted = Color(red: 74 / 255, green: 93 / 255, blue: 83 / 255)
    static let red = Color(red: 185 / 255, green: 59 / 255, blue: 54 / 255)
}

private enum NativeDestination: String, CaseIterable, Identifiable {
    case home
    case standings
    case statistics
    case history
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: "Agenda"
        case .standings: "Tabelas"
        case .statistics: "Estatísticas"
        case .history: "Histórico"
        case .settings: "Ajustes"
        }
    }

    var systemImage: String {
        switch self {
        case .home: "calendar"
        case .standings: "list.number"
        case .statistics: "chart.bar"
        case .history: "clock.arrow.circlepath"
        case .settings: "gearshape"
        }
    }

    var webTab: String? {
        switch self {
        case .home: "home"
        case .standings: "classificacao"
        case .statistics: "estatisticas"
        case .history: "historico"
        case .settings: nil
        }
    }
}

struct AppRootView: View {
    @Environment(\.colorScheme) private var systemColorScheme
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("nativeAppearance") private var appearance = "system"
    @AppStorage(NativePreferenceKey.scope) private var teamScope = "men"
    @AppStorage(NativePreferenceKey.spoiler) private var spoilerFree = false
    @AppStorage(NativePreferenceKey.oneHour) private var notifyOneHourBefore = false
    @AppStorage(NativePreferenceKey.kickoff) private var notifyKickoff = false
    @AppStorage(NativePreferenceKey.results) private var notifyResults = false
    @AppStorage(NativePreferenceKey.scheduleChanges) private var notifyScheduleChanges = false
    @AppStorage(NativePreferenceKey.liveEvents) private var notifyLiveEvents = false
    @AppStorage(NativePreferenceKey.news) private var notifyNews = false
    @StateObject private var webController = WebAppController()
    @State private var selectedDestination: NativeDestination = .home
    @State private var reloadID = UUID()
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            WebAppView(
                url: AppConfiguration.production.webAppURL,
                controller: webController,
                isLoading: $isLoading,
                errorMessage: $errorMessage,
                onOpenNotificationSettings: { select(.settings) },
                onRequestNotificationState: {
                    Task { await syncWebNotificationState() }
                }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipped()
            .id(reloadID)

            if isLoading {
                LoadingOverlay()
            }

            if let errorMessage {
                ErrorOverlay(message: errorMessage, retry: retry)
            }

            if selectedDestination == .settings {
                NativeSettingsView(
                    appearance: $appearance,
                    teamScope: $teamScope,
                    spoilerFree: $spoilerFree,
                    refreshData: refreshData,
                    onNotificationStateChanged: {
                        Task { await syncWebNotificationState() }
                    }
                )
                .transition(.opacity)
            }
        }
        .background(resolvedDarkMode ? NativeColors.darkCanvas : NativeColors.mist)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            NativeBottomBar(selection: $selectedDestination, select: select)
                .zIndex(100)
        }
        .preferredColorScheme(preferredColorScheme)
        .onAppear {
            syncWebTheme()
            syncWebPreferences()
            Task { await syncWebNotificationState() }
        }
        .onChange(of: appearance) { _, _ in syncWebTheme() }
        .onChange(of: systemColorScheme) { _, _ in syncWebTheme() }
        .onChange(of: teamScope) { _, _ in
            syncWebPreferences()
            Task { await NativeNotificationSync.synchronize() }
        }
        .onChange(of: spoilerFree) { _, _ in syncWebPreferences() }
        .onChange(of: notificationPreferenceFingerprint) { _, _ in
            Task { await syncWebNotificationState() }
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task { await syncWebNotificationState() }
        }
        .onReceive(NotificationCenter.default.publisher(for: NativeDeepLink.notification)) { notification in
            guard let matchID = notification.object as? String else { return }
            selectedDestination = .home
            webController.openMatch(matchID)
        }
    }

    private var preferredColorScheme: ColorScheme? {
        switch appearance {
        case "light": .light
        case "dark": .dark
        default: nil
        }
    }

    private var resolvedDarkMode: Bool {
        appearance == "dark" || (appearance == "system" && systemColorScheme == .dark)
    }

    private func select(_ destination: NativeDestination) {
        withAnimation(.easeInOut(duration: 0.16)) {
            selectedDestination = destination
        }
        if let webTab = destination.webTab {
            webController.selectWebTab(webTab)
        }
    }

    private func refreshData() {
        webController.refreshData()
        select(.home)
    }

    private func syncWebTheme() {
        let theme = appearance == "system"
            ? (systemColorScheme == .dark ? "dark" : "light")
            : appearance
        webController.setTheme(theme)
    }

    private func syncWebPreferences() {
        webController.setTeamScope(teamScope)
        webController.setSpoilerFree(spoilerFree)
    }

    private var notificationPreferencesEnabled: Bool {
        notifyOneHourBefore || notifyKickoff || notifyResults ||
            notifyScheduleChanges || notifyLiveEvents || notifyNews
    }

    private var notificationPreferenceFingerprint: String {
        [
            notifyOneHourBefore,
            notifyKickoff,
            notifyResults,
            notifyScheduleChanges,
            notifyLiveEvents,
            notifyNews
        ]
        .map { $0 ? "1" : "0" }
        .joined()
    }

    @MainActor
    private func syncWebNotificationState() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        let permission: String
        let authorized: Bool
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            permission = "authorized"
            authorized = true
        case .denied:
            permission = "denied"
            authorized = false
        case .notDetermined:
            permission = "notDetermined"
            authorized = false
        @unknown default:
            permission = "notDetermined"
            authorized = false
        }
        webController.setNativeNotificationState(
            active: notificationPreferencesEnabled && authorized,
            permission: permission
        )
    }

    private func retry() {
        errorMessage = nil
        isLoading = true
        reloadID = UUID()
    }
}

private struct NativeBottomBar: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var selection: NativeDestination
    let select: (NativeDestination) -> Void

    private var surface: Color {
        colorScheme == .dark ? NativeColors.darkSurface : NativeColors.ivory
    }

    private var inactive: Color {
        colorScheme == .dark ? Color(red: 174 / 255, green: 192 / 255, blue: 181 / 255) : NativeColors.muted
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(NativeDestination.allCases) { destination in
                Button {
                    select(destination)
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: destination.systemImage)
                            .font(.system(size: 18, weight: .medium))
                        Text(destination.title)
                            .font(.system(size: 10, weight: .medium))
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                    }
                    .foregroundStyle(selection == destination ? NativeColors.green700 : inactive)
                    .frame(maxWidth: .infinity)
                    .frame(minHeight: 56)
                    .contentShape(Rectangle())
                    .overlay(alignment: .top) {
                        Rectangle()
                            .fill(selection == destination ? NativeColors.gold500 : .clear)
                            .frame(height: 2)
                            .padding(.horizontal, 16)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel(destination.title)
                .accessibilityAddTraits(selection == destination ? .isSelected : [])
            }
        }
        .background(surface, ignoresSafeAreaEdges: .bottom)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(colorScheme == .dark ? Color.white.opacity(0.12) : NativeColors.ink.opacity(0.10))
                .frame(height: 1)
        }
    }
}

private struct NativeSettingsView: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var appearance: String
    @Binding var teamScope: String
    @Binding var spoilerFree: Bool
    let refreshData: () -> Void
    let onNotificationStateChanged: () -> Void

    @AppStorage("notifyOneHourBefore") private var notifyOneHourBefore = false
    @AppStorage("notifyKickoff") private var notifyKickoff = false
    @AppStorage("notifyResults") private var notifyResults = false
    @AppStorage("notifyScheduleChanges") private var notifyScheduleChanges = false
    @AppStorage("notifyLiveEvents") private var notifyLiveEvents = false
    @AppStorage("notifyNews") private var notifyNews = false
    @State private var notificationStatus = "Verificando permissão…"

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Lembrete 1 hora antes", isOn: $notifyOneHourBefore)
                    Toggle("Aviso no início do jogo", isOn: $notifyKickoff)
                    Toggle("Placar final", isOn: $notifyResults)
                    Toggle("Mudanças de data e horário", isOn: $notifyScheduleChanges)
                    Toggle("Gols e lances ao vivo", isOn: $notifyLiveEvents)
                    Toggle("Notícias importantes", isOn: $notifyNews)
                } header: {
                    Text("Notificações")
                } footer: {
                    Text(notificationStatus)
                }

                Section("Time e privacidade") {
                    Picker("Agenda", selection: $teamScope) {
                        Text("Masculino").tag("men")
                        Text("Feminino").tag("women")
                    }
                    .pickerStyle(.segmented)
                    Toggle("Modo sem spoilers", isOn: $spoilerFree)
                }

                Section("Aparência") {
                    Picker("Tema", selection: $appearance) {
                        Text("Sistema").tag("system")
                        Text("Claro").tag("light")
                        Text("Escuro").tag("dark")
                    }
                    .pickerStyle(.segmented)
                }

                Section("Dados") {
                    Button {
                        refreshData()
                    } label: {
                        Label("Atualizar dados agora", systemImage: "arrow.clockwise")
                    }
                }

                Section("Aplicativo") {
                    LabeledContent("Versão", value: AppConfiguration.appVersion)
                    LabeledContent("Fonte", value: "Palmeiras Agenda")
                }
            }
            .scrollContentBackground(.hidden)
            .background(colorScheme == .dark ? NativeColors.darkCanvas : NativeColors.mist)
            .listSectionSpacing(16)
            .navigationTitle("Ajustes")
            .navigationBarTitleDisplayMode(.inline)
            .tint(colorScheme == .dark ? NativeColors.green700 : NativeColors.green800)
            .task {
                await refreshNotificationStatus()
                onNotificationStateChanged()
            }
            .onChange(of: notificationPreferenceFingerprint) { _, _ in
                Task {
                    if notificationPreferencesEnabled {
                        await requestNotificationPermission()
                    }
                    await NativeNotificationSync.synchronize()
                    onNotificationStateChanged()
                }
            }
        }
    }

    private var notificationPreferencesEnabled: Bool {
        notifyOneHourBefore || notifyKickoff || notifyResults || notifyScheduleChanges || notifyLiveEvents || notifyNews
    }

    private var notificationPreferenceFingerprint: String {
        [notifyOneHourBefore, notifyKickoff, notifyResults, notifyScheduleChanges, notifyLiveEvents, notifyNews]
            .map { $0 ? "1" : "0" }
            .joined()
    }

    @MainActor
    private func refreshNotificationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        notificationStatus = switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            "Notificações autorizadas neste iPhone."
        case .denied:
            "Permissão negada. Ative as notificações nos Ajustes do iPhone."
        case .notDetermined:
            "A permissão será solicitada ao ativar um alerta."
        @unknown default:
            "Não foi possível verificar a permissão."
        }
    }

    private func requestNotificationPermission() async {
        do {
            _ = try await UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .badge, .sound]
            )
        } catch {
            notificationStatus = "Não foi possível solicitar a permissão."
            return
        }
        await refreshNotificationStatus()
    }
}

private struct LoadingOverlay: View {
    var body: some View {
        ZStack {
            BrandedGreenSurface()
            VStack(spacing: 12) {
                Image("PalmeirasAgendaLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 104, height: 104)
                    .accessibilityHidden(true)
                Text("Palmeiras Agenda")
                    .font(.system(size: 24, weight: .bold))
                    .tracking(-0.4)
                    .foregroundStyle(NativeColors.ivory)
                Text("O calendário do torcedor")
                    .font(.system(size: 12, weight: .medium))
                    .textCase(.uppercase)
                    .tracking(1.8)
                    .foregroundStyle(NativeColors.ivory.opacity(0.72))
                ProgressView()
                    .controlSize(.regular)
                    .tint(NativeColors.gold500)
                    .padding(.top, 8)
            }
        }
        .ignoresSafeArea()
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Carregando Palmeiras Agenda")
    }
}

private struct BrandedGreenSurface: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [NativeColors.green950, NativeColors.green800, Color(red: 17 / 255, green: 55 / 255, blue: 38 / 255)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            LinearGradient(
                colors: [NativeColors.gold500.opacity(0.16), .clear],
                startPoint: .topLeading,
                endPoint: .center
            )
            Canvas { context, size in
                var path = Path()
                stride(from: 0.0, through: size.width, by: 68).forEach { x in
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: size.height))
                }
                stride(from: 0.0, through: size.height, by: 68).forEach { y in
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: size.width, y: y))
                }
                context.stroke(path, with: .color(NativeColors.ivory.opacity(0.055)), lineWidth: 1)
            }
        }
    }
}

private struct ErrorOverlay: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ZStack {
            NativeColors.mist.ignoresSafeArea()
            VStack(spacing: 14) {
                Image("PalmeirasAgendaLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 64, height: 64)
                    .padding(8)
                    .background(NativeColors.green950, in: RoundedRectangle(cornerRadius: 8))
                Text("Não foi possível abrir o aplicativo")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(NativeColors.ink)
                    .multilineTextAlignment(.center)
                Text(message)
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(NativeColors.muted)
                    .multilineTextAlignment(.center)
                Button("Tentar novamente", action: retry)
                    .buttonStyle(.borderedProminent)
                    .tint(NativeColors.green800)
                    .controlSize(.large)
            }
            .padding(24)
            .frame(maxWidth: 320)
            .background(NativeColors.ivory, in: RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(NativeColors.ink.opacity(0.10))
            }
            .shadow(color: NativeColors.green950.opacity(0.08), radius: 16, y: 8)
            .padding(20)
        }
    }
}
