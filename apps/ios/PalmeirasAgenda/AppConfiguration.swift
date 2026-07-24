import Foundation

struct AppConfiguration {
    static let appVersion = "1.2.0"

    let webAppURL: URL

    var apiBaseURL: URL { webAppURL.appending(path: "api/v1") }

    static let production = AppConfiguration(
        webAppURL: URL(string: "https://palmeiras.rodrigolanna.com.br/")!
    )
}
