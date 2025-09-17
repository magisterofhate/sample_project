from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from . import db
from .vm import user_vm


class Users(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    full_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # роли/статус
    is_admin = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    is_blocked = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    vms = db.relationship('VM', secondary=user_vm, backref=db.backref('users', lazy='dynamic'))

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
