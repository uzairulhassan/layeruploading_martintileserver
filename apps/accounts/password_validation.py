"""Custom password complexity rules for GeoLayers accounts."""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexityPasswordValidator:
    """Require length, letter, digit, and special character."""

    min_length = 8
    letter_re = re.compile(r"[A-Za-z]")
    digit_re = re.compile(r"\d")
    special_re = re.compile(r"[^A-Za-z0-9]")

    def validate(self, password, user=None):
        errors = []
        if len(password) < self.min_length:
            errors.append(
                ValidationError(
                    _("Password must be at least %(min_length)d characters."),
                    code="password_too_short",
                    params={"min_length": self.min_length},
                )
            )
        if not self.letter_re.search(password):
            errors.append(
                ValidationError(
                    _("Password must include at least one letter."),
                    code="password_no_letter",
                )
            )
        if not self.digit_re.search(password):
            errors.append(
                ValidationError(
                    _("Password must include at least one number."),
                    code="password_no_digit",
                )
            )
        if not self.special_re.search(password):
            errors.append(
                ValidationError(
                    _("Password must include at least one special character (e.g. @, $, !, #)."),
                    code="password_no_special",
                )
            )
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must be at least %(min_length)d characters and include "
            "a letter, a number, and a special character (e.g. @, $, !, #)."
        ) % {"min_length": self.min_length}
