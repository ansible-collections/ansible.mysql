#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_tls_info
short_description: Gather MySQL or MariaDB TLS/SSL configuration
description:
  - Returns MySQL/MariaDB TLS/SSL configuration and status.
  - Queries TLS-related system variables.
version_added: "0.1.0"

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_tls
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get TLS configuration
  ansible.mysql.mysql_tls_info:
    login_user: root
    login_password: secret
  register: tls_info

- name: Check if TLS is enabled
  ansible.mysql.mysql_tls_info:
    login_user: root
    login_password: secret
  register: result

- debug:
    msg: "TLS is {{ 'enabled' if result.tls_enabled else 'disabled' }}"
'''

RETURN = r'''
tls_enabled:
  description: Whether TLS is enabled on the server.
  returned: always
  type: bool
have_ssl:
  description: Server SSL capability status.
  returned: always
  type: str
ssl_ca:
  description: Path to CA certificate file.
  returned: always
  type: str
ssl_cert:
  description: Path to server certificate file.
  returned: always
  type: str
ssl_key:
  description: Path to server key file.
  returned: always
  type: str
ssl_cipher:
  description: Permitted SSL ciphers.
  returned: always
  type: str
tls_version:
  description: Permitted TLS versions.
  returned: always
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

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, db_conn = mysql_connect(module, 'root', cursor_class='DictCursor')
    except Exception as e:
        module.fail_json(msg=f"unable to connect to database: {str(e)}")

    try:
        tls_vars = [
            'have_ssl', 'ssl_ca', 'ssl_cert', 'ssl_key',
            'ssl_cipher', 'tls_version'
        ]

        result = {}
        for var in tls_vars:
            cursor.execute("SHOW GLOBAL VARIABLES LIKE %s", [var])
            row = cursor.fetchone()
            if row:
                result[var] = row['Value']
            else:
                result[var] = ''

        # Determine if TLS is enabled
        result['tls_enabled'] = result.get('have_ssl', '').upper() == 'YES'

        module.exit_json(changed=False, **result)
    except Exception as e:
        module.fail_json(msg=f"unable to get TLS info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
