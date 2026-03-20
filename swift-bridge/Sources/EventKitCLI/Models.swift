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
