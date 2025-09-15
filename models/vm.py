from . import db

# Association table
user_vm = db.Table(
    'user_vm',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('vm_id', db.Integer, db.ForeignKey('vm.id'), primary_key=True)
)


class VM(db.Model):
    __tablename__ = 'vm'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    ram_gb = db.Column(db.Integer, nullable=False)
    cpu = db.Column(db.Integer, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
