import { describe, expect, it } from "vitest";
import { labelRobotOptions } from "../src/form";
import type { FormField } from "../src/types";
import { hass } from "./fixtures";

const select = (name: string, options: string[]): FormField => ({
  name,
  selector: { select: { options, mode: "dropdown" } },
});

describe("labelRobotOptions", () => {
  const h = hass("it");
  h.states = {
    "vacuum.tatiana": { entity_id: "vacuum.tatiana" } as never,
    "select.tatiana_work_mode": { entity_id: "select.tatiana_work_mode" } as never,
  };
  h.formatEntityAttributeValue = (_s, _a, v) => (v === "max_plus" ? "Max+" : String(v));
  h.formatEntityState = (_s, v) =>
    v === "mop_after_vacuum" ? "Aspirazione poi lavaggio" : String(v);

  it("names fan speeds and work modes as Home Assistant shows them", () => {
    const [fan, mode, other] = labelRobotOptions(
      [
        select("fan_speed", ["normal", "max_plus"]),
        select("full_mode", ["vacuum", "mop_after_vacuum"]),
        select("wake_days", ["sat"]),
      ],
      h,
      "vacuum.tatiana",
      "select.tatiana_work_mode",
    );
    expect((fan.selector as { select: { options: unknown } }).select.options).toEqual([
      { value: "normal", label: "normal" },
      { value: "max_plus", label: "Max+ (max_plus)" },
    ]);
    expect((mode.selector as { select: { options: unknown } }).select.options).toEqual([
      { value: "vacuum", label: "vacuum" },
      { value: "mop_after_vacuum", label: "Aspirazione poi lavaggio (mop_after_vacuum)" },
    ]);
    expect(other).toEqual(select("wake_days", ["sat"]));
  });

  it("keeps the raw values when the frontend cannot translate them", () => {
    const plain = hass("it");
    const [fan] = labelRobotOptions([select("fan_speed", ["max"])], plain, "vacuum.x", null);
    expect((fan.selector as { select: { options: unknown } }).select.options).toEqual([
      { value: "max", label: "max" },
    ]);
  });
});
