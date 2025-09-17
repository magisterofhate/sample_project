from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from flasgger import swag_from
from models import db
from models.vm import VM

api_bp = Blueprint('api', __name__)


@api_bp.route('/vms', methods=['GET'])
@login_required
@swag_from({
    'tags': ['VMs'],
    'summary': 'List VMs',
    'parameters': [
        {'in': 'query', 'name': 'include_deleted', 'schema': {'type': 'boolean'}, 'required': False,
         'description': 'Include deleted VMs if true (ignored for admin&all)'},
        {'in': 'query', 'name': 'all', 'schema': {'type': 'boolean'}, 'required': False,
         'description': 'Admin only: include all users VMs'}
    ],
    'responses': {
        200: {'description': 'List of VMs'},
        401: {'description': 'Unauthorized'}
    }
})
def api_list_vms():
    include_deleted = request.args.get('include_deleted', '').lower() in ('1','true','yes')
    all_flag = request.args.get('all', '').lower() in ('1','true','yes')

    if current_user.is_admin and all_flag:
        vms_all = VM.query.all()
    else:
        vms_all = list(current_user.vms)

    if not (current_user.is_admin and all_flag):
        if not include_deleted:
            vms_all = [vm for vm in vms_all if not vm.is_deleted]

    items = [{'id': vm.id, 'name': vm.name, 'ram_gb': vm.ram_gb, 'cpu': vm.cpu, 'is_deleted': vm.is_deleted} for vm in vms_all]
    return jsonify({'items': items})


@api_bp.route('/vms', methods=['POST'])
@login_required
@swag_from({
    'tags': ['VMs'],
    'summary': 'Create a VM',
    'consumes': ['application/json'],
    'parameters': [
        {
            'in': 'body',
            'name': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'example': 'vm-new'},
                    'ram_gb': {'type': 'integer', 'minimum': 0, 'maximum': 32, 'example': 4},
                    'cpu': {'type': 'integer', 'minimum': 1, 'maximum': 16, 'example': 2}
                },
                'required': ['name', 'ram_gb', 'cpu']
            }
        }
    ],
    'responses': {
        201: {
            'description': 'Created',
            'schema': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'name': {'type': 'string'},
                    'ram_gb': {'type': 'integer'},
                    'cpu': {'type': 'integer'}
                }
            }
        },
        400: {'description': 'Validation error'},
        401: {'description': 'Unauthorized'}
    }
})
def api_create_vm():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    ram_gb = data.get('ram_gb')
    cpu = data.get('cpu')
    errors = []

    if not name:
        errors.append('name is required')
    try:
        ram_gb = int(ram_gb)
    except (TypeError, ValueError):
        errors.append('ram_gb must be an integer')
    else:
        if not (0 <= ram_gb <= 32):
            errors.append('ram_gb must be between 0 and 32')
    try:
        cpu = int(cpu)
    except (TypeError, ValueError):
        errors.append('cpu must be an integer')
    else:
        if not (1 <= cpu <= 16):
            errors.append('cpu must be between 1 and 16')

    if errors:
        return jsonify({'errors': errors}), 400

    vm = VM(name=name, ram_gb=ram_gb, cpu=cpu)
    db.session.add(vm)
    db.session.commit()
    current_user.vms.append(vm)
    db.session.commit()
    return jsonify({'id': vm.id, 'name': vm.name, 'ram_gb': vm.ram_gb, 'cpu': vm.cpu}), 201


@api_bp.route('/vms/<int:vm_id>', methods=['GET'])
@login_required
@swag_from({
    'tags': ['VMs'],
    'summary': 'Get VM by id (only if it belongs to current user)',
    'parameters': [{'name': 'vm_id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
    'responses': {
        200: {'description': 'VM found'},
        403: {'description': "Forbidden (VM doesn't belong to user)"},
        404: {'description': 'Not found'},
        401: {'description': 'Unauthorized'}
    }
})
def api_get_vm(vm_id: int):
    vm = VM.query.get_or_404(vm_id)
    if vm not in current_user.vms:
        return jsonify({'error': 'forbidden'}), 403
    if vm.is_deleted:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'id': vm.id, 'name': vm.name, 'ram_gb': vm.ram_gb, 'cpu': vm.cpu, 'is_deleted': vm.is_deleted})
