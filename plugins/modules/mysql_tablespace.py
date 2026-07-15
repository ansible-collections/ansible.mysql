#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible community
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_tablespace

short_description: Manage MySQL InnoDB general tablespaces

description:
  - Create, update, rename, or drop MySQL InnoDB general tablespaces.
  - Supports general tablespace lifecycle operations on MySQL servers.
  - Key rotation is outside this module's scope because MySQL exposes it through
    C(ALTER INSTANCE ROTATE INNODB MASTER KEY), not as a per-tablespace lifecycle action.

version_added: '5.2.0'

options:
  name:
    description:
      - Name of the tablespace to manage.
    type: str
    required: true
  state:
    description:
      - If V(present), create the tablespace when it does not exist.
      - If V(present), alter mutable tablespace attributes when it already exists.
      - If V(absent), drop the tablespace.
    type: str
    choices: [absent, present]
    default: present
  datafile:
    description:
      - Tablespace datafile path.
      - Create-only.
      - Required on MySQL versions earlier than V(8.0.14).
      - Optional on MySQL V(8.0.14) and later.
    type: str
  file_block_size:
    description:
      - File block size for the general tablespace.
      - Create-only.
      - Existing tablespaces are compared best-effort using available metadata.
      - Deeper semantic validation is left to MySQL because valid values depend on
        C(innodb_page_size) and compressed-page rules rather than a standalone whitelist.
    type: int
  encryption:
    description:
      - Whether the general tablespace should be encrypted.
      - Uses MySQL literal values V(Y) or V(N).
      - Supported on MySQL V(8.0.13) and later.
      - Can be set during create or alter.
      - Does not rotate InnoDB master keys. Key rotation remains an instance-level
        operation exposed through C(ALTER INSTANCE ROTATE INNODB MASTER KEY).
    type: str
  rename_to:
    description:
      - Rename the tablespace to this new name.
      - Alter-only.
      - Supported on MySQL V(8.0.3) and later.
      - Cannot be used when O(state) is V(absent).
    type: str
  autoextend_size:
    description:
      - Tablespace autoextend size in bytes.
      - Supported on MySQL V(8.0.23) and later.
      - Can be set during create or alter.
    type: int

notes:
  - Compatible with MySQL only.
  - O(datafile) and O(file_block_size) are create-only options.
  - O(rename_to) is an alter-only option.
  - Key rotation is outside this module's scope because MySQL exposes it with
    C(ALTER INSTANCE ROTATE INNODB MASTER KEY).
  - Metadata reads used for idempotency and post-change verification may require the C(PROCESS) privilege.
  - C(DROP TABLESPACE) requires the tablespace to be empty.

attributes:
  check_mode:
    support: full
    details:
      - In check mode the module reads current tablespace state and reports the DDL it would run without executing it.
  idempotent:
    support: full
    details:
      - The module emits DDL only when the requested tablespace lifecycle state differs from the current server state.

seealso:
  - module: ansible.mysql.mysql_tablespace_info
  - name: MySQL ALTER INSTANCE reference
    description: Reference for instance-level operations such as C(ALTER INSTANCE ROTATE INNODB MASTER KEY).
    link: https://dev.mysql.com/doc/refman/8.4/en/alter-instance.html
  - name: MySQL CREATE TABLESPACE reference
    description: Complete reference of the CREATE TABLESPACE command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/create-tablespace.html
  - name: MySQL ALTER TABLESPACE reference
    description: Complete reference of the ALTER TABLESPACE command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/alter-tablespace.html
  - name: MySQL DROP TABLESPACE reference
    description: Complete reference of the DROP TABLESPACE command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/drop-tablespace.html

author:
  - Ron Gershburg (@ronger4)

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
# If you encounter the "Please explicitly state intended protocol" error,
# use the login_unix_socket argument
- name: Create a MySQL general tablespace
  ansible.mysql.mysql_tablespace:
    name: app_data
    datafile: ./app_data.ibd
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Create a MySQL general tablespace with file block and autoextend settings
  ansible.mysql.mysql_tablespace:
    name: analytics_data
    datafile: ./analytics_data.ibd
    file_block_size: 8192
    autoextend_size: 4194304

- name: Enable encryption on a MySQL tablespace
  ansible.mysql.mysql_tablespace:
    name: app_data
    encryption: Y

- name: Rename a MySQL tablespace
  ansible.mysql.mysql_tablespace:
    name: app_data
    rename_to: archive_data

- name: Drop an empty MySQL tablespace
  ansible.mysql.mysql_tablespace:
    name: archive_data
    state: absent
'''

RETURN = r'''
queries:
  description: List of executed queries.
  returned: when changed
  type: list
  sample:
    - CREATE TABLESPACE `app_data` ADD DATAFILE './app_data.ibd' ENGINE = InnoDB
tablespace:
  description:
    - Normalized representation of the MySQL tablespace after module execution when server metadata is available.
    - In create check mode, this is a predicted subset derived from requested values because no post-create server metadata exists yet.
  returned: when O(state) is V(present)
  type: dict
  contains:
    server_implementation:
      description: Server implementation that produced the result.
      type: str
      sample: mysql
    name:
      description: Tablespace name after module execution.
      type: str
      sample: app_data
    datafile:
      description: Tablespace datafile path when available.
      type: str
      sample: ./app_data.ibd
    autoextend_size:
      description: Autoextend size in bytes when available.
      type: int
      sample: 4194304
    encryption:
      description: Encryption state when available.
      type: str
      sample: N
    page_size:
      description: InnoDB page size in bytes when available.
      type: int
      sample: 16384
    zip_page_size:
      description: Compressed page size in bytes when available.
      type: int
      sample: 8192
    attached_tables:
      description: Tables attached to the tablespace when the server exposes them.
      type: list
      elements: str
      sample:
        - app/orders
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils.database import (
    check_input,
    mysql_quote_identifier,
)
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)
from ansible_collections.ansible.mysql.plugins.module_utils.tablespace import (
    ensure_tablespaces_supported,
    get_mysql_tablespace,
)

AUTOEXTEND_SIZE_INCREMENT = 4 * 1024 * 1024
MYSQL_TABLESPACE_RENAME_MIN_VERSION = (8, 0, 3)
MYSQL_TABLESPACE_ENCRYPTION_MIN_VERSION = (8, 0, 13)
MYSQL_TABLESPACE_OPTIONAL_DATAFILE_MIN_VERSION = (8, 0, 14)
MYSQL_TABLESPACE_AUTOEXTEND_SIZE_MIN_VERSION = (8, 0, 23)


def normalize_tablespace_encryption(encryption):
    if encryption is None:
        return None

    encryption = encryption.upper()
    if encryption not in ('Y', 'N'):
        raise ValueError("encryption must be either 'Y' or 'N'")

    return encryption


def validate_autoextend_size_input(autoextend_size):
    if autoextend_size is None:
        return None

    if autoextend_size < 0 or autoextend_size % AUTOEXTEND_SIZE_INCREMENT != 0:
        raise ValueError('autoextend_size must be a non-negative multiple of 4MB (4194304 bytes)')

    return autoextend_size


def validate_file_block_size_input(file_block_size):
    if file_block_size is None:
        return None

    if file_block_size <= 0:
        raise ValueError('file_block_size must be a positive integer')

    return file_block_size


def get_tablespace_file_block_size(tablespace):
    zip_page_size = tablespace.get('zip_page_size')
    # A ZIP page size of 0 means "not compressed", so the intentional falsy check
    # falls back to page_size instead of treating 0 as an actual file block size.
    if zip_page_size:
        return zip_page_size
    return tablespace.get('page_size')


def validate_tablespace_rename(server_version, rename):
    return _validate_version_gated_value(
        server_version,
        rename,
        MYSQL_TABLESPACE_RENAME_MIN_VERSION,
        'rename',
    )


def validate_tablespace_encryption(server_version, encryption):
    return _validate_version_gated_value(
        server_version,
        encryption,
        MYSQL_TABLESPACE_ENCRYPTION_MIN_VERSION,
        'encryption',
    )


def validate_tablespace_autoextend_size(server_version, autoextend_size):
    return _validate_version_gated_value(
        server_version,
        autoextend_size,
        MYSQL_TABLESPACE_AUTOEXTEND_SIZE_MIN_VERSION,
        'autoextend_size',
    )


def validate_tablespace_datafile(server_version, datafile):
    if datafile is None and server_version < MYSQL_TABLESPACE_OPTIONAL_DATAFILE_MIN_VERSION:
        raise ValueError(
            'datafile is required for MySQL versions earlier than %s'
            % _format_version(MYSQL_TABLESPACE_OPTIONAL_DATAFILE_MIN_VERSION)
        )
    return datafile


def _validate_version_gated_value(server_version, value, minimum_version, option_name):
    if value is None:
        return None
    if server_version < minimum_version:
        raise ValueError(
            '%s requires MySQL %s or later'
            % (option_name, _format_version(minimum_version))
        )
    return value


def _format_version(version):
    return '.'.join(str(part) for part in version)


def build_create_query(name, datafile=None, file_block_size=None, encryption=None, autoextend_size=None):
    query = ['CREATE TABLESPACE %s' % mysql_quote_identifier(name, 'role')]

    if datafile is not None:
        query.append('ADD DATAFILE %s' % quote_sql_value(datafile))

    if autoextend_size is not None:
        query.append('AUTOEXTEND_SIZE = %s' % autoextend_size)

    if file_block_size is not None:
        query.append('FILE_BLOCK_SIZE = %s' % file_block_size)

    if encryption is not None:
        query.append('ENCRYPTION = %s' % quote_sql_value(encryption))

    query.append('ENGINE = InnoDB')
    return ' '.join(query)


def build_alter_queries(current, rename_to=None, encryption=None, autoextend_size=None):
    queries = []
    target_name = current['name']

    if rename_to is not None and current['name'] != rename_to:
        queries.append(
            'ALTER TABLESPACE %s RENAME TO %s'
            % (
                mysql_quote_identifier(current['name'], 'role'),
                mysql_quote_identifier(rename_to, 'role'),
            )
        )
        target_name = rename_to

    if autoextend_size is not None and current.get('autoextend_size') != autoextend_size:
        queries.append(
            'ALTER TABLESPACE %s AUTOEXTEND_SIZE = %s'
            % (
                mysql_quote_identifier(target_name, 'role'),
                autoextend_size,
            )
        )

    if encryption is not None and current.get('encryption') != encryption:
        queries.append(
            'ALTER TABLESPACE %s ENCRYPTION = %s'
            % (
                mysql_quote_identifier(target_name, 'role'),
                quote_sql_value(encryption),
            )
        )

    return queries


def build_drop_query(name):
    return 'DROP TABLESPACE %s' % mysql_quote_identifier(name, 'role')


def quote_sql_value(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, int):
        return str(value)
    return "'%s'" % str(value).replace("'", "''")


def execute_query(cursor, query):
    cursor.execute(query)


def predict_tablespace(current=None, name=None, datafile=None, encryption=None, autoextend_size=None, rename_to=None):
    if current is None:
        predicted = {
            'server_implementation': 'mysql',
            'name': name,
        }
    else:
        predicted = current.copy()

    if datafile is not None and 'datafile' not in predicted:
        predicted['datafile'] = datafile

    if encryption is not None:
        predicted['encryption'] = encryption

    if autoextend_size is not None:
        predicted['autoextend_size'] = autoextend_size

    if rename_to is not None:
        predicted['name'] = rename_to

    return predicted


def resolve_current_tablespace(module, cursor, server_version, name, rename_to=None):
    current = get_mysql_tablespace(cursor, server_version, name, module=module)

    if rename_to is None or rename_to == name:
        return current, False

    renamed = get_mysql_tablespace(cursor, server_version, rename_to, module=module)

    if current is None:
        if renamed is None:
            module.fail_json(
                msg=(
                    'rename_to is alter-only and requires an existing tablespace named %s, '
                    'or a tablespace already renamed to %s.'
                    % (name, rename_to)
                )
            )
        return renamed, True

    if renamed is not None:
        module.fail_json(
            msg='Cannot rename tablespace %s to %s because %s already exists.'
            % (name, rename_to, rename_to)
        )

    return current, False


def fail_if_rename_target_requires_changes(
    module,
    current,
    rename_to,
    datafile=None,
    file_block_size=None,
    encryption=None,
    autoextend_size=None,
):
    mismatches = []

    if datafile is not None and current.get('datafile') != datafile:
        mismatches.append('datafile')

    if file_block_size is not None:
        current_file_block_size = get_tablespace_file_block_size(current)
        if current_file_block_size is None or current_file_block_size != file_block_size:
            mismatches.append('file_block_size')

    if mismatches:
        module.fail_json(
            msg=(
                'rename_to target %s already exists but does not match the requested end state '
                '(%s). Refusing to treat the rename as already applied.'
                % (rename_to, ', '.join(mismatches))
            ),
            tablespace=current,
        )


def fail_if_create_only_options_differ(module, current, datafile=None, file_block_size=None):
    if datafile is not None and current.get('datafile') != datafile:
        module.fail_json(
            msg=(
                'datafile is create-only and cannot be changed for existing tablespace %s '
                '(current: %s, requested: %s).'
                % (current['name'], current.get('datafile'), datafile)
            ),
            tablespace=current,
        )

    if file_block_size is None:
        return

    current_file_block_size = get_tablespace_file_block_size(current)
    if current_file_block_size is None:
        module.fail_json(
            msg=(
                'Cannot compare create-only file_block_size for existing tablespace %s '
                'because current metadata does not expose page_size or zip_page_size.'
                % current['name']
            ),
            tablespace=current,
        )

    if current_file_block_size != file_block_size:
        module.fail_json(
            msg=(
                'file_block_size is create-only and cannot be changed for existing tablespace %s '
                '(current best-effort value: %s, requested: %s).'
                % (current['name'], current_file_block_size, file_block_size)
            ),
            tablespace=current,
        )


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['absent', 'present'], default='present'),
        datafile=dict(type='str'),
        file_block_size=dict(type='int'),
        encryption=dict(type='str'),
        rename_to=dict(type='str'),
        autoextend_size=dict(type='int'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    name = module.params['name']
    state = module.params['state']
    datafile = module.params['datafile']
    file_block_size = module.params['file_block_size']
    encryption = module.params['encryption']
    rename_to = module.params['rename_to']
    autoextend_size = module.params['autoextend_size']
    login_user = module.params['login_user']
    login_password = module.params['login_password']
    config_file = module.params['config_file']
    ssl_cert = module.params['client_cert']
    ssl_key = module.params['client_key']
    ssl_ca = module.params['ca_cert']
    connect_timeout = module.params['connect_timeout']
    check_hostname = module.params['check_hostname']

    if rename_to == name:
        rename_to = None

    if state == 'absent' and rename_to is not None:
        module.fail_json(msg='rename_to cannot be used with state=absent')

    check_input(module, name, datafile, rename_to, encryption)

    try:
        encryption = normalize_tablespace_encryption(encryption)
        autoextend_size = validate_autoextend_size_input(autoextend_size)
        file_block_size = validate_file_block_size_input(file_block_size)
    except ValueError as e:
        module.fail_json(msg=to_native(e))

    try:
        cursor, _db_conn = mysql_connect(
            module,
            login_user,
            login_password,
            config_file,
            ssl_cert,
            ssl_key,
            ssl_ca,
            connect_timeout=connect_timeout,
            check_hostname=check_hostname,
            cursor_class='DictCursor',
            autocommit=True,
        )
    except Exception as e:
        module.fail_json(msg='unable to connect to database: %s' % to_native(e))

    server_version = ensure_tablespaces_supported(module, cursor)
    queries = []

    try:
        rename_to = validate_tablespace_rename(server_version, rename_to)
        encryption = validate_tablespace_encryption(server_version, encryption)
        autoextend_size = validate_tablespace_autoextend_size(server_version, autoextend_size)
    except ValueError as e:
        module.fail_json(msg=to_native(e))

    if state == 'absent':
        current = get_mysql_tablespace(cursor, server_version, name, module=module)
        if current is None:
            module.exit_json(changed=False)

        query = build_drop_query(name)
        queries.append(query)

        if module.check_mode:
            module.exit_json(changed=True, queries=queries)

        try:
            execute_query(cursor, query)
        except Exception as e:
            module.fail_json(msg=to_native(e))

        module.exit_json(changed=True, queries=queries)

    current, rename_already_applied = resolve_current_tablespace(
        module,
        cursor,
        server_version,
        name,
        rename_to=rename_to,
    )

    if current is None:
        try:
            validate_tablespace_datafile(server_version, datafile)
        except ValueError as e:
            module.fail_json(msg=to_native(e))

        query = build_create_query(
            name,
            datafile=datafile,
            file_block_size=file_block_size,
            encryption=encryption,
            autoextend_size=autoextend_size,
        )
        queries.append(query)

        predicted = predict_tablespace(
            name=name,
            datafile=datafile,
            encryption=encryption,
            autoextend_size=autoextend_size,
        )

        if module.check_mode:
            module.exit_json(changed=True, queries=queries, tablespace=predicted)

        try:
            execute_query(cursor, query)
        except Exception as e:
            module.fail_json(msg=to_native(e))

        current = get_mysql_tablespace(cursor, server_version, name, module=module)
        module.exit_json(changed=True, queries=queries, tablespace=current or predicted)

    if rename_already_applied:
        fail_if_rename_target_requires_changes(
            module,
            current,
            rename_to,
            datafile=datafile,
            file_block_size=file_block_size,
            encryption=encryption,
            autoextend_size=autoextend_size,
        )
    else:
        fail_if_create_only_options_differ(
            module,
            current,
            datafile=datafile,
            file_block_size=file_block_size,
        )

    queries = build_alter_queries(
        current,
        rename_to=rename_to,
        encryption=encryption,
        autoextend_size=autoextend_size,
    )

    if not queries:
        module.exit_json(changed=False, tablespace=current)

    predicted = predict_tablespace(
        current=current,
        encryption=encryption,
        autoextend_size=autoextend_size,
        rename_to=rename_to,
    )

    if module.check_mode:
        module.exit_json(changed=True, queries=queries, tablespace=predicted)

    try:
        for query in queries:
            execute_query(cursor, query)
    except Exception as e:
        module.fail_json(msg=to_native(e))

    current = get_mysql_tablespace(cursor, server_version, predicted['name'], module=module)
    module.exit_json(changed=True, queries=queries, tablespace=current or predicted)


if __name__ == '__main__':
    main()
