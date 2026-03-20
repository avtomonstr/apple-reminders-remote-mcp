// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "EventKitCLI",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "EventKitCLI",
            path: "Sources/EventKitCLI",
            linkerSettings: [
                .linkedFramework("EventKit")
            ]
        )
    ]
)
