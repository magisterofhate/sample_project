from flask import Flask, request, redirect, url_for, render_template, flash
from models import db
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flasgger import Swagger
from dotenv import load_dotenv
import os
from flask_migrate import Migrate
from flask import abort
from functools import wraps

# Инициализация приложения
app = Flask(__name__)

load_dotenv()  # подтягивает переменные из .env, если он есть
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SWAGGER'] = {
    'title': 'VM Manager API',
    'uiversion': 3,
}

swagger = Swagger(app)
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Импорт моделей ---
from models.user import Users
from models.vm import VM, user_vm

# --- Импорт API роутов ---
from routes.api import api_bp
app.register_blueprint(api_bp, url_prefix='/api/v1')


# --- Login manager ---
@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (current_user.is_authenticated and getattr(current_user, "is_admin", False)):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@app.before_request
def guard_swagger_for_non_admins():
    p = request.path or ""
    if p.startswith("/apidocs") or p.startswith("/apidoc") or p.startswith("/apispec"):
        if not (current_user.is_authenticated and getattr(current_user, "is_admin", False)):
            return redirect(url_for('login'))


# --- UI роуты ---
@app.route('/')
def index():
    return render_template('index.html', title='Главная')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('vms'))
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email').lower()
        password = request.form.get('password')
        if Users.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует')
        else:
            u = Users(email=email, full_name=full_name)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for('vms'))
    return render_template('auth.html', heading='Регистрация')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('vms'))
    if request.method == 'POST':
        email = request.form.get('email').lower()
        password = request.form.get('password')
        u = Users.query.filter_by(email=email).first()
        if not u or not u.check_password(password):
            flash('Неверный email или пароль')
        elif u.is_blocked:
            flash('Ваш аккаунт заблокирован. Обратитесь к администратору.')
        else:
            login_user(u)
            return redirect(url_for('vms'))
    return render_template('auth.html', heading='Вход')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email').lower()
        exists = Users.query.filter(Users.email == email, Users.id != current_user.id).first()
        if exists:
            flash('Email уже используется другим пользователем')
        else:
            current_user.full_name = full_name
            current_user.email = email
            db.session.commit()
            flash('Профиль обновлен')
            return redirect(url_for('profile'))
    return render_template('profile.html')


@app.route('/vms')
@login_required
def vms():
    vms = [vm for vm in current_user.vms if not vm.is_deleted]
    return render_template('vms.html', vms=vms)


@app.route('/vms/create', methods=['GET', 'POST'])
@login_required
def vm_create():
    errors = []
    if request.method == 'POST':
        name = request.form.get('name').strip()
        try:
            ram_gb = int(request.form.get('ram_gb'))
            cpu = int(request.form.get('cpu'))
        except (TypeError, ValueError):
            errors.append('RAM и CPU должны быть числами')
            return render_template('vm_create.html', errors=errors)

        if not (0 <= ram_gb <= 32):
            errors.append('RAM от 0 до 32')
        if not (1 <= cpu <= 16):
            errors.append('CPU от 1 до 16')

        if not errors:
            vm = VM(name=name, ram_gb=ram_gb, cpu=cpu)
            db.session.add(vm)
            db.session.commit()
            current_user.vms.append(vm)
            db.session.commit()
            flash('Виртуальная машина создана')
            return redirect(url_for('vms'))

    return render_template('vm_create.html', errors=errors)


@app.route('/vms/delete', methods=['POST'])
@login_required
def vms_delete():
    ids = request.form.getlist('vm_ids')  # список строк
    try:
        ids = list({int(x) for x in ids})
    except ValueError:
        flash('Некорректные идентификаторы ВМ')
        return redirect(url_for('vms'))

    if not ids:
        flash('Не выбрано ни одной ВМ')
        return redirect(url_for('vms'))

    # Обновляем только те ВМ, которые принадлежат текущему пользователю
    from models.vm import VM  # локальный импорт, чтобы избежать циклов
    owned_vm_ids = {vm.id for vm in current_user.vms}
    target_ids = [vid for vid in ids if vid in owned_vm_ids]
    if not target_ids:
        flash('Нет доступных ВМ для удаления')
        return redirect(url_for('vms'))

    # Помечаем как удалённые
    VM.query.filter(VM.id.in_(target_ids)).update(
        {VM.is_deleted: True},
        synchronize_session=False
    )
    from models import db
    db.session.commit()

    flash(f'Помечено как удалённые: {len(target_ids)} ВМ')
    return redirect(url_for('vms'))


@app.route('/vms/<int:vm_id>/edit', methods=['GET', 'POST'])
@login_required
def vm_edit(vm_id):
    vm = VM.query.get_or_404(vm_id)
    if vm not in current_user.vms:
        abort(403)
    if vm.is_deleted:
        flash('Нельзя редактировать удалённую ВМ')
        return redirect(url_for('vms'))

    errors = []
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        try:
            ram_gb = int(request.form.get('ram_gb'))
            cpu = int(request.form.get('cpu'))
        except (TypeError, ValueError):
            errors.append('RAM и CPU должны быть числами')
        else:
            if not (0 <= ram_gb <= 32): errors.append('RAM от 0 до 32')
            if not (1 <= cpu <= 16): errors.append('CPU от 1 до 16')
        if not name:
            errors.append('Имя обязательно')
        if not errors:
            vm.name = name
            vm.ram_gb = ram_gb
            vm.cpu = cpu
            db.session.commit()
            flash('ВМ обновлена')
            return redirect(url_for('vms'))

    return render_template('vm_edit.html', vm=vm, errors=errors)


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = Users.query.order_by(Users.id.asc()).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/<int:user_id>/toggle-block', methods=['POST'])
@login_required
@admin_required
def admin_toggle_block(user_id):
    user = Users.query.get_or_404(user_id)
    if user.is_admin:
        flash('Нельзя блокировать администратора')
        return redirect(url_for('admin_users'))
    user.is_blocked = not user.is_blocked
    db.session.commit()
    flash(('Заблокирован' if user.is_blocked else 'Разблокирован') + f' пользователь {user.email}')
    return redirect(url_for('admin_users'))


@app.route('/admin/vms')
@login_required
@admin_required
def admin_vms():
    vms = VM.query.order_by(VM.id.asc()).all()
    rows = [{'vm': vm, 'owners': [u.email for u in vm.users]} for vm in vms]
    return render_template('admin_vms.html', rows=rows)


@app.cli.command('ensure-admin')
def ensure_admin():
    """Создать/обновить предустановленного администратора."""
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com').lower()
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin12345')
    user = Users.query.filter_by(email=admin_email).first()
    if not user:
        user = Users(email=admin_email, full_name='Administrator', is_admin=True, is_blocked=False)
        user.set_password(admin_password)
        db.session.add(user)
        db.session.commit()
        print(f'Admin user created: {admin_email}')
    else:
        user.is_admin = True
        user.is_blocked = False
        if admin_password:
            user.set_password(admin_password)
        db.session.commit()
        print(f'Admin user ensured: {admin_email}')


# --- CLI helper ---
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database initialized')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
