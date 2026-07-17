import SwiftUI

struct AppRootView: View {
    private let apiClient = PalmeirasAPIClient()

    var body: some View {
        HomeView(apiClient: apiClient)
    }
}
