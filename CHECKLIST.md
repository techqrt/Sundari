# SUNNDARI – Project Checklist & Action Items

> Legend: `[ ]` Not Started · `[~]` In Progress · `[x]` Done  
> Owner: **R** = Rayyan · **C** = Claude · **R+C** = Both

---

## Phase 0 — Project Setup

- [x] **R** — Share PMS project patterns and standards
- [x] **C** — Review PMS patterns and confirm understanding
- [x] **R+C** — Finalize folder/module structure based on PMS standards
- [x] **C** — Initialize Django project (`sunndari`)
- [x] **C** — Configure settings (base / dev / prod split)
- [x] **C** — Configure PostgreSQL database connection
- [x] **C** — Set up `requirements.txt` (DRF, psycopg2, JWT, Celery, pandas, etc.)
- [x] **C** — Set up `.env.example` and `python-decouple` configuration
- [x] **C** — Set up `common` infrastructure (utils, common, serializer_validations, swagger, exceptions, dataclasses, serializers)
- [x] **C** — Set up `activity_log` middleware (LogMiddleware)
- [x] **C** — Scaffold all app directories with full PMS folder structure
- [ ] **R** — Create `.env` from `.env.example` with DB credentials

---

## Phase 1 — Users & Authentication Module (`sunndari_apps/authentication` + `sunndari_apps/users`)

### 1.1 User Model
- [x] **C** — `User` model (phone, role, full_name, email, is_active, otp, otp_expiry, lockout fields)
- [x] **C** — `CustomerAddress` model (max 5 per user, is_default logic)

### 1.2 Phone OTP Authentication (same as PMS)
- [x] **C** — Phone OTP request endpoint (`POST /auth/phone-otp/request/`) — prints OTP to console (SMS stub)
- [x] **C** — Phone OTP verify & JWT issue endpoint (`POST /auth/phone-otp/verify/`)
- [x] **C** — OTP validity: 10 min, max 5 attempts, lockout after 5 fails (30 min)
- [x] **C** — Account lockout after 5 failed attempts (unlocks after 30 min)
- [x] **C** — SMS gateway stub (prints to console — wire up provider once confirmed)
- [ ] **R** — Confirm SMS gateway provider (Twilio / MSG91)

### 1.3 Email OTP Authentication
- [x] **C** — Email OTP request endpoint (`POST /auth/email-otp/request/`) — sends email via Brevo
- [x] **C** — Email OTP verify & JWT issue endpoint (`POST /auth/email-otp/verify/`)
- [x] **C** — Email sending integration via Brevo (SMTP, port 587, TLS)
- [x] **R** — Confirm email provider → Brevo

### 1.4 Username & Password Authentication
- [x] **C** — Register with username + password endpoint (`POST /auth/register/`)
- [x] **C** — Login with username + password endpoint (`POST /auth/login/`)
- [x] **C** — Password hashing (Django's `set_password` / `check_password`)

### 1.5 Google Authentication
- [x] **C** — Google OAuth2 login endpoint (`POST /auth/google/`)
- [x] **C** — Verify Google ID token via `google-auth` library
- [x] **C** — Auto-create user on first Google login; account linking by email
- [x] **C** — `google_id` field on User model
- [x] **C** — `google-auth` library integration (`id_token.verify_oauth2_token`)
- [ ] **R** — Provide Google OAuth2 Client ID & Secret *(credentials as `.env` placeholders for now)*

### 1.6 JWT & Session
- [x] **C** — JWT issued on all auth flows (phone OTP, email OTP, password, Google)
- [x] **C** — Refresh token endpoint (`POST /auth/token/refresh/`)
- [x] **C** — Token stored in DB, validated on every request (same as PMS)
- [x] **C** — Custom `JWTAuthentication` class (same pattern as PMS)

### 1.7 User Profile
- [x] **C** — Profile fetch endpoint (`GET /users/profile/get/`)
- [x] **C** — Profile update endpoint (`PUT /users/profile/update/`)
- [x] **C** — Address CRUD endpoints (`/users/address/create/`, `/update/`, `/delete/`, `/get/`, `/get_all/`)

### 1.8 Testing
- [x] **C** — Unit tests written (`tests/test_authentication.py`, `tests/test_users.py`, plus new `tests/test_customers.py` + `tests/test_notifications.py`, 235 tests total)
- [x] **C** — Ran `python manage.py test tests` against local SQLite (235/235 passing) — *R should still re-run once on Postgres to confirm parity*
- [x] **C** — Smoke-tested phone OTP flow end-to-end live (request → OTP in DB → verify → JWT issued)
- [ ] **R** — Test email OTP flow end-to-end (needs a real Brevo-deliverable inbox, not smoke-testable here)
- [x] **C** — Smoke-tested username/password register & login live
- [ ] **R** — Test Google login flow (needs a real Google ID token)
- [x] **C** — Smoke-tested JWT refresh live; lockout-after-5-fails not re-verified this session (covered by `test_authentication.py`)
- [x] **C** — Smoke-tested profile get/update and full address CRUD live

---

## Phase 2 — Lookup / Master Data Module (`apps/core`)

> All master data is seeded once at setup. Artists reference these tables — customers never manage them directly.

### 2.1 Service Category & Sub-Category
- [x] **C** — `ServiceCategory` model (name, description, is_active) + seeder with real categories
- [x] **C** — `ServiceSubCategory` model (category FK, name, description, is_active) + seeder
- [x] **C** — Admin registration for both models
- [ ] **R** — Verify seed data matches product requirements

**Seed data — Categories & Services:**
| Category | Services (Sub-Categories) |
|---|---|
| Bridal Makeup | Full Bridal Makeup, Engagement Makeup, Reception Makeup, Sangeet Makeup, Mehendi Ceremony Makeup, Bachelorette Makeup |
| Party & Occasion Makeup | Cocktail Party Makeup, Birthday Makeup, Festival Makeup, Corporate Event Makeup, Graduation Makeup |
| HD Makeup | HD Bridal Makeup, HD Party Makeup, HD Photoshoot Makeup |
| Airbrush Makeup | Airbrush Bridal Makeup, Airbrush Party Makeup, Airbrush Foundation |
| Hair Styling | Blow Dry & Setting, Curls & Waves, Bridal Hair Updo, Braid Styling, Hair Coloring & Highlights, Hair Smoothening / Keratin, Hair Spa |
| Nail Art & Extensions | Basic Nail Paint, Gel Nail Paint, Acrylic Extensions, Gel Extensions, Simple Nail Art, Detailed / 3D Nail Art, Nail Removal |
| Skincare & Facial | Basic Cleanup Facial, D-Tan Facial, Gold Facial, Diamond Facial, Anti-Aging Facial, Oxygen Facial |
| Pre-Bridal Packages | Basic Pre-Bridal (3 sessions), Premium Pre-Bridal (6 sessions), Deluxe Pre-Bridal (9 sessions) |
| Mehendi / Henna | Simple Mehendi, Bridal Mehendi (hands & feet), Arabic Mehendi, Rajasthani Mehendi |
| Saree Draping | Simple Saree Draping, Bridal Saree Draping, Lehenga Draping |

### 2.2 Location Type (Artist's Working Locations)
- [x] **C** — `LocationType` model (name, description, is_active) + seeder
- [x] **C** — Admin registration
- [ ] **R** — Verify seed data

**Seed data:**
| Value | Description |
|---|---|
| Home Visit | Artist travels to the customer's home |
| Salon / Studio | Customer visits the artist's salon or studio |
| Event Venue | Artist works at the event venue (wedding hall, hotel, etc.) |
| Outdoor / On-Location | Artist works at outdoor shoots or destination events |

### 2.3 Status Enums
- [x] **C** — `BookingStatus` model + seeder — scoped to customer→artist service booking
- [x] **C** — `PaymentStatus` model + seeder — scoped to customer payment for artist service
- [x] **C** — `ApprovalStatus` model + seeder — for artist profile verification by admin
- [x] **C** — Admin registration for all status tables

**Seed data (as actually implemented in `seed_core.py` — corrected 2026-07-28; this table previously listed an 8-status set that was never seeded):**

| BookingStatus | Description |
|---|---|
| pending | Booking request placed by customer, awaiting artist confirmation |
| confirmed | Artist has accepted and confirmed the booking |
| in_progress | Service is currently being delivered |
| completed | Service successfully delivered and booking closed |
| cancelled | Booking cancelled by customer or artist — see `Booking.cancelled_by` / `cancellation_reason` for who/why |
| no_show | Customer did not show up / was not reachable at the scheduled time |

> Only 6 statuses exist — no separate `accepted`/`rejected`, and no separate cancelled-by-customer vs cancelled-by-artist status. That distinction is tracked on the `Booking` model itself (`cancelled_by`, `cancellation_reason`), decided in Phase 4.3.

| PaymentStatus | Description |
|---|---|
| pending | Payment not yet initiated |
| paid | Full payment received successfully |
| partially_refunded | Partial refund issued to the customer |
| refunded | Full refund issued to the customer |
| failed | Payment attempt failed or declined |

> Also only 5 statuses seeded — no separate `partially_paid`. Revisit when building Phase 4.4 if partial/advance payment needs its own status.

| ApprovalStatus | Description |
|---|---|
| Pending | Artist submitted profile, awaiting admin review |
| Approved | Admin approved, artist visible on platform |
| Rejected | Admin rejected, reason provided |
| Suspended | Temporarily suspended by admin |

### 2.4 API Endpoints & Infrastructure
- [x] **C** — `GET /core/service-category/get/` — get by category_id
- [x] **C** — `GET /core/service-category/get_all/` — paginated list with search/filter/sort
- [x] **C** — `GET /core/service-sub-category/get/` — get by sub_category_id
- [x] **C** — `GET /core/service-sub-category/get_all/` — paginated list (filter by categoryId supported)
- [x] **C** — `GET /core/location-type/get/` — get by location_type_id
- [x] **C** — `GET /core/location-type/get_all/` — paginated list
- [x] **C** — `GET /core/booking-status/get_all/` — all booking statuses
- [x] **C** — `GET /core/payment-status/get_all/` — all payment statuses
- [x] **C** — `GET /core/approval-status/get_all/` — all approval statuses
- [x] **C** — Management command `seed_core` (idempotent, 10 categories, 66 services, 3 location types, 15 statuses)
- [x] **C** — `CoreUtils` mapper (snake_case DB → camelCase API)
- [x] **C** — `core/migrations/0001_initial.py`

### 2.5 Testing
- [x] **C** — Unit tests written (`tests/test_core.py`) — 42 tests, all passing
- [x] **C** — Ran `python manage.py seed_core` against local DB (10 categories, 66 sub-categories, 3 location types, 6 booking statuses, 5 payment statuses, 4 approval statuses)
- [ ] **R** — Verify categories and services via `/docs/` Swagger UI (verified via live API calls this session, not the Swagger UI itself)

---

## Phase 3 — Artist Module (`apps/artists`)

> **Design decisions (confirmed):**
> - `ArtistProfile` auto-created via `_create_role_instance(user)` in `authentication/views.py`, called right after `User.objects.create()` in the same `transaction.atomic()` block — mirrors PMS `_create_module_instance` pattern
> - All service FKs point to `ServiceSubCategory` only (category is always derivable via `sub_category__category_id`)
> - Portfolio uses Django `FileField` (stored in `MEDIA_ROOT`), no cloud storage, no thumbnail generation
> - Availability is recurring weekly schedule + specific date blocks (not single date/time slots)
> - 3.5 Booking (Artist side) and 3.6 Earnings deferred to Phase 4 (depend on Booking/Payment models)

### 3.1 Artist Profile
- [x] **C** — `ArtistProfile` model: `user` (OneToOne FK → `User`), `bio`, `years_experience`, `city`, `service_radius_km`, `avg_rating` (read-only, computed), `total_reviews` (read-only, computed), `commission_rate` (admin-set only), `approval_status` FK → `ApprovalStatus`
- [x] **C** — `_create_role_instance(user)` helper in `authentication/views.py`: called right after `User.objects.create()` inside the same `transaction.atomic()` block at every user-creation point (phone OTP verify first-time, email OTP verify first-time, register, Google first-time login) — mirrors PMS `_create_module_instance` pattern exactly
- [x] **C** — `ArtistProfile.create_for_user(user_id)` static method on the model — called by `_create_role_instance` when `user.role == 'artist'`
- [x] **C** — `ArtistServiceOffering` model: `artist` FK → `ArtistProfile`, `sub_category` FK → `ServiceSubCategory`, `custom_price`, `custom_duration_minutes`, `is_active`
- [x] **C** — `ArtistLocationPreference` model: `artist` FK → `ArtistProfile`, `location_type` FK → `LocationType`
- [x] **C** — `GET /artists/profile/get/` — get own profile (artist) or any profile by artist_id
- [x] **C** — `PUT /artists/profile/update/` — update bio, city, radius, years_experience; triggers re-approval if city/radius changed
- [x] **C** — `POST /artists/services/add/` — add a service offering
- [x] **C** — `DELETE /artists/services/remove/` — remove a service offering (triggers re-approval)
- [x] **C** — `GET /artists/services/get_all/` — list own service offerings
- [x] **C** — `POST /artists/locations/add/` — add a location preference
- [x] **C** — `DELETE /artists/locations/remove/` — remove a location preference
- [x] **C** — `GET /artists/locations/get_all/` — list own location preferences
- [x] **R** — Test artist profile auto-creation on registration
- [x] **R** — Test profile update and re-approval trigger

### 3.2 Portfolio Management
- [x] **C** — `Portfolio` model: `artist` FK → `ArtistProfile`, `file` (`FileField`, stored in `MEDIA_ROOT/portfolios/`), `media_type` (choices: `image` / `video`), `sub_category` FK → `ServiceSubCategory`, `caption`, `approval_status` FK → `ApprovalStatus`, `is_active`
- [x] **C** — Max 20 active items per artist enforced on create
- [x] **C** — `POST /artists/portfolio/create/` — upload file (multipart)
- [x] **C** — `PUT /artists/portfolio/update/` — update caption, sub_category, is_active
- [x] **C** — `DELETE /artists/portfolio/delete/` — delete portfolio item
- [x] **C** — `GET /artists/portfolio/get/` — get single item
- [x] **C** — `GET /artists/portfolio/get_all/` — paginated list, filterable by media_type / sub_category
- [x] **R** — Test file upload, max limit, and get_all filtering

### 3.3 Pricing Packages
- [x] **C** — `PricingPackage` model: `artist` FK → `ArtistProfile`, `sub_category` FK → `ServiceSubCategory`, `name`, `price` (≥ ₹500 enforced), `duration_minutes`, `description`, `is_active`
- [x] **C** — `PackageInclusion` model: `package` FK → `PricingPackage`, `inclusion_text`, `order`
- [x] **C** — `POST /artists/packages/create/` — create package with inclusions
- [x] **C** — `PUT /artists/packages/update/` — update package + replace inclusions
- [x] **C** — `DELETE /artists/packages/delete/`
- [x] **C** — `GET /artists/packages/get/` — get single package with inclusions
- [x] **C** — `GET /artists/packages/get_all/` — paginated list
- [x] **C** — Enforce ≥1 active package for artist profile to be publicly visible
- [x] **R** — Test price validation (< ₹500 rejected), inclusion create/update, ≥1 enforcement

### 3.4 Availability Management
- [x] **C** — `ArtistAvailabilitySchedule` model: `artist` FK → `ArtistProfile`, `day_of_week` (0=Mon … 6=Sun), `start_time`, `end_time`, `location_type` FK → `LocationType`, `is_active`
- [x] **C** — `ArtistAvailabilityBlock` model: `artist` FK → `ArtistProfile`, `block_date` (`DateField`), `note` (optional) — specific date override (artist unavailable despite recurring schedule)
- [x] **C** — `POST /artists/availability/schedule/set/` — create or replace a day's recurring slot
- [x] **C** — `DELETE /artists/availability/schedule/remove/`
- [x] **C** — `GET /artists/availability/schedule/get_all/` — list all recurring slots
- [x] **C** — `POST /artists/availability/block/add/` — block a specific date
- [x] **C** — `DELETE /artists/availability/block/remove/`
- [x] **C** — `GET /artists/availability/block/get_all/` — list all blocked dates
- [x] **R** — Test schedule set, block add, and overlap detection

### 3.5 Booking Management (Artist Side)
- [x] **C** — `GET /artists/bookings/get/` — get single booking belonging to own artist profile
- [x] **C** — `GET /artists/bookings/get_all/` — list all bookings for own artist profile
- [x] **C** — `PUT /artists/bookings/update_status/` — artist drives the state machine: `pending`→`confirmed`/`cancelled`, `confirmed`→`in_progress`/`cancelled`, `in_progress`→`completed`/`no_show`
- [x] **C** — Smoke-tested artist confirm/in_progress/completed flow live, plus invalid-transition rejection (400)

### 3.6 Earnings Dashboard — *Deferred to Phase 4*
> Depends on `Payment` model. Will implement alongside Phase 4.4.

---

## Phase 4 — Customer Module (`apps/customers`)

> **Design decisions (confirmed 2026-07-28):**
> - No lat/lng anywhere (`ArtistProfile`, `CustomerAddress`) and no PostGIS installed (`django.contrib.gis` not in `INSTALLED_APPS`, plain `postgresql` DB engine). 4.1's "distance" filter is city string-match only until a geocoding/PostGIS decision is made.
> - No cloud storage provider chosen yet, so 4.2's portfolio media URLs are the raw stored path (same as `portfolio/get_all/` today) — not signed, no expiry. Revisit once S3/GCS is picked.
> - BookingStatus only has 6 values (see Phase 2.3, corrected) — artist "reject" and any cancellation both land on `cancelled`; who/why is tracked via `Booking.cancelled_by` + `cancellation_reason`, not via status name.
> - Auto-cancel (4.3) cancels any booking still `pending` 15 min after creation, regardless of payment — there's no `Payment` model yet to check real payment status against. Revisit once Phase 4.4 lands.
> - Artist drives the booking state machine (accept/reject/start/complete/no-show via `PUT /artists/bookings/update_status/`); customer can only cancel from `pending`/`confirmed`/`in_progress` via `PUT /customers/bookings/cancel/`.

### 4.1 Search & Discovery
- [x] **C** — Search artists endpoint (`GET /customers/artists/search/`) with filters: city, category_id/sub_category_id, min_price/max_price, min_rating
- [x] **C** — City string-match filter (PostGIS deferred — see design decisions above)
- [x] **C** — Pagination + sorting (rating default / price / experience / name)
- [x] **C** — Only approved artists with ≥1 active package in results
- [x] **C** — Smoke-tested search live: city filter (incl. multi-word values, see the query-parsing bugfix below), pagination, sort_by/sort_order, approved+active-package gating

### 4.2 Artist Profile View (Customer Side)
- [x] **C** — Artist detail endpoint (`GET /customers/artists/get/?artist_id=`) — consolidated profile + active packages + active portfolio + active services in one response
- [ ] **C** — CDN signed URL generation for portfolio media (1hr expiry) — *blocked on cloud storage decision, see Pending Decisions*
- [x] **C** — Smoke-tested consolidated detail endpoint live (profile + packages + portfolio + services); "media loading" itself untestable until real storage/signed URLs exist

### 4.3 Booking System (Customer books Artist's Service)
- [x] **C** — `Booking` model (customer FK, artist FK, sub_category FK, package FK, location_type FK, address FK, booking_date, start_time, end_time, status FK, total_amount, notes, cancelled_by, cancellation_reason, expires_at)
- [x] **C** — Check artist availability endpoint (`GET /customers/artists/availability/`) — working window + blocked-day flag + already-booked ranges for a given date
- [x] **C** — Create booking endpoint (`POST /customers/bookings/create/`) — atomic, validates package/location/schedule/block/overlap, 15-min slot lock (`expires_at`)
- [x] **C** — Booking state machine: pending → confirmed → in_progress → completed / cancelled / no_show (see design decisions above for the status-set correction)
- [x] **C** — Auto-cancel stale pending bookings after 15 min (Celery task `cancel_stale_pending_bookings`, beat schedule every 60s) — also required bootstrapping `sunndari/celery.py` + `CELERY_BEAT_SCHEDULE`, which didn't exist before
- [x] **C** — List customer bookings (`GET /customers/bookings/get_all/`)
- [x] **C** — Get booking detail (`GET /customers/bookings/get/`)
- [x] **C** — Cancel booking endpoint (`PUT /customers/bookings/cancel/`)
- [x] **C** — Smoke-tested full booking creation flow live (schedule/location/block validation, real slot lock)
- [x] **C** — Smoke-tested double-booking prevention live (second customer rejected with `double_booking` on the identical slot)
- [ ] **R** — Provision Redis and run a Celery worker + beat process so the auto-cancel task actually fires

### 4.4 Payment (Customer pays for Artist Service)
> **Scope decision (2026-07-28):** built model + endpoints skeleton only, gateway-agnostic. Real Razorpay/PayU order creation, signature verification, and refund API calls are explicitly NOT implemented — every gateway touchpoint is a clearly-marked stub to be plugged in once **R** confirms the provider and hands over credentials.
- [ ] **R** — Confirm payment gateway (Razorpay / PayU)
- [x] **C** — `Payment` model (booking FK, customer FK, artist FK, payment_type, amount, commission_amount, artist_payout_amount, status FK → `PaymentStatus`, gateway, gateway_order_id, gateway_payment_id, paid_at, failure_reason)
- [x] **C** — Initiate payment endpoint (`POST /customers/payments/initiate/`) — validates booking ownership/status and remaining due, computes commission split, creates a `Payment` row with a **placeholder** `gateway_order_id` (`PENDING-<uuid>`) — swap for the real gateway's create-order call once chosen
- [x] **C** — Payment webhook handler (`POST /customers/payments/webhook/`) — **STUB**: generic `{gateway_order_id, gateway_payment_id, status}` payload, `AllowAny`, **no signature verification** (can't verify a signature scheme that doesn't exist yet) — this must not go live before real gateway signature verification is added
- [x] **C** — `GET /customers/payments/get/` `get_all/` — customer's own payment history
- [x] **C** — Commission auto-deduction: `commission_amount`/`artist_payout_amount` computed and stored at `initiate` time from `ArtistProfile.commission_rate`
- [x] **C** — Advance payment support: `payment_type` (`full`/`advance`/`balance`) on the model; `Payment.total_paid_for_booking()` tracks running total against `Booking.total_amount` — no advance-percentage policy is set, caller passes an explicit `amount` for now
- [x] **C** — Refund trigger on cancellation: both cancel paths (`customers/bookings/cancel/` and `artists/bookings/update_status/`→`cancelled`) call `Payment.mark_refunded()`, which flips any `paid` payment on that booking to `refunded` — **full refund only, no policy tiers, no actual gateway refund call** (all stubbed pending cancellation policy + gateway choice)
- [x] **C** — Auto-cancel task revisited: `cancel_stale_pending_bookings` now excludes bookings with a `paid` Payment, so a paid-but-not-yet-artist-confirmed booking won't be swept up by the 15-min timer
- [x] **C** — Smoke-tested initiate + webhook stub live (commission split exact on ₹1500 → ₹150/₹1350, webhook processed with zero auth headers as a real gateway callback would send, over-amount correctly rejected)
- [ ] **R** — Test payment initiation and webhook against the *real* gateway sandbox (blocked until a gateway is chosen)

### 4.5 Reviews & Ratings
- [x] **C** — `Review` model (booking OneToOne, customer FK, artist FK, rating 1–5, comment)
- [x] **C** — Submit review endpoint (`POST /customers/reviews/create/`) — only after `completed` status (`Constants.booking_not_completed` otherwise)
- [x] **C** — One review per booking enforcement — explicit check (`Constants.booking_already_reviewed`) plus DB-level `OneToOneField` on `booking`
- [x] **C** — Incremental average rating calculation on artist profile — `ArtistProfile.record_review()`, atomic with `select_for_update` to avoid a race between two simultaneous reviews
- [x] **C** — `GET /customers/reviews/get/` `get_all/` — get_all filters by `artist_id` (reuses the shared `GetAll`/`GetAllSerializer` artist_id field added earlier, no bespoke serializer needed)
- [x] **C** — Smoke-tested submission + duplicate rejection + incremental average rating live (verified `avgRating` update on `ArtistProfile` after submission)

---

## Phase 5 — Notifications Module (`apps/notifications`)

> **Scope decision (2026-07-28):** same shape as Phase 4.4 — gateway-agnostic skeleton only. Every notify() call already writes a `Notification` row (so in-app history/list works today), but no real push is sent: `NotificationGateway.send()` is a stub returning `success: False` until an FCM project is confirmed and `firebase-admin` is wired in.
- [x] **C** — `Notification` model (user FK, booking FK, type, title, message, is_read, delivery_status, fcm_message_id, failure_reason, sent_at)
- [x] **C** — `NotificationGateway`/`NotificationService` in `notifications/utils.py` — the single plug-in point for the real FCM call; every event hook below goes through `NotificationService.notify()`, not a direct gateway call, so wiring FCM later is a one-file change
- [x] **C** — `GET /notifications/get/` `get_all/`, `PUT /notifications/mark_read/` `mark_all_read/`
- [x] **C** — Booking confirmation notification — hooked into `ArtistBookingView.update_status_extract` when status → `confirmed`
- [x] **C** — Payment status change notification — hooked into `PaymentWebhookView.webhook_extract` for both `paid` and `failed`
- [x] **C** — New booking alert for artist — hooked into `CreateBookingView.create_extract`, notifies `artist.user_id` after the booking transaction commits
- [x] **C** — 24hr and 2hr appointment reminder (Celery beat task `send_appointment_reminders`, every 10 min) — scans `confirmed` bookings, matches a ±10min window around the 24h/2h mark, dedupes via `Notification.exists_for_booking()` so re-runs don't double-send
- [ ] **R** — Confirm FCM project + provide credentials
- [ ] **R** — Test push notifications on device (blocked until FCM is wired)
- [ ] **R** — Provision Redis and run Celery worker + beat so both scheduled tasks (this one and the Phase 4.3 auto-cancel) actually fire

---

## Phase 6 — Admin Module (`apps/admin_panel`)

- [ ] **C** — RBAC setup (admin role enforcement on all admin endpoints)
- [ ] **C** — List/search users endpoint (`GET /admin/users`)
- [ ] **C** — Approve/reject artist endpoint (`PUT /admin/artists/{id}/approve`)
- [ ] **C** — Monitor all bookings endpoint (`GET /admin/bookings`)
- [ ] **C** — Force cancel/refund endpoint (`PUT /admin/bookings/{id}/refund`)
- [ ] **C** — Portfolio moderation endpoint (`POST /admin/portfolios/{id}/moderate`)
- [ ] **C** — Commission configuration (global + per-artist override)
- [ ] **C** — Revenue report endpoint (`GET /admin/reports/revenue`) — CSV/PDF export
- [ ] **C** — `AuditLog` model + auto-logging on critical admin actions
- [ ] **R** — Test all admin flows

---

## Phase 7 — Cross-Cutting Concerns

- [ ] **C** — Global exception handler and standard response format `{ success, data, message, error_code }` (existing `Common.exception_handler` mostly covers this — see the `ProtectedError` gap noted below)
- [ ] **C** — Input validation (serializers + custom validators)
- [x] **C** — Celery + Redis setup (async tasks: slot auto-cancel, reminders) — `sunndari/celery.py` app + `CELERY_BEAT_SCHEDULE` bootstrapped; both the Phase 4.3 auto-cancel task and the Phase 5 reminder task are wired into the schedule (still needs **R** to actually run a Redis broker + worker + beat process, see those items above)
- [x] **C** — Database indexes (bookings_customer, bookings_artist, booking_date) — added on the `Booking` model in Phase 4.3; `portfolios_artist`/`availability_artist_date` not yet added
- [ ] **C** — PostGIS spatial index for location-based search — *blocked on the same PostGIS decision as Phase 4.1*
- [x] **C** — **Bugfix (2026-07-29):** `Utils.get_query_params()`/`extract_params()` in `sunndari_apps/common/utils.py` did naive `.split('?')`/`.split('&')`/`.split('=')` with no URL-decoding — any GET query param containing a space (`search_key`, `filter_value`, `city`, etc., on *every* `get_all` endpoint app-wide) silently matched zero rows instead of erroring. Fixed with `urllib.parse.urlsplit` + `unquote_plus`; also fixes a latent crash on values containing a literal `=`. Verified live against both originally-broken cases; full suite (235 tests) still green.
- [ ] **C** — **Known issue (found 2026-07-29, not yet fixed):** deleting a row still referenced by an `on_delete=PROTECT` FK (e.g. a `CustomerAddress` used by a `Booking`) returns a raw Python exception repr instead of a clean error — `Common.exception_handler` only string-matches `'foreign key constraint'` (a raw DB `IntegrityError` phrasing), not Django's `ProtectedError` wording ("referenced through protected foreign keys"). Affects every `PROTECT` relationship in the app.
- [ ] **R** — Review indexes and performance test search queries

---

## Phase 8 — API Documentation & Testing

- [ ] **C** — OpenAPI 3.0 / Swagger UI setup (`/docs`)
- [ ] **C** — Unit tests for all serializers and models
- [ ] **C** — Integration tests for all endpoints
- [ ] **C** — Auth flow tests (OTP, lockout, token refresh)
- [ ] **C** — Booking flow end-to-end test (slot lock, payment, commission)
- [ ] **R** — Review API docs and test coverage report
- [ ] **R** — UAT — full customer booking flow (< 5 minutes target)
- [ ] **R** — UAT — artist profile + booking accept/reject
- [ ] **R** — UAT — admin approval and moderation

---

## Phase 9 — Deployment

- [ ] **R** — Provision cloud server and database
- [ ] **C** — Dockerfile + docker-compose setup
- [ ] **C** — Environment-based settings (dev/staging/prod)
- [ ] **C** — CI/CD pipeline setup
- [ ] **C** — Database migration scripts execution
- [ ] **C** — Seed lookup tables (service_categories, statuses, location_types)
- [ ] **R** — Configure domain + SSL (`api.sunndari.in`)
- [ ] **R** — Smoke test on production environment

---

## Pending Decisions (Blocked — Needs Rayyan's Input)

- [x] **R** — Share PMS project patterns and standards *(Phase 0 complete)*
- [ ] **R** — Confirm SMS gateway provider (Twilio / MSG91)
- [ ] **R** — Confirm cloud storage provider (AWS S3 / GCS / other)
- [ ] **R** — Confirm payment gateway (Razorpay / PayU)
- [ ] **R** — Provide FCM project credentials
- [ ] **R** — Provide seed data for service_categories
