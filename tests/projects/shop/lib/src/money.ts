/** The sum of the prices, in cents. */
export function total(prices: number[]): number {
  return prices.reduce((sum, price) => sum + price, 0);
}
