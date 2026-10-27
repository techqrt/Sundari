import html
import logging
import smtplib
import ssl

import certifi
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend
from django.utils.functional import cached_property

logger = logging.getLogger(__name__)

BRAND = 'SUNNDARI'


class CertifiSMTPEmailBackend(DjangoSMTPEmailBackend):
    """Django's SMTP backend, verifying the mail server's certificate against the `certifi` bundle instead of the
    operating system's store. Verification stays fully on; only the list of trusted authorities is made independent
    of the host. This matters because some Python builds (the python.org build on macOS, minimal containers) ship
    with no trusted certificates at all, and every email then fails with a certificate error."""

    @cached_property
    def ssl_context(self):
        if self.ssl_certfile or self.ssl_keyfile:                       # a client certificate was configured
            return super().ssl_context
        return ssl.create_default_context(cafile=certifi.where())


class EmailDeliveryError(Exception):
    """The mail server did not accept the message (or could not be reached). Carries no credentials, address or
    message text: the underlying exception is dropped on purpose, and only its class is logged."""


def send_email(to: str, subject: str, text: str, html_body: str = None, tag: str = None) -> None:
    """Sends one email through the configured SMTP relay (Brevo). Raises EmailDeliveryError on any failure, never
    anything else, so callers have one thing to handle. `tag` is a Brevo category (X-Mailin-Tag) used to group
    messages in its reports."""
    message = EmailMultiAlternatives(subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=[to])
    if html_body:
        message.attach_alternative(html_body, 'text/html')
    if tag:
        message.extra_headers['X-Mailin-Tag'] = tag
    try:
        sent = message.send(fail_silently=False)
    except (smtplib.SMTPException, OSError, ValueError) as error:       # OSError covers timeouts and connection errors
        logger.warning('Email delivery failed: %s (smtp code %s)', type(error).__name__, getattr(error, 'smtp_code', None))
        raise EmailDeliveryError() from None
    if not sent:
        logger.warning('Email delivery failed: the server accepted no recipient')
        raise EmailDeliveryError()


# ─── Message layout ───────────────────────────────────────────────────────────

def _render(heading: str, paragraphs: list, code: str = None, footer: str = '') -> tuple:
    """(plain text, HTML) for one message. Everything dynamic is escaped. The HTML is a single column with inline
    styles, which is what mail clients support, and uses no remote images."""
    text_lines = [heading, ''] + paragraphs + ([''] + [f'    {code}', ''] if code else []) + ['', f'-- {BRAND}'] + ([footer] if footer else [])
    esc = html.escape
    body = ''.join(f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#2b3340">{esc(p)}</p>' for p in paragraphs)
    code_block = (
        f'<p style="margin:8px 0 24px;font-size:32px;letter-spacing:8px;font-weight:700;color:#7a1f5c;'
        f'font-family:Menlo,Consolas,monospace">{esc(code)}</p>' if code else ''
    )
    footer_html = f'<p style="margin:24px 0 0;font-size:12px;line-height:1.5;color:#7b8594">{esc(footer)}</p>' if footer else ''
    page = (
        '<!doctype html><html><body style="margin:0;padding:24px 12px;background:#f3f4f7;'
        'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;background:#ffffff;border-radius:10px;padding:28px">'
        f'<tr><td><p style="margin:0 0 20px;font-size:13px;font-weight:700;letter-spacing:3px;color:#7a1f5c">{esc(BRAND)}</p>'
        f'<h1 style="margin:0 0 16px;font-size:20px;line-height:1.3;color:#131c29">{esc(heading)}</h1>'
        f'{body}{code_block}{footer_html}</td></tr></table></td></tr></table></body></html>'
    )
    return '\n'.join(text_lines), page


def otp_message(otp: int, valid_minutes: int, purpose: str = None) -> tuple:
    """(subject, text, html) for a one-time code. `purpose` says what the code is for ("change the email address on
    your SUNNDARI account"), so the reader can tell a code they asked for from one they did not."""
    text, page = _render(
        heading='Your verification code',
        paragraphs=[f'Use this code to {purpose or "continue"}. It is valid for {valid_minutes} minutes and can be used once.'],
        code=str(otp),
        footer='If you did not ask for this code, you can ignore this email. Never share it with anyone, including us.',
    )
    return f'Your {BRAND} verification code', text, page


def notification_message(title: str, message: str) -> tuple:
    """(subject, text, html) for an account notification sent by email."""
    text, page = _render(
        heading=title,
        paragraphs=[message],
        footer='You are receiving this because it concerns your SUNNDARI account.',
    )
    return title, text, page


def mask_email(email: str) -> str:
    """'asha.rao@example.com' -> 'a***@example.com': enough to recognise, not enough to harvest."""
    local, _, domain = email.partition('@')
    return f'{local[:1]}***@{domain}' if domain else '***'


def email_changed_message(new_email_masked: str) -> tuple:
    """(subject, text, html) for the warning sent to the OLD address after an account's email was changed."""
    text, page = _render(
        heading='Your email address was changed',
        paragraphs=[
            f'The email address on your SUNNDARI account was changed to {new_email_masked}.',
            'If you made this change, no action is needed. If you did not, contact support right away.',
        ],
        footer='This message was sent to the address that was on your account before the change.',
    )
    return 'Your SUNNDARI email address was changed', text, page
