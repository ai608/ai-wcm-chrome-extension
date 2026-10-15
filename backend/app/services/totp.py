import pyotp


def verify_code(secret: str, code: str) -> bool:
    """valid_window=1 tolerates +/-30s of clock drift between server and device."""
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
