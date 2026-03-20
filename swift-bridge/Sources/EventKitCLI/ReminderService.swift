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
                return []
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
            let cal = Calendar.current

            reminders = reminders.filter { r in
                switch dueWithin {
                case "no-date":
                    return r.dueDateComponents == nil
                case "overdue":
                    guard let due = r.dueDateComponents,
                          let dueDate = cal.date(from: due) else { return false }
                    return dueDate < now && !r.isCompleted
                case "today":
                    guard let due = r.dueDateComponents,
                          let dueDate = cal.date(from: due) else { return false }
                    return cal.isDateInToday(dueDate)
                case "tomorrow":
                    guard let due = r.dueDateComponents,
                          let dueDate = cal.date(from: due) else { return false }
                    return cal.isDateInTomorrow(dueDate)
                case "this-week":
                    guard let due = r.dueDateComponents,
                          let dueDate = cal.date(from: due),
                          let weekEnd = cal.date(byAdding: .day, value: 7, to: now)
                    else { return false }
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
            let subtasks = subtaskTitles.map {
                StoredSubtask(id: UUID().uuidString, title: $0, isCompleted: false)
            }
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
            let cleanedNotes = userNotes.replacingOccurrences(
                of: "\\[#\\w+\\]\\s*",
                with: "",
                options: .regularExpression
            ).trimmingCharacters(in: .whitespacesAndNewlines)

            var newNotes = cleanedNotes
            if !tags.isEmpty {
                let tagString = tags.map { "[#\($0)]" }.joined(separator: " ")
                newNotes = [cleanedNotes, tagString]
                    .filter { !$0.isEmpty }
                    .joined(separator: "\n")
            }
            let existingSubtasks = SubtaskStore.parse(notes: reminder.notes)
            reminder.notes = SubtaskStore.serialize(
                userNotes: newNotes, subtasks: existingSubtasks
            )
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
        let newSubtask = StoredSubtask(
            id: UUID().uuidString, title: title, isCompleted: false
        )
        subtasks.append(newSubtask)

        let userNotes = SubtaskStore.userNotes(from: reminder.notes)
        reminder.notes = SubtaskStore.serialize(userNotes: userNotes, subtasks: subtasks)
        try store.save(reminder, commit: true)

        return SubtaskData(
            id: newSubtask.id, title: newSubtask.title, isCompleted: newSubtask.isCompleted
        )
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
        return SubtaskData(
            id: updated.id, title: updated.title, isCompleted: updated.isCompleted
        )
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
        return SubtaskData(
            id: toggled.id, title: toggled.title, isCompleted: toggled.isCompleted
        )
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
