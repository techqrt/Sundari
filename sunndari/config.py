from decouple import config


class Configurations:
    db_name = config('DB_NAME')
    db_user = config('DB_USER')
    db_password = config('DB_PASSWORD')
    db_host = config('DB_HOST')
    db_port = config('DB_PORT')
    # Strictly parsed (True/False/1/0/yes/no/on/off, case-insensitive; anything else raises at
    # startup). It used to be `False if value == 'False' else True`, so a typo such as
    # DEBUG=false silently turned debug ON in production.
    debug = config('DEBUG', cast=bool)
    pagination_count = 10
    otp_expiry_minutes = 10
    otp_max_attempts = 3
    account_lockout_attempts = 5
    account_lockout_minutes = 30
    jwt_expiry_days = 7
    slot_lock_minutes = 15
    on_my_way_window_hours = 2
    min_booking_advance_hours = 2
    booking_missed_grace_hours = 2
    reschedule_response_hours = 24
    # An unpaid payment order older than this is considered abandoned (it no longer blocks a new one).
    payment_pending_window_minutes = 30
    # Version of the partner Terms + Privacy Policy an artist accepts; bump when the text changes.
    agreement_version = '1.0'
    # Public legal/contact info shown in the apps; empty until configured in the environment.
    terms_url = config('TERMS_URL', default='')
    privacy_url = config('PRIVACY_URL', default='')
    contact_email = config('CONTACT_EMAIL', default='')
    contact_phone = config('CONTACT_PHONE', default='')
    max_portfolio_items = 20
    max_saved_addresses = 5
    min_package_price = 500
    commission_min = 10
    commission_max = 25
    brevo_smtp_login = config('BREVO_SMTP_LOGIN')
    brevo_smtp_key = config('BREVO_SMTP_KEY')
    default_from_email = config('DEFAULT_FROM_EMAIL', default='noreply@sunndari.in')
    google_client_id = config('GOOGLE_CLIENT_ID', default='')
    chat_message_max_length = 2000
    firebase_credentials_path = config('FIREBASE_CREDENTIALS_PATH', default='')
    razorpay_key_id = config('RAZORPAY_KEY_ID')
    razorpay_key_secret = config('RAZORPAY_KEY_SECRET')
    razorpay_currency = 'INR'
