// Prints today's (or a given date's) Calendar.app events as JSON.
//
// Why EventKit instead of AppleScript: querying Calendar.app via AppleScript's
// `whose` clause (e.g. "every event of cal whose start date >= ...") is a
// known dead end -- it can hang indefinitely rather than erroring, especially
// once more than a couple of calendars (subscribed/holiday calendars, etc.)
// are involved. EventKit talks to the same calendar store Calendar.app and
// Day One itself use, and returns in well under a second.
//
// Why this needs a one-time manual permission grant: this is a standalone
// compiled binary, not a signed .app bundle with an NSCalendarsUsageDescription
// string, so macOS won't show the normal permission popup when it calls
// requestFullAccessToEvents -- it just silently denies. The fix (same one
// long used for tools like icalBuddy) is to add the compiled binary directly
// under System Settings -> Privacy & Security -> Calendars via the "+" button.
//
// Usage: calendar_agenda [--date YYYY-MM-DD]
// Prints one JSON array to stdout: [{title, start, end, isAllDay, calendar}, ...]

import EventKit
import Foundation

func isoDay(_ s: String?) -> Date {
    guard let s = s else { return Date() }
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    f.timeZone = TimeZone.current
    guard let d = f.date(from: s) else {
        FileHandle.standardError.write("Invalid --date, expected YYYY-MM-DD\n".data(using: .utf8)!)
        exit(1)
    }
    return d
}

var targetDateString: String? = nil
var args = CommandLine.arguments.dropFirst().makeIterator()
while let arg = args.next() {
    if arg == "--date", let v = args.next() {
        targetDateString = v
    }
}

let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)
var granted = false
var requestError: Error? = nil

if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { ok, err in
        granted = ok
        requestError = err
        sem.signal()
    }
} else {
    store.requestAccess(to: .event) { ok, err in
        granted = ok
        requestError = err
        sem.signal()
    }
}
sem.wait()

guard granted else {
    let msg = requestError?.localizedDescription ?? "no error reported"
    FileHandle.standardError.write((
        "Calendar access not granted (\(msg)).\n" +
        "Add this binary under System Settings -> Privacy & Security -> Calendars, " +
        "then run again.\n"
    ).data(using: .utf8)!)
    exit(1)
}

let referenceDate = isoDay(targetDateString)
let cal = Calendar.current
let startOfDay = cal.startOfDay(for: referenceDate)
let endOfDay = cal.date(byAdding: .day, value: 1, to: startOfDay)!

let predicate = store.predicateForEvents(withStart: startOfDay, end: endOfDay, calendars: nil)
let events = store.events(matching: predicate).sorted { $0.startDate < $1.startDate }

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime]

struct EventOut: Encodable {
    let title: String
    let start: String
    let end: String
    let isAllDay: Bool
    let calendar: String
}

let out = events.map { e in
    EventOut(
        title: e.title ?? "(untitled)",
        start: isoFormatter.string(from: e.startDate),
        end: isoFormatter.string(from: e.endDate),
        isAllDay: e.isAllDay,
        calendar: e.calendar.title
    )
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
let data = try! encoder.encode(out)
print(String(data: data, encoding: .utf8)!)
