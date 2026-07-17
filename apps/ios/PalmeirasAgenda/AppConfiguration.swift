import Foundation

struct AppConfiguration {
    static let appVersion = "1.1.37"

    var apiBaseURL: URL
    var fallbackAPIBaseURLs: [URL] = []

    static let production = AppConfiguration(
        apiBaseURL: URL(string: "https://palmeiras.rodrigolanna.com.br/api/v1")!,
        fallbackAPIBaseURLs: [
            URL(string: "https://palmeiras.rodrigolanna.com.br/api")!,
        ]
    )
}
