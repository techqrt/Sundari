from decouple import config


class Configurations:
    db_name = config('DB_NAME')
    db_user = config('DB_USER')
    db_password = config('DB_PASSWORD')
    db_host = config('DB_HOST')
    db_port = config('DB_PORT')
    debug = False if config('DEBUG') == 'False' else True
    pagination_count = 10
    otp_expiry_minutes = 10
    otp_max_attempts = 3
    account_lockout_attempts = 5
    account_lockout_minutes = 30
    jwt_expiry_days = 7
    slot_lock_minutes = 15
    max_portfolio_items = 20
    max_saved_addresses = 5
    min_package_price = 500
    commission_min = 10
    commission_max = 25
    brevo_smtp_login = config('BREVO_SMTP_LOGIN')
    brevo_smtp_key = config('BREVO_SMTP_KEY')
    default_from_email = config('DEFAULT_FROM_EMAIL', default='noreply@sunndari.in')
    google_client_id = config('GOOGLE_CLIENT_ID', default='')
