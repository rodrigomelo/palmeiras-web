import ActivityKit
import SwiftUI
import WidgetKit

private struct WidgetTeam: Decodable, Sendable { let name: String; let shortName: String? }
private struct WidgetCompetition: Decodable, Sendable { let name: String? }
private struct WidgetMatch: Decodable, Sendable {
    let id: String
    let utcDate: String?
    let status: String
    let homeTeam: WidgetTeam
    let awayTeam: WidgetTeam
    let competition: WidgetCompetition?
    let homeScore: Int?
    let awayScore: Int?

    enum CodingKeys: String, CodingKey {
        case id, utcDate, status, homeTeam, awayTeam, competition, homeScore, awayScore
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        if let text = try? values.decode(String.self, forKey: .id) {
            id = text
        } else {
            id = String(try values.decode(Int.self, forKey: .id))
        }
        utcDate = try values.decodeIfPresent(String.self, forKey: .utcDate)
        status = try values.decode(String.self, forKey: .status)
        homeTeam = try values.decode(WidgetTeam.self, forKey: .homeTeam)
        awayTeam = try values.decode(WidgetTeam.self, forKey: .awayTeam)
        competition = try values.decodeIfPresent(WidgetCompetition.self, forKey: .competition)
        homeScore = try values.decodeIfPresent(Int.self, forKey: .homeScore)
        awayScore = try values.decodeIfPresent(Int.self, forKey: .awayScore)
    }
}
private struct WidgetEnvelope: Decodable, Sendable { let matches: [WidgetMatch] }

private struct MatchEntry: TimelineEntry, Sendable {
    let date: Date
    let match: WidgetMatch?
}

private struct MatchProvider: TimelineProvider {
    func placeholder(in context: Context) -> MatchEntry {
        MatchEntry(date: .now, match: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (MatchEntry) -> Void) {
        completion(MatchEntry(date: .now, match: nil))
    }

    func getTimeline(in context: Context, completion: @escaping @Sendable (Timeline<MatchEntry>) -> Void) {
        Task {
            let match = await fetchMatch()
            let refresh = Date(timeIntervalSinceNow: match?.status == "IN_PLAY" ? 5 * 60 : 30 * 60)
            completion(Timeline(entries: [.init(date: .now, match: match)], policy: .after(refresh)))
        }
    }

    private func fetchMatch() async -> WidgetMatch? {
        guard let url = URL(string: "https://palmeiras.rodrigolanna.com.br/api/v1/matches?status=SCHEDULED,TIMED,IN_PLAY,PAUSED&limit=1&team_scope=men") else { return nil }
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else { return nil }
        return try? JSONDecoder().decode(WidgetEnvelope.self, from: data).matches.first
    }
}

private struct MatchWidgetView: View {
    let entry: MatchEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("PALMEIRAS AGENDA")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Color(red: 0.79, green: 0.60, blue: 0.24))
                Spacer()
                if entry.match?.status == "IN_PLAY" || entry.match?.status == "PAUSED" {
                    Text("AO VIVO").font(.caption2.bold()).foregroundStyle(.red)
                }
            }
            if let match = entry.match {
                Text(match.competition?.name ?? "Próximo jogo")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                HStack(alignment: .firstTextBaseline) {
                    Text(match.homeTeam.shortName ?? match.homeTeam.name).lineLimit(1)
                    Spacer()
                    Text(score(match)).font(.title2.monospacedDigit().bold())
                    Spacer()
                    Text(match.awayTeam.shortName ?? match.awayTeam.name).lineLimit(1)
                }
                .font(.subheadline.weight(.semibold))
                if let date = match.utcDate.flatMap(parseDate) {
                    Text(date, style: match.status == "IN_PLAY" ? .timer : .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Abra o app para atualizar a agenda.")
                    .font(.subheadline.weight(.medium))
            }
        }
        .containerBackground(Color(red: 0.96, green: 0.97, blue: 0.94), for: .widget)
        .widgetURL(URL(string: "https://palmeiras.rodrigolanna.com.br/"))
    }

    private func score(_ match: WidgetMatch) -> String {
        guard let home = match.homeScore, let away = match.awayScore else { return "×" }
        return "\(home)–\(away)"
    }

    private func parseDate(_ value: String) -> Date? {
        ISO8601DateFormatter().date(from: value)
    }
}

struct PalmeirasMatchWidget: Widget {
    let kind = "PalmeirasMatchWidget"
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: MatchProvider()) { entry in
            MatchWidgetView(entry: entry)
        }
        .configurationDisplayName("Próximo jogo")
        .description("Agenda, horário e placar do Palmeiras.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

struct PalmeirasMatchLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MatchActivityAttributes.self) { context in
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(context.attributes.homeTeam).lineLimit(1)
                    Text(context.attributes.awayTeam).lineLimit(1)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(context.state.homeScore.map(String.init) ?? "–")
                    Text(context.state.awayScore.map(String.init) ?? "–")
                }
                .font(.title3.monospacedDigit().bold())
                Text(context.state.minute ?? "AO VIVO")
                    .font(.caption.bold())
                    .foregroundStyle(.red)
            }
            .padding()
            .activityBackgroundTint(Color(red: 0.04, green: 0.25, blue: 0.17))
            .activitySystemActionForegroundColor(.white)
            .foregroundStyle(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) { Text(context.attributes.homeTeam).lineLimit(1) }
                DynamicIslandExpandedRegion(.trailing) { Text(context.attributes.awayTeam).lineLimit(1) }
                DynamicIslandExpandedRegion(.center) {
                    Text("\(context.state.homeScore ?? 0) – \(context.state.awayScore ?? 0)")
                        .font(.title2.monospacedDigit().bold())
                }
                DynamicIslandExpandedRegion(.bottom) { Text(context.state.minute ?? "Ao vivo") }
            } compactLeading: {
                Text(context.state.homeScore.map(String.init) ?? "–")
            } compactTrailing: {
                Text(context.state.awayScore.map(String.init) ?? "–")
            } minimal: {
                Image(systemName: "soccerball")
            }
            .widgetURL(URL(string: "https://palmeiras.rodrigolanna.com.br/?match=\(context.attributes.matchID)"))
        }
    }
}

@main
struct PalmeirasWidgetBundle: WidgetBundle {
    var body: some Widget {
        PalmeirasMatchWidget()
        PalmeirasMatchLiveActivity()
    }
}
