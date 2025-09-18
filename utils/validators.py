import re

# 1..100, латиница/кириллица, пробел, - и _
FULL_NAME_RE = re.compile(r'^[A-Za-zА-Яа-яЁё\s\-_]{1,100}$')

# 6..18, латиница/цифры/!@#$%&()_-
PASS_RE = re.compile(r'^[A-Za-z0-9!@#$%&()_-]{6,18}$')

# простая, но рабочая проверка email (user@host.tld)
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def validate_full_name(value: str):
    value = (value or '').strip()
    if not value:
        return 'ФИО обязательно'
    if not FULL_NAME_RE.fullmatch(value):
        return 'ФИО: 1–100 символов; только буквы (лат/кир), пробелы, "-" и "_"'
    return None


def validate_password(value: str):
    value = (value or '').strip()
    if not PASS_RE.fullmatch(value):
        return 'Пароль: 6–18 символов; только латиница, цифры и !@#$%&()_-'
    return None


def validate_email(value: str):
    value = (value or '').strip().lower()
    if not EMAIL_RE.fullmatch(value):
        return 'Некорректный формат email'
    return None
