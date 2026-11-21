// Fails the build if a bundle is missing or grows past its budget.
import { statSync } from "node:fs";

const DIR = "../custom_components/tidy_rooms/frontend";
const BUDGET = { "tidy-rooms-panel.js": 250_000, "tidy-rooms-card.js": 90_000 };

let failed = false;
for (const [file, max] of Object.entries(BUDGET)) {
  let size;
  try {
    size = statSync(`${DIR}/${file}`).size;
  } catch {
    console.error(`missing ${file}`);
    failed = true;
    continue;
  }
  const ok = size <= max;
  console.log(`${file}: ${size} bytes (budget ${max})${ok ? "" : " TOO BIG"}`);
  failed ||= !ok;
}
process.exit(failed ? 1 : 0);
