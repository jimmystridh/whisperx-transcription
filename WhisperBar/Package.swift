// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WhisperBar",
    platforms: [
        .macOS(.v14),
    ],
    targets: [
        .executableTarget(
            name: "WhisperBar",
            path: "Sources/WhisperBar",
            swiftSettings: [
                .enableUpcomingFeature("StrictConcurrency"),
            ]),
        .testTarget(
            name: "WhisperBarTests",
            dependencies: ["WhisperBar"],
            path: "Tests",
            swiftSettings: [
                .enableUpcomingFeature("StrictConcurrency"),
            ]),
    ])
