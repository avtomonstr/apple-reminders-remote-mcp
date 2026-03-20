import EventKit
import Foundation

final class ListService {
    private let store: EKEventStore

    init(store: EKEventStore) {
        self.store = store
    }

    func listLists() -> [ListData] {
        let calendars = store.calendars(for: .reminder)
        return calendars.map { cal in
            let count = (try? store.countOfReminders(
                matching: store.predicateForReminders(in: [cal])
            )) ?? 0
            return ListData(
                id: cal.calendarIdentifier,
                title: cal.title,
                count: count,
                color: cal.cgColor.flatMap { colorToHex($0) }
            )
        }
    }

    func createList(title: String) throws -> ListData {
        let calendar = EKCalendar(for: .reminder, eventStore: store)
        calendar.title = title

        if let defaultCal = store.defaultCalendarForNewReminders() {
            calendar.source = defaultCal.source
        } else if let localSource = store.sources.first(where: { $0.sourceType == .local }) {
            calendar.source = localSource
        } else {
            throw BridgeError.invalidParams("No calendar source available")
        }

        try store.saveCalendar(calendar, commit: true)
        return ListData(
            id: calendar.calendarIdentifier,
            title: calendar.title,
            count: 0,
            color: calendar.cgColor.flatMap { colorToHex($0) }
        )
    }

    func updateList(id: String, title: String) throws -> ListData {
        guard let calendar = store.calendar(withIdentifier: id) else {
            throw BridgeError.notFound("List '\(id)' not found")
        }
        calendar.title = title
        try store.saveCalendar(calendar, commit: true)

        let count = (try? store.countOfReminders(
            matching: store.predicateForReminders(in: [calendar])
        )) ?? 0
        return ListData(
            id: calendar.calendarIdentifier,
            title: calendar.title,
            count: count,
            color: calendar.cgColor.flatMap { colorToHex($0) }
        )
    }

    func deleteList(id: String) throws {
        guard let calendar = store.calendar(withIdentifier: id) else {
            throw BridgeError.notFound("List '\(id)' not found")
        }
        try store.removeCalendar(calendar, commit: true)
    }

    private func colorToHex(_ cgColor: CGColor) -> String? {
        guard let components = cgColor.components, components.count >= 3 else { return nil }
        let r = Int(components[0] * 255)
        let g = Int(components[1] * 255)
        let b = Int(components[2] * 255)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}

// MARK: - Synchronous reminder count

extension EKEventStore {
    func countOfReminders(matching predicate: NSPredicate) throws -> Int {
        var result: Int = 0
        let semaphore = DispatchSemaphore(value: 0)
        fetchReminders(matching: predicate) { reminders in
            result = reminders?.count ?? 0
            semaphore.signal()
        }
        semaphore.wait()
        return result
    }
}

enum BridgeError: Error, LocalizedError {
    case notFound(String)
    case invalidParams(String)
    case permissionDenied(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let msg): return msg
        case .invalidParams(let msg): return msg
        case .permissionDenied(let msg): return msg
        }
    }
}
