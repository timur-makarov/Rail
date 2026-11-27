import assert from "node:assert/strict";
import { test } from "node:test";

import { total } from "../src/money.ts";

test("the total is the sum", () => {
  assert.equal(total([250, 100]), 350);
});
