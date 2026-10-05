# Sundari Artist App — Backend API Audit

- **Audit date:** 2026-10-03
- **Baseline requirements:** `SUNNDARI ARTIST APP - API LIST.pdf` (2 pages, text extracted with `pypdf` installed into a scratchpad only — not into the project venv or `requirements.txt`)
- **Audited tree:** `main` working tree **including** the 57 uncommitted changes (per decision: audit working tree).
- **Scope of this document:** audit only. **No application code, migration, or existing uncommitted change was modified.** The only file created in the repo is this report.
- **Not available:** frontend repository (all frontend-contract checks are **UNVERIFIED**), production environment, real SMS / Brevo / Google / Razorpay / Firebase credentials.

## 0. Evidence legend

| Tag | Meaning |
|---|---|
| **[CODE]** | Read from source; not executed |
| **[TEST]** | Existing automated test evidence (`manage.py test tests`) |
| **[PROBE]** | Executed by me against a **copy** of `db.sqlite3` with a throw-away `MEDIA_ROOT`, in the scratchpad |
| **[DOC]** | Stated in repo docs (`CHECKLIST.md`) — not independently verified |

Statuses used exactly as defined in the brief: VERIFIED WORKING, EXISTS — NEEDS ENHANCEMENT, EXISTS — BUG, PARTIALLY IMPLEMENTED, MISSING API, MISSING PERSISTENCE, FRONTEND INTEGRATION ISSUE, DATABASE/MODEL GAP, EXTERNAL DEPENDENCY BLOCKED, UNVERIFIED.

## 1. Executive summary

1. **P0 security defect (confirmed by probe): anyone can self-register as `admin`.** `POST /auth/register/` accepts `role=admin`; the new account immediately passes `AdminArtistReviewView._require_admin` and the help-center admin endpoints. This must be fixed before any KYC/onboarding flow goes live (S-01).
2. **KYC documents are not safe yet.** Uploads have no type/size validation (an `.html` file was accepted as `id_proof`), file names are predictable, and the `/media/` route serves them to unauthenticated callers whenever `DEBUG` is true (S-02, S-03). Admins also have no API to *view* or *verify* documents; `verification_status` is set to `pending` on creation and never changed (S-07).
3. **Much of Category B "onboarding" already exists in the working tree** (documents, payout account with masked number, onboarding status/submit, agreement acceptance, admin review queue/approve/reject). It is **not** the "Aadhaar-only" state the frontend describes — but it only supports `id_proof | address_proof | certification`, one file per document, no `id_type`, no back image.
4. **Genuinely missing (no model, no endpoint):** registration fields (display name, DOB, Instagram, profile type, specialities as a field, work samples), profile/cover photo, review-feedback history, earnings & payout history, package extras, add-ons, service areas/travel charges, rescheduling. Also **forgot/reset password does not exist** though the PDF lists it as "already working".
5. **Test suite:** 489 tests, `OK`. The 346 `Firebase is disabled under the test runner` tracebacks in the log are **handled, logged exceptions** (deliberate guard in `notifications/firebase_utils.py`), not failures.

---

## 2. Deliverable 1 — Repository and architecture summary

| Aspect | Finding | Evidence |
|---|---|---|
| Language / framework | Python 3.12, Django + Django REST Framework, drf-spectacular (Swagger at `/docs/`, `/redoc/`, schema `/api/schema/`) | `requirements.txt`, `sunndari/urls.py` |
| Database | SQLite (`db.sqlite3`) active; PostgreSQL block present but commented out | `sunndari/settings.py:106-121` |
| Async / realtime | Celery + Redis, Channels/Daphne, Firebase (Firestore sync of notifications & bookings) | `requirements.txt`, `notifications/firebase_utils.py`, `customers/firebase_utils.py` |
| Payments | Razorpay SDK in requirements; gateway **not wired for real** (`Payment.gateway*` nullable, "stub") | `payments/models.py`, `CHECKLIST.md` L280-290 [DOC] |
| Auth | Custom `JWTAuthentication` (HS256, `settings.SECRET_KEY`); token must **equal** `User.access_token` stored in DB (single active session) | `authentication/authentication.py` |
| Roles | `User.role ∈ {customer, artist, admin}`; there is **no DRF permission class per role** — every endpoint is `IsAuthenticated`, and role is enforced ad hoc (artist = "has an `ArtistProfile`", admin = `User.get()['role']=='admin'` inside the view) | `authentication/models.py:20-30`, `admin_panel/views/artist_review.py:_require_admin` |
| Layering (project convention) | `urls.py → controllers/*.py (@api_view + extend_schema + SerializerValidations) → views/*.py (business logic, @Common().exception_handler) → models/*.py (static methods returning dicts via .values())` ; request `serializers/` + `dataclasses/`; response serializers are Swagger-only/validation | e.g. `artists/controllers/document.py`, `artists/views/document.py` |
| Response format | `{status, message, data}`; lists `{data:[…], presentPage, totalPage}`; **camelCase** output via `ArtistsUtils.mapper` (pandas); **snake_case** input; `GET` params in query string; every domain error is an HTTP **400** | `common/common.py`, `common/utils.py` |
| File storage | Django `FileField` on local disk: `artist_documents/artist_<id>/<filename>`, `portfolios/artist_<id>/<filename>`; `MEDIA_URL='media/'`, `MEDIA_ROOT=BASE_DIR/media` (git-ignored); served by `static()` in `urls.py` **only if DEBUG** | `artists/models/document.py`, `portfolio.py`, `sunndari/urls.py`, `settings.py:138-139` |
| Money | `ArtistProfile.commission_rate` (default 10.00) → per-payment `Payment.commission_amount`, `Payment.artist_payout_amount` snapshotted at initiate time | `payments/views/initiate_payment.py:79-80`, `payments/models.py:138-139` |
| Admin | Django admin via `django-unfold` (all artist models registered with plain `ModelAdmin`); API admin panel = 3 routes (`/admin-panel/artists/{review_queue/get_all,approve,reject}/`); help-center admin chat page | `artists/admin.py`, `admin_panel/urls.py` |
| Tests | Django `TestCase`; 13 files; senders (`send_otp_sms`, `send_otp_email`, `verify_google_token`) are mocked; Firebase refused under `settings.TESTING` | `tests/` |
| Constraints | No staging/prod config in repo; `docs/` did not exist before this report; `CHECKLIST.md` lists unresolved infra decisions (SMS, payment gateway, FCM, cloud storage/CDN) | `CHECKLIST.md` |

### 2.1 The 57 uncommitted changes (what they actually are)

- **Modified (14):** `db.sqlite3`, `sunndari/constants.py` (3 new messages), `admin_panel/urls.py`, `artists/{admin,urls,utils}.py`, `artists/controllers/artist_profile.py` (+`accept_agreement`), `artists/dataclasses|serializers/.../update_profile.py` (+`base_address_id`), `artists/models/{__init__,artist_profile}.py` (+`terms_accepted_at`, `submitted_for_review_at`, `rejection_reason`, `base_address`, approve/reject/submit helpers), `artists/serializers/response/get/get_profile.py`, `artists/views/artist_profile.py`, `tests/test_artists.py` (+277 lines).
- **New:** artist `document`, `payout_account`, `onboarding` (controller/view/serializer/dataclass), admin `artist_review` module, migrations `0002`, `0003`, `tests/test_admin_panel.py`, `.env.example`, `firestore.rules`, two PDFs, a DB backup file.
- I read all of the above that are on a requirement path. `db.sqlite3` was **not** touched by me (mtime Sep 25 03:51, before this session).

---

## 3. Deliverable 2 — Complete API inventory

All routes below are `IsAuthenticated` unless stated. "Own" = scoped by `request.user` → `ArtistProfile`. Source: each `*/urls.py`.

### Auth (`/auth/`, public) — `authentication/urls.py`
`POST phone-otp/request/`, `POST phone-otp/verify/`, `POST email-otp/request/`, `POST email-otp/verify/`, `POST register/`, `POST login/`, `POST google/`, `POST token/refresh/`. **No forgot/reset-password route.**

### Users (`/users/`)
`GET|PUT profile/get|update/`, `POST address/create`, `PUT address/update`, `DELETE address/delete`, `GET address/get`, `GET address/get_all`. Model: `User`, `CustomerAddress`.

### Core master data (`/core/`)
`service-category`, `service-sub-category`, `location-type` (`get`, `get_all`); `booking-status`, `payment-status`, `approval-status` (`get_all`).

### Artist (`/artists/`) — all "own" unless noted
| Group | Routes | Model |
|---|---|---|
| Profile | `GET profile/get/` (**accepts `artist_id` → any artist**), `PUT profile/update/`, `PUT profile/agreement/accept/` | `ArtistProfile` |
| Services / locations | `services/{add,remove,get_all}`, `locations/{add,remove,get_all}` (get_all accepts `artist_id`) | `ArtistServiceOffering`, `ArtistLocationPreference` |
| Portfolio | `portfolio/{create,update,delete,get,get_all}` (get_all accepts `artist_id`) | `Portfolio` |
| Packages | `packages/{create,update,delete,get,get_all}` (get_all accepts `artist_id`) | `PricingPackage`, `PackageInclusion` |
| Availability | `availability/schedule/{set,remove,get_all}`, `availability/block/{add,remove,get_all}` | `ArtistAvailabilitySchedule`, `ArtistAvailabilityBlock` |
| Bookings | `bookings/{get,get_all,update_status,on_my_way,arrived}`, `bookings/start_pin/verify/`, `bookings/completion_pin/verify/` | `Booking` |
| **KYC** *(new, uncommitted)* | `documents/{create (multipart),delete,get,get_all}` | `ArtistDocument` |
| **Bank** *(new)* | `PUT payout_account/set/`, `GET payout_account/get/` (masked) | `ArtistPayoutAccount` |
| **Onboarding** *(new)* | `GET onboarding/status/`, `POST onboarding/submit/` | derived + `ArtistProfile` |

### Admin (`/admin-panel/`) *(new)* — admin role checked in view
`GET artists/review_queue/get_all/`, `PUT artists/approve/`, `PUT artists/reject/`.

### Customer (`/customers/`)
`artists/{search,get,availability}`, `bookings/{create,get,get_all,cancel}`, `bookings/{start_pin,completion_pin}/`, `reviews/{create,get,get_all}`; `payments/{payment_types,initiate,initiate_group,verify,get,get_all}`; `wallet/{eligible_tiers,get,transactions}`.

### Notifications / Chat / Help center
`notifications/{get,get_all,mark_read,mark_all_read}`; `chat/{conversation/get,messages/get_all,messages/create}`; `help_center/{conversation,messages}` (customer), `help_center/artist/{conversation,messages}`, `help_center/admin/{conversations,conversation,messages}` + `admin/chat/` page (**one conversation per user — not tickets**).

---

## 4. Deliverable 3 — Requirements-to-API audit matrix (all 17 columns)

Conventions: **Cat** = original PDF category (A already working, B pre-launch, C post-launch, D phone-only). **Contract** points to §7; **Tests** points to §9. Baseline priority = PDF category unless a documented dependency changes it (noted in "Launch impact").

### 4.1 Category A — "already working"

| ID | Cat | Feature | Required behavior | Existing endpoint | Impl. location | Model | Status | Evidence | Gap | Action | Contract | Persistence | Deps | Tests | Pri | Launch impact |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A-01 | A | Login / register / OTP (phone, email) / Google / forgot / reset password | Full account lifecycle | `POST /auth/{register,login,phone-otp/*,email-otp/*,google,token/refresh}/` | `authentication/{urls,views,controller}.py` | `User` | **PARTIALLY IMPLEMENTED** | [TEST] 64 auth tests pass with mocked senders; [CODE] no `forgot`/`reset` anywhere (grep); real SMS/Brevo/Google untested [DOC] CHECKLIST L73-75 | Forgot/reset password absent (OTP login is the only recovery path); **S-01 role escalation**; real providers unverified | Bug fix (S-01) + new API (forgot/reset, or confirm OTP-login is the intended recovery) | §7.0, Q-5 | `User.password` hash exists | SMS/Brevo creds | AUTH-* | **P0** (S-01) / P1 | Blocker |
| A-02 | A | Artist profile get/update | Own profile read/write | `GET /artists/profile/get/`, `PUT /artists/profile/update/` | `artists/views/artist_profile.py` | `ArtistProfile` | **EXISTS — BUG** | [TEST] `ArtistProfileGet/UpdateTest`; [PROBE] customer reads another artist's profile via `artist_id` and receives `commissionRate`, `baseAddressId`, `termsAcceptedAt`, `submittedForReviewAt`, `rejectionReason` | Over-exposure (S-06); profile lacks the B-03/B-04 fields | Bug fix + enhancement | §7.2-7.3 | — | — | PROF-* | P1 | Important |
| A-03 | A | Portfolio CRUD | Add/view/edit/delete, own only | `/artists/portfolio/{create,update,delete,get,get_all}/` | `artists/views/portfolio.py` | `Portfolio` | **VERIFIED WORKING** (CRUD + ownership) | [TEST] `PortfolioCreateTest`, `PortfolioGetUpdateDeleteTest` incl. cross-artist `400`; [CODE] 20-item cap | No file-type/size validation (S-03); `fileUrl` returns relative storage name, not a URL; no ordering (D-08) | Enhancement (validation) | §7.1 | — | — | PORT-* | P1 | Important |
| A-04 | A | Package CRUD | Add/view/edit/delete, own only | `/artists/packages/*` | `artists/views/pricing_package.py` | `PricingPackage`, `PackageInclusion` | **VERIFIED WORKING** | [TEST] `PricingPackageTest`; [CODE] ownership checks, "keep ≥1 active package" rule; `sub_category_id` not pre-validated (FK error would surface as generic 400 — not probed) | B-07 fields absent | None for A; see B-07 | — | — | — | PKG-* | P1 | No change |
| A-05 | A | Services, locations, weekly schedule, blocked dates | Own CRUD | `/artists/{services,locations,availability/*}/` | `artist_profile.py`, `availability.py` | `ArtistServiceOffering`, `ArtistLocationPreference`, `ArtistAvailabilitySchedule/Block` | **VERIFIED WORKING** | [TEST] `ArtistServiceOfferingTest`, `ArtistLocationPreferenceTest`, `AvailabilitySchedule/BlockTest` | Behavioural: adding/removing a service calls `reset_approval=True` → an *approved* artist silently drops to `pending` with `submitted_for_review_at=NULL` and is hidden from search until they resubmit (`artist_profile.py:update`, `views/artist_profile.py`) — intended? (Q-4) | Decision needed | — | — | — | — | P1 | Important |
| A-06 | A | Customer profile & addresses | CRUD | `/users/profile/*`, `/users/address/*` | `users/` | `User`, `CustomerAddress` | **VERIFIED WORKING** | [TEST] 34 tests in `test_users.py`; [CODE] `UserProfileUpdateSerializer` lets name/email/phone change with no re-verification (not probed) | Possible unverified contact change (S-14, UNVERIFIED) | None / review | — | — | — | USR-* | P3 | No change |
| A-07 | A | Core lists | Categories, sub-categories, statuses, location types | `/core/*` | `core/` | `ServiceCategory`, `ServiceSubCategory`, `LocationType`, `*Status` | **VERIFIED WORKING** | [TEST] 42 tests; seeds ran in test log | `suspended` approval status has no setter anywhere (S-07) | None | — | — | — | — | — | No change |
| A-08 | A | Booking workflow: list, details, accept/decline, on-my-way, arrived, start code, finish code | Artist-side lifecycle | `/artists/bookings/{get,get_all,update_status,on_my_way,arrived}/`, `start_pin/verify/`, `completion_pin/verify/` | `artists/views/booking.py` | `Booking`, `Payment` | **VERIFIED WORKING** (functional); two residual risks | [CODE] full trace: ownership by `artist_id`; `ARTIST_TRANSITIONS`; payment-settled gate before `confirmed`; IST-aware deadlines; OTP/PIN lockout (5/30 min) and single-use nulling; completion under `select_for_update`; [TEST] `test_booking_lifecycle.py` (30 refs), `test_customers.py` (109 refs) | (1) Artist cancel marks `Payment` **refunded in DB only** — "gateway refund API call still need to be plugged in" (`payments/models.py:mark_refunded`) → EXTERNAL DEPENDENCY BLOCKED; (2) `update_status_extract` & `arrived` read without row lock → accept-vs-cancel race **UNVERIFIED** (S-12) | None for lifecycle; track (1),(2) | — | — | gateway | BKG-* | P1 | Important (refund) |
| A-09 | A | Notifications, chat, help center | Existing modules | `/notifications/*`, `/chat/*`, `/help_center/*` | respective apps | `Notification`, `Conversation`, `Message` | **VERIFIED WORKING** (backend); Firestore push **EXTERNAL DEPENDENCY BLOCKED** | [TEST] 15 + 17 + 29 tests; Firebase calls refused under test, wrapped by `try/except … logger.exception` (see §8.2); real FCM/Firestore untested [DOC] CHECKLIST L312-313 | Help center = single chat thread per user, not tickets (C-06) | None | — | — | FCM creds | — | — | No change |

### 4.2 Category B — missing / incomplete, needed before launch

| ID | Cat | Feature | Required behavior | Existing endpoint | Impl. location | Model | Status | Evidence | Gap | Action | Contract | Persistence | Deps | Tests | Pri | Launch impact |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-01 | B | KYC + bank details live | Both endpoints exist & work | `/artists/documents/*`; `PUT|GET /artists/payout_account/*` | `artists/{controllers,views}/{document,payout_account}.py` | `ArtistDocument`, `ArtistPayoutAccount` | **EXISTS — NEEDS ENHANCEMENT** (functional, with security gaps) | [PROBE] upload `201`, get `200`, cross-artist get/delete `400` (no IDOR), customer `400 Artist not found`; payout set `200`, GET masked; [TEST] `ArtistDocumentTest`, `ArtistPayoutAccountTest`; [PROBE] DB holds bank number **plaintext** | S-02, S-03, S-07, S-08; no admin view/verify path | Enhancement + security fixes | §7.1 | exists | S-01 first | KYC-*, PAY-* | P1 (**P0 security prerequisites**) | Blocker |
| B-02 | B | Multiple ID types | `id_type` ∈ aadhaar/voter_id/passport/driving_licence, `id_number`, front + back image | `POST /artists/documents/create/` | same | `ArtistDocument.document_type ∈ {id_proof,address_proof,certification}` | **DATABASE/MODEL GAP** | [CODE] `CreateDocumentSerializer`, `ArtistDocument` (single `file`, free-text `document_number`) | No `id_type`, no `back_file`, no per-type number validation. (PDF says "only Aadhaar fields exist" — repo has none; neither state meets the need) | Schema change + API enhancement | §7.1 | + `id_type`, `back_file` | B-01 | KYC-* | P1 | Blocker |
| B-03 | B | Registration fields | full name, display name, DOB, Instagram, address, profile type, experience, specialities, ≤5 work photos | `PUT /artists/profile/update/` (only bio, years_experience, city, service_radius_km, base_address_id) ; `PUT /users/profile/update/` (name) | `ArtistProfile`, `User.name` | partially | **PARTIALLY IMPLEMENTED** / **DATABASE/MODEL GAP** | [CODE] model fields listed in §6. Existing equivalents: full name→`User.name`; address→`base_address` (FK `CustomerAddress`); experience→`years_experience`; specialities≈`ArtistServiceOffering` (**do not duplicate** — Q-2). Missing: display_name, date_of_birth, instagram_url, profile_type, work samples | See §6 | Schema change + API | §7.2 | + 4 columns; work-sample storage | Portfolio reuse decision (Q-3) | PROF-* | P1 | Blocker |
| B-04 | B | Profile & cover photo | Upload; URLs in profile get | none | — | none (no image field on `ArtistProfile` or `User`) | **MISSING API** + **DATABASE/MODEL GAP** | [CODE] grep for `profile_photo|cover` → no source hits | Everything | New API + schema | §7.3 | + 2 `ImageField`s | storage decision (CHECKLIST L262 [DOC]) | PHOTO-* | P1 | Blocker |
| B-05 | B | Artist page review | Submit, status (submitted/changes_required/approved), admin feedback list, resubmit | `POST onboarding/submit/`, `GET onboarding/status/`, admin `review_queue/approve/reject` | `views/onboarding.py`, `admin_panel/views/artist_review.py` | `ArtistProfile.approval_status`, `submitted_for_review_at`, `rejection_reason` | **PARTIALLY IMPLEMENTED** | [TEST] `ArtistOnboardingStatusTest`, `test_admin_panel.py` (10 tests) incl. resubmission after rejection & double-approve idempotency; [CODE] states computed: `not_started|in_progress|submitted|approved|rejected|suspended` | Vocabulary differs (`rejected` vs required `changes_required`); only **one** latest `rejection_reason` — no feedback **list**/history; admin queue shows no documents/photos; `suspended` can be overridden (S-07); onboarding only requires an `id_proof` doc | Enhancement + new model | §7.4 | + `ArtistReviewFeedback` | S-01, B-02 | REV-* | P1 | Blocker |
| B-06 | B | Earnings & payouts | summary (gross, platform fee, adjustments, net, paid out, pending) + payout history | none | — | `Payment.{amount,commission_amount,artist_payout_amount,status}` is a usable **source of truth** for gross/fee/net; no payout, no adjustment model | **MISSING API** + **DATABASE/MODEL GAP**; actual money movement **EXTERNAL DEPENDENCY BLOCKED** | [CODE] `payments/models.py`, `initiate_payment.py:79-80`; no payout provider configured ([DOC] CHECKLIST L280) | Need payout ledger + adjustments ledger; definition of "earned" (completed vs paid); coin-redemption interplay (group-payment comment: "amount stays the pre-redemption figure") must be reconciled first | New API + schema (ledger only, no provider) | §7.5 | + `ArtistPayout`, `ArtistEarningAdjustment` | Payment verification, Q-6 | EARN-* | P1 | Important (history can ship empty) |
| B-07 | B | Package extras | category, makeup type, brands, product details, service photo | `packages/*` | `pricing_package.py` | `PricingPackage` | **PARTIALLY IMPLEMENTED** / **DATABASE/MODEL GAP** | [CODE] `sub_category` FK exists → *category* is derivable via `sub_category.category` (no new field). Missing: makeup_type, brands, product_details, photo | See §6 | Schema + API enhancement | §7.6 | + 3-4 columns | C-03 brands (Q-7) | PKG-* | P1 | Blocker |
| B-08 | B | Add-ons | CRUD + linked packages | none | — | none | **MISSING API** + **DATABASE/MODEL GAP** | grep `add_?on` → no hits | Everything; booking must later snapshot chosen add-ons (C-07) | New API + schema | §7.7 | + `PackageAddOn` (+ link) | B-07 | ADDON-* | P1 | Blocker |
| B-09 | B | Service areas & travel charge | cities, free/charge, amount, per-visit/per-km | none (only `city`, `service_radius_km` scalar) | — | `ArtistProfile.city/service_radius_km` | **MISSING API** + **DATABASE/MODEL GAP** | [CODE] `create_booking.py:100` sets `total_amount=package.price` — **travel is not priced anywhere** | New model; quoting must be server-side; changes touch booking total & `Payment.amount` | New API + schema | §7.8 | + `ArtistServiceArea` | booking snapshot (C-07), payments | AREA-* | P1 | Blocker |
| B-10 | B | Reschedule | request new date/time; customer confirm/reject | none | — | `Booking.{booking_date,start_time,end_time}` | **MISSING API** + **DATABASE/MODEL GAP** | [CODE] no `reschedul` hits. Note `booking_otp_expiry`/PIN expiries are computed from the *original* date (`Booking.generate_booking_otp`, `confirm_arrival`) and must be refreshed on accept | New model & workflow | New API + schema | §7.9 | + `BookingReschedule` | availability checker (`has_overlap`), Firebase sync, notifications | RESCH-* | P1 | Blocker |

### 4.3 Category C — post-launch

| ID | Cat | Feature | Required behavior | Existing endpoint | Impl. location | Model | Status | Evidence | Gap | Action | Contract | Persistence | Deps | Tests | Pri | Launch impact |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C-01 | C | Reviews & ratings (list + artist reply) | list reviews, reply | `/customers/reviews/{create,get,get_all}/` (customer-only create) | `customers/views/review.py` | `Review` (OneToOne booking) | **PARTIALLY IMPLEMENTED** | [CODE] create requires own, `completed`, not already reviewed; `ArtistProfile.record_review` under `select_for_update`; `get_all` accepts `artist_id` | No artist-facing route, no `reply` field. `Review.get` readable by any authenticated user (probably intended) | Enhancement | §7.10 | + `reply`, `replied_at` | — | REVW-* | P2 | Post-launch |
| C-02 | C | Business insights | bookings, earnings, repeat clients, top services, profile views | none | — | derivable from `Booking`/`Payment`; profile views need counter | **MISSING API** | grep `insight|view_count` → none | All | New API | §7.10 | + counter | B-06, C-11 | INS-* | P2 | Post-launch |
| C-03 | C | Brands list + request | admin-managed list, artist request | none | — | none | **MISSING API** + **DATABASE/MODEL GAP** | grep `brand` → none | All | New API + schema | §7.10 | + `Brand`, `BrandRequest` | B-07 | BRAND-* | P2 | Post-launch (B-07 may need a stopgap) |
| C-04 | C | Partner agreement (Terms + Privacy, with date) | store acceptance + date | `PUT /artists/profile/agreement/accept/` | `views/artist_profile.py:accept_agreement_extract` | `ArtistProfile.terms_accepted_at` | **EXISTS — NEEDS ENHANCEMENT** | [TEST] `ArtistAgreementTest`; [CODE] single timestamp, no version, no separate Privacy; it's also an **onboarding submit prerequisite** | No document version/IP/history; **dependency → effectively pre-launch** since `onboarding/submit` blocks without it | Enhancement | §7.10 | + `agreement_version` (optional) | — | AGR-* | P2 (**exists; version optional**) | Done for launch |
| C-05 | C | Accepting-bookings switch | persisted on/off | none | — | none | **MISSING API** + **DATABASE/MODEL GAP** | grep `accepting` → none; availability blocks exist but are date-based | New flag + enforcement in `customers/search` and `create_booking` | New API + schema | §7.10 | + `ArtistProfile.is_accepting_bookings` | — | SW-* | P2 | Post-launch |
| C-06 | C | Help-center tickets | many tickets, status, booking id, issue type, photos | `/help_center/artist/*` (single conversation) | `help_center/` | `Conversation`, `Message` | **PARTIALLY IMPLEMENTED** | [CODE] one running conversation per user; no ticket/issue-type/booking/attachment model | New model | New API + schema | §7.10 | + `SupportTicket`, `…Attachment` | upload validation | TKT-* | P2 | Post-launch |
| C-07 | C | Booking money & travel fields | platform fee, net, travel-before, return buffer, add-ons chosen | `Booking` has `total_amount` only; fee/net live on `Payment` | `customers/models/booking.py`, `payments/models.py` | `Booking`, `Payment` | **DATABASE/MODEL GAP** | [CODE] fields listed; `VALUES_FIELDS` has none | Snapshot fields + `BookingAddOn`; **blocks B-08/B-09 correctness** | Schema (additive) | §7.7-7.8 | + snapshot columns | **B-08, B-09** | BKG-SNAP-* | P2 → **P1 for the snapshot part** (documented dependency: add-on/travel pricing cannot be honoured at booking time without it) | Important |
| C-08 | C | Public profile link | shareable URL | `GET /customers/artists/get/` (approved only) | `customers/views/get_artist_detail.py` | — | **PARTIALLY IMPLEMENTED** | [CODE] approved-only filter at line 26; no slug / unauthenticated public route | Public slug + no-auth read | New API | §7.10 | + `public_slug` | privacy review | PUB-* | P3 | Post-launch |
| C-09 | C | Artist reviews a customer | rate after completed booking | none | — | none | **MISSING API** + **DATABASE/MODEL GAP** | grep → none | New `CustomerReview` (separate from `Review`) | New API + schema | §7.10 | + model | — | CREV-* | P2 | Post-launch |
| C-10 | C | Terms / Privacy / Contact | links or content | none | — | none | **MISSING API** | no route | Could be static URLs in app config | Config / tiny API | §7.10 | — | legal copy | — | P3 | Post-launch |
| C-11 | C | Small ones | view counter, portfolio reorder, My Clients + notes, Marketing Studio, service-styles list | none | — | none | **MISSING API** | grep → none | All five | New APIs | §7.10 | + several | — | MISC-* | P3 | Post-launch |

### 4.4 Category D — phone-only data

| ID | Cat | Item | Backend model today | Endpoint today | Status | Evidence | Gap / action | Pri |
|---|---|---|---|---|---|---|---|---|
| D-01 | D | Date of birth | none | none | **MISSING PERSISTENCE** / DB gap | no `date_of_birth` in repo | `ArtistProfile.date_of_birth` + profile update (§7.2) | P1 |
| D-02 | D | Display name | none (`User.name` = full name only) | `PUT /users/profile/update/` sets `name` | **MISSING PERSISTENCE** | model review | `ArtistProfile.display_name` (§7.2) | P1 |
| D-03 | D | Specialities | `ArtistServiceOffering` (sub-category per artist) is the likely equivalent | `/artists/services/*` | **UNVERIFIED** (is it the same concept?) | Q-2 | Reuse if yes; avoid duplicate field | P1 |
| D-04 | D | Address | `ArtistProfile.base_address` → `CustomerAddress` | `profile/update` (`base_address_id`), `/users/address/*` | **VERIFIED WORKING** (backend, working tree) [TEST] `ArtistProfileUpdateTest`; ownership of address enforced in `update_extract` | Frontend must call it — **FRONTEND INTEGRATION: UNVERIFIED** | P1 |
| D-05 | D | Profile type | none | none | **MISSING PERSISTENCE** | — | `profile_type` choices freelance/studio (§7.2) | P1 |
| D-06 | D | Profile / cover photo | none | none | **MISSING PERSISTENCE** | B-04 | §7.3 | P1 |
| D-07 | D | Service (package) photos | none | none | **MISSING PERSISTENCE** | B-07 | §7.6 | P1 |
| D-08 | D | Add-ons / service areas / travel charges | none | none | **MISSING PERSISTENCE** | B-08, B-09 | §7.7-7.8 | P1 |
| D-09 | D | Portfolio order | `Portfolio` has no order column | none | **MISSING PERSISTENCE** | model review | `sort_order` + reorder endpoint (C-11) | P3 |
| D-10 | D | Agreement accepted | `terms_accepted_at` | `PUT profile/agreement/accept/` | **EXISTS — NEEDS ENHANCEMENT**; app may still keep local flag — FRONTEND: UNVERIFIED | C-04 | Frontend to call it; server value is source of truth | P1 (needed for submit) |
| D-11 | D | Reviews written about customers | none | none | **MISSING PERSISTENCE** | C-09 | — | P2 |

> **Reinstall caveat (non-negotiable per brief):** no server copy of D-01/02/05/06/07/08/09/11 has ever existed, so **historical on-device values cannot be recovered**. They can only be re-captured when the app next syncs them through the new endpoints. No backfill is claimed.

---

## 5. Deliverable 4 — Confirmed gap report

### 5.1 Missing endpoints (confirmed by repo-wide search of all 14 apps)
B-04 photos · B-06 earnings/payouts · B-08 add-ons · B-09 service areas · B-10 reschedule · forgot/reset password (A-01) · C-02, C-03, C-05, C-06 (tickets), C-09, C-10, C-11 · artist reply to reviews (C-01).

### 5.2 Existing endpoints needing enhancement
`documents/*` (B-02, S-03) · `profile/update` & `profile/get` (B-03, S-06) · `packages/*` (B-07) · `onboarding/*` + admin review (B-05) · `agreement/accept` (C-04) · `payout_account/*` (S-08) · `customers/bookings/create` (travel/add-on pricing, C-07).

### 5.3 Reproducible bugs
- **S-01** self-registration as admin (probe).
- **S-06** profile data over-exposure via `artist_id` (probe).
- **S-07** admin approve flips `suspended`→`approved`; document `verification_status` stays `pending` after approval (probe).
- **S-03** `.html` accepted as ID proof (probe).

### 5.4 Database/model gaps — see §6.

### 5.5 Frontend integration issues
**None confirmable** — frontend unavailable. Items the frontend must be checked against: D-04, D-10 (calls the server?), file URL handling (`fileUrl` is currently a relative storage name such as `artist_documents/artist_28/evil.html`, **not** an absolute URL — [PROBE]), HTTP-400-for-authorization behaviour (S-09).

### 5.6 Phone-only persistence gaps — §4.4.

### 5.7 Security findings

| ID | Sev | Finding | Endpoint / file | Evidence | Impact | Remediation |
|---|---|---|---|---|---|---|
| **S-01** | **Critical** | Public role escalation: `role` ChoiceField uses all `User.ROLE_CHOICES` incl. `admin` on register, phone-OTP request and Google login | `authentication/serializers_auth.py` (`RegisterWithPasswordSerializer`, `PhoneOTPRequestSerializer`, `GoogleAuthSerializer`) | [PROBE] `POST /auth/register/ {role:"admin"}` → `200`, DB role `admin`; same token then got `200` on `/admin-panel/artists/review_queue/get_all/` and `/help_center/admin/conversations/get_all/` (listing real conversation data in the copy) | Anyone can approve/reject artists and read all help-center chats | Restrict public choices to `customer`/`artist`; create admins only via `createsuperuser`/Django admin; audit existing `users` rows with `role='admin'`; add test |
| **S-02** | High | KYC files publicly retrievable + predictable path | `urls.py` (`static(MEDIA_URL)` under DEBUG), `ArtistDocument.file` (`artist_documents/artist_<id>/<original name>`) | [PROBE] unauthenticated `GET /media/artist_documents/artist_28/evil.html` → `200`, `text/html`. **Production serving is UNVERIFIED** (not in repo) | Identity-document leak; same-origin HTML/JS served from user upload | Store KYC outside web root / private bucket; serve only via authenticated, owner-or-admin download endpoint; randomise names |
| **S-03** | High | No upload validation (type, size, content) for KYC and portfolio | `views/document.py:create_extract`, `views/portfolio.py:create_extract` | [PROBE] `.html` accepted as `id_proof`; [CODE] only `if not file` check | Malware/HTML hosting, storage abuse | Allow-list (jpeg/png/webp/pdf), max size, `Pillow.verify()` for images, sanitised names |
| **S-04** | High | `SECRET_KEY` hard-coded (`django-insecure-change-this-in-production`) and is the JWT signing key | `sunndari/settings.py:9` | [CODE] | Mitigated only by the "token must equal stored `access_token`" check | Load from env; rotate before launch |
| **S-05** | High | `db.sqlite3` is **tracked by git** (contains users, tokens, OTPs, payout accounts); not in `.gitignore` | repo root | `git ls-files db.sqlite3` → tracked; `git status` shows it modified; a `.bak` copy also sits untracked | Credential/PII exposure in history | Untrack + purge history policy; rotate tokens; use Postgres |
| **S-06** | Medium | `GET /artists/profile/get/?artist_id=` returns internal fields for any artist to any authenticated user | `views/artist_profile.py:get_extract` | [PROBE] customer read `commissionRate`, `termsAcceptedAt`, `rejectionReason`, etc. | Leaks commission rate and review state | When `artist_id` ≠ own: return the public subset (as `customers/get_artist_detail` already does) |
| **S-07** | Medium | Admin approval ignores `suspended` and KYC state; no way to verify documents/payout account | `admin_panel/views/artist_review.py`, `ArtistProfile.approve` | [PROBE] suspended artist → `approve` `200` → `approved`; doc `verification_status` still `pending`; [CODE] no code sets `verification_status` after create; `Constants.artist_suspended` can be bypassed | Un-suspends banned artists; approval without identity check | Block approve when `suspended`; add admin document/payout verification endpoints; require verified docs to approve |
| **S-08** | Medium | Bank account number stored in plaintext; changing it after approval needs no re-review/notification | `ArtistPayoutAccount`, `set_for_artist` | [PROBE] raw value read from DB; API masks correctly (`bankAccountNumberMasked`) | DB leak exposes bank data; account-swap fraud | Encrypt at rest or tokenise; mark pending + notify on change |
| **S-09** | Medium | Authorization failures are HTTP **400**, not 403/404 | `common/common.py` (`ValueError`→400); `tests/test_admin_panel.py` asserts 400 | [PROBE] non-admin approve → `400 "Not allowed to access this resource"` | Client cannot distinguish "forbidden" from "bad input" | Do **not** change globally without frontend coordination (compat); consider a `ForbiddenError`→403 for new endpoints |
| **S-10** | Medium | `DEBUG = False if config('DEBUG') == 'False' else True` — any other value (e.g. `false`) enables DEBUG; `ALLOWED_HOSTS=['*']`; `CORS_ALLOW_ALL_ORIGINS=True` | `sunndari/config.py:10`, `settings.py:18,167` | [CODE] | Accidental debug in prod exposes `/media/` and error text | Strict bool parse; env-driven hosts/CORS |
| **S-11** | Low | `artist_id` on `portfolio/get_all` and `packages/get_all` returns any artist's items, incl. inactive / un-approved | `views/portfolio.py`, `views/pricing_package.py:_get_profile` | [CODE]; [PROBE] returned `200` for an arbitrary artist | Draft/hidden content visible | Public path should filter `approved` + `is_active` |
| **S-12** | Low | Booking accept / arrival read without row lock | `views/booking.py:update_status_extract`, `arrived_extract` | [CODE]; race **not reproduced** — UNVERIFIED | Possible double transition | `select_for_update` as already done for completion |
| **S-13** | High (financial) | Cancel/refund is DB-only | `payments/models.py:mark_refunded` | [CODE] comment "gateway refund API call … still need to be plugged in" | Customer shown "refunded" but not refunded | External dependency — block launch until gateway refund exists |
| **S-14** | Low | Contact info editable without re-verification | `UserProfileUpdateSerializer` | [CODE] only — UNVERIFIED | Takeover/identity-mismatch | Verify in a probe before deciding |

### 5.8 External blockers
Real SMS/Brevo/Google verification (CHECKLIST L37, 73, 75) · payment gateway + refund API (L280-290) · FCM/Firestore (L312-313) · Redis/Celery workers for expiry sweeps (L276) · cloud storage/CDN (L262) · any payout provider (none exists).

### 5.9 Unverified (and what resolves each)
| Item | Why | Evidence needed |
|---|---|---|
| All frontend contracts | repo unavailable | frontend repo or recorded HAR/Postman |
| Production media serving (S-02) | no deploy config | nginx/storage config |
| Booking race (S-12) | not reproduced | concurrent test on Postgres |
| Contact change without OTP (S-14) | not probed | probe `users/profile/update` |
| Specialities ≡ services? (D-03) | product meaning | Q-2 |
| Package sub-category pre-validation (A-04) | not probed | one request with bad id |

---

## 6. Deliverable 6 — Data model and migration plan

Existing migrations: `artists/0001_initial`, `0002_artistprofile_base_address_and_more`, `0003_artistprofile_rejection_reason` (untracked). All plan items below are **additive**; none drops or renames a field. Existing rows get NULL/default, so deployed app versions keep working.

| # | Change | Model | Fields (type, null/default) | Constraints / index | Notes |
|---|---|---|---|---|---|
| M1 | KYC types | `ArtistDocument` | `id_type` Char(20, choices, null) ; `back_file` File(null) | `unique(artist, document_type, id_type)` for `id_proof`; `document_number` validated per type (Aadhaar 12 digits, passport `^[A-PR-WYa-pr-wy][1-9]\d\s?\d{4}[1-9]$`, DL/voter regex) ; **store `document_number` encrypted or last-4 only** (Q-8) | Existing `id_proof` rows → `id_type=NULL` (legacy); keep `file` as front |
| M2 | Registration | `ArtistProfile` | `display_name` Char(100,null); `date_of_birth` Date(null); `instagram_url` URL(null); `profile_type` Char(10, choices freelance/studio, null) | validate age ≥ 18 (Q-9) | `specialities` **not added** unless Q-2 says it differs from `ArtistServiceOffering` |
| M3 | Photos | `ArtistProfile` | `profile_photo` Image(null); `cover_photo` Image(null) | upload validation (S-03) | Path `artist_photos/artist_<id>/…` |
| M4 | Work samples | Option A (recommended): `Portfolio.is_work_sample` Bool(default False) + cap 5 ; Option B: new `ArtistWorkSample` | — | cap enforced in view under transaction | Option A avoids a duplicate media table; Q-3 |
| M5 | Review feedback | new `ArtistReviewFeedback` | `artist` FK, `admin_user` FK→User, `decision` (changes_required/approved), `message` Text, `created_at` | index `(artist, created_at)` | Keeps `ArtistProfile.rejection_reason` as "latest" for compatibility |
| M6 | Earnings ledger | new `ArtistPayout`, `ArtistEarningAdjustment` | Payout: artist FK, amount Decimal(10,2), status (`pending|processing|paid|failed`), reference Char(100,null), period_from/to, paid_at, created_by FK | status only changed by admin endpoint; **amount never client-supplied** | Gross/fee/net **computed** from `Payment` (+completed `Booking`), never stored (single source of truth) |
| M7 | Package extras | `PricingPackage` | `makeup_type` Char(30,null, choices TBD); `product_details` Text(null); `photo` Image(null); brands: M2M `Brand` (needs C-03 minimal model) **or** JSON list as stopgap | — | `category` = derive from `sub_category.category`; **no new column** |
| M8 | Add-ons | new `PackageAddOn` + `PackageAddOnLink`(addon, package) | artist FK, name, description, price Decimal(>0), duration_minutes, is_active | `unique(addon, package)`; ownership: addon.artist == package.artist | |
| M9 | Service areas | new `ArtistServiceArea` | artist FK, city Char(100), travel_charge_type (`free|per_visit|per_km`), charge_amount Decimal(null), is_active | `unique(artist, city)`; `charge_amount` required iff not free | |
| M10 | Reschedule | new `BookingReschedule` | booking FK, requested_by FK, proposed_date, proposed_start, proposed_end, status (`pending|accepted|rejected|cancelled|expired`), responded_at, created_at | partial unique: one `pending` per booking | Audit trail retained after accept |
| M11 | Booking snapshots (C-07) | `Booking` (+ new `BookingAddOn`) | `platform_fee`, `net_amount`, `travel_fee`, `travel_minutes_before`, `return_buffer_minutes` — all null, backfilled from `Payment` where present | no recompute of historical rows | **Do not change `total_amount` semantics for existing bookings.** |
| M12 | Misc post-launch | `ArtistProfile`: `is_accepting_bookings` (default True), `profile_view_count`, `public_slug`(unique, null); `Review`: `reply`, `replied_at`; `Portfolio.sort_order`; new `Brand`, `BrandRequest`, `SupportTicket`(+attachments), `CustomerReview`, `ClientNote` | — | — | |

**Migration safety:** every migration is `AddField(null=True/default)` or `CreateModel`; reverse = `RemoveField`/`DeleteModel`; no data migration required except optional M11 backfill. SQLite → Postgres move (S-05) should happen **before** M6/M10 where partial unique indexes are used.

---

## 7. Deliverable 5 — Proposed API contracts (PROPOSED, not implemented)

Conventions copied from the repo: snake_case request, camelCase response, `{status, message, data}`, GET params in query, list envelope `{data, presentPage, totalPage}`, errors as HTTP 400 with `{status:false,message,error:[…]}` (existing behaviour; see S-09).

### 7.0 Auth hardening and password recovery (S-01, A-01)
- **Change** `role` choices on `/auth/register/`, `/auth/phone-otp/request/`, `/auth/google/` to `['customer','artist']`. Sending `admin` → `400 validation_error`. Compatibility: none for the app (it never legitimately registers admins).
- **Proposed (only if Q-5 = "needed")** `POST /auth/forgot-password/ {username}` → sends OTP (reuses `User.generate_otp`, nulled on use per the single-use rule) ; `POST /auth/reset-password/ {username, otp, new_password(min 8)}` → invalidates `access_token`/`refresh_token`. Idempotent request; 5-attempt lockout reused from `User.is_locked_out`.

### 7.1 KYC (B-01, B-02)
`POST /artists/documents/create/` (multipart)
- Fields: `document_type` (`id_proof|address_proof|certification`), `id_type` (**required iff** `id_proof`: `aadhaar|voter_id|passport|driving_licence`), `document_number` (required for `id_proof`, validated per `id_type`), `file` (front, required), `back_file` (required for aadhaar/voter_id/driving_licence, optional for passport — Q-10).
- Limits: jpeg/png/webp/pdf, ≤ 5 MB each (Q-11).
- `201 {data:{documentId}}`. Re-submitting the same `(id_proof,id_type)` replaces and resets verification to `pending`.
- Response (get/get_all) adds `idType`, `documentNumberMasked` (never raw), `hasBackFile`; **no raw file path** — `fileUrl` becomes an authenticated URL `GET /artists/documents/file/?document_id=&side=front|back` (owner or admin only; `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`).
- Admin: `GET /admin-panel/artists/documents/get_all/?artist_id=`, `GET /admin-panel/artists/documents/file/?document_id=&side=`, `PUT /admin-panel/artists/documents/verify/ {document_id, decision: approved|rejected, reason}` (admin only; writes `verification_status`, `rejection_reason`).
- Compat: existing `id_proof` rows keep working; `fileUrl` value format changes — **needs frontend confirmation**.
- Tests: wrong type, missing back, size/MIME, cross-artist `400`, customer `400`, admin-only verify, unauthenticated `401`, file not reachable via `/media/`.

### 7.2 Registration fields (B-03)
Extend `PUT /artists/profile/update/` with optional `display_name` (≤100), `date_of_birth` (`YYYY-MM-DD`, age ≥ 18), `instagram_url` (https Instagram host only), `profile_type` (`freelance|studio`). Full name → existing `PUT /users/profile/update/ {name}`; experience → `years_experience`; address → `base_address_id`. Work samples: `POST /artists/portfolio/create/` with `is_work_sample=true` (≤5, `409/400` on 6th). `GET profile/get` adds `displayName`, `dateOfBirth`, `instagramUrl`, `profileType`, `workSampleCount`. `onboarding/status.steps` gains `registrationFields` and `workSamples`. DOB is private: omitted from any cross-user response.

### 7.3 Photos (B-04)
`PUT /artists/profile/photo/upload/` multipart `profile_photo` and/or `cover_photo` (≤5 MB, jpeg/png/webp, `Pillow.verify`). `200`. `GET profile/get` returns **absolute** `profilePhotoUrl`, `coverPhotoUrl` (null if unset). Delete: `DELETE /artists/profile/photo/delete/?kind=profile|cover`. Public images may use media storage; KYC may not (§7.1).

### 7.4 Page review (B-05)
- `GET /artists/review/status/` → `{reviewStatus: "submitted|changes_required|approved|not_submitted|suspended", submittedAt, decidedAt, latestFeedback}`; mapping: `pending+submitted_for_review_at`→`submitted`, `rejected`→`changes_required` (DB values unchanged — smallest change; Q-1).
- `GET /artists/review/feedback/get_all/` → paginated `[{feedbackId, decision, message, createdAt}]` (own only).
- Resubmit = existing `POST /artists/onboarding/submit/`.
- Admin: existing `reject` accepts `reason` and additionally writes an `ArtistReviewFeedback` row; add `PUT /admin-panel/artists/request_changes/ {artist_id, message}` if "changes required" and "rejected" must differ (Q-1). Legal transitions: `not_submitted→submitted→{approved|changes_required}`, `changes_required→submitted`, `approved→(profile edit)→submitted`; `suspended` is terminal until an admin lifts it (new explicit endpoint), never via `approve`.

### 7.5 Earnings & payouts (B-06)
- `GET /artists/earnings/summary/?from_date&to_date` → `{grossAmount, platformFee, adjustments, netAmount, paidOut, pending, currency:"INR"}`. Definition (proposed, Q-6): over bookings `completed` with a `Payment` in `paid`: gross = Σ`amount`, fee = Σ`commission_amount`, adjustments = Σ`ArtistEarningAdjustment`, net = gross − fee + adjustments, paidOut = Σ`ArtistPayout(status=paid)`, pending = net − paidOut. Computed on read; no stored totals.
- `GET /artists/payouts/get_all/` → `[{payoutId, amount, status, date, reference}]`.
- Admin: `POST /admin-panel/artists/payouts/create/ {artist_id, amount, period…}` and `PUT …/payouts/update_status/` (manual ledger entries — **no provider integration exists; a payout is never reported `paid` without an admin recording it**).
- Constraint: amount ≤ current `pending`; idempotency key on create.

### 7.6 Package extras (B-07)
Extend `packages/create|update` with `makeup_type`, `product_details`, `brand_ids[]` (or `brands[]` text stopgap), multipart `photo`; responses add `category{categoryId,name}` (derived), `makeupType`, `brands`, `productDetails`, `photoUrl`. Ownership unchanged.

### 7.7 Add-ons (B-08, C-07)
`/artists/addons/{create,update,delete,get,get_all}/` — fields `name, description, price(>0), duration_minutes, package_ids[] (all must belong to the caller), is_active, photo?`. Booking create accepts `addon_ids[]`; **server recomputes** total = package price + Σ add-on price (+ travel, §7.8) and snapshots into `BookingAddOn`; client-supplied amounts are ignored.

### 7.8 Service areas & travel (B-09)
`/artists/service_areas/{add,update,remove,get_all}/` — `city`, `travel_charge_type (free|per_visit|per_km)`, `charge_amount` (required unless free). Customer booking quote/creation computes travel fee server-side (per_visit flat; per_km needs distance source — **external dependency: geocoding/Distance API not present**, Q-12). Changing an area never mutates existing bookings (snapshot, M11).

### 7.9 Rescheduling (B-10)
- `POST /artists/bookings/reschedule/request/ {booking_id, proposed_date, proposed_start_time, proposed_end_time, reason?}` (artist, own booking, status `confirmed`, `on_my_way_at` is null, not past missed-deadline, ≤1 pending).
- `GET /customers/bookings/reschedule/get/?booking_id=` ; `PUT /customers/bookings/reschedule/respond/ {reschedule_id, decision: accepted|rejected}` (booking owner only).
- Accept (single `transaction.atomic` + `select_for_update` on booking): re-run availability (`Booking.has_overlap(exclude_booking_id)`, weekly schedule, blocks), update date/time, **regenerate `booking_otp_expiry` from the new end time**, sync Firebase, notify both parties. Reject/expiry leaves booking untouched. Idempotent respond (second call → `400` already decided). Add expiry sweep alongside the existing celery task.

### 7.10 Post-launch outlines (not specified further until prioritised)
Reply: `PUT /artists/reviews/reply/ {review_id, reply}` (own artist only, once/editable) · insights `GET /artists/insights/summary/` · brands `GET /core/brands/get_all/`, `POST /artists/brands/request/` · `agreement_version` on accept · `PUT /artists/profile/accepting_bookings/` · tickets `/help_center/artist/tickets/*` · `GET /public/artists/<slug>/` (no auth, public subset only) · `POST /artists/customer_reviews/create/` (completed booking only, one per booking) · static pages via config URLs · `portfolio/reorder/`, `clients/*`, `marketing/generate/`, `core/service-styles/get_all/`.

---

## 8. Deliverable 8 — Test and regression evidence

### 8.1 Commands executed
```
venv/bin/python manage.py test tests            → Ran 489 tests in 5.784s — OK   (exit 0)
DJANGO_SETTINGS_MODULE=probe_settings (scratchpad; DB=copy of db.sqlite3, MEDIA_ROOT=scratchpad, DEBUG=True)
  python run_probe.py, probe2.py                → results in §5.7
```
Per-file test counts: admin_panel 10 · artists 70 · authentication 64 · booking_lifecycle 2 · chat 17 · core 42 · customers 92 · help_center 29 · notifications 15 · payments 40 · smoke_group_payment 4 · users 34 · wallet 65.

### 8.2 Firebase log errors — verified as handled, not failures
`notifications/firebase_utils.py:26-27` deliberately raises `RuntimeError('Firebase is disabled under the test runner (settings.TESTING)')`; `NotificationFirebaseUtils.sync_notification` wraps the call in `except Exception: logger.exception('Failed to sync notification %s to Firestore', …)`. The log has 346 such tracebacks and the suite still ends `OK` (0 failures, 0 errors). Consequence: Firestore sync logic is **never exercised** by tests (real behaviour UNVERIFIED).

### 8.3 Probe results (copy DB only; users created only in the copy)
| Probe | Result |
|---|---|
| `.html` as `id_proof` | `201` accepted |
| Own `documents/get` | `200`, `fileUrl` = relative name |
| Unauthenticated `GET /media/artist_documents/…` (DEBUG on) | `200`, `text/html` |
| Artist B get / delete artist A's document | `400 No matching record` (ownership OK) |
| Customer `documents/get_all` | `400 Artist not found` (role gate by profile OK) |
| Customer `profile/get?artist_id=` | `200` with `commissionRate`, `rejectionReason`… (S-06) |
| Admin approve a `suspended` artist | `200`, status → `approved`; doc still `pending` (S-07) |
| Non-admin approve | `400 Not allowed to access this resource` |
| Payout set/get | `200`; masked in API; **plaintext in DB** |
| `POST /auth/register/ role=admin` | `200`; admin endpoints `200` (S-01) |
Not covered by probe: portfolio upload validation, package pre-validation, concurrency, real providers.

### 8.4 Proposed regression plan (to accompany implementation)
For each task: focused tests first, then `manage.py test tests` (must remain 489+ passing). New suites: `AuthRoleHardeningTest`, `KycDocumentTypeTest`, `KycFileAccessTest` (asserts not served via `/media/`), `UploadValidationTest`, `ProfileRegistrationFieldsTest`, `ProfilePhotoTest` (upload → stored → DB → URL → re-get → other artist denied), `ReviewFeedbackTest`, `EarningsSummaryTest` (hand-computed fixtures reconcile with `Payment`), `AddOnTest`, `ServiceAreaTest`, `RescheduleFlowTest` (request, accept, reject, overlap, blocked date, OTP expiry refreshed, unauthorized), `ProfileExposureTest`, `AdminApproveSuspendedTest`. Also run `python manage.py makemigrations --check` and review each migration SQL (`sqlmigrate`).

---

## 9. Deliverable 7 — Prioritised roadmap (proposal; no estimates)

Priority baseline = PDF category. Deviations are listed with their dependency reason.

### Stage 0 — P0 security prerequisites (new; not in the PDF)
| Task | Req | Files | Change | Acceptance |
|---|---|---|---|---|
| T0-1 | A-01 | `authentication/serializers_auth.py` | Restrict public roles; audit existing admin rows | `role=admin` → 400 on all three entry points |
| T0-2 | B-01 | `artists/serializers/request/create/create_document.py`, `portfolio`, new `common/uploads.py` | Upload allow-list/size/Pillow verify | `.html` rejected |
| T0-3 | B-01 | `urls.py`, document model/view | Private KYC storage + authenticated download | `/media/` cannot reach KYC |
| T0-4 | S-04/S-05/S-10 | `settings.py`, `config.py`, `.gitignore` | env `SECRET_KEY`, strict DEBUG, untrack DB | ops sign-off |
| T0-5 | S-06/S-07 | `views/artist_profile.py`, `admin_panel/views/artist_review.py` | Public subset for foreign `artist_id`; block approve of `suspended`; require verified docs | probe cases return denied |
| T0-6 | S-13 | payments | Real gateway refund or documented launch gate | **EXTERNAL** |

### Stage 1 — Required pre-launch (all PDF Category B)
Order by dependency: **T1-1** B-02 KYC types + admin verify (M1) → **T1-2** B-03 registration fields + work samples (M2, M4) → **T1-3** B-04 photos (M3) → **T1-4** B-05 review status/feedback (M5) → **T1-5** B-07 package extras (M7) → **T1-6** B-08 add-ons (M8) → **T1-7** C-07 booking snapshots (M11) *(promoted from C to P1: B-08/B-09 totals can't be honoured without it)* → **T1-8** B-09 service areas/travel (M9) → **T1-9** B-10 reschedule (M10) → **T1-10** B-06 earnings/payout ledger (M6; can launch with empty history).
Each task: files = the matching controller/view/serializer/dataclass/model/urls/admin/tests under `sunndari_apps/artists/` (plus `customers/` for T1-7/8/9 and `admin_panel/` for T1-1/4/10); acceptance = §7 contract + §8.4 tests; risk = frontend contract changes (`fileUrl`), travel `per_km` distance source, coin-redemption reconciliation for earnings.

### Stage 2 — Persistence & integration (needs frontend repo/HAR)
Confirm the app now sends D-01…D-11 to the server, uses `agreement/accept` (D-10), and handles absolute URLs; test reinstall by logging in on a clean client and re-reading profile.

### Stage 3 — Post-launch (C-01…C-11, D-09, D-11) in §7.10 order; C-04 version, C-01 reply, C-05 switch first by product value.

### Separation: confirmed vs conditional
- **Confirmed work:** everything in §5.1-5.3, §5.7 (S-01…S-11, S-13).
- **Conditional on your decisions:** forgot/reset password (Q-5), `changes_required` as separate DB status (Q-1), specialities reuse (Q-2), work-sample storage (Q-3), brands stopgap (Q-7), KYC number encryption (Q-8), per-km distance source (Q-12).

---

## 10. Open questions and assumptions

**Assumptions:** (a) the working tree is the intended current state; (b) `Payment` rows are the financial source of truth; (c) production serves `/media/` through the same Django `static()` route or an equivalent public web-server alias — unverified.

| # | Question | My recommendation |
|---|---|---|
| Q-1 | Must "changes_required" be distinct from "rejected" (final)? | Map `rejected`→`changes_required` in the API now; add a real final-reject status only if product needs it |
| Q-2 | Are "specialities" the same as `ArtistServiceOffering` sub-categories? | Yes unless told otherwise — no new field |
| Q-3 | Work photos: reuse `Portfolio` (+flag, cap 5) or separate table? | Reuse with `is_work_sample` |
| Q-4 | Should adding/removing a service demote an *approved* artist to pending? | Probably not; recommend only re-review for KYC/bank/identity changes |
| Q-5 | Is forgot/reset password required, or is OTP login the recovery path? | Confirm with the frontend; OTP login may suffice |
| Q-6 | Earnings recognised on `completed` + `paid` payment? Are coin-redeemed amounts part of gross? | Yes completed+paid; redeemed value treated as settled amount — needs sign-off |
| Q-7 | Brands before launch: free-text list or admin-managed table? | Free-text/JSON stopgap, table post-launch |
| Q-8 | May we store only the last 4 digits of Aadhaar (UIDAI guidance) and encrypt others? | Yes |
| Q-9 | Minimum age for DOB? | 18 |
| Q-10 | Is a passport back image required? | Optional |
| Q-11 | KYC file limits/types? | jpeg/png/webp/pdf, 5 MB |
| Q-12 | Source for per-km distance (Google/Mapbox)? | Out of repo; needs credentials |

---

## 10.1 Decisions log (owner answers, 2026-10-03)

| Item | Decision | Effect on this plan |
|---|---|---|
| B-06 Earnings & payout history | **Skipped for now** | Remove T1-10 and M6, §7.5; Q-6 deferred. No earnings/payout API or ledger models. |
| Q-1 | **No separate status** | No new DB status and no extra admin "request changes" endpoint. Existing `pending`/`rejected`/`approved` stay. Add feedback history (M5) on reject; exact API label for `rejected` pending frontend naming (see open point below). |
| Q-2 | Specialities **differ** from service offerings ("which service the artist specialises in") | Add a new specialities field; do **not** reuse `ArtistServiceOffering`. Proposed: M2M `ArtistProfile.specialities → ServiceSubCategory`, subset of the artist's offered services. |
| Q-4 | Adding/removing a service must **not** demote an approved artist | Remove `reset_approval=True` calls in `add_service_extract` / `remove_service_extract` (`views/artist_profile.py`). Covered by a regression test. |
| Q-5 | Forgot + reset password **required** | Implement §7.0 `POST /auth/forgot-password/` and `/auth/reset-password/`. |
| Q-6 | Deferred with B-06 | — |

Approved by the owner ("use defaults"): Q-3 work photos reuse `Portfolio` with a flag (max 5); Q-7 brands are free text; Q-8 Aadhaar keeps only the last 4 digits (other IDs encrypted); Q-9 minimum age 18; Q-10 passport back image optional; Q-11 jpeg/png/webp/pdf up to 5 MB; Q-12 per-km travel charge deferred until a distance source exists. Q-1 answer: the review status stays `rejected` (no separate status).

---

## 11. Deliverable 9 — Implementation report (Stage 0, completed 2026-10-03)

Scope approved by owner: **Stage 0, then pause** (plus the two items the owner decided explicitly: forgot/reset password and the Q-4 fix). Earnings/payouts (B-06) skipped. Stage 1 has **not** been started.

### 11.1 What was done

| Task | Finding | Result | Verified by |
|---|---|---|---|
| T0-1 | S-01 | Public `role` choices now `customer`/`artist` only, on register, phone-OTP, email-OTP and Google | [TEST] `PublicRoleRestrictionTest` (5); [PROBE] `role=admin` → 400, no user created |
| A-01 | forgot/reset password | `POST /auth/forgot-password/` (always 200, no account enumeration) and `POST /auth/reset-password/` (OTP single-use and nulled, 5-attempt lockout, revokes existing sessions) | [TEST] `ForgotResetPasswordTest` (9) |
| Q-4 | A-05 | Adding/removing a service no longer demotes an approved artist | [TEST] 2 new + 1 updated (the old test asserted the demotion) |
| T0-2 | S-03 | Uploads content-validated: JPEG/PNG/WEBP decoded with Pillow and extension must match; PDF header check (KYC only); portfolio video container check; 5 MB images / 50 MB video; empty rejected; stored names randomised | [TEST] `UploadValidationTest` (11); [PROBE] `.html` → 400 |
| T0-3 | S-02 | KYC files stored in `PRIVATE_MEDIA_ROOT` (outside `MEDIA_ROOT`, no URL); `fileUrl` now `/artists/documents/file/?document_id=N`; new owner-or-admin download with `nosniff`, CSP sandbox, `no-store`; legacy non-image files forced to download | [TEST] `KycFilePrivacyTest` (8); [PROBE] `/media/<path>` → 404, customer → 400, anonymous → 401 |
| T0-4 (part) | S-04, S-10 | `SECRET_KEY` read from env (fallback keeps old value so local setups don't break); `DEBUG` parsed strictly (typo now fails at startup instead of enabling debug) | manual check of `decouple` behaviour |
| T0-5 | S-06, S-07 | Another user's `profile/get?artist_id=` returns only public fields and only for approved artists; admin approve/reject of a `suspended` artist is refused | [TEST] 4 + 2 new; [PROBE] both closed |
| New finding S-15 | — | **Existing bug fixed:** `SerializerValidations` deep-copied `request.data`, which crashes on any upload > 2.5 MB ("cannot pickle BufferedRandom"), so large portfolio/KYC photos errored before reaching the view | [TEST] `test_large_valid_upload_is_not_crashed_by_request_copying` |

### 11.2 Files

- **Created:** `sunndari_apps/common/storage.py`, `sunndari_apps/common/uploads.py`, `sunndari_apps/artists/migrations/0004_kyc_documents_private_storage.py`, `sunndari_apps/artists/management/{__init__,commands/__init__,commands/move_kyc_files_to_private}.py`, this report.
- **Modified (Stage 0):** `authentication/{serializers_auth,views,controller,urls}.py`, `artists/{urls.py,models/document.py,models/portfolio.py,controllers/document.py,views/document.py,views/portfolio.py,views/artist_profile.py,serializers/response/get/get_profile.py}`, `admin_panel/views/artist_review.py`, `common/serializer_validations.py`, `sunndari/{settings,config,constants}.py`, `.gitignore` (+`/private_media/`), `.env.example` (+`SECRET_KEY`), `tests/{test_authentication,test_artists,test_admin_panel}.py`.
  Several of these files were already modified in the working tree before this audit; my edits are additive on top and nothing was reverted, staged or committed.
- **Endpoints added:** `POST /auth/forgot-password/`, `POST /auth/reset-password/`, `GET /artists/documents/file/`.
- **Endpoints changed:** `GET /artists/profile/get/` (foreign `artist_id` → public subset; `commissionRate`/`approvalStatusId` now optional in the response schema), `documents/get|get_all` (`fileUrl` value), all auth entry points (`role`), `documents/create` and `portfolio/create` (validation), admin `approve`/`reject`.
- **Migration:** `artists/0004` — `AlterField` on `ArtistDocument.file` (storage only). On SQLite Django rebuilds the table and copies all rows; no column or data change. `makemigrations --check` → no further changes.

### 11.3 Test results (actual)
- `manage.py test tests` → **Ran 531 tests — OK** (489 before; +42 new; 2 existing tests edited to the new rules, none removed or weakened). Firebase tracebacks in the log remain the handled, expected ones (§8.2).
- Existing test helpers that uploaded `b'fake-bytes'` as `image/jpeg` were changed to upload real images, because that content is now (correctly) rejected. Test uploads go to temp directories (`settings.TESTING`), not the repo's `media/`.
- Re-probe on a fresh copy of `db.sqlite3`: all Stage 0 attacks closed (table in 11.1).

### 11.4 Still open / needs the owner

1. **Existing KYC files on disk** (any real `media/artist_documents/…`) are still in the public folder and will 404 through the app until moved: run `python manage.py move_kyc_files_to_private --dry-run`, then without the flag. Production serving of `/media/` remains **UNVERIFIED** — confirm nothing else (nginx alias, bucket) exposes `artist_documents/`.
2. **S-05 `db.sqlite3` is still tracked by git.** Untracking (`git rm --cached`) and history clean-up change the index/history, so I did not do them without your go-ahead. Also set a real `SECRET_KEY` in every deployed environment and rotate (existing JWTs become invalid when you do).
3. **Existing `admin` users:** audit `users` rows with `role='admin'` — before the fix, anyone could have self-registered one.
4. **S-13 refund** is still DB-only (external dependency, T0-6).
5. Not in Stage 0, still open: admin approval does not yet require verified documents and there is no admin document view/verify endpoint (T1-1); S-08 bank-number encryption; S-09 authorization failures return 400; S-11 `artist_id` on portfolio/package lists exposes inactive/unapproved items; S-12 booking race; S-14 contact change without re-verification.
6. **New observation:** `GET /customers/artists/get/` (`customers/views/get_artist_detail.py`) still returns `commissionRate` and `approvalStatusId` of an artist to any customer. It is the same exposure as S-06 but is a customer-app contract, so I left it for your decision.
7. **Frontend must be told:** `fileUrl` on documents is now an API route (prepend the API base URL and send the bearer token), forgot/reset endpoints exist, `role=admin` is refused, and foreign profile reads no longer include internal fields.

Stage 1 was approved afterwards — see §12.


---

## 12. Stage 1 implementation report (completed 2026-10-03)

Scope: every Category B item except B-06 (earnings/payouts, skipped by the owner). Built in small batches, each followed by the full suite.

### 12.1 Status of the Category B requirements after implementation

| ID | Feature | Now | What was built | Evidence |
|---|---|---|---|---|
| B-01 | KYC + bank | **VERIFIED WORKING** | Private storage, validated uploads, admin list/verify, approval requires a verified ID proof | 17+ new tests; Stage 0 probes |
| B-02 | ID types | **VERIFIED WORKING** | `id_type` aadhaar/voter_id/passport/driving_licence, per-type number validation, back image (required except passport), one ID proof per artist (new one replaces old), Aadhaar stored as last-4 only, other numbers encrypted (Fernet) | `KycIdTypeTest` (10) |
| B-03 | Registration fields | **VERIFIED WORKING** | `display_name`, `date_of_birth` (18+, private), `instagram_url` (instagram.com only), `profile_type`, specialities (separate from services), up to 5 work samples; two new onboarding steps; admin review-detail endpoint | `ArtistRegistrationFieldsTest`, `ArtistSpecialityTest`, `WorkSampleTest`, `AdminReviewDetailTest` |
| B-04 | Profile & cover photo | **VERIFIED WORKING** | Upload/replace/delete; absolute URLs in `profile/get`; old files removed | `ArtistPhotoTest` (10) |
| B-05 | Page review | **VERIFIED WORKING** (label stays `rejected`) | Append-only `ArtistReviewFeedback` history; `GET /artists/review/feedback/get_all/`; `latestFeedback` in onboarding status; artist notified on approve/reject; resubmit = existing `onboarding/submit` | `ReviewFeedbackHistoryTest` (7) |
| B-06 | Earnings & payouts | **SKIPPED (owner decision)** | — | — |
| B-07 | Package extras | **VERIFIED WORKING** | `makeup_type`, `brands` (free text, max 10), `product_details`, package photo (own endpoints), derived `category` | `PackageExtrasTest` (8) |
| B-08 | Add-ons | **VERIFIED WORKING** | CRUD, linked to own packages; selectable at booking; price and duration included in total and slot length; snapshotted per booking | `AddOnCrudTest`, `BookingTotalsTest` |
| B-09 | Service areas & travel | **PARTIALLY IMPLEMENTED** | Cities + free/per-visit charge, applied server-side to Home Visit bookings; **per-km deliberately refused** (needs a distance source — Q-12) | `ServiceAreaApiTest`, travel tests in `BookingTotalsTest` |
| B-10 | Rescheduling | **VERIFIED WORKING** | Artist requests, customer accepts/rejects, 24 h expiry, audit trail, same slot rules as booking creation, OTP expiry refreshed | `test_reschedule.py` (26) |
| C-07 | Booking financial/travel fields | **VERIFIED WORKING** (promoted to P1 as planned) | `travel_fee`, `commission_rate`, `platform_fee`, `net_amount`, travel/return buffer snapshots, `BookingAddOn`; artist sees fees, customer never does | `BookingTotalsTest` |

### 12.2 Endpoints added
- **Artist:** `profile/specialities/{set,get_all}`, `profile/photo/{upload,delete}`, `review/feedback/get_all`, `packages/photo/{upload,delete}`, `addons/{create,update,delete,get,get_all}`, `service_areas/{add,update,remove,get_all}`, `bookings/reschedule/{request,cancel,get_all}`.
- **Customer:** `bookings/reschedule/{respond,get_all}`.
- **Admin:** `artists/documents/{get_all,verify}`, `artists/review/get`.
- **Changed (additive unless noted):** `documents/create` (needs `id_type`/`document_number`; **breaking for old clients**), `profile/update`/`get`, `portfolio/create` (`is_work_sample`), `packages/*` (extras), `bookings/create` (`addon_ids`; response adds `total_amount`, `travel_fee`), booking get/get_all for both apps (`travelFee`, `addOns`; artist also `platformFee`, `netAmount`, buffers), `customers/artists/get` (`addOns`, `serviceAreas`, extras), `admin approve` (optional `message`; **now requires a verified ID proof**), `onboarding/status` (`latestFeedback`, two new steps).

### 12.3 Migrations (all additive; applied successfully to a copy of `db.sqlite3`)
`artists/0004` private KYC storage · `0005` ID types/back image/encrypted number · `0006` registration fields, specialities, work-sample flag · `0007` photos · `0008` review feedback · `0009` package extras · `0010` add-ons, service areas, travel buffers · `customers/0006` booking snapshots + `BookingAddOn` · `customers/0007` reschedules. The dev DB has no bookings/documents, so these migrations were exercised on empty tables; existing user/artist rows were preserved. Run `move_kyc_files_to_private` for any real KYC uploads.

### 12.4 Test results (actual)
`manage.py test tests` → **Ran 650 tests — OK** (489 at the start of the audit; +161). `makemigrations --check` → no changes. Existing tests edited: the helper that completes onboarding (now also sets registration fields and a work sample), uploads in tests (real images instead of opaque bytes), and the two admin approval tests (now verify the ID proof first). No assertion was weakened.

### 12.5 Behaviour changes the frontend / ops must know
1. **Onboarding is stricter:** submission now also needs display name, date of birth, profile type and ≥1 work sample; **approval needs a verified ID proof** (admin must call `documents/verify` first). Artists who submitted before this change but are not yet approved will be blocked at approval until verified.
2. **`documents/create`** requires `id_type` + `document_number` (+ `back_file` for aadhaar, voter_id, driving_licence). Old clients sending only a file get 400.
3. **Document and package/profile file URLs:** documents are served through the authenticated route; profile/package photos are absolute URLs of public media.
4. **Booking totals are server-computed** (package + add-ons + travel). Anything the client sends as an amount is ignored.
5. **Payments** now use the commission rate snapshotted on the booking (falls back to the artist's current rate for older bookings). This is a deliberate change to `payments/views/initiate_payment.py` and `initiate_group_payment.py`.
6. Artists with at least one **active service area** can only take Home Visit bookings for addresses in those cities; artists with none behave exactly as before.

### 12.6 Open items and decisions for the owner
- **Travel/return buffers are recorded, not enforced.** `travel_time_before_minutes` / `return_buffer_minutes` are snapshotted onto each booking but do not yet block neighbouring time. Enforcing them changes overlap rules for all bookings — needs a product decision.
- **Per-km charging** is refused until a distance source (Google/Mapbox) exists.
- **Reminders:** the 24 h/2 h reminder job de-duplicates per booking, so a reminder already sent for the old time is not repeated after a reschedule.
- **Reschedule expiry** is lazy (applied on every read/write) with no new beat job; that is sufficient for correctness.
- **Pre-existing, not changed:** the `values=` column filter on booking/profile `get` endpoints fails response validation for any subset of fields (confirmed on the original code path); `GET /customers/artists/get/` still returns `commissionRate`; an unrelated `git stash` entry exists in the repo and was left alone.
- **Still open from Stage 0:** untrack `db.sqlite3`, set `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` in every environment, audit existing `role='admin'` users, real gateway refunds, S-08/S-09/S-11/S-12/S-14.
- **B-06 earnings/payouts** remain skipped; the `Payment` table already carries `commission_amount` and `artist_payout_amount` per payment, which is the planned source of truth when this is picked up.


---

## 13. Remaining open work — implementation report (completed 2026-10-03)

After Stage 1 the owner asked to skip earnings/payouts and work through the other open items. Done in four batches, each followed by the full suite. B-06 remains skipped.

### 13.1 Status after this round

| ID | Item | Now | What was built |
|---|---|---|---|
| S-08 | Bank number in plaintext | **FIXED** | Account number encrypted at rest (data migration encrypts existing rows — verified on a DB copy with a plaintext row); API still returns only the masked value; changing it resets verification to pending and notifies the owner |
| S-11 | `artist_id` on portfolio/package lists | **FIXED** | Other users see only active items of **approved** artists; owners still see everything |
| S-12 | Accept-vs-cancel race | **MITIGATED** | Artist accept/decline/cancel runs under a booking row lock (effective on PostgreSQL; SQLite serialises writes anyway). Booking-OTP verification was deliberately left unlocked: wrapping it would roll back the failed-attempt counter and weaken the lockout |
| C-01 | Reviews + artist reply | **VERIFIED WORKING** | `GET /artists/reviews/get_all/`, `PUT /artists/reviews/reply/` (editable; customer notified on first reply); customers see `reply`/`repliedAt` |
| C-02 | Business insights | **VERIFIED WORKING (no earnings)** | `GET /artists/insights/summary/`: bookings by status, repeat clients, top services, profile views, optional date range |
| C-03 | Brands | **VERIFIED WORKING** | Admin-managed list (`/core/brands/get_all/`, admin create/update), artist requests with admin approve/reject (approve adds the brand). Package `brands` stay free text — not forced to the list |
| C-04 | Agreement | **VERIFIED WORKING** | Acceptance stores date **and version** (`agreement_version` from config); date/version are private to the artist |
| C-05 | Accepting-bookings switch | **VERIFIED WORKING** | `PUT /artists/profile/accepting_bookings/`; off hides the artist from search and blocks new bookings; existing bookings unaffected; flag visible to customers |
| C-06 | Help-center tickets | **VERIFIED WORKING** | Customers and artists: many tickets with issue type, optional own booking, ≤5 image/PDF attachments (private storage, owner/admin download), status; admin list/detail/status update with notification; users can close their own; max 10 open |
| C-08 | Public profile link | **VERIFIED WORKING** | `GET /artists/profile/share_link/` (stable slug) and anonymous `GET /public/artists/get/?slug=` returning a minimal public projection of approved artists only |
| C-09 | Artist reviews a customer | **VERIFIED WORKING** | Separate `CustomerReview` table; completed bookings only, once per booking, private to the artist side |
| C-10 | Terms/Privacy/Contact | **VERIFIED WORKING** | Public `GET /core/pages/get/` from env (`TERMS_URL`, `PRIVACY_URL`, `CONTACT_EMAIL`, `CONTACT_PHONE`); null until configured |
| C-11 | Profile views, portfolio order, My Clients + notes | **VERIFIED WORKING** | Atomic view counter (customer detail + public page); `PUT /artists/portfolio/reorder/` (listings and customer view follow it); `GET /artists/clients/get_all/` + `PUT /artists/clients/note/set/` (private notes, clients = customers with a confirmed/started/completed booking) |
| C-11 | Marketing Studio content generation | **NOT DONE — needs a spec** | No definition of what is generated, from what, or by which service; it would need an external model/provider |
| C-11 | Service styles list | **NOT DONE — needs the list** | The set of styles/makeup types is product content, not something to invent; `makeup_type` on packages is currently free text |

### 13.2 Endpoints added
Artist: `profile/{accepting_bookings,share_link}`, `portfolio/reorder`, `reviews/{get_all,reply}`, `customer_reviews/{create,get_all}`, `clients/{get_all,note/set}`, `insights/summary`, `brands/{request,requests/get_all}`. Public: `public/artists/get`. Core: `core/{brands/get_all,pages/get}`. Admin: `admin-panel/brands/{create,update,requests/get_all,requests/decide}`. Help center: `tickets/{create,get,get_all,close,attachment}`, `admin/tickets/{get_all,get,update_status}`.
Changed: profile `get` (switch/slug/views/agreement version), customer artist detail (ordering, switch, view count), search (excludes artists who switched bookings off), `create_booking` (refuses them), portfolio/package lists (S-11), payout account (S-08).

### 13.3 Migrations (all applied to a copy of `db.sqlite3`)
`artists/0011` (payout encryption + data step), `0012` (switch, slug, views, agreement version, portfolio order), `0013` (client notes), `0014` (brand requests) · `core/0002` (brands) · `customers/0008` (review reply, customer reviews) · `help_center/0002` (tickets).

### 13.4 Tests
`manage.py test tests` → **Ran 712 tests — OK** (650 after Stage 1; +62 in this round). `makemigrations --check` → no changes. One existing test was adjusted: it listed an *unapproved* artist's portfolio as a stranger, which S-11 now correctly refuses (the test approves the artist first).

### 13.5 Still open
- **Decided by the owner (see §14):** S-14 → OTP step (done); buffers → enforced (done); per-km charges → stay refused; Marketing Studio and service-styles → later.
- **Skipped by the owner:** B-06 earnings & payouts (and earnings in insights).
- **Ops / infra (unchanged):** untrack `db.sqlite3`; set `SECRET_KEY` and `FIELD_ENCRYPTION_KEY` per environment (rotating either makes existing encrypted ID/bank numbers unreadable — set a dedicated key before real data exists); audit existing `role='admin'` users; real gateway refunds; run `move_kyc_files_to_private` if real KYC files exist; confirm how production serves public media.
- **Not verifiable here:** all frontend contracts; real push/SMS/email/Google/payment providers.
- **Known limitations:** the public share endpoint has no rate limiting; `S-09` (authorization failures are HTTP 400) is unchanged by design to avoid breaking clients; the pre-existing `values=` subset limitation remains.


---

## 14. Owner decisions on the open items — implemented (2026-10-03)

| Item | Decision | Result |
|---|---|---|
| S-14 contact change | **OTP step** | **FIXED.** `users/profile/update` no longer changes email/phone (400 if they differ from the current values; re-sending the current value is fine). New flow: `POST /users/contact/change/request/` (send exactly one of `email`/`phone_number`; a 6-digit code goes to the **new** contact, valid 10 min, 1 request/minute) then `POST /users/contact/change/verify/ {otp}`. The code is single-use and nulled on success, 5 wrong guesses burn it, uniqueness is re-checked at verify time, the login OTP and this code are separate and not interchangeable, and the user gets an in-app notification. Tests: `ContactChangeTest` (12) |
| Travel / return buffers | **Block neighbouring time** | **ENFORCED.** Each Home Visit booking occupies `[start − travelBefore, end + returnBuffer]` (the artist's settings, snapshotted at booking time) and two bookings conflict when those windows overlap. So back-to-back Home Visits need the earlier one's return time plus the later one's travel time; exactly touching windows are allowed. The same rule applies when rescheduling. Studio bookings carry no buffers of their own but still wait for a preceding Home Visit's return trip and leave travel time before a following one. Working-hours checks still apply to the appointment itself, not the buffers. Existing bookings without a snapshot count as zero. `GET /customers/artists/availability/` now also returns `blockedRanges`, `bufferBeforeMinutes`, `bufferAfterMinutes` (additive). Tests: `TravelBufferTest` (13) |
| Per-km travel charge | Stays refused ("Okay!") | Unchanged |
| Marketing Studio, service styles | Later | Not started |

Migration: `authentication/0003` (six nullable/defaulted columns on `User`), applied cleanly to a copy of `db.sqlite3`.
**Behaviour changes for the frontend:** (1) email/phone can no longer be edited through the profile screen's save — use the two new endpoints; (2) the booking calendar should use `blockedRanges` (plus the buffers) instead of `bookedRanges` to grey out unavailable times; (3) the buffer snapshot on a booking is now 0/0 for non-Home-Visit locations.
**Tests:** `manage.py test tests` → **Ran 739 tests — OK**; `makemigrations --check` → no changes. Edited existing tests: the profile-update email test (now asserts the direct change is refused).
**Known limits:** buffers are compared within the same calendar day (an appointment just after midnight is not checked against the previous evening); the contact-change request has a per-user throttle but no per-IP limit.
