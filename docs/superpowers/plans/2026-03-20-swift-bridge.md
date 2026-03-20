# Swift EventKit Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Swift CLI binary (`EventKitCLI`) that wraps Apple's EventKit framework, reading JSON commands from stdin and writing JSON responses to stdout, enabling the Python MCP server to manage Apple Reminders.

**Architecture:** A single long-lived Swift process communicates via newline-delimited JSON over stdin/stdout. It requests EventKit access on startup, then enters a read-dispatch-respond loop. Commands are dispatched to `ListService` (list CRUD) and `ReminderService` (reminder/subtask CRUD). Subtasks are stored in the reminder's notes field using `---SUBTASKS---` markers. Tags use `[#tag]` format in notes.

**Tech Stack:** Swift 5.9+, EventKit framework, Foundation (JSONEncoder/Decoder)

**Constraint:** This code runs exclusively on macOS. We are developing on Windows, so no compilation or testing is possible here. The plan produces syntactically correct Swift that will be compiled on the target Mac with `swift build -c release`.

---

## File Structure

```
swift-bridge/
  Package.swift                         — Swift package manifest, EventKit dependency
  Sources/
    EventKitCLI/
      main.swift                        — Entry point: request EventKit access, stdin read loop, command dispatch
      Models.swift                      — Codable structs: Request, Response, ReminderData, ListData, SubtaskData
      ListService.swift                 — EKEventStore operations for reminder lists
      ReminderService.swift             — EKEventStore operations for reminders + subtasks
      SubtaskStore.swift                — Parse/serialize subtasks in notes field (---SUBTASKS--- markers)

scripts/
  build-swift.sh                        — Compile the Swift binary (swift build -c release)
```

---

## Task 1: Package.swift and Build Script

**Files:**
- Create: `swift-bridge/Package.swift`
- Create: `scripts/build-swift.sh`

- [ ] **Step 1: Create `swift-bridge/Package.swift`**

```swift
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
```

- [ ] **Step 2: Create `scripts/build-swift.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building EventKitCLI..."
cd "$PROJECT_ROOT/swift-bridge"
swift build -c release

BINARY="$PROJECT_ROOT/swift-bridge/.build/release/EventKitCLI"
if [ -f "$BINARY" ]; then
    echo "Build successful: $BINARY"
else
    echo "Build failed: binary not found at $BINARY" >&2
    exit 1
fi
```

- [ ] **Step 3: Commit**

```bash
git add swift-bridge/Package.swift scripts/build-swift.sh
git commit -m "chore: add Swift package manifest and build script"
```

---

## Task 2: Codable Models

**Files:**
- Create: `swift-bridge/Sources/EventKitCLI/Models.swift`

- [ ] **Step 1: Create `Models.swift`**

These structs match the Python-side Pydantic models exactly.

```swift
import Foundation

// MARK: - JSON Protocol

struct BridgeRequest: Codable {
    let id: String
    let command: String
    let params: [String: AnyCodable]
}

struct BridgeResponse: Codable {
    let id: String
    let success: Bool
    var data: AnyCodable?
    var error: String?

    static func ok(id: String, data: Any?) -> BridgeResponse {
        BridgeResponse(id: id, success: true, data: AnyCodable(data), error: nil)
    }

    static func fail(id: String, error: String) -> BridgeResponse {
        BridgeResponse(id: id, success: false, data: nil, error: error)
    }
}

// MARK: - Data Models

struct ListData: Codable {
    let id: String
    let title: String
    let count: Int
    let color: String?
}

struct ReminderData: Codable {
    let id: String
    let title: String
    let listId: String
    let listTitle: String
    let isCompleted: Bool
    let priority: Int
    let dueDate: String?
    let notes: String?
    let url: String?

    enum CodingKeys: String, CodingKey {
        case id, title, priority, notes, url
        case listId = "list_id"
        case listTitle = "list_title"
        case isCompleted = "is_completed"
        case dueDate = "due_date"
    }
}

struct SubtaskData: Codable {
    let id: String
    let title: String
    let isCompleted: Bool

    enum CodingKeys: String, CodingKey {
        case id, title
        case isCompleted = "is_completed"
    }
}

// MARK: - AnyCodable (type-erased Codable wrapper)

struct AnyCodable: Codable {
    let value: Any?

    init(_ value: Any?) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            value = nil
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        if value == nil {
            try container.encodeNil()
        } else if let bool = value as? Bool {
            try container.encode(bool)
        } else if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let string = value as? String {
            try container.encode(string)
        } else if let array = value as? [Any?] {
            try container.encode(array.map { AnyCodable($0) })
        } else if let dict = value as? [String: Any?] {
            try container.encode(dict.mapValues { AnyCodable($0) })
        } else if let encodable = value as? Encodable {
            try encodable.encode(to: encoder)
        } else {
            try container.encodeNil()
        }
    }
}

// MARK: - Param Helpers

extension BridgeRequest {
    func string(_ key: String) -> String? {
        params[key]?.value as? String
    }

    func bool(_ key: String) -> Bool? {
        params[key]?.value as? Bool
    }

    func int(_ key: String) -> Int? {
        if let i = params[key]?.value as? Int { return i }
        if let d = params[key]?.value as? Double { return Int(d) }
        return nil
    }

    func stringArray(_ key: String) -> [String]? {
        if let arr = params[key]?.value as? [Any?] {
            return arr.compactMap { $0 as? String }
        }
        return nil
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add swift-bridge/Sources/EventKitCLI/Models.swift
git commit -m "feat: add Codable models for Swift bridge JSON protocol"
```

---

## Task 3: SubtaskStore (notes field parsing)

**Files:**
- Create: `swift-bridge/Sources/EventKitCLI/SubtaskStore.swift`

- [ ] **Step 1: Create `SubtaskStore.swift`**

Subtasks are stored in the reminder's notes field between `---SUBTASKS---` and `---END SUBTASKS---` markers as a JSON array. Each subtask has an id (UUID), title, and is_completed flag.

```swift
import Foundation

struct StoredSubtask: Codable {
    let id: String
    var title: String
    var isCompleted: Bool

    enum CodingKeys: String, CodingKey {
        case id, title
        case isCompleted = "is_completed"
    }
}

enum SubtaskStore {
    private static let startMarker = "---SUBTASKS---"
    private static let endMarker = "---END SUBTASKS---"

    /// Extract subtasks from the notes field.
    static func parse(notes: String?) -> [StoredSubtask] {
        guard let notes = notes,
              let startRange = notes.range(of: startMarker),
              let endRange = notes.range(of: endMarker) else {
            return []
        }

        let jsonString = String(notes[startRange.upperBound..<endRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = jsonString.data(using: .utf8),
              let subtasks = try? JSONDecoder().decode([StoredSubtask].self, from: data) else {
            return []
        }
        return subtasks
    }

    /// Return the user-visible notes (everything outside the subtask markers).
    static func userNotes(from notes: String?) -> String? {
        guard let notes = notes else { return nil }
        guard let startRange = notes.range(of: startMarker),
              let endRange = notes.range(of: endMarker) else {
            return notes.isEmpty ? nil : notes
        }

        let before = String(notes[..<startRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
        let after = String(notes[endRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
        let combined = [before, after].filter { !$0.isEmpty }.joined(separator: "\n")
        return combined.isEmpty ? nil : combined
    }

    /// Serialize subtasks back into the notes field, preserving user text.
    static func serialize(userNotes: String?, subtasks: [StoredSubtask]) -> String? {
        if subtasks.isEmpty {
            return userNotes
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(subtasks),
              let json = String(data: data, encoding: .utf8) else {
            return userNotes
        }

        var parts: [String] = []
        if let userNotes = userNotes, !userNotes.isEmpty {
            parts.append(userNotes)
        }
        parts.append(startMarker)
        parts.append(json)
        parts.append(endMarker)
        return parts.joined(separator: "\n")
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add swift-bridge/Sources/EventKitCLI/SubtaskStore.swift
git commit -m "feat: add subtask storage in notes field with marker parsing"
```

---

## Task 4: ListService

**Files:**
- Create: `swift-bridge/Sources/EventKitCLI/ListService.swift`

- [ ] **Step 1: Create `ListService.swift`**

```swift
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
            let count = try? store.countOfReminders(matching: store.predicateForReminders(in: [cal]))
            return ListData(
                id: cal.calendarIdentifier,
                title: cal.title,
                count: count ?? 0,
                color: cal.cgColor.flatMap { colorToHex($0) }
            )
        }
    }

    func createList(title: String) throws -> ListData {
        let calendar = EKCalendar(for: .reminder, eventStore: store)
        calendar.title = title
        calendar.source = store.defaultCalendarForNewReminders()?.source ?? store.sources.first { $0.sourceType == .local }!
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

        let count = try? store.countOfReminders(matching: store.predicateForReminders(in: [calendar]))
        return ListData(
            id: calendar.calendarIdentifier,
            title: calendar.title,
            count: count ?? 0,
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
```

- [ ] **Step 2: Commit**

```bash
git add swift-bridge/Sources/EventKitCLI/ListService.swift
git commit -m "feat: add ListService for EventKit reminder list CRUD"
```

---

## Task 5: ReminderService

**Files:**
- Create: `swift-bridge/Sources/EventKitCLI/ReminderService.swift`

- [ ] **Step 1: Create `ReminderService.swift`**

```swift
import EventKit
import Foundation

final class ReminderService {
    private let store: EKEventStore

    init(store: EKEventStore) {
        self.store = store
    }

    // MARK: - ISO 8601 date helpers

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private func parseDate(_ str: String?) -> Date? {
        guard let str = str else { return nil }
        return Self.isoFormatter.date(from: str)
    }

    private func formatDate(_ date: Date?) -> String? {
        guard let date = date else { return nil }
        return Self.isoFormatter.string(from: date)
    }

    // MARK: - Convert EKReminder to ReminderData

    private func toData(_ reminder: EKReminder) -> ReminderData {
        let calendar = reminder.calendar!
        return ReminderData(
            id: reminder.calendarItemIdentifier,
            title: reminder.title ?? "",
            listId: calendar.calendarIdentifier,
            listTitle: calendar.title,
            isCompleted: reminder.isCompleted,
            priority: reminder.priority,
            dueDate: reminder.dueDateComponents.flatMap {
                Calendar.current.date(from: $0)
            }.flatMap { formatDate($0) },
            notes: reminder.notes,
            url: reminder.url?.absoluteString
        )
    }

    // MARK: - Fetch helpers

    private func fetchAllReminders(in calendars: [EKCalendar]?) -> [EKReminder] {
        let predicate = store.predicateForReminders(in: calendars)
        var result: [EKReminder] = []
        let semaphore = DispatchSemaphore(value: 0)
        store.fetchReminders(matching: predicate) { reminders in
            result = reminders ?? []
            semaphore.signal()
        }
        semaphore.wait()
        return result
    }

    private func findCalendar(named name: String) -> EKCalendar? {
        store.calendars(for: .reminder).first { $0.title == name }
    }

    private func findCalendarById(_ id: String) -> EKCalendar? {
        store.calendar(withIdentifier: id)
    }

    private func findReminder(id: String) -> EKReminder? {
        let predicate = store.predicateForReminders(in: nil)
        var found: EKReminder?
        let semaphore = DispatchSemaphore(value: 0)
        store.fetchReminders(matching: predicate) { reminders in
            found = reminders?.first { $0.calendarItemIdentifier == id }
            semaphore.signal()
        }
        semaphore.wait()
        return found
    }

    // MARK: - List Reminders

    func listReminders(params: BridgeRequest) throws -> [ReminderData] {
        let showCompleted = params.bool("show_completed") ?? false
        let listFilter = params.string("list")
        let search = params.string("search")?.lowercased()
        let dueWithin = params.string("due_within")
        let priorityFilter = params.string("priority")
        let tagsFilter = params.stringArray("tags")

        // Determine calendars to search
        var calendars: [EKCalendar]? = nil
        if let listFilter = listFilter {
            if let cal = findCalendar(named: listFilter) ?? findCalendarById(listFilter) {
                calendars = [cal]
            } else {
                return [] // list not found, return empty
            }
        }

        var reminders = fetchAllReminders(in: calendars)

        // Filter completed
        if !showCompleted {
            reminders = reminders.filter { !$0.isCompleted }
        }

        // Search filter
        if let search = search {
            reminders = reminders.filter { r in
                (r.title?.lowercased().contains(search) ?? false) ||
                (r.notes?.lowercased().contains(search) ?? false)
            }
        }

        // Due date filter
        if let dueWithin = dueWithin {
            let now = Date()
            let calendar = Calendar.current

            reminders = reminders.filter { r in
                switch dueWithin {
                case "no-date":
                    return r.dueDateComponents == nil
                case "overdue":
                    guard let due = r.dueDateComponents,
                          let dueDate = calendar.date(from: due) else { return false }
                    return dueDate < now && !r.isCompleted
                case "today":
                    guard let due = r.dueDateComponents,
                          let dueDate = calendar.date(from: due) else { return false }
                    return calendar.isDateInToday(dueDate)
                case "tomorrow":
                    guard let due = r.dueDateComponents,
                          let dueDate = calendar.date(from: due) else { return false }
                    return calendar.isDateInTomorrow(dueDate)
                case "this-week":
                    guard let due = r.dueDateComponents,
                          let dueDate = calendar.date(from: due),
                          let weekEnd = calendar.date(byAdding: .day, value: 7, to: now) else { return false }
                    return dueDate >= now && dueDate <= weekEnd
                default:
                    return true
                }
            }
        }

        // Priority filter
        if let priorityFilter = priorityFilter {
            let targetPriority: Int
            switch priorityFilter {
            case "high": targetPriority = 1
            case "medium": targetPriority = 5
            case "low": targetPriority = 9
            case "none": targetPriority = 0
            default: targetPriority = -1
            }
            if targetPriority >= 0 {
                reminders = reminders.filter { $0.priority == targetPriority }
            }
        }

        // Tags filter
        if let tagsFilter = tagsFilter, !tagsFilter.isEmpty {
            reminders = reminders.filter { r in
                guard let notes = r.notes else { return false }
                return tagsFilter.allSatisfy { tag in
                    notes.contains("[#\(tag)]")
                }
            }
        }

        return reminders.map { toData($0) }
    }

    // MARK: - Get Reminder

    func getReminder(id: String) throws -> ReminderData {
        guard let reminder = findReminder(id: id) else {
            throw BridgeError.notFound("Reminder '\(id)' not found")
        }
        return toData(reminder)
    }

    // MARK: - Create Reminder

    func createReminder(params: BridgeRequest) throws -> ReminderData {
        guard let title = params.string("title") else {
            throw BridgeError.invalidParams("'title' is required")
        }

        let reminder = EKReminder(eventStore: store)
        reminder.title = title

        // Set calendar (list)
        if let listName = params.string("list") {
            guard let calendar = findCalendar(named: listName) ?? findCalendarById(listName) else {
                throw BridgeError.notFound("List '\(listName)' not found")
            }
            reminder.calendar = calendar
        } else {
            reminder.calendar = store.defaultCalendarForNewReminders()
        }

        // Due date
        if let dueDateStr = params.string("due_date"), let date = parseDate(dueDateStr) {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute, .second], from: date
            )
        }

        // Notes, tags, subtasks
        var noteText = params.string("note")
        if let tags = params.stringArray("tags"), !tags.isEmpty {
            let tagString = tags.map { "[#\($0)]" }.joined(separator: " ")
            noteText = [noteText, tagString].compactMap { $0 }.joined(separator: "\n")
        }
        if let subtaskTitles = params.stringArray("subtasks"), !subtaskTitles.isEmpty {
            let subtasks = subtaskTitles.map { StoredSubtask(id: UUID().uuidString, title: $0, isCompleted: false) }
            noteText = SubtaskStore.serialize(userNotes: noteText, subtasks: subtasks)
        }
        reminder.notes = noteText

        // URL
        if let urlStr = params.string("url") {
            reminder.url = URL(string: urlStr)
        }

        // Priority
        if let priority = params.int("priority") {
            reminder.priority = priority
        }

        // Alarms
        if let alarms = params.stringArray("alarms") {
            for alarmStr in alarms {
                if let date = parseDate(alarmStr) {
                    reminder.addAlarm(EKAlarm(absoluteDate: date))
                }
            }
        }

        try store.save(reminder, commit: true)
        return toData(reminder)
    }

    // MARK: - Update Reminder

    func updateReminder(params: BridgeRequest) throws -> ReminderData {
        guard let id = params.string("id") else {
            throw BridgeError.invalidParams("'id' is required")
        }
        guard let reminder = findReminder(id: id) else {
            throw BridgeError.notFound("Reminder '\(id)' not found")
        }

        if let title = params.string("title") {
            reminder.title = title
        }

        if let dueDateStr = params.string("due_date") {
            if dueDateStr.isEmpty {
                reminder.dueDateComponents = nil
            } else if let date = parseDate(dueDateStr) {
                reminder.dueDateComponents = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute, .second], from: date
                )
            }
        }

        if let completed = params.bool("completed") {
            reminder.isCompleted = completed
        }

        if let priority = params.int("priority") {
            reminder.priority = priority
        }

        if let urlStr = params.string("url") {
            reminder.url = urlStr.isEmpty ? nil : URL(string: urlStr)
        }

        // Handle note update (preserve subtask section)
        if let note = params.string("note") {
            let existingSubtasks = SubtaskStore.parse(notes: reminder.notes)
            reminder.notes = SubtaskStore.serialize(userNotes: note, subtasks: existingSubtasks)
        }

        // Handle tags update (replace all tags in notes)
        if let tags = params.stringArray("tags") {
            let userNotes = SubtaskStore.userNotes(from: reminder.notes) ?? ""
            // Remove existing tags from user notes
            let cleanedNotes = userNotes.replacingOccurrences(
                of: "\\[#\\w+\\]\\s*",
                with: "",
                options: .regularExpression
            ).trimmingCharacters(in: .whitespacesAndNewlines)

            var newNotes = cleanedNotes
            if !tags.isEmpty {
                let tagString = tags.map { "[#\($0)]" }.joined(separator: " ")
                newNotes = [cleanedNotes, tagString].filter { !$0.isEmpty }.joined(separator: "\n")
            }
            let existingSubtasks = SubtaskStore.parse(notes: reminder.notes)
            reminder.notes = SubtaskStore.serialize(userNotes: newNotes, subtasks: existingSubtasks)
        }

        // Move to different list
        if let listName = params.string("list") {
            guard let calendar = findCalendar(named: listName) ?? findCalendarById(listName) else {
                throw BridgeError.notFound("List '\(listName)' not found")
            }
            reminder.calendar = calendar
        }

        try store.save(reminder, commit: true)
        return toData(reminder)
    }

    // MARK: - Delete Reminder

    func deleteReminder(id: String) throws {
        guard let reminder = findReminder(id: id) else {
            throw BridgeError.notFound("Reminder '\(id)' not found")
        }
        try store.remove(reminder, commit: true)
    }

    // MARK: - Subtask Operations

    func listSubtasks(reminderId: String) throws -> [SubtaskData] {
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }
        return SubtaskStore.parse(notes: reminder.notes).map {
            SubtaskData(id: $0.id, title: $0.title, isCompleted: $0.isCompleted)
        }
    }

    func createSubtask(reminderId: String, title: String) throws -> SubtaskData {
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }
        var subtasks = SubtaskStore.parse(notes: reminder.notes)
        let newSubtask = StoredSubtask(id: UUID().uuidString, title: title, isCompleted: false)
        subtasks.append(newSubtask)

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: subtasks)
        try store.save(reminder, commit: true)

        return SubtaskData(id: newSubtask.id, title: newSubtask.title, isCompleted: newSubtask.isCompleted)
    }

    func updateSubtask(reminderId: String, params: BridgeRequest) throws -> SubtaskData {
        guard let subtaskId = params.string("id") else {
            throw BridgeError.invalidParams("'id' is required")
        }
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }

        var subtasks = SubtaskStore.parse(notes: reminder.notes)
        guard let index = subtasks.firstIndex(where: { $0.id == subtaskId }) else {
            throw BridgeError.notFound("Subtask '\(subtaskId)' not found")
        }

        if let title = params.string("title") {
            subtasks[index].title = title
        }
        if let completed = params.bool("completed") {
            subtasks[index].isCompleted = completed
        }

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: subtasks)
        try store.save(reminder, commit: true)

        let updated = subtasks[index]
        return SubtaskData(id: updated.id, title: updated.title, isCompleted: updated.isCompleted)
    }

    func deleteSubtask(reminderId: String, subtaskId: String) throws {
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }

        var subtasks = SubtaskStore.parse(notes: reminder.notes)
        subtasks.removeAll { $0.id == subtaskId }

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: subtasks)
        try store.save(reminder, commit: true)
    }

    func toggleSubtask(reminderId: String, subtaskId: String) throws -> SubtaskData {
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }

        var subtasks = SubtaskStore.parse(notes: reminder.notes)
        guard let index = subtasks.firstIndex(where: { $0.id == subtaskId }) else {
            throw BridgeError.notFound("Subtask '\(subtaskId)' not found")
        }

        subtasks[index].isCompleted.toggle()

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: subtasks)
        try store.save(reminder, commit: true)

        let toggled = subtasks[index]
        return SubtaskData(id: toggled.id, title: toggled.title, isCompleted: toggled.isCompleted)
    }

    func reorderSubtasks(reminderId: String, order: [String]) throws {
        guard let reminder = findReminder(id: reminderId) else {
            throw BridgeError.notFound("Reminder '\(reminderId)' not found")
        }

        let subtasks = SubtaskStore.parse(notes: reminder.notes)
        var reordered: [StoredSubtask] = []

        for id in order {
            if let subtask = subtasks.first(where: { $0.id == id }) {
                reordered.append(subtask)
            }
        }
        // Append any subtasks not in the order list
        for subtask in subtasks where !order.contains(subtask.id) {
            reordered.append(subtask)
        }

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: reordered)
        try store.save(reminder, commit: true)
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add swift-bridge/Sources/EventKitCLI/ReminderService.swift
git commit -m "feat: add ReminderService for reminder and subtask CRUD via EventKit"
```

---

## Task 6: Main Entry Point (stdin/stdout loop)

**Files:**
- Create: `swift-bridge/Sources/EventKitCLI/main.swift`

- [ ] **Step 1: Create `main.swift`**

```swift
import EventKit
import Foundation

// MARK: - JSON helpers

let jsonEncoder: JSONEncoder = {
    let e = JSONEncoder()
    e.outputFormatting = [.sortedKeys]
    return e
}()

let jsonDecoder = JSONDecoder()

func writeResponse(_ response: BridgeResponse) {
    guard let data = try? jsonEncoder.encode(response),
          let line = String(data: data, encoding: .utf8) else {
        // Last resort: write a minimal error
        let fallback = "{\"id\":\"\(response.id)\",\"success\":false,\"error\":\"Failed to encode response\"}"
        FileHandle.standardOutput.write(Data((fallback + "\n").utf8))
        return
    }
    FileHandle.standardOutput.write(Data((line + "\n").utf8))
}

// MARK: - Request EventKit access

func requestAccess(store: EKEventStore) -> Bool {
    var granted = false
    let semaphore = DispatchSemaphore(value: 0)

    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { success, error in
            granted = success
            if let error = error {
                FileHandle.standardError.write(Data("EventKit access error: \(error.localizedDescription)\n".utf8))
            }
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { success, error in
            granted = success
            if let error = error {
                FileHandle.standardError.write(Data("EventKit access error: \(error.localizedDescription)\n".utf8))
            }
            semaphore.signal()
        }
    }

    semaphore.wait()
    return granted
}

// MARK: - Command dispatch

func handleCommand(request: BridgeRequest, listService: ListService, reminderService: ReminderService) -> BridgeResponse {
    do {
        switch request.command {
        // List commands
        case "list_lists":
            let lists = listService.listLists()
            return .ok(id: request.id, data: lists)

        case "create_list":
            guard let title = request.string("title") else {
                return .fail(id: request.id, error: "'title' is required")
            }
            let list = try listService.createList(title: title)
            return .ok(id: request.id, data: list)

        case "update_list":
            guard let id = request.string("id"), let title = request.string("title") else {
                return .fail(id: request.id, error: "'id' and 'title' are required")
            }
            let list = try listService.updateList(id: id, title: title)
            return .ok(id: request.id, data: list)

        case "delete_list":
            guard let id = request.string("id") else {
                return .fail(id: request.id, error: "'id' is required")
            }
            try listService.deleteList(id: id)
            return .ok(id: request.id, data: nil)

        // Reminder commands
        case "list_reminders":
            let reminders = try reminderService.listReminders(params: request)
            return .ok(id: request.id, data: reminders)

        case "get_reminder":
            guard let id = request.string("id") else {
                return .fail(id: request.id, error: "'id' is required")
            }
            let reminder = try reminderService.getReminder(id: id)
            return .ok(id: request.id, data: reminder)

        case "create_reminder":
            let reminder = try reminderService.createReminder(params: request)
            return .ok(id: request.id, data: reminder)

        case "update_reminder":
            let reminder = try reminderService.updateReminder(params: request)
            return .ok(id: request.id, data: reminder)

        case "delete_reminder":
            guard let id = request.string("id") else {
                return .fail(id: request.id, error: "'id' is required")
            }
            try reminderService.deleteReminder(id: id)
            return .ok(id: request.id, data: nil)

        // Subtask commands
        case "list_subtasks":
            guard let reminderId = request.string("reminder_id") else {
                return .fail(id: request.id, error: "'reminder_id' is required")
            }
            let subtasks = try reminderService.listSubtasks(reminderId: reminderId)
            return .ok(id: request.id, data: subtasks)

        case "create_subtask":
            guard let reminderId = request.string("reminder_id"),
                  let title = request.string("title") else {
                return .fail(id: request.id, error: "'reminder_id' and 'title' are required")
            }
            let subtask = try reminderService.createSubtask(reminderId: reminderId, title: title)
            return .ok(id: request.id, data: subtask)

        case "update_subtask":
            guard let reminderId = request.string("reminder_id") else {
                return .fail(id: request.id, error: "'reminder_id' is required")
            }
            let subtask = try reminderService.updateSubtask(reminderId: reminderId, params: request)
            return .ok(id: request.id, data: subtask)

        case "delete_subtask":
            guard let reminderId = request.string("reminder_id"),
                  let subtaskId = request.string("id") else {
                return .fail(id: request.id, error: "'reminder_id' and 'id' are required")
            }
            try reminderService.deleteSubtask(reminderId: reminderId, subtaskId: subtaskId)
            return .ok(id: request.id, data: nil)

        case "toggle_subtask":
            guard let reminderId = request.string("reminder_id"),
                  let subtaskId = request.string("id") else {
                return .fail(id: request.id, error: "'reminder_id' and 'id' are required")
            }
            let subtask = try reminderService.toggleSubtask(reminderId: reminderId, subtaskId: subtaskId)
            return .ok(id: request.id, data: subtask)

        case "reorder_subtasks":
            guard let reminderId = request.string("reminder_id"),
                  let order = request.stringArray("order") else {
                return .fail(id: request.id, error: "'reminder_id' and 'order' are required")
            }
            try reminderService.reorderSubtasks(reminderId: reminderId, order: order)
            return .ok(id: request.id, data: nil)

        default:
            return .fail(id: request.id, error: "Unknown command: \(request.command)")
        }
    } catch let error as BridgeError {
        return .fail(id: request.id, error: error.localizedDescription)
    } catch {
        return .fail(id: request.id, error: error.localizedDescription)
    }
}

// MARK: - Main

let store = EKEventStore()

guard requestAccess(store: store) else {
    FileHandle.standardError.write(Data("ERROR: Reminders access denied. Grant access in System Settings > Privacy & Security > Reminders.\n".utf8))
    exit(1)
}

FileHandle.standardError.write(Data("EventKitCLI ready\n".utf8))

let listService = ListService(store: store)
let reminderService = ReminderService(store: store)

// Read stdin line by line
while let line = readLine(strippingNewline: true) {
    guard !line.isEmpty else { continue }

    guard let data = line.data(using: .utf8),
          let request = try? jsonDecoder.decode(BridgeRequest.self, from: data) else {
        FileHandle.standardError.write(Data("Failed to parse request: \(line)\n".utf8))
        continue
    }

    let response = handleCommand(request: request, listService: listService, reminderService: reminderService)
    writeResponse(response)
}
```

- [ ] **Step 2: Commit**

```bash
git add swift-bridge/Sources/EventKitCLI/main.swift
git commit -m "feat: add main entry point with stdin/stdout JSON loop and command dispatch"
```

---

## Summary

| Task | What it builds | Files |
|------|---------------|-------|
| 1 | Package manifest + build script | `Package.swift`, `scripts/build-swift.sh` |
| 2 | Codable models + AnyCodable | `Models.swift` |
| 3 | Subtask notes parsing | `SubtaskStore.swift` |
| 4 | List CRUD via EventKit | `ListService.swift` |
| 5 | Reminder + subtask CRUD via EventKit | `ReminderService.swift` |
| 6 | CLI entry point + command dispatch | `main.swift` |

**Total: 6 tasks, 7 files**

**To build on Mac:** `./scripts/build-swift.sh` (or `cd swift-bridge && swift build -c release`)

**To test manually:** `echo '{"id":"1","command":"list_lists","params":{}}' | ./swift-bridge/.build/release/EventKitCLI`
