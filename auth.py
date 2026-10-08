"""Password hashing and login helpers."""
import binascii
import hashlib
import os

import queries


def hash_password(password, salt=None):
    if salt is None:
        salt = binascii.hexlify(os.urandom(16)).decode()
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return digest, salt


def verify_password(password, salt, expected_hash):
    digest, _ = hash_password(password, salt)
    return digest == expected_hash



def login(email, password):
    try:
        emp = queries.get_employee_by_email(email)
    except Exception:
        return None
    if not emp or not emp["active"]:
        return None
    if verify_password(password, emp["salt"], emp["password_hash"]):
        return emp
    return None
