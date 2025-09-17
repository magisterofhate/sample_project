from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user
from flasgger import swag_from

from models import db
from models.user import Users
from models.vm import VM
from sqlalchemy import or_

api_bp = Blueprint('api', __name__)

# ---------- Helpers ----------


def require_admin():
    if not (current_user.is_authenticated and getattr(current_user, "is_admin", False)):
        abort(403)


def parse_bool(val: str) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


def vm_to_dict(vm: VM):
    return {
        "id": vm.id,
        "name": vm.name,
        "ram_gb": vm.ram_gb,
        "cpu": vm.cpu,
        "is_deleted": bool(vm.is_deleted),
    }


def user_to_dict(u: Users):
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "is_admin": bool(u.is_admin),
        "is_blocked": bool(u.is_blocked),
    }


# ---------- VMs ----------

@api_bp.route('/vms', methods=['GET'])
@login_required
@swag_from({
    "tags": ["VMs"],
    "summary": "List VMs",
    "description": "Обычный пользователь видит только **свои** ВМ. "
                   "Администратор может видеть все ВМ при параметре `all=true`.",
    "parameters": [
        {
            "in": "query",
            "name": "include_deleted",
            "type": "boolean",
            "required": False,
            "description": "Включить логически удалённые ВМ (is_deleted=true) для обычного списка."
        },
        {
            "in": "query",
            "name": "all",
            "type": "boolean",
            "required": False,
            "description": "Только для администратора: показать все ВМ всех пользователей."
        }
    ],
    "responses": {
        200: {
            "description": "OK",
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "name": {"type": "string"},
                                "ram_gb": {"type": "integer"},
                                "cpu": {"type": "integer"},
                                "is_deleted": {"type": "boolean"}
                            }
                        }
                    }
                }
            }
        },
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_list_vms():
    include_deleted = parse_bool(request.args.get('include_deleted'))
    all_flag = parse_bool(request.args.get('all'))

    if current_user.is_admin and all_flag:
        vms_all = VM.query.order_by(VM.id.asc()).all()
    else:
        vms_all = list(current_user.vms)

    if not (current_user.is_admin and all_flag):
        if not include_deleted:
            vms_all = [vm for vm in vms_all if not vm.is_deleted]

    return jsonify({"items": [vm_to_dict(vm) for vm in vms_all]}), 200


@api_bp.route('/vms', methods=['POST'])
@login_required
@swag_from({
    "tags": ["VMs"],
    "summary": "Create a VM",
    "description": "Создаёт ВМ для **текущего пользователя**. "
                   "Если запрос выполняет **администратор**, можно указать `owner_id` для создания ВМ на выбранного пользователя.",
    "consumes": ["application/json"],
    "parameters": [
        {
            "in": "body",
            "name": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["name", "ram_gb", "cpu"],
                "properties": {
                    "name": {"type": "string", "example": "vm-new"},
                    "ram_gb": {"type": "integer", "minimum": 0, "maximum": 32, "example": 4},
                    "cpu": {"type": "integer", "minimum": 1, "maximum": 16, "example": 2},
                    "owner_id": {"type": "integer", "description": "Только для администратора"}
                }
            }
        }
    ],
    "responses": {
        201: {
            "description": "Created",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "ram_gb": {"type": "integer"},
                    "cpu": {"type": "integer"},
                    "is_deleted": {"type": "boolean"}
                }
            }
        },
        400: {"description": "Validation error"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"}
    },
    "security": [{"cookieAuth": []}]
})
def api_create_vm():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    try:
        ram_gb = int(data.get('ram_gb'))
        cpu = int(data.get('cpu'))
    except (TypeError, ValueError):
        return jsonify({"error": "ram_gb и cpu должны быть целыми числами"}), 400

    errors = []
    if not name:
        errors.append("Имя обязательно")
    if not (0 <= ram_gb <= 32):
        errors.append("RAM от 0 до 32")
    if not (1 <= cpu <= 16):
        errors.append("CPU от 1 до 16")
    if errors:
        return jsonify({"errors": errors}), 400

    owner = current_user
    if current_user.is_admin and data.get('owner_id') is not None:
        owner = Users.query.get(data.get('owner_id'))
        if not owner:
            return jsonify({"error": "Владелец не найден"}), 400

    vm = VM(name=name, ram_gb=ram_gb, cpu=cpu, is_deleted=False)
    db.session.add(vm)
    db.session.flush()
    owner.vms.append(vm)
    db.session.commit()
    return jsonify(vm_to_dict(vm)), 201


@api_bp.route('/vms/<int:vm_id>', methods=['GET'])
@login_required
@swag_from({
    "tags": ["VMs"],
    "summary": "Get VM by id",
    "parameters": [
        {"in": "path", "name": "vm_id", "type": "integer", "required": True}
    ],
    "responses": {
        200: {"description": "OK"},
        403: {"description": "Forbidden (не ваша ВМ)"},
        404: {"description": "Not found"},
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_get_vm(vm_id: int):
    vm = VM.query.get_or_404(vm_id)
    if not current_user.is_admin and vm not in current_user.vms:
        abort(403)
    return jsonify(vm_to_dict(vm)), 200


@api_bp.route('/vms/<int:vm_id>', methods=['PATCH'])
@login_required
@swag_from({
    "tags": ["VMs"],
    "summary": "Update VM",
    "description": "Редактирование доступно владельцу ВМ и администратору. "
                   "Нельзя редактировать логически удалённую ВМ.",
    "consumes": ["application/json"],
    "parameters": [
        {"in": "path", "name": "vm_id", "type": "integer", "required": True},
        {
            "in": "body",
            "name": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "ram_gb": {"type": "integer", "minimum": 0, "maximum": 32},
                    "cpu": {"type": "integer", "minimum": 1, "maximum": 16}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "OK"},
        400: {"description": "Validation error"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_update_vm(vm_id: int):
    vm = VM.query.get_or_404(vm_id)
    if not current_user.is_admin and vm not in current_user.vms:
        abort(403)
    if vm.is_deleted:
        return jsonify({"error": "Нельзя редактировать удалённую ВМ"}), 400

    data = request.get_json(silent=True) or {}
    errors = []

    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            errors.append("Имя не может быть пустым")
        else:
            vm.name = name

    if 'ram_gb' in data:
        try:
            ram_gb = int(data.get('ram_gb'))
        except (TypeError, ValueError):
            errors.append("ram_gb должен быть целым числом")
        else:
            if not (0 <= ram_gb <= 32):
                errors.append("RAM от 0 до 32")
            else:
                vm.ram_gb = ram_gb

    if 'cpu' in data:
        try:
            cpu = int(data.get('cpu'))
        except (TypeError, ValueError):
            errors.append("cpu должен быть целым числом")
        else:
            if not (1 <= cpu <= 16):
                errors.append("CPU от 1 до 16")
            else:
                vm.cpu = cpu

    if errors:
        return jsonify({"errors": errors}), 400

    db.session.commit()
    return jsonify(vm_to_dict(vm)), 200


@api_bp.route('/vms/<int:vm_id>', methods=['DELETE'])
@login_required
@swag_from({
    "tags": ["VMs"],
    "summary": "Soft delete VM",
    "description": "Логическое удаление (is_deleted=true). Доступно владельцу и администратору.",
    "parameters": [
        {"in": "path", "name": "vm_id", "type": "integer", "required": True}
    ],
    "responses": {
        204: {"description": "No Content"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_delete_vm(vm_id: int):
    vm = VM.query.get_or_404(vm_id)
    if not current_user.is_admin and vm not in current_user.vms:
        abort(403)
    if not vm.is_deleted:
        vm.is_deleted = True
        db.session.commit()
    return ("", 204)


# ---------- Users (admin) ----------

@api_bp.route('/users', methods=['GET'])
@login_required
@swag_from({
    "tags": ["Users"],
    "summary": "List users (admin)",
    "description": "Доступно только администратору.",
    "responses": {
        200: {
            "description": "OK",
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "email": {"type": "string"},
                                "full_name": {"type": "string"},
                                "is_admin": {"type": "boolean"},
                                "is_blocked": {"type": "boolean"}
                            }
                        }
                    }
                }
            }
        },
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"}
    },
    "security": [{"cookieAuth": []}]
})
def api_list_users():
    require_admin()
    users = Users.query.order_by(Users.id.asc()).all()
    return jsonify({"items": [user_to_dict(u) for u in users]}), 200


@api_bp.route('/users', methods=['POST'])
@login_required
@swag_from({
    "tags": ["Users"],
    "summary": "Create user (admin)",
    "description": "Создание пользователя администратором.",
    "consumes": ["application/json"],
    "parameters": [
        {
            "in": "body",
            "name": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "email": {"type": "string", "example": "user@example.com"},
                    "full_name": {"type": "string", "example": "Иван Иванов"},
                    "password": {"type": "string", "minLength": 6, "example": "secret123"},
                    "is_admin": {"type": "boolean", "example": False},
                    "is_blocked": {"type": "boolean", "example": False}
                }
            }
        }
    ],
    "responses": {
        201: {"description": "Created"},
        400: {"description": "Validation error"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"}
    },
    "security": [{"cookieAuth": []}]
})
def api_create_user():
    require_admin()
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    full_name = (data.get('full_name') or '').strip() or None
    password = (data.get('password') or '').strip()

    is_admin = bool(data.get('is_admin', False))
    is_blocked = bool(data.get('is_blocked', False))

    errors = []
    if not email:
        errors.append("Email обязателен")
    if not password or len(password) < 6:
        errors.append("Пароль обязателен и должен быть не короче 6 символов")
    if Users.query.filter_by(email=email).first():
        errors.append("Пользователь с таким email уже существует")

    if errors:
        return jsonify({"errors": errors}), 400

    u = Users(email=email, full_name=full_name, is_admin=is_admin, is_blocked=is_blocked)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return jsonify(user_to_dict(u)), 201


@api_bp.route('/users/<int:user_id>/block', methods=['PATCH'])
@login_required
@swag_from({
    "tags": ["Users"],
    "summary": "Block/unblock user (admin)",
    "description": "Установить флаг блокировки. Заблокированный пользователь не может войти.",
    "consumes": ["application/json"],
    "parameters": [
        {"in": "path", "name": "user_id", "type": "integer", "required": True},
        {
            "in": "body",
            "name": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["blocked"],
                "properties": {
                    "blocked": {"type": "boolean", "example": True}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "OK"},
        400: {"description": "Validation error"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"}
    },
    "security": [{"cookieAuth": []}]
})
def api_block_user(user_id: int):
    require_admin()
    u = Users.query.get_or_404(user_id)
    if u.is_admin:
        return jsonify({"error": "Нельзя блокировать администратора"}), 400

    data = request.get_json(silent=True) or {}
    if "blocked" not in data:
        return jsonify({"error": "Поле 'blocked' обязательно"}), 400

    u.is_blocked = bool(data.get("blocked"))
    db.session.commit()
    return jsonify(user_to_dict(u)), 200


# ---------- Profile (current user) ----------

@api_bp.route('/me', methods=['GET'])
@login_required
@swag_from({
    "tags": ["Profile"],
    "summary": "Get current user profile",
    "responses": {
        200: {
            "description": "OK",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string"},
                    "full_name": {"type": "string"},
                    "is_admin": {"type": "boolean"},
                    "is_blocked": {"type": "boolean"}
                }
            }
        },
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_me():
    return jsonify(user_to_dict(current_user)), 200


@api_bp.route('/me', methods=['PATCH'])
@login_required
@swag_from({
    "tags": ["Profile"],
    "summary": "Update current user profile",
    "description": "Обычный пользователь может изменять **email** и **full_name**. "
                   "Администратор — **только пароль** (email/ФИО игнорируются).",
    "consumes": ["application/json"],
    "parameters": [
        {
            "in": "body",
            "name": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "full_name": {"type": "string"},
                    "new_password": {"type": "string", "minLength": 6},
                    "new_password2": {"type": "string", "minLength": 6}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "OK"},
        400: {"description": "Validation error"},
        401: {"description": "Unauthorized"}
    },
    "security": [{"cookieAuth": []}]
})
def api_update_me():
    data = request.get_json(silent=True) or {}
    errors = []

    if current_user.is_admin:
        # только смена пароля
        new_password = (data.get('new_password') or '').strip()
        new_password2 = (data.get('new_password2') or '').strip()
        if new_password or new_password2:
            if len(new_password) < 6:
                errors.append('Пароль должен быть не короче 6 символов')
            if new_password != new_password2:
                errors.append('Пароли не совпадают')
            if not errors:
                current_user.set_password(new_password)
                db.session.commit()
        else:
            errors.append("Для администратора доступна только смена пароля (поля new_password/new_password2).")
    else:
        # обычный пользователь: email/full_name
        email = data.get('email')
        full_name = data.get('full_name')

        if email is not None:
            email = email.strip().lower()
            if not email:
                errors.append("Email обязателен")
            else:
                exists = Users.query.filter(Users.email == email, Users.id != current_user.id).first()
                if exists:
                    errors.append("Пользователь с таким email уже существует")
                else:
                    current_user.email = email

        if full_name is not None:
            current_user.full_name = (full_name or '').strip() or None

        if not errors:
            db.session.commit()

    if errors:
        return jsonify({"errors": errors}), 400

    return jsonify(user_to_dict(current_user)), 200


@api_bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
@swag_from({
    "tags": ["Users"],
    "summary": "Get user by id (admin)",
    "description": "Доступно только администратору.",
    "parameters": [
        {"in": "path", "name": "user_id", "type": "integer", "required": True}
    ],
    "responses": {
        200: {
            "description": "OK",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string"},
                    "full_name": {"type": "string"},
                    "is_admin": {"type": "boolean"},
                    "is_blocked": {"type": "boolean"}
                }
            }
        },
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"}
    },
    "security": [{"cookieAuth": []}]
})
def api_get_user(user_id: int):
    require_admin()
    u = Users.query.get_or_404(user_id)
    return jsonify(user_to_dict(u)), 200


@api_bp.route('/users/search', methods=['GET'])
@login_required
@swag_from({
    "tags": ["Users"],
    "summary": "Search users (admin)",
    "description": "Поиск по подстроке в email или ФИО (регистронезависимый). Доступно только администратору.",
    "parameters": [
        {
            "in": "query",
            "name": "q",
            "type": "string",
            "required": True,
            "description": "Подстрока для поиска (email или ФИО)"
        }
    ],
    "responses": {
        200: {
            "description": "OK",
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "email": {"type": "string"},
                                "full_name": {"type": "string"},
                                "is_admin": {"type": "boolean"},
                                "is_blocked": {"type": "boolean"}
                            }
                        }
                    }
                }
            }
        },
        400: {"description": "Validation error (q is required)"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"}
    },
    "security": [{"cookieAuth": []}]
})
def api_search_users():
    require_admin()
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({"errors": ["q is required"]}), 400

    users = Users.query.filter(
        or_(Users.email.ilike(f"%{q}%"),
            Users.full_name.ilike(f"%{q}%"))
    ).order_by(Users.id.asc()).all()

    return jsonify({"items": [user_to_dict(u) for u in users]}), 200


