#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_role_info
short_description: Gather information about MySQL or MariaDB roles
description:
  - Returns information about roles on a MySQL 8.0+ or MariaDB 10.0.5+ server.
  - Roles are not supported in MySQL < 8.0 or MariaDB < 10.0.5.
version_added: "0.1.0"
options:
  name:
    description:
      - Name of a specific role to query.
      - If omitted, returns info for all roles.
    type: str

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_role
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get all role info
  ansible.mysql.mysql_role_info:
    login_user: root
    login_password: secret
  register: role_info

- name: Get info for a specific role
  ansible.mysql.mysql_role_info:
    login_user: root
    login_password: secret
    name: app_reader
  register: role_info
'''

RETURN = r'''
roles:
  description: List of role dictionaries.
  returned: always
  type: list
  elements: dict
  contains:
    user:
      description: Role name (stored as a user).
      type: str
    host:
      description: Host (always '%' for roles).
      type: str
    account_locked:
      description: Whether role is locked.
      type: str
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
    mysql_common_argument_spec,
)


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    name = module.params.get('name')

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, db_conn = mysql_connect(module, 'root', cursor_class='DictCursor')
    except Exception as e:
        module.fail_json(msg=f"unable to connect to database: {str(e)}")

    try:
        # Roles are users with account_locked = 'Y' and Host = '%'
        query = "SELECT User, Host, account_locked FROM mysql.user WHERE account_locked = 'Y'"
        params = []

        if name:
            query += " AND User = %s"
            params.append(name)

        cursor.execute(query, params)
        roles = [dict(user=row['User'], host=row['Host'], account_locked=row['account_locked'])
                 for row in cursor.fetchall()]

        module.exit_json(changed=False, roles=roles)
    except Exception as e:
        module.fail_json(msg=f"unable to get role info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
