import ActivityKit
import BackgroundTasks
import Foundation
@preconcurrency import UserNotifications

struct NativeTeam: Codable, Sendable {
    let id: Int?
    let name: String
    let shortName: String?
}

struct NativeCompetition: Codable, Sendable {
    let name: String?
    let code: String?
}

struct NativeMatch: Codable, Identifiable, Sendable {
    let id: String
    let utcDate: String?
    let status: String
    let venue: String?
    let homeTeam: NativeTeam
    let awayTeam: NativeTeam
    let competition: NativeCompetition?
    let homeScore: Int?
    let awayScore: Int?
    let liveMinute: String?
    let events: [NativeMatchEvent]?

    enum CodingKeys: String, CodingKey {
        case id, utcDate, status, venue, homeTeam, awayTeam, competition, homeScore, awayScore, liveMinute, events
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
        venue = try values.decodeIfPresent(String.self, forKey: .venue)
        homeTeam = try values.decode(NativeTeam.self, forKey: .homeTeam)
        awayTeam = try values.decode(NativeTeam.self, forKey: .awayTeam)
        competition = try values.decodeIfPresent(NativeCompetition.self, forKey: .competition)
        homeScore = try values.decodeIfPresent(Int.self, forKey: .homeScore)
        awayScore = try values.decodeIfPresent(Int.self, forKey: .awayScore)
        if let text = try? values.decodeIfPresent(String.self, forKey: .liveMinute) {
            liveMinute = text
        } else if let number = try? values.decodeIfPresent(Int.self, forKey: .liveMinute) {
            liveMinute = String(number)
        } else {
            liveMinute = nil
        }
        events = try values.decodeIfPresent([NativeMatchEvent].self, forKey: .events)
    }

    var date: Date? { utcDate.flatMap(ISO8601DateParser.date) }
    var displayTitle: String { "\(homeTeam.shortName ?? homeTeam.name) × \(awayTeam.shortName ?? awayTeam.name)" }
}

struct NativeMatchEvent: Codable, Sendable {
    let type: String?
    let minute: Int?
    let team: String?
    let player: String?
}

private struct MatchEnvelope: Codable, Sendable { let matches: [NativeMatch] }

fileprivate struct NativeNews: Codable, Sendable {
    let id: String?
    let title: String
    let url: String?
    let publishedAt: String?
    let collectedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, url
        case publishedAt = "published_at"
        case collectedAt = "collected_at"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        if let text = try? values.decodeIfPresent(String.self, forKey: .id) {
            id = text
        } else if let number = try? values.decodeIfPresent(Int.self, forKey: .id) {
            id = String(number)
        } else {
            id = nil
        }
        title = try values.decode(String.self, forKey: .title)
        url = try values.decodeIfPresent(String.self, forKey: .url)
        publishedAt = try values.decodeIfPresent(String.self, forKey: .publishedAt)
        collectedAt = try values.decodeIfPresent(String.self, forKey: .collectedAt)
    }
}

private struct NewsEnvelope: Codable, Sendable { let news: [NativeNews] }

enum ISO8601DateParser {
    static func date(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
}

enum NativePreferenceKey {
    static let scope = "nativeTeamScope"
    static let spoiler = "nativeSpoilerFree"
    static let oneHour = "notifyOneHourBefore"
    static let kickoff = "notifyKickoff"
    static let results = "notifyResults"
    static let scheduleChanges = "notifyScheduleChanges"
    static let liveEvents = "notifyLiveEvents"
    static let news = "notifyNews"
}

enum NativeDeepLink {
    static let notification = Notification.Name("PalmeirasAgendaDeepLink")
}

actor NativeAPIClient {
    static let shared = NativeAPIClient()
    private let decoder = JSONDecoder()

    func matches(status: String, limit: Int = 40, scope: String) async throws -> [NativeMatch] {
        var components = URLComponents(url: AppConfiguration.production.apiBaseURL.appending(path: "matches"), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "status", value: status),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "team_scope", value: scope),
        ]
        let (data, response) = try await URLSession.shared.data(from: components.url!)
        try validate(response)
        return try decoder.decode(MatchEnvelope.self, from: data).matches
    }

    fileprivate func news() async throws -> [NativeNews] {
        let url = AppConfiguration.production.apiBaseURL.appending(path: "news").appending(queryItems: [.init(name: "limit", value: "5")])
        let (data, response) = try await URLSession.shared.data(from: url)
        try validate(response)
        return try decoder.decode(NewsEnvelope.self, from: data).news
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}

enum NativeNotificationSync {
    static let backgroundTaskIdentifier = "com.palmeiras.agenda.refresh"
    private static var center: UNUserNotificationCenter { UNUserNotificationCenter.current() }
    private static var defaults: UserDefaults { UserDefaults.standard }

    static func synchronize() async {
        let scope = defaults.string(forKey: NativePreferenceKey.scope) == "women" ? "women" : "men"
        do {
            let upcoming = try await NativeAPIClient.shared.matches(
                status: "SCHEDULED,TIMED,IN_PLAY,PAUSED",
                scope: scope
            )
            await scheduleUpcoming(upcoming)
            await reconcileChanges(upcoming)
            await reconcileLatestResult(scope: scope)
            await reconcileNews()
            await MatchLiveActivityCoordinator.reconcile(upcoming)
            defaults.set(Date(), forKey: "nativeLastSuccessfulSync")
        } catch {
            // Background refresh is best-effort. Existing scheduled alerts remain valid.
        }
    }

    static func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: backgroundTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func scheduleUpcoming(_ matches: [NativeMatch]) async {
        let pending = await center.pendingNotificationRequests()
        let identifiers = pending.map(\.identifier).filter { $0.hasPrefix("match.") }
        center.removePendingNotificationRequests(withIdentifiers: identifiers)

        for match in matches where match.status == "SCHEDULED" || match.status == "TIMED" {
            guard let date = match.date else { continue }
            if defaults.bool(forKey: NativePreferenceKey.oneHour) {
                await schedule(match, at: date.addingTimeInterval(-3600), kind: "one-hour", body: "\(match.displayTitle) começa em 1 hora.")
            }
            if defaults.bool(forKey: NativePreferenceKey.kickoff) {
                await schedule(match, at: date, kind: "kickoff", body: "Bola rolando: \(match.displayTitle).")
            }
        }
    }

    private static func schedule(_ match: NativeMatch, at date: Date, kind: String, body: String) async {
        guard date > Date() else { return }
        let content = UNMutableNotificationContent()
        content.title = "Palmeiras Agenda"
        content.body = body
        content.sound = .default
        content.userInfo = ["matchID": match.id]
        let components = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        let request = UNNotificationRequest(
            identifier: "match.\(match.id).\(kind)",
            content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
        )
        try? await center.add(request)
    }

    private static func reconcileChanges(_ matches: [NativeMatch]) async {
        let key = "nativeMatchSnapshots"
        let previous = defaults.dictionary(forKey: key) as? [String: String] ?? [:]
        var current: [String: String] = [:]
        for match in matches {
            let eventCount = match.events?.count ?? 0
            let snapshot = "\(match.utcDate ?? "")|\(match.status)|\(match.homeScore ?? -1)|\(match.awayScore ?? -1)|\(eventCount)"
            current[match.id] = snapshot
            guard let old = previous[match.id], old != snapshot else { continue }
            if defaults.bool(forKey: NativePreferenceKey.scheduleChanges), old.split(separator: "|").first != snapshot.split(separator: "|").first {
                await notify(title: "Horário atualizado", body: "Confira a nova programação de \(match.displayTitle).", matchID: match.id)
            }
            if defaults.bool(forKey: NativePreferenceKey.liveEvents), ["IN_PLAY", "PAUSED"].contains(match.status) {
                let oldCount = Int(old.split(separator: "|").last ?? "0") ?? 0
                if eventCount > oldCount {
                    await notify(title: "Lance no jogo", body: "Há uma atualização em \(match.displayTitle).", matchID: match.id)
                }
            }
        }
        defaults.set(current, forKey: key)
    }

    private static func reconcileLatestResult(scope: String) async {
        guard let match = try? await NativeAPIClient.shared.matches(status: "FINISHED,PLAYING_TIME_FINISHED", limit: 1, scope: scope).first else { return }
        let key = "nativeLastResultID.\(scope)"
        let previous = defaults.string(forKey: key)
        defaults.set(match.id, forKey: key)
        guard previous != nil, previous != match.id, defaults.bool(forKey: NativePreferenceKey.results) else { return }
        let spoiler = defaults.bool(forKey: NativePreferenceKey.spoiler)
        let body = spoiler
            ? "O jogo terminou. Toque para ver o resultado."
            : "\(match.displayTitle): \(match.homeScore ?? 0)–\(match.awayScore ?? 0)."
        await notify(title: "Fim de jogo", body: body, matchID: match.id)
    }

    private static func reconcileNews() async {
        guard let item = try? await NativeAPIClient.shared.news().first else { return }
        let identity = item.id ?? item.url ?? item.title
        let previous = defaults.string(forKey: "nativeLastNewsID")
        defaults.set(identity, forKey: "nativeLastNewsID")
        guard previous != nil, previous != identity, defaults.bool(forKey: NativePreferenceKey.news) else { return }
        await notify(title: "Notícia do Palmeiras", body: item.title, matchID: nil)
    }

    private static func notify(title: String, body: String, matchID: String?) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        if let matchID { content.userInfo = ["matchID": matchID] }
        try? await center.add(.init(identifier: UUID().uuidString, content: content, trigger: nil))
    }
}

enum MatchLiveActivityCoordinator {
    static func reconcile(_ matches: [NativeMatch]) async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let live = matches.first { ["IN_PLAY", "PAUSED"].contains($0.status) }
        for activity in Activity<MatchActivityAttributes>.activities {
            guard let live, activity.attributes.matchID == live.id else {
                await activity.end(nil, dismissalPolicy: .after(.now + 60))
                continue
            }
            await activity.update(.init(state: state(for: live), staleDate: .now + 10 * 60))
        }
        guard let live, !Activity<MatchActivityAttributes>.activities.contains(where: { $0.attributes.matchID == live.id }) else { return }
        let attributes = MatchActivityAttributes(
            matchID: live.id,
            homeTeam: live.homeTeam.shortName ?? live.homeTeam.name,
            awayTeam: live.awayTeam.shortName ?? live.awayTeam.name,
            teamScope: UserDefaults.standard.string(forKey: NativePreferenceKey.scope) ?? "men"
        )
        _ = try? Activity.request(
            attributes: attributes,
            content: .init(state: state(for: live), staleDate: .now + 10 * 60),
            pushType: nil
        )
    }

    private static func state(for match: NativeMatch) -> MatchActivityAttributes.ContentState {
        .init(homeScore: match.homeScore, awayScore: match.awayScore, status: match.status, minute: match.liveMinute)
    }
}
