import ActivityKit
import Foundation

struct MatchActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        let homeScore: Int?
        let awayScore: Int?
        let status: String
        let minute: String?
    }

    let matchID: String
    let homeTeam: String
    let awayTeam: String
    let teamScope: String
}
