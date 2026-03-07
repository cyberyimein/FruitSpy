import Foundation

final class ServiceController {
    private let scriptURL: URL
    private let projectRootURL: URL

    init(scriptURL: URL, projectRootURL: URL) {
        self.scriptURL = scriptURL
        self.projectRootURL = projectRootURL
    }

    @discardableResult
    private func run(_ action: String) -> (Int32, String) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [scriptURL.path, action]
        var env = ProcessInfo.processInfo.environment
        env["FRUITSPY_ROOT"] = projectRootURL.path
        process.environment = env

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""
            return (process.terminationStatus, output.trimmingCharacters(in: .whitespacesAndNewlines))
        } catch {
            return (1, "Failed to run launcher script: \(error.localizedDescription)")
        }
    }

    func start() -> String {
        let result = run("start")
        return result.1
    }

    func stop() -> String {
        let result = run("stop")
        return result.1
    }

    func openPanel() {
        _ = run("open")
    }

    func status() -> String {
        let result = run("status")
        return result.1
    }
}
