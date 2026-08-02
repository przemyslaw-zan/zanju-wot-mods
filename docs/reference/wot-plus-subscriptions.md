# WoT Plus Subscriptions

Reference notes on the renewable subscription (WoT Plus / WoT Plus Pro): its data model,
how the client decides a subscription is active or cancelled, and how its lobby-header
button and hover tooltip are built.

Verified against WoT client **2.3.0.1 / 2.3.1.0** by decompiling the shipped scripts.

> **Why this page exists.** `premium-time` originally covered WoT Plus alongside Premium
> Account: a countdown on the WoT Plus header button and an exact end time appended to its
> hover tooltip. Both were removed — the subscription is niche, and the tooltip half in
> particular carried ongoing maintenance cost (see [Cost of the tooltip
> integration](#cost-of-the-tooltip-integration)). Everything needed to rebuild it is
> recorded here.

## Data model

Per-account state arrives in the account sync diff under the top-level key `renewableSub`
and is replace-synced into `Account.renewableSubscription`; the change event is
`g_playerEvents.onRenewableSubscriptionStatusChanged`. Keys come from
`renewable_subscription_common/settings_constants.py`:

| Key | Meaning |
| --- | --- |
| `expiry` | Unix timestamp when the entitlement ends (`IWotPlusController.getExpiryTime()`, 0 when none) |
| `tier` | `WotPlusTier`: 0 NONE, 1 CORE, 2 PRO |
| `badges`, `serviceRecordBackground`, `serviceRecordRibbon` | Cosmetic extras |

The matching entitlement names are `premium_subs` (Core) and `premium_pro_subs` (Pro).

`IWotPlusController.getStartTime()` is **derived, not delivered**: it returns
`expiry - SUBSCRIPTION_DURATION_LENGTH` where that constant is a fixed 30 days.

## Active vs cancelled is derived client-side

There is no "cancelled" flag in the account data. `WotPlusController` works it out in two
steps:

1. Immediately on a state change: `state = ACTIVE if tier != NONE else INACTIVE`.
2. Then asynchronously (only when a subscription exists; results cached 5 minutes) it
   fetches the player's subscription products from the platform. If **no** matching product
   has status `ACTIVE` but at least one is in `SUBSCRIPTION_CANCEL_STATUSES`
   (`INACTIVE`, `GDPR_SUSPENDED`, `NEXT_PAYMENT_UNAVAILABLE`), the state becomes
   `CANCELLED`.

Each product (`UserSubscription`) carries `subscription_id`, `product_code`, `status`,
`billing_period.value` (days), `next_billing_time` (ISO), and `platform`
(`wg_platform` / `steam`).

So: **Cancelled** means paid through `expiry`, after which service simply ends.
**Active** means a live billing agreement that renews at `next_billing_time`
(`getNextBillingTime()`, which only returns it for `ACTIVE` products).

### Billing periods

Core bills every 30 days; Pro bills every 180 or 360 days. This is why
`BILLING_PERIOD_DAYS_MAP` only maps `{180: P6MONTHS, 360: P12MONTHS}` — periodicity is a
Pro-only concept and Core's 30 deliberately falls through to `None`. `PRO_THRESHOLD_DAYS`
(270) is what dialogs and service-channel messages use to tell a 6-month Pro subscription
from a 12-month one.

Unverified: whether an Active Pro subscription's `expiry` covers the whole paid period or
rolls forward in 30-day chunks. The 30-day `SUBSCRIPTION_DURATION_LENGTH` hints at the
latter.

## Header button

`UserAccountPresenter.__updateWotPlusInfo()` fills
`UserAccountModel.subscriptions.wotPlus` (`WotPlusSubscriptionModel`):

| Property | Values |
| --- | --- |
| `type` | `None` / `Core` / `Pro` |
| `state` | `Inactive` / `Active` / `Cancelled` |
| `periodicity` | 6 or 12 (Pro only; defaults to 6) |
| `expiryTime` | unix timestamp |
| `isWotPlusEnabled` | whether the feature is visible at all |

The button is rendered by the hangar header JS bundle
(`mono/hangar/views/header/header.html/bundle.js`). Its label is **a bare text child** of
`div[class*="Premiums_text"]` — unlike the Premium Account button, which nests its label in
a `<span>`. Anything rewriting these labels must write into whichever node React owns the
text of, or React's later updates land on a detached node; see the note in
`header_patch.js`.

## Hover tooltip

The WoT Plus button opens a **param tooltip**: `useParamTooltip` raises a wulf view event
that `createParamTooltipWindow` turns into a `ParamTooltipView` hosting the Gameface
tooltips document, which renders the `wot_plus_header_widget` template from JSON params.
`ParamTooltipModel` exposes `type`, `params` and `resId`; the template itself is fixed, so
extra content has to be appended to the DOM on the JS side.

Two things make that awkward:

- **The OpenWG injector cannot reach it.** `gf_mod_inject` attaches a `ModInjectModel` that
  the OpenWG bootstrap discovers by scanning `window.subViews`. The tooltip's content view
  is the *document root* (`window.model`), which is never scanned. The workaround was to
  ship a shadowed copy of the document shell,
  `res/gui/gameface/_dist/production/mono/hangar/tooltips/tooltips.html`, with one extra
  `<script type="module">` tag — VFS shadowing means a mod's `res/` file overrides the same
  path inside the game's `gui-partN.pkg`.
- **The model's type is set after creation.** `ParamTooltipModel` backs *every* param
  tooltip, so data has to be attached to all of them (by wrapping `_initialize`) and the JS
  side must gate on `type === 'wot_plus_header_widget'` and retry until the type appears.

### Cost of the tooltip integration

The shadowed `tooltips.html` is a verbatim copy of a game file, so it must be re-diffed on
**every client update**. This is not theoretical: 2.3.1.0 swapped the hangar `common.css`
stylesheet for `perk.css` in that shell, and the stale copy would have overridden the real
one — loading a stylesheet that no longer exists while dropping the live one, leaving
unrelated hangar tooltips unstyled. A mod-caused regression in game UI the mod does not
otherwise touch.

## Rebuilding the feature

1. Read the end time from `IWotPlusController.getExpiryTime()` and treat it as running only
   while `state` is `Active` or `Cancelled` **and** the expiry is still ahead
   (`formatting.end_text_if_running` already encodes that rule).
2. For a header countdown, extend `header_patch.js` to also track
   `subscriptions.wotPlus` — the state machine there is subscription-agnostic; it was
   driven for both buttons before the removal.
3. For a tooltip line, restore the shadowed shell plus a `ParamTooltipModel._initialize`
   wrapper carrying a pre-formatted string, and budget for re-diffing the shell on every
   client update.

Deleted implementation: `src/zanju_pt/gameface/tooltip_inject.py`,
`res/gui/gameface/mods/zanju_premiumtime/tooltip_patch.js`, the shadowed `tooltips.html`,
and `subscriptions.wot_plus_ends_on()` — recoverable from git history.

## Testing without a subscription

`WotPlusController.setWotPlusStateDev(state)` is purely client-side: it sets `_state`,
resets the platform fetch cache and fires the change events. Combined with poking
`_cache['tier']` / `_cache['expiry']` and firing `onDataChanged`, any tier/state
combination can be driven through the real presenter pipeline on an account that has never
bought the subscription. The other `*Dev` helpers on the controller issue account commands
that a retail server rejects.
