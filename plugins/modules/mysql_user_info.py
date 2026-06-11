#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_user_info
short_description: Gather information about MySQL or MariaDB users
description:
  - Returns information about users on a MySQL or MariaDB server.
  - Queries mysql.user table for user metadata.
version_added: "0.1.0"
options:
  name:
    description:
      - Name of a specific user to query.
      - If omitted, returns info for all users.
    type: str
  host:
    description:
      - Host part of the user to query.
      - Only used when I(name) is specified.
    type: str
    default: '%'

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_user
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get all user info
  ansible.mysql.mysql_user_info:
    login_user: root
    login_password: secret
  register: user_info

- name: Get info for a specific user
  ansible.mysql.mysql_user_info:
    login_user: root
    login_password: secret
    name: myapp_user
    host: localhost
  register: user_info
'''

RETURN = r'''
users:
  description: List of user dictionaries.
  returned: always
  type: list
  elements: dict
  contains:
    user:
      description: Username.
      type: str
    host:
      description: Host from which user can connect.
      type: str
    plugin:
      description: Authentication plugin.
      type: str
    password_expired:
      description: Whether password is expired.
      type: str
    account_locked:
      description: Whether account is locked.
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
        host=dict(type='str', default='%'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    name = module.params.get('name')
    host = module.params.get('host')

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, db_conn = mysql_connect(module, 'root', cursor_class='DictCursor')
    except Exception as e:
        module.fail_json(msg=f"unable to connect to database: {str(e)}")

    try:
        query = "SELECT User, Host, plugin, password_expired, account_locked FROM mysql.user"
        params = []

        if name:
            query += " WHERE User = %s"
            params.append(name)
            if host != '%':
                query += " AND Host = %s"
                params.append(host)

        cursor.execute(query, params)
        users = [dict(user=row['User'], host=row['Host'], plugin=row['plugin'],
                      password_expired=row['password_expired'], account_locked=row['account_locked'])
                 for row in cursor.fetchall()]

        module.exit_json(changed=False, users=users)
    except Exception as e:
        module.fail_json(msg=f"unable to get user info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
