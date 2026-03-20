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
        let fallback = """
        {"id":"\(response.id)","success":false,"error":"Failed to encode response"}
        """
        FileHandle.standardOutput.write(Data((fallback.trimmingCharacters(in: .newlines) + "\n").utf8))
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
                FileHandle.standardError.write(
                    Data("EventKit access error: \(error.localizedDescription)\n".utf8)
                )
            }
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { success, error in
            granted = success
            if let error = error {
                FileHandle.standardError.write(
                    Data("EventKit access error: \(error.localizedDescription)\n".utf8)
                )
            }
            semaphore.signal()
        }
    }

    semaphore.wait()
    return granted
}

// MARK: - Command dispatch

func handleCommand(
    request: BridgeRequest,
    listService: ListService,
    reminderService: ReminderService
) -> BridgeResponse {
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
            guard let id = request.string("id"),
                  let title = request.string("title") else {
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
                return .fail(
                    id: request.id, error: "'reminder_id' and 'title' are required"
                )
            }
            let subtask = try reminderService.createSubtask(
                reminderId: reminderId, title: title
            )
            return .ok(id: request.id, data: subtask)

        case "update_subtask":
            guard let reminderId = request.string("reminder_id") else {
                return .fail(id: request.id, error: "'reminder_id' is required")
            }
            let subtask = try reminderService.updateSubtask(
                reminderId: reminderId, params: request
            )
            return .ok(id: request.id, data: subtask)

        case "delete_subtask":
            guard let reminderId = request.string("reminder_id"),
                  let subtaskId = request.string("id") else {
                return .fail(
                    id: request.id, error: "'reminder_id' and 'id' are required"
                )
            }
            try reminderService.deleteSubtask(
                reminderId: reminderId, subtaskId: subtaskId
            )
            return .ok(id: request.id, data: nil)

        case "toggle_subtask":
            guard let reminderId = request.string("reminder_id"),
                  let subtaskId = request.string("id") else {
                return .fail(
                    id: request.id, error: "'reminder_id' and 'id' are required"
                )
            }
            let subtask = try reminderService.toggleSubtask(
                reminderId: reminderId, subtaskId: subtaskId
            )
            return .ok(id: request.id, data: subtask)

        case "reorder_subtasks":
            guard let reminderId = request.string("reminder_id"),
                  let order = request.stringArray("order") else {
                return .fail(
                    id: request.id, error: "'reminder_id' and 'order' are required"
                )
            }
            try reminderService.reorderSubtasks(
                reminderId: reminderId, order: order
            )
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
    FileHandle.standardError.write(Data(
        "ERROR: Reminders access denied. Grant access in System Settings > Privacy & Security > Reminders.\n".utf8
    ))
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
        FileHandle.standardError.write(
            Data("Failed to parse request: \(line)\n".utf8)
        )
        continue
    }

    let response = handleCommand(
        request: request,
        listService: listService,
        reminderService: reminderService
    )
    writeResponse(response)
}
