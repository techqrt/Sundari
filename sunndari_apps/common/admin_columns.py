from django.contrib import admin

EMPTY = '—'


def related_column(label: str, *paths: str, ordering: str = None):
    """An admin list column that shows a value reached through relations, so a row reads "Asha Verma" instead of
    "Artist #29". Each path is tried in order and the first non-empty value is shown (e.g. a user's name, then their
    phone number for someone who signed up without one). The column sorts by the first path.

        artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')"""
    def column(self, obj):
        for path in paths:
            value = obj
            for part in path.split('__'):
                value = getattr(value, part, None)
                if value is None:
                    break
            if value not in (None, ''):
                return value
        return EMPTY
    return admin.display(description=label, ordering=ordering or paths[0])(column)


def preview_column(label: str, field: str, length: int = 60):
    """The start of a long text field, so a list row stays one line."""
    def column(self, obj):
        text = (getattr(obj, field, None) or '').strip().replace('\n', ' ')
        if not text:
            return EMPTY
        return text if len(text) <= length else text[:length].rstrip() + '…'
    return admin.display(description=label, ordering=field)(column)
