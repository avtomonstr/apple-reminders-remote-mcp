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

        let jsonString = String(notes[startRange.upperBound..<endRange.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
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

        let before = String(notes[..<startRange.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let after = String(notes[endRange.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
