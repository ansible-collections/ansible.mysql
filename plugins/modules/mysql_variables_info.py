#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_variables_info
short_description: Gather MySQL or MariaDB variable values
description:
  - Returns MySQL/MariaDB system variable values.
  - Executes SHOW GLOBAL VARIABLES or retrieves a specific variable.
version_added: "0.1.0"
options:
  variable:
    description:
      - Specific variable name to query.
      - If omitted, returns all global variables.
    type: str

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_variables
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get all variables
  ansible.mysql.mysql_variables_info:
    login_user: root
    login_password: secret
  register: vars_info

- name: Get a specific variable
  ansible.mysql.mysql_variables_info:
    login_user: root
    login_password: secret
    variable: max_connections
  register: result

- debug:
    msg: "Max connections: {{ result.variables.max_connections }}"
'''

RETURN = r'''
variables:
  description: Dictionary of variable names and values.
  returned: always
  type: dict
  sample:
    max_connections: "151"
    innodb_buffer_pool_size: "134217728"
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
        variable=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    variable = module.params.get('variable')

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, db_conn = mysql_connect(module, 'root', cursor_class='DictCursor')
    except Exception as e:
        module.fail_json(msg=f"unable to connect to database: {str(e)}")

    try:
        if variable:
            cursor.execute("SHOW GLOBAL VARIABLES LIKE %s", [variable])
        else:
            cursor.execute("SHOW GLOBAL VARIABLES")

        variables = {row['Variable_name']: row['Value'] for row in cursor.fetchall()}
        module.exit_json(changed=False, variables=variables)
    except Exception as e:
        module.fail_json(msg=f"unable to get variable info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
