#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Steve Fulmer
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_replication_info
short_description: Gather MySQL or MariaDB replication status
description:
  - Returns MySQL/MariaDB replication status.
  - Executes SHOW MASTER STATUS and SHOW REPLICA STATUS (or SHOW SLAVE STATUS).
version_added: "0.1.0"

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_replication
- module: ansible.mysql.mysql_info

author:
- Steve Fulmer (@stevefulme1)

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Get replication status
  ansible.mysql.mysql_replication_info:
    login_user: root
    login_password: secret
  register: repl_info

- name: Check if server is a replica
  ansible.mysql.mysql_replication_info:
    login_user: repl_user
    login_password: secret
  register: result

- debug:
    msg: "Replica lag: {{ result.replica_status.Seconds_Behind_Master }}"
  when: result.replica_status is defined
'''

RETURN = r'''
master_status:
  description: Output of SHOW MASTER STATUS.
  returned: always
  type: dict
  sample:
    File: mysql-bin.000123
    Position: 456789
replica_status:
  description: Output of SHOW REPLICA STATUS (or SHOW SLAVE STATUS).
  returned: when server is configured as a replica
  type: dict
  sample:
    Slave_IO_Running: "Yes"
    Slave_SQL_Running: "Yes"
    Seconds_Behind_Master: 0
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

    result = {}

    try:
        # Get master status
        cursor.execute("SHOW MASTER STATUS")
        master_row = cursor.fetchone()
        if master_row:
            result['master_status'] = dict(master_row)
        else:
            result['master_status'] = {}

        # Try SHOW REPLICA STATUS (MySQL 8.0.22+)
        try:
            cursor.execute("SHOW REPLICA STATUS")
            replica_row = cursor.fetchone()
            if replica_row:
                result['replica_status'] = dict(replica_row)
        except Exception:
            # Fall back to SHOW SLAVE STATUS
            try:
                cursor.execute("SHOW SLAVE STATUS")
                replica_row = cursor.fetchone()
                if replica_row:
                    result['replica_status'] = dict(replica_row)
            except Exception:
                pass

        module.exit_json(changed=False, **result)
    except Exception as e:
        module.fail_json(msg=f"unable to get replication info: {str(e)}")
    finally:
        cursor.close()


if __name__ == '__main__':
    main()
