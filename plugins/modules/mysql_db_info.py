#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_db_info
short_description: Gather information about MySQL or MariaDB databases
description:
  - Returns information about databases on a MySQL or MariaDB server.
  - Queries INFORMATION_SCHEMA.SCHEMATA and optionally database size.
version_added: "0.1.0"
options:
  name:
    description:
      - Name of a specific database to query.
      - If omitted, returns info for all databases.
    type: str
  exclude_fields:
    description:
      - List of fields which are not needed to collect.
      - "Supports elements: C(db_size). Unsupported elements will be ignored."
    type: list
    elements: str

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_db
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get all database info
  ansible.mysql.mysql_db_info:
    login_user: root
    login_password: secret
    login_unix_socket: /run/mysqld/mysqld.sock
  register: db_info

- name: Get info for a specific database
  ansible.mysql.mysql_db_info:
    login_user: root
    login_password: secret
    name: myapp
  register: db_info

- name: Get database info excluding size calculation
  ansible.mysql.mysql_db_info:
    login_user: root
    login_password: secret
    exclude_fields: db_size
  register: db_info
'''

RETURN = r'''
databases:
  description: Dictionary of database information.
  returned: always
  type: dict
  sample:
    myapp:
      charset: utf8mb4
      collation: utf8mb4_unicode_ci
      size: 1048576
  contains:
    charset:
      description: Default character set.
      type: str
    collation:
      description: Default collation.
      type: str
    size:
      description: Total size in bytes (omitted if excluded).
      type: int
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
    mysql_common_argument_spec,
)


def get_databases_info(cursor, db_name=None, exclude_size=False):
    """Get database information from INFORMATION_SCHEMA."""
    databases = {}

    # Get basic database info
    query = """
        SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
        FROM INFORMATION_SCHEMA.SCHEMATA
    """
    params = []
    if db_name:
        query += " WHERE SCHEMA_NAME = %s"
        params.append(db_name)

    cursor.execute(query, params)

    for row in cursor.fetchall():
        schema_name = row[0]
        databases[schema_name] = {
            'charset': row[1],
            'collation': row[2],
        }

        # Calculate size if not excluded
        if not exclude_size:
            size_query = """
                SELECT SUM(DATA_LENGTH + INDEX_LENGTH)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
            """
            cursor.execute(size_query, [schema_name])
            size_result = cursor.fetchone()
            databases[schema_name]['size'] = int(size_result[0] or 0)

    return databases


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        exclude_fields=dict(type='list', elements='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    name = module.params.get('name')
    exclude_fields = module.params.get('exclude_fields') or []
    exclude_size = 'db_size' in exclude_fields

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, db_conn = mysql_connect(module, 'root', cursor_class='DictCursor')
    except Exception as e:
        module.fail_json(msg=f"unable to connect to database: {str(e)}")

    try:
        databases = get_databases_info(cursor, name, exclude_size)
        module.exit_json(changed=False, databases=databases)
    except Exception as e:
        module.fail_json(msg=f"unable to get database info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
