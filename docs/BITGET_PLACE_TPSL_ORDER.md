## Bitget API Reference — Place-Tpsl-Order (USDT-M Futures)

Source: https://www.bitget.com/api-doc/contract/plan/Place-Tpsl-Order

Last verified: 2025-11-13


### Endpoint

- Method: POST
- Path: `/api/v2/mix/order/place-tpsl-order`


### Purpose

Create exchange-side conditional orders that execute at MARKET on trigger:

- Take Profit (profit_plan)
- Stop Loss (loss_plan)
- Trailing Take Profit (moving_plan)

These orders live on Bitget’s servers and will trigger even if the bot is offline.


### Headers (Auth)

- `ACCESS-KEY` — API key
- `ACCESS-SIGN` — HMAC SHA256 signature (base64)
- `ACCESS-TIMESTAMP` — ms timestamp (string)
- `ACCESS-PASSPHRASE` — plain text passphrase
- `Content-Type: application/json`


### Common Request Fields

- `symbol` (string): e.g. `BTCUSDT`
- `productType` (string): `usdt-futures` (lowercase)
- `marginMode` (string): `isolated` or `crossed` (we use `isolated`)
- `marginCoin` (string): `USDT`
- `planType` (string): One of
  - `profit_plan` — Take Profit
  - `loss_plan` — Stop Loss
  - `moving_plan` — Trailing Take Profit
- `holdSide` (string): One-way mode uses
  - `buy` — protects a long position
  - `sell` — protects a short position
- `triggerPrice` (string/decimal): activation price; must obey side rules (see below)
- `triggerType` (string): `mark_price` | `market_price` | `index_price`
- `size` (string/decimal): required for `profit_plan` and `moving_plan`; optional for `loss_plan` (see notes)
- `executePrice` (optional): not needed for market execution; omit to execute at market on trigger

Notes:
- Bitget enforces instrument precision:
  - `pricePlace`: number of decimal places allowed for prices
  - `priceEndStep`: tick size
  - `volumePlace`: decimals for `size`
- If the API responds with `checkScale=X`, round `triggerPrice` to X decimals and resend.


### Price Side Rules (Validation)

- Take Profit (`profit_plan`, `moving_plan`):
  - Long (`holdSide=buy`): TP trigger must be greater than (≥) current price
  - Short (`holdSide=sell`): TP trigger must be less than (≤) current price

- Stop Loss (`loss_plan`):
  - Long (`holdSide=buy`): SL trigger must be less than (≤) current price
  - Short (`holdSide=sell`): SL trigger must be greater than (≥) current price

Bitget may enforce strict inequality depending on `triggerType`. If you receive a rule violation, nudge by one tick (`priceEndStep`) to the valid side and retry.


### Error Codes (commonly encountered)

- `40832` — The take profit price of short positions should be less than the current price
- `45135` — Take-profit price must be on the correct side of the mark price
- `43034` — The trigger price should be ≤ the current market price (moving_plan validation)
- `43035` — The trigger price should be ≥ the current market price (complementary rule)
- `40808` — Parameter verification exception `checkBDScale`/`checkScale` (round to required decimals)
- `43011` — `rangeRate` must have 2 decimal places (for trailing)
- `43023` — Insufficient position (place after position is visible/settled on exchange)


### Examples

Take Profit (profit_plan), Long

```json
{
  "symbol": "BTCUSDT",
  "productType": "usdt-futures",
  "marginMode": "isolated",
  "marginCoin": "USDT",
  "planType": "profit_plan",
  "holdSide": "buy",
  "size": "0.002",
  "triggerPrice": "65350.0",
  "triggerType": "mark_price"
}
```

Stop Loss (loss_plan), Long

```json
{
  "symbol": "BTCUSDT",
  "productType": "usdt-futures",
  "marginMode": "isolated",
  "marginCoin": "USDT",
  "planType": "loss_plan",
  "holdSide": "buy",
  "size": "0.002",
  "triggerPrice": "63950.0",
  "triggerType": "mark_price"
}
```

Trailing Take Profit (moving_plan), Long

```json
{
  "symbol": "BTCUSDT",
  "productType": "usdt-futures",
  "marginMode": "isolated",
  "marginCoin": "USDT",
  "planType": "moving_plan",
  "holdSide": "buy",
  "size": "0.002",
  "triggerPrice": "65500.0",
  "triggerType": "mark_price",
  "rangeRate": "0.50"  // 0.50% trailing
}
```


### Precision and Rounding

- Round `triggerPrice` to `pricePlace` decimals; clamp to tick grid if `priceEndStep` dictates a step size.
- Round `size` to `volumePlace` decimals.
- If server responds with `checkScale=X`, re-round `triggerPrice` to X decimals and resend immediately.


### Bot Invariants (how we use it)

- We always submit:
  - `profit_plan` (min-profit floor; guarantees ≥ 2.5% ROE)
  - `moving_plan` (trailing TP; activates at the floor)
  - `loss_plan` backup SL at -15% ROE (full size) to complement a fixed full-position SL
- We pre-validate each trigger vs live mark price, nudging by 1 tick to the valid side.
- We verify presence via `orders-plan-pending` and re-place missing orders.


### Related

- Place-Plan-Order (Trailing “track_plan”): `/api/v2/mix/order/place-plan-order`
  - `planType=track_plan`
  - `orderType=market`, `price=""`
  - Shows under “Trailing” tab; also supported in our bot.


