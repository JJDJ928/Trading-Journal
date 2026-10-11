"""Input parsing that collects friendly per-field errors instead of crashing."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_MONEY_CENTS = 100_000_000_000  # $1 billion, a sanity cap


class ValidationError(Exception):
    def __init__(self, errors):
        if isinstance(errors, str):
            errors = {"_": errors}
        self.errors = errors
        super().__init__("; ".join(errors.values()))


class NotFound(Exception):
    pass


def to_cents(value, allow_negative=False):
    """Parse '$50,000', '50000', 49.99 or -120.5 into integer cents. Raises ValueError."""
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, (int, float)):
        text = repr(value)
    else:
        text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError
    if not amount.is_finite():
        raise ValueError
    cents = int((amount * 100).quantize(Decimal("1")))
    if cents < 0 and not allow_negative:
        raise ValueError
    if abs(cents) > MAX_MONEY_CENTS:
        raise ValueError
    return cents


def from_cents(cents):
    return None if cents is None else cents / 100


def today():
    return date.today().isoformat()


class Form:
    """Reads fields from a dict (JSON body or form data) and records errors."""

    def __init__(self, data):
        self.data = data or {}
        self.errors = {}

    def has(self, name):
        return name in self.data

    def raw(self, name):
        value = self.data.get(name)
        if isinstance(value, str):
            value = value.strip()
        return None if value in (None, "") else value

    def error(self, name, message):
        self.errors.setdefault(name, message)

    def _missing(self, name, required, label):
        if required:
            self.error(name, f"{label or name.replace('_', ' ').capitalize()} is required.")
        return None

    def text(self, name, required=False, max_len=20000, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        value = str(value)
        if len(value) > max_len:
            self.error(name, f"Must be {max_len} characters or fewer.")
        return value

    def money(self, name, required=False, allow_negative=False, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        try:
            return to_cents(value, allow_negative=allow_negative)
        except ValueError:
            kind = "an amount" if allow_negative else "a non-negative amount"
            self.error(name, f"Enter {kind}, e.g. 150 or 1,250.50.")
            return None

    def date(self, name, required=False, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except ValueError:
            self.error(name, "Enter a valid date (YYYY-MM-DD).")
            return None

    def datetime(self, name, required=False, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            self.error(name, "Enter a valid date and time.")
            return None
        return parsed.strftime("%Y-%m-%dT%H:%M")

    def choice(self, name, choices, required=False, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        value = str(value).lower()
        if value not in choices:
            self.error(name, f"Must be one of: {', '.join(choices)}.")
            return None
        return value

    def integer(self, name, required=False, label=None):
        value = self.raw(name)
        if value is None:
            return self._missing(name, required, label)
        try:
            return int(value)
        except (TypeError, ValueError):
            self.error(name, "Must be a whole number.")
            return None

    def check(self):
        if self.errors:
            raise ValidationError(self.errors)
