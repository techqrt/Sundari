# SUNNDARI — Setup & Running Guide (Phase 1)

## 1. Create Virtual Environment

```bash
cd /Users/rayyanshaikh/VSProjects/sundari
python3 -m venv venv
source venv/bin/activate
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## 3. Create `.env` File

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
DEBUG=True

# Database (PostgreSQL)
DB_NAME=sunndari_db
DB_USER=your_postgres_user
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432

# Brevo (Email OTP)
BREVO_SMTP_LOGIN=your_brevo_login@example.com
BREVO_SMTP_KEY=your_brevo_smtp_key
DEFAULT_FROM_EMAIL=noreply@sunndari.in

# Google OAuth2
GOOGLE_CLIENT_ID=your_google_client_id
```

## 4. Create Database

```bash
psql -U postgres
CREATE DATABASE sunndari_db;
\q
```

## 5. Run Migrations

```bash
python manage.py makemigrations authentication
python manage.py makemigrations users
python manage.py migrate
```

## 6. Create Django Superuser (optional — for admin panel access)

```bash
python manage.py createsuperuser
```

## 7. Run Development Server

```bash
python manage.py runserver
```

---

## 8. Test Endpoints

Swagger UI: http://127.0.0.1:8000/docs/

### Auth — Phone OTP
```
POST /auth/phone-otp/request/
{ "phone_number": "+919876543210", "role": "customer" }

POST /auth/phone-otp/verify/
{ "phone_number": "+919876543210", "otp": "123456" }
```
> OTP is printed to the console (SMS not wired yet).

### Auth — Email OTP
```
POST /auth/email-otp/request/
{ "email": "test@example.com", "role": "customer" }

POST /auth/email-otp/verify/
{ "email": "test@example.com", "otp": "123456" }
```

### Auth — Register & Login (Password)
```
POST /auth/register/
{ "name": "Test User", "email": "test@example.com", "password": "password123", "role": "customer" }

POST /auth/login/
{ "username": "test@example.com", "password": "password123" }
```

### Auth — Google
```
POST /auth/google/
{ "id_token": "<google_id_token>", "role": "customer" }
```

### Auth — Token Refresh
```
POST /auth/token/refresh/
{ "refresh_token": "<refresh_token>" }
```

### Profile (requires `Authorization: Bearer <token>` header)
```
GET  /users/profile/get/
PUT  /users/profile/update/
     { "name": "New Name" }
```

### Address (requires `Authorization: Bearer <token>` header)
```
POST   /users/address/create/
       { "address_line_1": "123 Main St", "city": "Mumbai", "pin_code": "400001", "is_default": true }

PUT    /users/address/update/
       { "address_id": 1, "city": "Delhi" }

DELETE /users/address/delete/?address_id=1

GET    /users/address/get/?address_id=1

GET    /users/address/get_all/
```

---

## Expected Response Format

```json
{
  "status": true,
  "message": "...",
  "data": { ... }
}
```

Error:
```json
{
  "status": false,
  "message": "...",
  "error": ["..."]
}
```

---

## Production checklist

These only matter when `DEBUG=False`. In that mode the app **refuses to start** unless the first four are set.

| Variable | Why |
|---|---|
| `SECRET_KEY` | 50+ random characters. It signs every login token. Generate: `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"` |
| `FIELD_ENCRYPTION_KEY` | Fernet key for ID numbers and bank details, kept separate from `SECRET_KEY` so rotating one never locks you out of the other. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. To rotate: put the new key first, a comma, then the old one; drop the old one once nothing uses it. |
| `ALLOWED_HOSTS` | Comma-separated hostnames. |
| `THROTTLE_NUM_PROXIES` | Reverse proxies / load balancers in front of the app (`0` if none). Wrong values either let attackers dodge rate limits or put all users in one bucket. |
| `CORS_ALLOWED_ORIGINS` | Web origins allowed (the admin dashboard). The mobile apps need none. |
| `REDIS_URL` | Shared cache for the rate-limit counters (defaults to `redis://localhost:6379/1`). |

Changing `SECRET_KEY` on a running system signs everyone out. Do it once, before launch, or schedule it.

### Background jobs (Celery) — required, not optional

Payments, refunds and booking expiry depend on these running. Start **both**:

```bash
celery -A sunndari worker -l info
celery -A sunndari beat -l info
```

| Job | Every | What it protects |
|---|---|---|
| `payments.tasks.retry_owed_refunds` | 5 min | Retries refunds the gateway rejected, with backoff, then alerts the admins. |
| `payments.tasks.reconcile_pending_payments` | 10 min | Settles payments the customer paid but the app never confirmed. |
| `customers.tasks.cancel_stale_pending_bookings` | 1 min | Releases unpaid slot locks and returns redeemed coins. |
| `customers.tasks.mark_missed_bookings` | 5 min | Marks bookings nobody turned up for. |
| `wallet.tasks.expire_lapsed_coins` | daily | Expires old cashback coins. |

If beat is not running, none of these happen. `python manage.py retry_refunds` runs the refund retry by hand.

### Payment webhook

1. In the Razorpay dashboard add a webhook to `https://<your-host>/customers/payments/webhook/razorpay/`
   with events `payment.captured`, `refund.processed`, `refund.failed`, and choose a secret.
2. Put the same value in `RAZORPAY_WEBHOOK_SECRET`.

Until the secret is set the endpoint refuses every request (nothing unsigned is ever accepted). The customer
app's `/verify/` call keeps working either way; the webhook covers the app being closed right after paying.

### Never commit the database

`db.sqlite3` holds real phone numbers, password hashes and login tokens, and is now git-ignored. If it was ever
pushed, treat what it held as exposed: sign everyone out (`python manage.py revoke_all_sessions`) and, if the
repository is or was public, purge it from history (`git filter-repo --path db.sqlite3 --invert-paths`, then a
coordinated force-push) — deleting the file in a new commit does not remove it from earlier ones.

### Email (Brevo SMTP)

Sign-in codes, password-reset codes, email-change codes and the email copy of account notifications go out through
Brevo's SMTP relay (`smtp-relay.brevo.com`, port 587, TLS). Set `BREVO_SMTP_LOGIN`, `BREVO_SMTP_KEY` (the **SMTP key**,
not an API key) and `DEFAULT_FROM_EMAIL` in `.env`. Never put them in code or commit them.

Brevo has three account-side requirements; none can be done from the code:

1. **Authorised IPs.** If Brevo's *Security → Authorised IPs* is on (the default for newer accounts), SMTP from any other
   address fails with `525 5.7.1 Unauthorized IP address`. Add the public IP of every machine that sends mail, or turn the
   restriction off. A production server needs a **static** IP; a home or office connection changes address and will break.
2. **A verified sender.** `DEFAULT_FROM_EMAIL` must be a sender or domain verified in Brevo (*Senders, Domains & Dedicated
   IPs*). Brevo refuses mail from an unverified address.
3. **Domain authentication** for `sunndari.in`: the SPF, DKIM and DMARC records Brevo shows for the domain, so codes reach
   the inbox instead of spam.

Check delivery end to end (sends one real email to the address you give):

```bash
python manage.py send_test_email you@example.com
```

Which notifications are emailed (transactional only: booking, payment, refund, approval, support updates) is the list in
`sunndari_apps/notifications/email_channel.py`; codes/PINs, live job updates, chat and the promotional “new service”
notice are never emailed. `EMAIL_NOTIFICATIONS_ENABLED=False` turns the whole channel off. Email jobs run on the Celery
worker, like the other background jobs above.

