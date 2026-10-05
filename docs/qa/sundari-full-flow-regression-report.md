# SUNDARI — FULL FLOW REGRESSION REPORT

**Run date:** 2026-10-05 · **Scope:** backend API, executed against an isolated Django test database · **Application code changed during testing:** none
**Evidence:** [`docs/qa/evidence/qa-results.json`](evidence/qa-results.json) (all 622 checks with expected/actual) · [`qa-endpoints-exercised.json`](evidence/qa-endpoints-exercised.json) · test code in [`qa/`](../../qa/) (run with `python manage.py test qa`)

---

## 1. Executive summary

**Launch verdict: NOT READY — P0 BLOCKER** (details in §15).

| | |
|---|---|
| Flows tested | 21 (list in §4) |
| Checks executed | **622** — 537 passed · 50 failed · 3 blocked · 2 unverified · 30 observations |
| API routes | 163 defined · **158 reached** · **122 functionally exercised** (got a real answer, not just 401) · 608 distinct method+path combinations · 2,175 hostile JSON field mutations + 186 multipart + 980 query-parameter probes |
| Distinct defects found | **16** (1 P0 · 5 P1 · 7 P2 · 3 P3; two of these are *unverified* risks) — table in §12 |
| Existing suite before / after | 739 OK / 739 OK — **no regression** |

**The one thing that matters most:** any logged-in user (a plain customer) can read **any other user's access token**, including an admin's, through `GET /users/profile/get/?user_id=<id>`, and then act as that user. Everything else in the authorization design is solid (74 of 77 cross-user attempts were correctly refused) — this single endpoint defeats all of it. It was demonstrated end to end inside the test database: attacker → admin token → admin review queue and every help-center conversation.

**Next most serious (P1):** artists can book their own services (cashback/review farming); customers can cancel and be refunded while the service is already running; duplicate payment orders let a customer be charged 3,500 for a 2,000 booking; refunds are database-only (no money returns); and a first-booking race on slot allocation cannot be ruled out on PostgreSQL.

**What is genuinely good:** token forgery/expiry/type-confusion all rejected; KYC and bank data masked, encrypted and private; upload validation and path safety hold; the booking lifecycle with OTP/PIN single-use and lockouts works end to end; reschedule, chat, ticket and admin isolation hold; no field-level input crashes the API or leaks internals.

---

## 2. Environment

| | |
|---|---|
| Commit | `7d5ad358ec736494ac9c36f9fdc4273eb1c40064` (branch `main`, last commit "Updated the Multi-booking payment merge") |
| Working tree | 246 uncommitted entries at baseline (70 modified, 176 untracked) — **untouched**; one `git stash` entry present, untouched. Only addition during QA: the `qa/` test package and this report. `git status` diff vs baseline = `?? qa/` |
| Database | Django test database (SQLite, in-memory/ephemeral). The development `db.sqlite3` hash was identical before and after (`361f1c7d…`) |
| Python / Django | 3.12.6 / 6.0.4 |
| Files | Temp directories (`settings.TESTING` redirects `MEDIA_ROOT` and `PRIVATE_MEDIA_ROOT`) |
| External services | **None real.** Razorpay mocked (order create/fetch + signature); Firebase deliberately disabled by the app under test; FCM is a stub in the app; SMS is a `print()` stub; email/Google not exercised. Time travel via patched `timezone.now()` for the on-my-way window |
| Safety | No production data, no real payments/payouts, no real KYC, no destructive action on the working tree |
| Limits | SQLite cannot reproduce true concurrent writers; the frontend is unavailable; production web-server config unknown |

## 3. Baseline test results (before any testing)

`python manage.py test tests` → **Ran 739 tests — OK** (0 failures, 0 errors, 0 skipped). Warnings: 4 `ResourceWarning: unclosed file` messages (unclosed file handles during the test run; not failures). The log contains 794 `Firebase is disabled under the test runner` tracebacks — **expected and handled** (§10). **Pre-existing failures: none.** Everything reported below was found by this QA run, not inherited.

---

## 4. Full flow results

| Flow | Result | Evidence (checks) | Blocker | Notes |
|---|---|---|---|---|
| Registration, OTP, login, tokens, forgot/reset password | **FAIL** | 45 pass / 2 fail / 1 blocked / 0 unverified | Q-10, Q-11 | Token forgery, expiry, type confusion, single-session, brute-force lockout all hold. Inactive users still receive a (useless) token; weak passwords accepted. |
| Authorization / cross-user isolation (IDOR matrix) | **FAIL** | 75 pass / 3 fail / 0 blocked / 0 unverified | **Q-01 (P0)** | 74 cross-actor attempts across ~45 resources refused. **One catastrophic exception: user profile endpoint.** |
| Account takeover chain (security proof) | **FAIL** | 3 pass / 3 fail / 0 blocked / 0 unverified | **Q-01 (P0)** | Plain customer obtains an admin token and uses admin endpoints. |
| Artist profile, photos, specialities, persistence across re-login, mass assignment | **PASS** | 9 pass / 0 fail / 0 blocked / 0 unverified | - | All registration fields, photos and work samples survive logout/login; protected fields cannot be set by the client. |
| Portfolio, packages, add-ons, upload handling | **FAIL** | 24 pass / 1 fail / 0 blocked / 0 unverified | Q-14 | CRUD, ordering, extras, booking snapshot integrity hold. Deleted portfolio files stay on disk. |
| File upload security | **PARTIAL** | 23 pass / 0 fail / 0 blocked / 1 unverified | Q-16 (unverified) | Type/size/content validation, safe naming, private KYC storage verified. Production media serving unverified. |
| KYC (4 ID types, validation, privacy) | **PASS** | 34 pass / 0 fail / 0 blocked / 0 unverified | - | Types distinguished in DB; numbers masked/encrypted; no leakage. |
| Bank / payout account | **FAIL** | 12 pass / 1 fail / 0 blocked / 0 unverified | Q-12 | Stored encrypted and masked; account number accepts letters; no payout provider exists. |
| Artist review / approval state machine | **FAIL** | 24 pass / 1 fail / 0 blocked / 0 unverified | Q-13 | pending > submitted > rejected/approved > resubmit works; approval needs verified KYC; repeat approvals write duplicate feedback. |
| Booking creation, availability, guards | **FAIL** | 46 pass / 1 fail / 0 blocked / 0 unverified | **Q-02 (P1)** | Blocked dates, hours, overlap, service area, ownership, price tampering all enforced. **Artists can book themselves.** |
| Booking lifecycle end-to-end (accept > on-my-way > arrived > PINs > complete > review) | **PASS** | 46 pass / 0 fail / 0 blocked / 0 unverified | - | Full happy path with time travel passes; OTP/PIN single-use, lockouts, cashback exactly once. |
| Booking state machine / invalid transitions | **FAIL** | 34 pass / 1 fail / 0 blocked / 0 unverified | **Q-03 (P1)** | 35 transitions tested; **customer can cancel (and be refunded) mid-service.** |
| Reschedule | **PASS** | 16 pass / 0 fail / 0 blocked / 0 unverified | - | Request/accept/reject/expiry/stale-slot/unauthorized all correct. |
| Concurrency (double booking race) | **PARTIAL** | 0 pass / 0 fail / 0 blocked / 1 unverified | Q-06 (unverified, P1) | Not executable on SQLite; code-analysis risk recorded. |
| Payments & financial logic | **FAIL** | 17 pass / 2 fail / 1 blocked / 0 unverified | **Q-04, Q-05 (P1)** | Arithmetic and gateway re-verification correct; **duplicate orders can overpay**; refund is a stub; earnings/payouts not implemented (owner-deferred). |
| Customer flow (profile, addresses) | **PASS** | 6 pass / 0 fail / 0 blocked / 0 unverified | - | Address limits/default/isolation correct; contact change needs OTP. |
| Notifications & Firebase | **PARTIAL** | 4 pass / 0 fail / 1 blocked / 0 unverified | External (blocked) | In-app notifications correct; FCM/Firestore blocked (credentials). |
| Chat | **PASS** | 16 pass / 0 fail / 0 blocked / 0 unverified | - | Participant-only; length/empty rules; outsider blocked. |
| Admin | **PASS** | 2 pass / 0 fail / 0 blocked / 0 unverified | Q-01 | All admin routes reject customer/artist/anonymous (but see Q-01: a leaked admin token defeats this). |
| Validation / malformed input (2,361 hostile body requests + 980 query probes) | **FAIL** | 128 pass / 32 fail / 0 blocked / 0 unverified | Q-07 (P2) | No crashes or leaks from field-level input; non-object JSON bodies return 500 on 31 endpoints. |
| Database integrity & transactions | **FAIL** | 14 pass / 2 fail / 0 blocked / 0 unverified | Q-08, Q-15 | FK/cascade/rollback correct; notification failure after commit gives a false failure; failed KYC upload leaves an orphan file. |
| Logs & error audit | **FAIL** | 5 pass / 1 fail / 0 blocked / 0 unverified | Q-09 | No tokens/passwords/ID numbers in logs; OTP codes are printed by the SMS stub. |

---

## 5. API results (by endpoint group)

Legend: ✔ verified correct · ✖ defect · – not applicable · ◐ partly (see note). "Regression" = existing suite unaffected (all ✔).

| Endpoint group | Methods | Flow | Result | Validation | Auth | Persistence | Logic | Regression |
|---|---|---|---|---|---|---|---|---|
| `/auth/register,login,phone-otp/*,token/refresh,forgot-password,reset-password` | POST | Auth | PASS* | ◐ weak pwd (Q-11) | ✔ | ✔ | ◐ inactive token (Q-10) | ✔ |
| `/auth/email-otp/*`, `/auth/google/` | POST | Auth | UNVERIFIED | ✔ (fuzz) | – | – | – (needs Brevo / Google token) | ✔ |
| `/users/profile/get/` | GET | Profile | **FAIL (P0)** | ✔ | ✖ any user, any `user_id`; returns tokens | – | ✖ | ✔ |
| `/users/profile/update/`, `/users/contact/change/*` | PUT/POST | Profile | PASS | ✔ | ✔ | ✔ | ✔ OTP-verified contact change | ✔ |
| `/users/address/*` | CRUD | Customer | PASS | ✔ | ✔ | ✔ | ✔ limit 5, single default | ✔ |
| `/artists/profile/*` (get, update, photos, specialities, switch, share link) | GET/PUT/DELETE | Profile | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/artists/portfolio/*` | CRUD + reorder | Content | PASS* | ✔ | ✔ | ✔ | ◐ file orphaned on delete (Q-14) | ✔ |
| `/artists/packages/*`, `/artists/addons/*`, `/artists/service_areas/*` | CRUD | Content | PASS | ✔ | ✔ | ✔ | ✔ snapshots protect bookings | ✔ |
| `/artists/availability/*`, `/artists/services/*`, `/artists/locations/*` | CRUD | Content | PASS | ✔ | ✔ own-scoped | ✔ | ✔ | ✔ |
| `/artists/documents/*` (KYC) | POST/GET/DELETE | KYC | PASS | ✔ 4 ID types | ✔ | ✔ encrypted, 1 per artist | ✔ | ✔ |
| `/artists/payout_account/*` | PUT/GET | Bank | PASS* | ◐ letters accepted (Q-12) | ✔ | ✔ encrypted, masked | ◐ no verify path | ✔ |
| `/artists/onboarding/*`, `/artists/review/feedback`, `/admin-panel/artists/*` | GET/POST/PUT | Approval | PASS* | ✔ | ✔ | ✔ | ◐ duplicate feedback (Q-13) | ✔ |
| `/admin-panel/brands/*`, `/artists/brands/*`, `/core/brands` | CRUD | Admin/Content | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/customers/artists/search,get,availability` | GET | Discovery | PASS | ✔ | ✔ | ✔ | ✔ buffers/blocked ranges | ✔ |
| `/customers/bookings/create/` | POST | Booking | **FAIL (P1)** | ✔ | ◐ no role check | ✔ | ✖ self-booking (Q-02) | ✔ |
| `/customers/bookings/get,get_all,start_pin,completion_pin` | GET | Booking | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/customers/bookings/cancel/` | PUT | State machine | **FAIL (P1)** | ✔ | ✔ | ✔ | ✖ cancels in-progress (Q-03) | ✔ |
| `/artists/bookings/*` (accept, on-my-way, arrived, PIN verify) | GET/PUT | Lifecycle | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/artists/bookings/reschedule/*`, `/customers/bookings/reschedule/*` | POST/PUT/GET | Reschedule | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/customers/payments/initiate,verify` | POST | Money | **FAIL (P1)** | ✔ | ✔ | ✔ | ✖ overpayment (Q-04) | ✔ |
| refund path (cancel of a paid booking) | – | Money | **FAIL (P1)** | – | – | ✔ status flips | ✖ no gateway call (Q-05) | ✔ |
| `/customers/reviews/*`, `/artists/reviews/*`, `/artists/customer_reviews/*` | CRUD | Booking | PASS | ✔ | ✔ | ✔ | ✔ once per booking | ✔ |
| `/chat/*`, `/help_center/*` (chat) | GET/POST | Chat | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/help_center/tickets/*`, `/help_center/admin/tickets/*` | CRUD | Support | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/notifications/*` | GET/PUT | Notify | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| `/artists/clients/*`, `/artists/insights/*`, `/public/artists/get`, `/core/pages/get` | GET/PUT | Misc | PASS | ✔ | ✔ | ✔ | ✔ | ✔ |
| **JSON endpoints behind `SerializerValidations` (31 of the 40 probed)** | POST/PUT | Validation | **FAIL (P2)** | ✖ non-object body → 500 (Q-07) | ✔ | – | – | ✔ |
| `/customers/wallet/*` | GET | Wallet | NOT FUNCTIONALLY EXERCISED here | – | ✔ (401 sweep) | – | – (65 existing unit tests) | ✔ |

The full list of 608 method+path combinations and the HTTP statuses observed is in `qa-endpoints-exercised.json`. **Not reached by this QA run:** `/auth/email-otp/*`, `/core/pages/get/`, `/public/artists/get/`, the admin chat HTML page (the last three are covered by the project's unit tests).

---

## 6. Business-logic findings

| ID | Sev | Finding |
|---|---|---|
| **Q-02** | P1 | An artist can create a booking for their own package (HTTP 201). Completing it pays cashback coins to themselves and allows a self-review that inflates their public rating. |
| **Q-03** | P1 | A customer can cancel a booking that is `in_progress` and the payment is marked refunded. `cancel_extract` accepts every "active" status, which includes `in_progress`. |
| **Q-04** | P1 | A booking can be overpaid: with a 2,000 total, an advance of 500 plus two separately initiated 1,500 balance orders — all verified — settled **3,500**. |
| **Q-05** | P1 | Refund is a stub. Cancelling a paid booking flips `Payment.status` to `refunded` but the gateway refund API is never called (0 calls observed). Customers are shown "refunded" and get no money back. |
| Q-13 | P2 | `approve` is idempotent for the status but not for its side effects: each repeat call appends another "approved" feedback row and sends another notification. |
| — | info | Earnings, payouts, adjustments and payout history **do not exist** (owner deferred). Gross/fee/net per payment are stored (`Payment.commission_amount`, `artist_payout_amount`) and arithmetic was verified over six price/rate combinations (sum exact, 2 dp, within one paisa of exact; banker's rounding), but there is no ledger, no paid-out/pending concept and no defined treatment of refunded/cancelled bookings for earnings. Not claimed as working. |

## 7. Security findings

| ID | Sev | Finding | Impact |
|---|---|---|---|
| **Q-01** | **P0** | `GET /users/profile/get/?user_id=X` returns any user's profile including **`access_token`**, `fcmToken`, phone and email, to any authenticated user. Demonstrated: customer → admin token → `GET /admin-panel/artists/review_queue/get_all/` = 200 and `GET /help_center/admin/conversations/get_all/` = 200; a customer's token also accepted as that customer. Own-profile responses also echo the bearer token (P1). | Full account takeover of every user including admins; makes every other authorization control moot |
| Q-10 | P2 | Login issues a token for an `is_active=False` user. (The token is rejected on use, so impact is low.) | Inconsistent account-state handling |
| Q-11 | P3 | Only `min_length=8`; `12345678` accepted | Weak passwords |
| Q-09 | P2 | `send_otp_sms` prints the OTP and phone number to stdout (52 lines in the run) | OTPs in server logs once deployed |
| Q-16 | P2 (unverified) | Whether public media (profile/portfolio photos) is reachable in production depends on web-server config not in the repo; Django serves it only when `DEBUG` | Unknown exposure |
| — | info | OTP request for an unregistered number returns 404 vs 200 (account enumeration, P3). No logout endpoint exists. Admin accounts can only be created outside the API (good). The JWT signing key is the repo default unless `SECRET_KEY` is set in the environment (the stored-token check prevents forging; see §13) |

Verified safe (examples): token forgery, `alg=none`, wrong key, expired, refresh-as-access and access-as-refresh all rejected; 74 cross-user attempts refused for portfolio, packages, add-ons, service areas, KYC (get/delete/**download**), bank, schedule/blocks, bookings (every artist/customer action), reschedule, reviews, client notes, tickets and attachments, notifications, chat, help-center chat, addresses; mass assignment of commission, approval, rating, slug, role, active flag ignored; no KYC/bank field names in any public response; KYC files stored outside `MEDIA_ROOT` with no URL; admin routes (×4 methods) reject customer, artist and anonymous.

## 8. Database findings

| ID | Sev | Finding |
|---|---|---|
| Q-08 | P2 | Notification/OTP delivery after commit is unguarded in `create_booking`: if it raises, the booking **is stored** but the API returns 400; a retry then gets "slot already booked". |
| Q-15 | P3 | A KYC upload that fails after the file is written leaves an orphan identity file in private storage (rollback removes the row, not the file). |
| Q-14 | P3 | Deleting a portfolio item removes the row, not the media file. |
| Q-06 | P1 (unverified) | No database constraint prevents two bookings in one slot; the application lock (`select_for_update`) is taken on *existing* bookings only, so with no existing booking two simultaneous first requests can both pass on PostgreSQL. Needs a real concurrency test. |

Verified: foreign keys are enforced under real commit semantics (non-existent sub-category/location refused, nothing stored); deleting a package that has bookings is refused and keeps the booking; booking creation rolls back fully on OTP-issue or add-on-snapshot failure; artist registration is all-or-nothing; completion rolls back and keeps the PIN usable if the wallet credit fails; exactly one conversation per booking; snapshots protect bookings from later package/add-on/service-area edits.

## 9. Validation findings

2,175 hostile JSON field mutations (missing, null, empty, whitespace, 5,000-char, wrong types, 10^30, negative, SQL, HTML/script, path traversal, unicode, NUL, nested) across 37 JSON endpoints, 186 more across 3 multipart endpoints, plus 980 query-parameter probes (`page_num`, `limit`, `sort_by`, `filter_key=password/access_token`, SQL in `search_key`, bad dates) across 20 list endpoints: **zero 5xx, zero leaked traces/paths/SQL, zero secrets, all error bodies JSON.**

| ID | Sev | Finding |
|---|---|---|
| **Q-07** | P2 | A JSON body that is not an object (`[]`, `"text"`, `123`, `null`) returns **HTTP 500** on 31 endpoints. Root cause: `SerializerValidations._copy_request_data` returns `request_data.copy()` (a list) and the next line calls `.update()` on it. |
| Q-12 | P2 | `bank_account_number` is validated for length (6–30) only; letters are accepted (`ABCDEFGHIJ12` → 200). |
| — | P3 | Package `duration_minutes` has no upper bound (100000 accepted; such a package can never be booked). Deleting a package that has bookings returns a generic/internal-text message instead of "deactivate it instead". |

## 10. External integration findings

| Integration | Status | Evidence |
|---|---|---|
| **Firebase / Firestore** | **Verified handled** | The 794 test-log tracebacks are the app's own guard (`Firebase is disabled under the test runner`) caught by `except Exception: logger.exception("Failed to sync …")`. Booking creation, acceptance, cancellation and completion all succeeded with Firestore failing, so the implemented semantics are *business success + notification-sync failure*. Real Firestore sync: **BLOCKED — EXTERNAL DEPENDENCY.** |
| Notifications (in-app) | Verified | Rows are stored and marked read correctly. Push (FCM) is a stub that reports "not configured": **BLOCKED**. |
| Razorpay | **Mocked** | Order creation, signature verification, and the app's independent re-fetch of payment+order (captured/paid/amount) all behave correctly, including rejecting an uncaptured payment with a valid signature. **Refunds/payouts: BLOCKED** (and see Q-05). |
| SMS OTP | Stub (prints) | Q-09 |
| Email OTP (Brevo), Google login | **Not exercised** | Need credentials; covered only by the unit tests with mocks |
| File storage | Verified locally | Local disk; production storage/serving unverified |

## 11. Regression results

| | Baseline | After QA |
|---|---|---|
| `manage.py test tests` | 739 run, OK | 739 run, OK |
| New failures / changed behaviour | – | none |
| `git status` | 246 entries | identical plus untracked `qa/` |
| `db.sqlite3` | `361f1c7d6c15a6d6` | `361f1c7d6c15a6d6` (unchanged) |

---

## 12. Blocker list (P0 → P3)

| ID | Sev | Title | Flow |
|---|---|---|---|
| **Q-01** | **P0** | Profile endpoint exposes any user's access token (account takeover incl. admin) | Authorization |
| Q-02 | P1 | Artists can book their own services | Booking |
| Q-03 | P1 | Customer can cancel + be refunded while service is in progress | State machine |
| Q-04 | P1 | Duplicate payment orders allow overpayment (3,500 on a 2,000 booking) | Payments |
| Q-05 | P1 | Refund is a database flag only; no money returned | Payments (external) |
| Q-06 | P1 (unverified) | First-booking race / no DB constraint on slot | Concurrency |
| Q-07 | P2 | Non-object JSON body → HTTP 500 on 31 endpoints | Validation |
| Q-08 | P2 | Post-commit notification failure turns a stored booking into an error response | Integrity |
| Q-09 | P2 | OTP printed to logs | Logs |
| Q-10 | P2 | Inactive user is issued a token at login | Auth |
| Q-12 | P2 | Bank account number accepts letters | Bank |
| Q-13 | P2 | Repeat approval duplicates feedback + notification | Approval |
| Q-16 | P2 (unverified) | Production exposure of public media unknown | Uploads |
| Q-11 | P3 | Weak passwords accepted | Auth |
| Q-14 | P3 | Portfolio delete leaves the file on disk | Content |
| Q-15 | P3 | Failed KYC upload leaves an orphan file | Integrity |

*Deferred by the owner (not defects):* earnings, payouts, payout-account verification — launch-scope items under the original requirements (B-06).

---

## 13. Root-cause analysis

**Q-01 — token leak (P0).** Three independent weaknesses combine:
1. `users/views/user_profile.py:22-28` — `get_extract` loads `User.get(user_id=params.profile_user_id)` where the id comes straight from the query string. There is no check that it equals `request.user.user_id` (or that the caller is an admin).
2. `authentication/models.py:97` — `User.get()` selects `access_token` (and `fcm_token`) because the JWT authenticator uses the same helper.
3. `users/utils.py:66-78` — `UsersUtils.mapper` renames only mapped columns and keeps the rest (`DataFrame.rename` is not a whitelist), so `access_token` is emitted under its raw name.
Because `JWTAuthentication` accepts any token equal to the stored `access_token`, a read of that column *is* a login. **Fix (smallest safe):** whitelist the output columns, never select the token fields for API responses, and restrict `user_id` to the caller (or admin / a public subset for artists). Regression test: customer B requests customer A and admin → 403/400 and the body never contains `access_token`/`fcmToken` for anyone.

**Q-04 — overpayment.** `payments/views/initiate_payment.py:65-71` computes `remaining_due` from *paid* payments only (`total_settled_for_booking`), so a second order for the same dues is allowed while the first is pending; `verify_payment._verify_solo` marks each paid without re-checking the booking total. **Fix:** refuse a new order when pending payments already cover the remaining due (or reuse the pending order), and re-check `settled + this payment <= total` inside the verification transaction (with a row lock on the booking); auto-refund any capture that exceeds it.

**Q-03 — cancel in progress.** `customers/views/booking.py:87` tests `status_name not in Booking.ACTIVE_STATUSES` and `ACTIVE_STATUSES = ['pending','confirmed','in_progress']` (`customers/models/booking.py:22`), a list designed for slot-blocking, reused as "cancellable". **Fix:** a dedicated customer-cancellable set (`pending`, `confirmed`, and a defined cutoff policy before arrival).

**Q-02 — self-booking.** `customers/views/create_booking.py` looks up the artist by id/approval only; there is no `artist.user_id != request.user` check and no role check. **Fix:** reject when the caller owns the artist profile (and decide whether artist-role accounts may book others at all).

**Q-05 — refund stub.** `payments/models.py:309-314` (`mark_refunded`): "the gateway refund API call … still need to be plugged in". External dependency; until fixed, cancellation of paid bookings must not report `refunded`.

**Q-06 — slot race.** `customers/slot_rules.py:49` locks only existing booking rows; with zero rows nothing is locked, and no unique/exclusion constraint exists. **Fix:** lock the artist's `ArtistProfile` row (or use an advisory lock) around the check-and-insert, and add a PostgreSQL exclusion constraint on (artist, date, time range). Then run a real two-thread test on PostgreSQL.

**Q-07 — non-object body.** `common/serializer_validations.py:24,31` — `request.data.copy()` on a list returns a list and `.update()` follows. **Fix:** reject non-mapping `request.data` with a 400 before copying.

**Q-08 — false failure.** `customers/views/create_booking.py:138-153` — notifications and the OTP send run after the atomic block and are not guarded. **Fix:** wrap delivery in try/except-and-log (the same pattern the Firestore sync already uses) or move it to a background task.

## 14. Recommended fix plan (no implementation yet)

| Group | Items | Notes |
|---|---|---|
| 1. Critical security | **Q-01** first, then Q-10, Q-09, Q-16 | Rotate every stored access/refresh token after the Q-01 fix (they may already be exposed); set `SECRET_KEY`/`FIELD_ENCRYPTION_KEY`; audit `role='admin'` users |
| 2. Core business logic | Q-02, Q-03, Q-13 | Small, local changes + tests |
| 3. Data integrity | Q-04, Q-06, Q-08, Q-15, Q-14 | Q-06 needs PostgreSQL; Q-04 needs a booking-level lock |
| 4. Launch features | Q-05 refunds (needs Razorpay), earnings/payouts/payout verification (owner-deferred B-06) | External dependency |
| 5. Validation | Q-07, Q-12, Q-11 | One shared guard fixes Q-07 everywhere |
| 6. External integrations | Real Firestore/FCM, Brevo, Google, SMS gateway, refund API | Re-run this QA package against sandbox credentials |
| 7. Post-launch | Account-enumeration messages, logout endpoint, `duration_minutes` bound, specific package-delete message | |

Each fix should ship with the matching case from `qa/` converted into a permanent regression test.

## 15. Final launch verdict

**NOT READY — P0 BLOCKER.**

Q-01 lets any customer become any user, including an admin, with one request. Until it is fixed and all issued tokens are rotated, no other result in this report matters for launch. After Q-01, the five P1 items (self-booking, in-service cancel-and-refund, overpayment, non-functional refunds, and the unproven slot race) are the next gate; earnings/payouts remain deferred scope and should be re-confirmed as post-launch.

*Truth statement:* the application is substantially sound — the QA matrix passed 537 of 622 checks and the stricter parts of the design (token handling, ownership checks, KYC privacy, lifecycle PINs, input handling) held up under attack — but it is not production-ready, and several things this report marks "unverified" or "blocked" (concurrency, real payment/refund, FCM/Firestore, email/Google login, production media serving) have **not** been shown to work.


---

## 16. Remediation status (2026-10-05, after the fixes)

Every defect above was fixed in the code, each with a permanent regression test in [`tests/test_security_regressions.py`](../../tests/test_security_regressions.py) (47 tests, class names carry the finding id). The whole QA package (`python manage.py test qa`) was then re-run against the fixed code.

| | Before fixes | After fixes |
|---|---|---|
| QA checks | 622 — 537 pass · **50 fail** · 3 blocked · 2 unverified | 617 — **585 pass · 0 fail** · 3 blocked · 2 unverified · 27 observations |
| Main test suite | 739 OK | **786 OK** (+47 regression tests; 1 old fixture password replaced) |
| Migrations | – | none needed (`makemigrations --check` clean) |

| ID | Sev | Status | What was changed |
|---|---|---|---|
| **Q-01** | P0 | **FIXED** | `users/views/user_profile.py`: another user gets only `userId/name/role`; admins also see contact details; nobody ever gets `access_token`, and `fcmToken` is owner-only. `users/utils.py`: the mapper is now a **whitelist** (unmapped columns can no longer leak). New command `revoke_all_sessions --yes` to rotate every stored token. |
| Q-02 | P1 | **FIXED** | `create_booking` refuses `artist.user_id == caller` |
| Q-03 | P1 | **FIXED** | Customer cancel is refused once the booking is `in_progress` or the artist has arrived |
| Q-04 | P1 | **FIXED** | `/initiate/` reuses an identical open order (double-tap) and refuses orders that together exceed the remaining due; verification takes a booking lock and refuses any capture that would overpay (payment marked failed with an "Overpayment … refund required" reason and logged); same guard for group orders |
| Q-05 | P1 | **FIXED, not testable against the real gateway** | `Payment.mark_refunded` now calls Razorpay `payment.refund` for the cash amount; a payment becomes `refunded` only after the gateway accepts it. On gateway failure it stays `paid` with the reason recorded and the customer is told it is being handled; `retry_refunds` command retries. Wallet-only payments need no gateway call. Verified with a mocked gateway only. |
| Q-06 | P1 | **MITIGATED, still needs a PostgreSQL concurrency test** | `validate_slot` locks the artist profile row before checking bookings. No DB exclusion constraint added. |
| Q-07 | P2 | **FIXED** | `SerializerValidations` returns 400 for non-object bodies |
| Q-08 | P2 | **FIXED** | `NotificationService.notify` is best-effort (own savepoint, logs and swallows errors); booking-OTP SMS/e-mail delivery after commit is guarded |
| Q-09 | P2 | **FIXED** | OTP is printed only when `DEBUG`; otherwise a masked log line without the code |
| Q-10 | P2 | **FIXED** | `_issue_token` refuses inactive accounts for every login path (password, OTP, Google, refresh) |
| Q-11 | P3 | **FIXED** | Registration and reset-password reject numeric-only and common passwords |
| Q-12 | P2 | **FIXED** | Bank account number must be 6–30 digits |
| Q-13 | P2 | **FIXED** | A repeat approval is a pure no-op (no extra feedback row or notification) |
| Q-14 | P3 | **FIXED** | Deleting a portfolio item deletes its media file |
| Q-15 | P3 | **FIXED** | A failed KYC upload removes the files it had already stored |
| Q-16 | P2 | **OPEN — deployment** | Cannot be fixed in code; confirm the production web server does not expose `artist_documents/`, `support_tickets/` (private storage is outside `MEDIA_ROOT`) and serves only the intended public media |

**Still open (not code defects):** earnings/payouts (owner-deferred); real-gateway refund and Firestore/FCM/Brevo/Google verification (credentials); production media exposure (Q-16); the two-connection booking race on PostgreSQL (Q-06); and — important — **the leaked tokens may already have been read before this fix**, so run `python manage.py revoke_all_sessions --yes` on every real environment right after deploying.
