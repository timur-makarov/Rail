import assert from "node:assert/strict";
import { test } from "node:test";

import { shown } from "../src/cart.ts";

test("the cart shows its total in euros", () => {
  assert.equal(shown([250, 100]), "3.50 EUR");
});
