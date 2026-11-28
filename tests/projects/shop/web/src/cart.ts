import { total } from "../../lib/src/money.ts";

/** What the cart page shows as its total. */
export function shown(prices: number[]): string {
  return `${(total(prices) / 100).toFixed(2)} EUR`;
}
