import Foundation

enum PalmeirasAPIError: Error {
    case invalidURL
    case badStatus(Int)
}

struct PalmeirasAPIClient {
    private let configuration: AppConfiguration
    private let session: URLSession
    private let decoder: JSONDecoder

    init(configuration: AppConfiguration = .production, session: URLSession = .shared) {
        self.configuration = configuration
        self.session = session
        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    func upcomingPalmeirasMatches(limit: Int = 5) async throws -> [Match] {
        let response: MatchesResponse = try await get(
            "matches",
            query: [
                URLQueryItem(name: "status", value: "SCHEDULED,TIMED,IN_PLAY,PAUSED"),
                URLQueryItem(name: "team_id", value: "1769"),
                URLQueryItem(name: "limit", value: String(limit)),
            ]
        )
        return response.matches
    }

    func competitionSummaries(year: Int? = nil) async throws -> CompetitionsResponse {
        var query = [
            URLQueryItem(name: "team_id", value: "1769"),
        ]
        if let year {
            query.append(URLQueryItem(name: "year", value: String(year)))
        }
        return try await get("competitions", query: query)
    }

    func worldCupMatches() async throws -> [Match] {
        let response: MatchesResponse = try await get(
            "matches",
            query: [
                URLQueryItem(name: "competition", value: "WC"),
                URLQueryItem(name: "from_date", value: "2026-06-11"),
                URLQueryItem(name: "to_date", value: "2026-07-19"),
                URLQueryItem(name: "limit", value: "200"),
            ]
        )
        return response.matches
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let baseURLs = [configuration.apiBaseURL] + configuration.fallbackAPIBaseURLs
        var lastError: Error?

        for baseURL in baseURLs {
            do {
                return try await get(path, query: query, baseURL: baseURL)
            } catch {
                lastError = error
            }
        }

        throw lastError ?? PalmeirasAPIError.invalidURL
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem], baseURL: URL) async throws -> T {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        ) else {
            throw PalmeirasAPIError.invalidURL
        }
        components.queryItems = query.isEmpty ? nil : query

        guard let url = components.url else {
            throw PalmeirasAPIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        if let httpResponse = response as? HTTPURLResponse, !(200..<300).contains(httpResponse.statusCode) {
            throw PalmeirasAPIError.badStatus(httpResponse.statusCode)
        }
        return try decoder.decode(T.self, from: data)
    }
}
