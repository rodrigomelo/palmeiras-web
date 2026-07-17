import Foundation

struct MatchesResponse: Decodable {
    let matches: [Match]
}

struct CompetitionsResponse: Decodable {
    let year: Int
    let teamId: Int
    let competitions: [CompetitionSummary]
}

struct CompetitionSummary: Decodable, Identifiable {
    let code: String
    let name: String
    let year: Int
    let totalMatches: Int
    let finished: Int
    let upcoming: Int
    let live: Int
    let record: CompetitionRecord
    let nextMatch: Match?
    let lastMatch: Match?
    let currentStage: String?
    let standing: Standing?

    var id: String { code }
}

struct CompetitionRecord: Decodable {
    let played: Int
    let wins: Int
    let draws: Int
    let losses: Int
    let goalsFor: Int
    let goalsAgainst: Int
    let goalDifference: Int
    let points: Int
}

struct Standing: Decodable {
    let position: Int?
    let teamId: Int?
    let teamName: String?
    let teamShort: String?
    let playedGames: Int?
    let points: Int?
    let goalsFor: Int?
    let goalsAgainst: Int?
    let goalDifference: Int?
}

struct Match: Decodable, Identifiable {
    let id: Int
    let utcDate: String
    let status: String
    let matchday: Int?
    let stage: String?
    let venue: String?
    let broadcast: String?
    let homeTeam: Team
    let awayTeam: Team
    let competition: Competition
    let score: Score
    let homeScore: Int?
    let awayScore: Int?
}

struct Team: Decodable, Identifiable {
    let id: Int?
    let name: String
    let shortName: String?
    let tla: String?
    let crest: String?
}

struct Competition: Decodable {
    let code: String?
    let name: String?
}

struct Score: Decodable {
    let fullTime: ScoreLine
    let halfTime: ScoreLine?
}

struct ScoreLine: Decodable {
    let home: Int?
    let away: Int?
}
