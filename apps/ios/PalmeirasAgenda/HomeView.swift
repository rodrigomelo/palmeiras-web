import SwiftUI

struct HomeView: View {
    let apiClient: PalmeirasAPIClient
    @State private var state: LoadState = .loading

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                HeaderBand()

                Group {
                    switch state {
                    case .loading:
                        LoadingPanel()
                    case .failed:
                        ErrorPanel(retry: {
                            Task { await load() }
                        })
                    case .loaded(let dashboard):
                        DashboardContent(dashboard: dashboard)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 28)
            }
        }
        .background(AppTheme.background.ignoresSafeArea())
        .task {
            await load()
        }
    }

    private func load() async {
        state = .loading
        do {
            async let competitions = apiClient.competitionSummaries()
            async let matches = apiClient.upcomingPalmeirasMatches()
            let competitionsResponse = try await competitions
            let upcomingMatches = try await matches
            let dashboard = DashboardState(
                competitions: competitionsResponse.competitions,
                upcomingMatches: upcomingMatches
            )
            if Task.isCancelled { return }
            state = .loaded(dashboard)
        } catch is CancellationError {
            return
        } catch {
            state = .failed
        }
    }
}

private struct DashboardContent: View {
    let dashboard: DashboardState

    private var featuredMatch: Match? {
        dashboard.upcomingMatches.first ?? dashboard.competitions.compactMap(\.nextMatch).first
    }

    var body: some View {
        VStack(spacing: 14) {
            MatchHero(match: featuredMatch)
            CompetitionSummarySection(competitions: dashboard.competitions)
            UpcomingSection(matches: dashboard.upcomingMatches)
        }
    }
}

private struct HeaderBand: View {
    var body: some View {
        ZStack(alignment: .bottomLeading) {
            LinearGradient(
                colors: [AppTheme.brandStrong, AppTheme.brand, AppTheme.headerDeep],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .overlay(GridTexture().opacity(0.26))

            HStack(spacing: 14) {
                PAAgendaMark(size: 54)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Palmeiras Agenda")
                        .font(.system(size: 24, weight: .black, design: .rounded))
                        .foregroundStyle(AppTheme.onDark)
                    Text("Agenda tática de jogos, desempenho e calendário")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.onDark.opacity(0.74))
                }
                Spacer()
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 28)
        }
        .frame(height: 148)
    }
}

private struct MatchHero: View {
    let match: Match?

    var body: some View {
        VStack(spacing: 18) {
            HStack {
                Text(match?.competition.name ?? "Próximo jogo")
                    .font(.system(size: 11, weight: .black))
                    .textCase(.uppercase)
                    .foregroundStyle(AppTheme.gold)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(AppTheme.onDark.opacity(0.12), in: Capsule())
                    .overlay(Capsule().stroke(AppTheme.onDark.opacity(0.16), lineWidth: 1))
                Spacer()
            }

            if let match {
                HStack(spacing: 14) {
                    TeamColumn(name: teamName(match.homeTeam), isPalmeiras: match.homeTeam.id == 1769)
                    Text(scoreText(for: match))
                        .font(.system(size: 32, weight: .black, design: .rounded))
                        .foregroundStyle(AppTheme.onDark.opacity(0.86))
                        .frame(minWidth: 56)
                    TeamColumn(name: teamName(match.awayTeam), isPalmeiras: match.awayTeam.id == 1769)
                }

                VStack(spacing: 8) {
                    Text(matchDateText(match.utcDate))
                        .font(.system(size: 13, weight: .black))
                        .foregroundStyle(AppTheme.onDark)
                    HStack(spacing: 8) {
                        HeroPill(text: match.venue ?? "Estádio a definir")
                        HeroPill(text: match.broadcast ?? "TV a confirmar")
                    }
                }
            } else {
                VStack(spacing: 10) {
                    PAAgendaMark(size: 72)
                    Text("Nenhum jogo agendado")
                        .font(.system(size: 18, weight: .black))
                        .foregroundStyle(AppTheme.onDark)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            }
        }
        .padding(20)
        .background(
            LinearGradient(
                colors: [AppTheme.brand, AppTheme.brandBright, AppTheme.brandStrong],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 8, style: .continuous)
        )
        .overlay(GridTexture().clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous)).opacity(0.22))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(AppTheme.onDark.opacity(0.13), lineWidth: 1))
        .shadow(color: AppTheme.shadow, radius: 28, x: 0, y: 16)
        .offset(y: -18)
        .padding(.bottom, -18)
    }
}

private struct CompetitionSummarySection: View {
    let competitions: [CompetitionSummary]

    var body: some View {
        AppCard {
            VStack(alignment: .leading, spacing: 12) {
                SectionHeader(
                    title: "Disputas do Palmeiras",
                    subtitle: "\(competitions.count) competições consolidadas"
                )

                if competitions.isEmpty {
                    EmptyPanel(text: "Nenhuma competição encontrada.")
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(competitions) { competition in
                            CompetitionCard(competition: competition)
                        }
                    }
                }
            }
        }
    }
}

private struct CompetitionCard: View {
    let competition: CompetitionSummary

    private var featuredMatch: Match? {
        competition.nextMatch ?? competition.lastMatch
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(competition.code)
                        .font(.system(size: 10, weight: .black))
                        .foregroundStyle(compColor(for: competition.code))
                    Text(displayCompetitionName(competition))
                        .font(.system(size: 17, weight: .black))
                        .foregroundStyle(AppTheme.ink)
                }
                Spacer()
                StatusCapsule(text: competitionStatus(competition), color: statusColor(competition))
            }

            HStack(spacing: 6) {
                StatTile(value: "\(competition.record.played)", label: "J")
                StatTile(value: "\(competition.record.wins)", label: "V")
                StatTile(value: "\(competition.record.draws)", label: "E")
                StatTile(value: "\(competition.record.losses)", label: "D")
                StatTile(value: performanceText(competition.record), label: "APR")
            }

            if let featuredMatch {
                VStack(alignment: .leading, spacing: 5) {
                    Text(competition.nextMatch == nil ? "Último" : "Próximo")
                        .font(.system(size: 10, weight: .black))
                        .foregroundStyle(AppTheme.textMuted)
                    Text(matchTitle(featuredMatch))
                        .font(.system(size: 14, weight: .black))
                        .foregroundStyle(AppTheme.text)
                    Text(matchDateText(featuredMatch.utcDate))
                        .font(.system(size: 11, weight: .black))
                        .foregroundStyle(compColor(for: competition.code))
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.surface, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
            }
        }
        .padding(14)
        .background(compColor(for: competition.code).opacity(0.09), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(compColor(for: competition.code).opacity(0.32), lineWidth: 1))
    }
}

private struct UpcomingSection: View {
    let matches: [Match]

    var body: some View {
        AppCard {
            VStack(alignment: .leading, spacing: 12) {
                SectionHeader(title: "Próximos jogos", subtitle: "Agenda imediata do Verdão")

                if matches.isEmpty {
                    EmptyPanel(text: "Nenhum jogo encontrado.")
                } else {
                    VStack(spacing: 8) {
                        ForEach(matches.prefix(5)) { match in
                            UpcomingMatchRow(match: match)
                        }
                    }
                }
            }
        }
    }
}

private struct UpcomingMatchRow: View {
    let match: Match

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(match.competition.name ?? "Campeonato")
                    .font(.system(size: 10, weight: .black))
                    .foregroundStyle(compColor(for: match.competition.code ?? ""))
                Text(matchTitle(match))
                    .font(.system(size: 15, weight: .black))
                    .foregroundStyle(AppTheme.text)
                Text(matchDateText(match.utcDate))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.textMuted)
            }
            Spacer()
            Text(match.status == "IN_PLAY" ? "AO VIVO" : "AGENDADO")
                .font(.system(size: 10, weight: .black))
                .foregroundStyle(match.status == "IN_PLAY" ? AppTheme.live : AppTheme.brand)
                .padding(.horizontal, 9)
                .padding(.vertical, 6)
                .background(AppTheme.brandSoft, in: Capsule())
        }
        .padding(12)
        .background(AppTheme.softSurface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
    }
}

private struct LoadingPanel: View {
    var body: some View {
        AppCard {
            VStack(spacing: 12) {
                ProgressView()
                    .tint(AppTheme.brand)
                Text("Carregando Palmeiras Agenda")
                    .font(.system(size: 16, weight: .black))
                    .foregroundStyle(AppTheme.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 28)
        }
        .offset(y: -18)
    }
}

private struct ErrorPanel: View {
    let retry: () -> Void

    var body: some View {
        AppCard {
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(AppTheme.live)
                Text("Erro ao carregar")
                    .font(.system(size: 18, weight: .black))
                    .foregroundStyle(AppTheme.ink)
                Text("Não foi possível acessar o backend compartilhado.")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textMuted)
                    .multilineTextAlignment(.center)
                Button("Tentar novamente", action: retry)
                    .font(.system(size: 14, weight: .black))
                    .foregroundStyle(AppTheme.onDark)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 11)
                    .background(AppTheme.brand, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 20)
        }
        .offset(y: -18)
    }
}

private struct SectionHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 19, weight: .black))
                .foregroundStyle(AppTheme.ink)
            Text(subtitle)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(AppTheme.textMuted)
        }
    }
}

private struct AppCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(18)
            .background(AppTheme.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
            .shadow(color: AppTheme.shadow.opacity(0.7), radius: 18, x: 0, y: 10)
    }
}

private struct EmptyPanel: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(AppTheme.textMuted)
            .frame(maxWidth: .infinity)
            .padding(18)
            .background(AppTheme.softSurface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private struct TeamColumn: View {
    let name: String
    let isPalmeiras: Bool

    var body: some View {
        VStack(spacing: 8) {
            if isPalmeiras {
                PAAgendaMark(size: 52)
            } else {
                Circle()
                    .fill(AppTheme.onDark.opacity(0.82))
                    .frame(width: 52, height: 52)
                    .overlay(Text("?").font(.system(size: 21, weight: .bold)).foregroundStyle(AppTheme.textMuted))
            }
            Text(name)
                .font(.system(size: 17, weight: .black))
                .foregroundStyle(AppTheme.onDark)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .minimumScaleFactor(0.75)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct HeroPill: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .bold))
            .foregroundStyle(AppTheme.onDark.opacity(0.78))
            .lineLimit(1)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(AppTheme.onDark.opacity(0.09), in: Capsule())
            .overlay(Capsule().stroke(AppTheme.onDark.opacity(0.14), lineWidth: 1))
    }
}

private struct StatusCapsule: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .black))
            .foregroundStyle(color)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(color.opacity(0.11), in: Capsule())
    }
}

private struct StatTile: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 15, weight: .black))
                .foregroundStyle(AppTheme.ink)
                .minimumScaleFactor(0.72)
            Text(label)
                .font(.system(size: 9, weight: .black))
                .foregroundStyle(AppTheme.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 9)
        .background(AppTheme.surface, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
    }
}

private struct PAAgendaMark: View {
    let size: CGFloat

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.17, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [AppTheme.brandBright, AppTheme.brand, AppTheme.brandStrong],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: size * 0.17, style: .continuous)
                        .stroke(AppTheme.gold, lineWidth: max(2, size * 0.055))
                )

            RoundedRectangle(cornerRadius: size * 0.12, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [AppTheme.ivory, AppTheme.brandSoft],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size * 0.53, height: size * 0.58)
                .overlay(alignment: .top) {
                    Rectangle()
                        .fill(AppTheme.gold)
                        .frame(height: size * 0.13)
                }

            HStack(spacing: size * 0.16) {
                Capsule().fill(AppTheme.onDark)
                Capsule().fill(AppTheme.onDark)
            }
            .frame(width: size * 0.44, height: size * 0.24)
            .offset(y: -size * 0.3)

            PitchLineMark()
                .stroke(AppTheme.brand.opacity(0.34), lineWidth: max(1, size * 0.026))
                .frame(width: size * 0.42, height: size * 0.34)
                .offset(y: size * 0.08)

            Text("PA")
                .font(.system(size: size * 0.24, weight: .black, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .offset(y: size * 0.08)
        }
        .frame(width: size, height: size)
        .shadow(color: AppTheme.shadow, radius: 10, x: 0, y: 6)
        .accessibilityLabel("Logo Palmeiras Agenda")
    }
}

private struct PitchLineMark: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let left = rect.minX
        let right = rect.maxX
        let top = rect.minY
        let bottom = rect.maxY
        let midX = rect.midX
        let midY = rect.midY

        for y in [top + rect.height * 0.18, midY, bottom - rect.height * 0.18] {
            path.move(to: CGPoint(x: left, y: y))
            path.addLine(to: CGPoint(x: right, y: y))
        }
        for x in [midX - rect.width * 0.18, midX, midX + rect.width * 0.18] {
            path.move(to: CGPoint(x: x, y: top))
            path.addLine(to: CGPoint(x: x, y: bottom))
        }
        path.addEllipse(in: CGRect(x: midX - rect.width * 0.22, y: midY - rect.width * 0.22, width: rect.width * 0.44, height: rect.width * 0.44))
        return path
    }
}

private struct GridTexture: View {
    var body: some View {
        Canvas { context, size in
            let step: CGFloat = 44
            var path = Path()
            stride(from: CGFloat.zero, through: size.width, by: step).forEach { x in
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
            }
            stride(from: CGFloat.zero, through: size.height, by: step).forEach { y in
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            }
            context.stroke(path, with: .color(AppTheme.onDark.opacity(0.16)), lineWidth: 1)
        }
    }
}

private enum AppTheme {
    static let brand = Color(hex: 0x075C3B)
    static let brandStrong = Color(hex: 0x043522)
    static let brandBright = Color(hex: 0x0A7A4A)
    static let headerDeep = Color(hex: 0x113726)
    static let brandSoft = Color(hex: 0xE7F1E9)
    static let gold = Color(hex: 0xC99A3D)
    static let ivory = Color(hex: 0xFFFDF3)
    static let blue = Color(hex: 0x2468A8)
    static let live = Color(hex: 0xB93B36)
    static let ink = Color(hex: 0x10231A)
    static let text = Color(hex: 0x17251D)
    static let textMuted = Color(hex: 0x6D7A72)
    static let background = Color(hex: 0xF3F5EF)
    static let surface = Color(hex: 0xFBFCF8)
    static let softSurface = Color(hex: 0xE9EFE8)
    static let line = Color(hex: 0xD9E2D8)
    static let onDark = Color(hex: 0xFAFCF8)
    static let shadow = Color(hex: 0x06351F).opacity(0.13)
}

private extension Color {
    init(hex: UInt, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}

private struct DashboardState {
    let competitions: [CompetitionSummary]
    let upcomingMatches: [Match]
}

private enum LoadState {
    case loading
    case loaded(DashboardState)
    case failed
}

private func teamName(_ team: Team) -> String {
    team.shortName ?? team.name
}

private func matchTitle(_ match: Match) -> String {
    "\(teamName(match.homeTeam)) x \(teamName(match.awayTeam))"
}

private func scoreText(for match: Match) -> String {
    if let home = match.homeScore, let away = match.awayScore {
        return "\(home)-\(away)"
    }
    return "x"
}

private func matchDateText(_ value: String) -> String {
    let date = ISO8601DateFormatter.palmeiras.date(from: value)
        ?? ISO8601DateFormatter.palmeirasWithFractionalSeconds.date(from: value)
    guard let date else {
        return value
    }
    return DateFormatter.palmeirasMatch.string(from: date)
}

private func displayCompetitionName(_ competition: CompetitionSummary) -> String {
    switch competition.code {
    case "BSA": return "Brasileirão"
    case "CLI": return "Libertadores"
    case "COPA": return "Copa do Brasil"
    case "CPA": return "Paulistão"
    case "WC": return "Copa 2026"
    default: return competition.name
    }
}

private func compColor(for code: String) -> Color {
    switch code {
    case "BSA": return AppTheme.brandBright
    case "CLI": return AppTheme.gold
    case "COPA": return AppTheme.blue
    case "CPA": return Color(hex: 0x6B7F32)
    case "WC": return Color(hex: 0x8B3F68)
    default: return AppTheme.textMuted
    }
}

private func competitionStatus(_ competition: CompetitionSummary) -> String {
    if competition.live > 0 { return "Ao vivo" }
    if competition.nextMatch != nil { return "Em disputa" }
    if competition.finished == competition.totalMatches { return "Encerrada" }
    return "Sem agenda"
}

private func statusColor(_ competition: CompetitionSummary) -> Color {
    if competition.live > 0 { return AppTheme.live }
    if competition.nextMatch != nil { return AppTheme.brand }
    return AppTheme.textMuted
}

private func performanceText(_ record: CompetitionRecord) -> String {
    guard record.played > 0 else { return "0%" }
    let pct = Int(round(Double(record.points) / Double(record.played * 3) * 100))
    return "\(pct)%"
}

private extension ISO8601DateFormatter {
    static let palmeiras: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static let palmeirasWithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

private extension DateFormatter {
    static let palmeirasMatch: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "pt_BR")
        formatter.timeZone = TimeZone(identifier: "America/Sao_Paulo")
        formatter.dateFormat = "dd/MM HH:mm"
        return formatter
    }()
}
