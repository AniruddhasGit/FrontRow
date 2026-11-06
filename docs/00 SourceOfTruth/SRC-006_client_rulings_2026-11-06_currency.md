# SRC-006 — FrontRow client rulings, fourth batch: prices in US dollars

```
Source type ....... Client rulings, typed in chat and two structured answers
Received .......... 2026-11-06, build session chat
Author ............ Aniruddha Jathar (the client)
Status ............ FROZEN — never edited
Citation form ..... SRC-006 <ROW-ID>
Supersedes ........ SRC-003 OPEN-LOCALE-01 (currency only)
```

> **FROZEN INPUT. DO NOT EDIT.** Ruling blocks are the client's words verbatim, or the option they
> selected. Anything under `Filed as` is the build session's reading and is **not** client text.
> The only permitted modification is a clearly marked `ERRATUM` appended at the foot.

## CUR-1 · The currency is US dollars · `RULED` · reserved (money)

**Ruling (typed):** *"i want the prices to be in $ all over the website."*

**Ruling (selected):** prices → *"$12.99 base"*; place and time → *"Dollars only, keep India time"*.

**Filed as:**
- Currency **USD**, minor unit **cents**, ratio **100**. The minor-unit ratio is unchanged (paise and cents
  are both 1/100), so stored integers keep their meaning and no column changes. This supersedes the
  currency half of `SRC-003 OPEN-LOCALE-01`. **Country and timezone stay as ruled there: Asia/Kolkata.**
- **The one-way door is still open:** no booking exists in any environment on 2026-11-06 (Neon is not
  seeded), so nothing already paid is reinterpreted. Once the first real booking exists, this ratio is
  frozen again.
- The demo base price is **$12.99** (1299 cents). The category uplifts and the rounding rule are
  unchanged (`SRC-003 OPEN-PRICE-01`), so Premium and Recliner prices follow from the existing rule.
- **What changes:** `CURRENCY_CODE` → `USD` and its validation, the display format everywhere money is
  shown (the `$` symbol, `en-US` grouping, two decimals), the receipt email, the seed's base price, and
  every test and acceptance criterion that names INR, ₹ or paise as the *currency*. Internal names such
  as `*_paise` columns describe a 1/100 minor unit. Renaming them is a migration, so it is not done
  under this ruling; a `ponytail:` note records it.
- **What does not change:** integer minor units, no floats, `Idempotency-Key`, the database guard, the
  simulated payment and the absence of card data.
