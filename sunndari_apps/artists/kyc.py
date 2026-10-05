import re

ID_TYPES = ('aadhaar', 'voter_id', 'passport', 'driving_licence')

# Patterns are applied to the normalised number (upper-case, spaces and hyphens removed).
ID_NUMBER_PATTERNS = {
    'aadhaar': re.compile(r'^[2-9]\d{11}$'),
    'voter_id': re.compile(r'^[A-Z]{3}\d{7}$'),
    'passport': re.compile(r'^[A-PR-WY][1-9]\d\d{4}[1-9]$'),
    'driving_licence': re.compile(r'^[A-Z]{2}\d{2}(19|20)\d{2}\d{7}$'),
}
ID_NUMBER_ERRORS = {
    'aadhaar': 'Aadhaar number must be 12 digits and cannot start with 0 or 1',
    'voter_id': 'Voter ID must be 3 letters followed by 7 digits',
    'passport': 'Invalid passport number format',
    'driving_licence': 'Invalid driving licence number format',
}
# The back of the card carries required information for these; a passport is validated
# from the photo page alone.
BACK_IMAGE_REQUIRED = ('aadhaar', 'voter_id', 'driving_licence')


def normalise_id_number(raw: str) -> str:
    return re.sub(r'[\s-]', '', raw or '').upper()


def validate_id_number(id_type: str, raw: str) -> str:
    number = normalise_id_number(raw)
    if not ID_NUMBER_PATTERNS[id_type].match(number):
        raise ValueError(ID_NUMBER_ERRORS[id_type])
    return number


def mask_number(number: str) -> str:
    if not number or len(number) <= 4:
        return 'XXXX'
    return 'X' * (len(number) - 4) + number[-4:]
