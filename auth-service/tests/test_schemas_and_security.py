"""
Unit tests for auth-service schemas and security utilities.
No DB or HTTP needed — pure Python.
"""
import pytest
from pydantic import ValidationError

from app.schemas.auth_schema import SignUpModel, validate_password_strength
from app.core.security import hash_password, verify_password


# ── Password validator ────────────────────────────────────────────────────────

class TestPasswordValidator:

    def test_valid_password_passes(self):
        assert validate_password_strength("Secure1!") == "Secure1!"

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="at least 8 characters"):
            validate_password_strength("Ab1!")

    def test_no_uppercase_raises(self):
        with pytest.raises(ValueError, match="uppercase"):
            validate_password_strength("secure1!")

    def test_no_digit_raises(self):
        with pytest.raises(ValueError, match="number"):
            validate_password_strength("Securepass!")

    def test_no_special_char_raises(self):
        with pytest.raises(ValueError, match="special character"):
            validate_password_strength("Secure123")

    def test_exactly_8_chars_passes(self):
        assert validate_password_strength("Abcde1!x") == "Abcde1!x"

    @pytest.mark.parametrize("special", list('!@#$%^&*(),.?":{}|<>_-+=[]\\;\'`~'))
    def test_various_special_chars_accepted(self, special):
        pwd = f"Secure1{special}"
        assert validate_password_strength(pwd) == pwd


# ── SignUpModel schema ────────────────────────────────────────────────────────

class TestSignUpModel:

    def test_valid_signup(self):
        m = SignUpModel(username="uche", email="uche@example.com", password="Secure1!")
        assert m.username == "uche"
        assert m.email == "uche@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            SignUpModel(username="uche", email="not-an-email", password="Secure1!")

    def test_weak_password_rejected(self):
        with pytest.raises(ValidationError, match="uppercase"):
            SignUpModel(username="uche", email="uche@example.com", password="weak123!")

    def test_password_stored_as_provided(self):
        """Schema must not hash the password — that's the service layer's job."""
        m = SignUpModel(username="uche", email="uche@example.com", password="Secure1!")
        assert m.password == "Secure1!"


# ── Password hashing ──────────────────────────────────────────────────────────

class TestSecurity:

    def test_hash_is_not_plaintext(self):
        h = hash_password("Secure1!")
        assert h != "Secure1!"

    def test_verify_correct_password(self):
        h = hash_password("Secure1!")
        assert verify_password("Secure1!", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("Secure1!")
        assert verify_password("WrongPassword1!", h) is False

    def test_two_hashes_of_same_password_differ(self):
        """Werkzeug uses salted hashing — same input never produces same hash."""
        h1 = hash_password("Secure1!")
        h2 = hash_password("Secure1!")
        assert h1 != h2

    def test_hash_is_string(self):
        assert isinstance(hash_password("Secure1!"), str)


# ── Verification token ────────────────────────────────────────────────────────

class TestVerificationToken:

    def test_round_trip(self):
        from app.utils.verification import generate_verification_token, confirm_verification_token
        token = generate_verification_token("uche@example.com")
        assert confirm_verification_token(token) == "uche@example.com"

    def test_tampered_token_returns_none(self):
        from app.utils.verification import confirm_verification_token
        assert confirm_verification_token("tampered.token.value") is None

    def test_empty_token_returns_none(self):
        from app.utils.verification import confirm_verification_token
        assert confirm_verification_token("") is None
