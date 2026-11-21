import { describe, expect, it } from "vitest";
import { summarize } from "../src/panel/tr-view-history";
import type { JobRecord } from "../src/types";

const job = (over: Partial<JobRecord>): JobRecord => ({
  room_id: "k",
  room: "Cucina",
  kind: "vacuum",
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
      job({ kind: "full" }),
      job({}),
      job({ result: "interrupted" }),
      job({ room_id: "c", room: "Camera", result: "failed" }),
    ]);
    expect(s.map((r) => r.room)).toEqual(["Camera", "Cucina"]);
    expect(s[1]).toMatchObject({ full: 1, vacuum: 1, interrupted: 1, minutes: 60 });
    expect(s[0]).toMatchObject({ full: 0, failed: 1, minutes: 0 });
  });
});
