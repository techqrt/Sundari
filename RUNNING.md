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
