#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible community
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_tablespace_info

short_description: Gather MySQL tablespace information

description:
  - Gather general tablespace metadata from MySQL servers.
  - This module returns the general-tablespace view using
    C(INFORMATION_SCHEMA.FILES) together with the version-appropriate InnoDB metadata family.
  - On V(5.7), the module uses C(INFORMATION_SCHEMA.INNODB_SYS_TABLESPACES),
    C(INFORMATION_SCHEMA.INNODB_SYS_DATAFILES), and C(INFORMATION_SCHEMA.INNODB_SYS_TABLES).
  - On V(8.0) or later, the module uses C(INFORMATION_SCHEMA.INNODB_TABLESPACES),
    C(INFORMATION_SCHEMA.INNODB_DATAFILES), and C(INFORMATION_SCHEMA.INNODB_TABLES).
  - This module is read-only and always reports no change.

version_added: '5.2.0'

options:
  name:
    description:
      - Limit the collected information to a single tablespace name.
      - This matches the general tablespace name.
    type: str
    version_added: '5.2.0'

notes:
  - Compatible with MySQL V(5.7.6) or later.
  - This module reports metadata only. Key rotation remains outside scope because
    MySQL exposes it through C(ALTER INSTANCE ROTATE INNODB MASTER KEY).
  - Tablespace metadata queries may require the C(PROCESS) privilege.
  - No external tools are required.

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
  - module: ansible.mysql.mysql_tablespace
  - name: MySQL INFORMATION_SCHEMA FILES reference
    description: Reference for C(INFORMATION_SCHEMA.FILES), used as the base MySQL metadata source.
    link: https://dev.mysql.com/doc/refman/8.4/en/information-schema-files-table.html

author:
  - Ron Gershburg (@ronger4)

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
# If you encounter the "Please explicitly state intended protocol" error,
# use the login_unix_socket argument
- name: Gather MySQL tablespace information
  ansible.mysql.mysql_tablespace_info:
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Gather one MySQL tablespace by name
  ansible.mysql.mysql_tablespace_info:
    login_unix_socket: /run/mysqld/mysqld.sock
    name: app_data
'''

RETURN = r'''
tablespaces:
  description:
    - List of normalized MySQL tablespace metadata rows.
    - Rows expose the general-tablespace view returned by the server.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Tablespace name.
      type: str
      sample: app_data
    space_id:
      description: Internal InnoDB space identifier.
      type: int
      sample: 17
    datafile:
      description: Tablespace datafile path reported by the server.
      returned: when available
      type: str
      sample: ./app_data.ibd
    extent_size:
      description: Extent size in bytes.
      returned: when available
      type: int
      sample: 1048576
    autoextend_size:
      description: Autoextend size in bytes.
      returned: when available
      type: int
      sample: 8388608
    maximum_size:
      description: Maximum size in bytes.
      returned: when available
      type: int
      sample: 67108864
    filesystem_block_size:
      description: Filesystem block size in bytes when available.
      returned: when available
      type: int
      sample: 4096
    page_size:
      description: InnoDB page size in bytes when available.
      returned: when available
      type: int
      sample: 16384
    file_size:
      description: Current file size in bytes when available.
      returned: when available
      type: int
      sample: 16777216
    allocated_size:
      description: Allocated size in bytes when available.
      returned: when available
      type: int
      sample: 8388608
    status:
      description: Tablespace status reported by the server.
      returned: when available
      type: str
      sample: NORMAL
    zip_page_size:
      description: Compressed page size in bytes.
      returned: when available
      type: int
      sample: 0
    state:
      description: Tablespace state.
      returned: when available
      type: str
      sample: active
    encryption:
      description: Encryption state.
      returned: when available
      type: str
      sample: N
    attached_tables:
      description: Tables attached to the tablespace when the server exposes them.
      type: list
      elements: str
      sample:
        - app/orders
        - app/order_items
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)
from ansible_collections.ansible.mysql.plugins.module_utils.tablespace import (
    ensure_tablespaces_supported,
    get_server_version_tuple,
    get_mysql_tablespaces,
)


def get_tablespaces_info(cursor, name=None, server_version=None, module=None):
    if server_version is None:
        server_version = get_server_version_tuple(cursor)

    return {
        'tablespaces': [
            format_tablespace_info(row)
            for row in get_mysql_tablespaces(
                cursor,
                server_version,
                name=name,
                module=module,
            )
        ]
    }


def format_tablespace_info(row):
    info = {
        'name': row['name'],
        'space_id': row['space_id'],
        'attached_tables': row['attached_tables'],
    }

    optional_fields = (
        'datafile',
        'extent_size',
        'autoextend_size',
        'maximum_size',
        'filesystem_block_size',
        'page_size',
        'file_size',
        'allocated_size',
        'zip_page_size',
        'status',
        'state',
        'encryption',
    )

    for field_name in optional_fields:
        if field_name in row and row[field_name] is not None:
            info[field_name] = row[field_name]

    return info


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    login_user = module.params['login_user']
    login_password = module.params['login_password']
    config_file = module.params['config_file']
    ssl_cert = module.params['client_cert']
    ssl_key = module.params['client_key']
    ssl_ca = module.params['ca_cert']
    connect_timeout = module.params['connect_timeout']
    check_hostname = module.params['check_hostname']
    name = module.params['name']

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
        )
    except Exception as e:
        module.fail_json(msg='unable to connect to database: %s' % to_native(e))

    server_version = ensure_tablespaces_supported(module, cursor)

    module.exit_json(
        changed=False,
        **get_tablespaces_info(
            cursor,
            name=name,
            server_version=server_version,
            module=module,
        )
    )


if __name__ == '__main__':
    main()
