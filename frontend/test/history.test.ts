import { describe, expect, it } from "vitest";
import { summarize } from "../src/panel/tr-view-history";
import type { JobRecord } from "../src/types";

const job = (over: Partial<JobRecord>): JobRecord => ({
  room_id: "k",
  room: "Cucina",
  work_mode: "vacuum",
  pass_id: "vacuum-1",
  forced: false,
  quiet: false,
  manual: false,
  attempts: 1,
  started: "2026-01-12T10:00:00+01:00",
  ended: "2026-01-12T10:30:00+01:00",
  result: "done",
  ...over,
});

describe("summarize", () => {
  it("counts passes, problems and time per room", () => {
    const s = summarize([
      job({ work_mode: undefined, pass_id: undefined, kind: "full" }), // logged by 0.3.0
      job({}),
      job({ manual: true, pass_id: null, work_mode: "mop" }), // did not count
      job({ result: "interrupted" }),
      job({ room_id: "c", room: "Camera", result: "failed" }),
    ]);
    expect(s.map((r) => r.room)).toEqual(["Camera", "Cucina"]);
    expect(s[1]).toMatchObject({ passes: 2, extra: 1, interrupted: 1, minutes: 90 });
    expect(s[0]).toMatchObject({ passes: 0, failed: 1, minutes: 0 });
  });
});
