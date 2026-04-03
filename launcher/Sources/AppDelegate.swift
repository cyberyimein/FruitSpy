import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var statusMenu: NSMenu!
    private var statusLabelItem: NSMenuItem!

    private var serviceController: ServiceController!
    private var projectRootURL: URL!
    private var startMenuItem: NSMenuItem!
    private var stopMenuItem: NSMenuItem!
    private var hasShownHelp = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let scriptURL = resolveLauncherScript() else {
            showBlockingError(message: "Cannot find scripts/launcher.sh")
            NSApp.terminate(nil)
            return
        }

        guard let rootURL = resolveProjectRoot() else {
            showBlockingError(message: "Cannot resolve FruitSpy project root")
            NSApp.terminate(nil)
            return
        }

        projectRootURL = rootURL

        serviceController = ServiceController(scriptURL: scriptURL, projectRootURL: rootURL)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "FruitSpy"
        statusItem.button?.toolTip = "FruitSpy"

        statusMenu = NSMenu()

        statusLabelItem = NSMenuItem(title: "Status: --", action: nil, keyEquivalent: "")
        statusLabelItem.isEnabled = false
        statusMenu.addItem(statusLabelItem)
        statusMenu.addItem(NSMenuItem.separator())

        startMenuItem = NSMenuItem(title: "Start Service", action: #selector(startService), keyEquivalent: "s")
        stopMenuItem = NSMenuItem(title: "Stop Service", action: #selector(stopService), keyEquivalent: "x")
        statusMenu.addItem(startMenuItem)
        statusMenu.addItem(stopMenuItem)
        statusMenu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "o"))
        statusMenu.addItem(NSMenuItem.separator())
        statusMenu.addItem(NSMenuItem(title: "Stop Service and Quit", action: #selector(stopAndQuitApp), keyEquivalent: "q"))
        statusMenu.addItem(NSMenuItem(title: "Quit Launcher Only", action: #selector(quitApp), keyEquivalent: ""))

        for item in statusMenu.items {
            item.target = self
        }

        statusItem.menu = statusMenu
        refreshStatusLabel()

        // One-click startup behavior: launching the app should bring service online.
        if serviceController.status() != "running" {
            _ = serviceController.start()
        }
        serviceController.openPanel()
        refreshStatusLabel()
        showUsageHelpIfNeeded()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        serviceController.openPanel()
        return true
    }

    @objc private func startService() {
        let result = serviceController.start()
        if result == "failed" || result == "timeout" {
            showBlockingError(message: "Service start failed. Please check runtime/fruitspy.log")
        } else {
            serviceController.openPanel()
        }
        refreshStatusLabel()
    }

    @objc private func stopService() {
        _ = serviceController.stop()
        refreshStatusLabel()
    }

    @objc private func openDashboard() {
        serviceController.openPanel()
    }

    @objc private func quitApp() {
        NSApp.terminate(nil)
    }

    @objc private func stopAndQuitApp() {
        _ = serviceController.stop()
        NSApp.terminate(nil)
    }

    private func refreshStatusLabel() {
        let status = serviceController.status()
        statusLabelItem.title = "Status: \(status)"
        let isRunning = status == "running"
        startMenuItem.isEnabled = !isRunning
        stopMenuItem.isEnabled = isRunning
    }

    private func resolveLauncherScript() -> URL? {
        if let resourceURL = Bundle.main.resourceURL {
            let bundledScript = resourceURL
                .appendingPathComponent("scripts")
                .appendingPathComponent("launcher.sh")
            if FileManager.default.fileExists(atPath: bundledScript.path) {
                return bundledScript
            }
        }

        // Dev fallback so the launcher can run before packaging.
        let devPath = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("scripts")
            .appendingPathComponent("launcher.sh")
        if FileManager.default.fileExists(atPath: devPath.path) {
            return devPath
        }
        return nil
    }

    private func resolveProjectRoot() -> URL? {
        if let envRoot = ProcessInfo.processInfo.environment["FRUITSPY_ROOT"] {
            let candidate = URL(fileURLWithPath: envRoot)
            if FileManager.default.fileExists(atPath: candidate.appendingPathComponent("scripts/launcher.sh").path) {
                return candidate
            }
        }

        if let resourceURL = Bundle.main.resourceURL,
           FileManager.default.fileExists(atPath: resourceURL.appendingPathComponent("scripts/launcher.sh").path) {
            return resourceURL
        }

        let fromBundle = Bundle.main.bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        if FileManager.default.fileExists(atPath: fromBundle.appendingPathComponent("scripts/launcher.sh").path) {
            return fromBundle
        }

        let fromCurrent = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        if FileManager.default.fileExists(atPath: fromCurrent.appendingPathComponent("scripts/launcher.sh").path) {
            return fromCurrent
        }
        return nil
    }

    private func showBlockingError(message: String) {
        let alert = NSAlert()
        alert.messageText = "FruitSpy Launcher"
        alert.informativeText = message
        alert.alertStyle = .critical
        alert.runModal()
    }

    private func showUsageHelpIfNeeded() {
        if hasShownHelp {
            return
        }
        hasShownHelp = true

        let alert = NSAlert()
        alert.messageText = "FruitSpy is running"
        alert.informativeText = "Use menu bar item 'FruitSpy' to control service.\nChoose 'Stop Service and Quit' to fully close."
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Got it")
        alert.runModal()
    }
}
