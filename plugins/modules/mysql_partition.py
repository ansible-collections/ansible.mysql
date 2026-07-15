#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
---
module: mysql_partition

short_description: Manage MySQL table partitions

description:
  - Add, drop, reorganize, truncate, or run maintenance operations on MySQL table partitions.
  - Supports RANGE, RANGE COLUMNS, LIST, LIST COLUMNS, HASH, and KEY partition types.
  - The module auto-detects the partition method of the target table and generates the appropriate SQL syntax.
  - The module is limited to MySQL and fails on MariaDB.

version_added: '5.2.0'

options:
  table:
    description:
      - Name of the partitioned table to manage.
    type: str
    required: true
  schema:
    description:
      - Database (schema) containing the table.
      - If omitted, the current default database from the connection is used.
    type: str
  action:
    description:
      - Partition operation to perform.
      - V(add) adds a new partition. For RANGE and LIST types, O(name) and O(value) are required.
        For HASH and KEY types, O(number) is required instead.
      - V(drop) removes partitions. Only valid for RANGE and LIST types.
      - V(reorganize) splits or merges partitions. Only valid for RANGE and LIST types.
        Requires O(name) and O(into).
      - V(truncate) removes all rows from specified partitions without dropping them.
      - V(check), V(repair), V(analyze), and V(optimize) run maintenance operations on specified partitions.
    type: str
    required: true
    choices:
      - add
      - drop
      - reorganize
      - truncate
      - check
      - repair
      - analyze
      - optimize
  name:
    description:
      - Partition name or names to operate on.
      - For O(action=add) on RANGE and LIST partition types, provide exactly one partition name.
      - For O(action=drop), O(action=truncate), O(action=check), O(action=repair),
        O(action=analyze), and O(action=optimize), provide one or more partition names.
      - For O(action=reorganize), specifies the source partitions to reorganize.
      - For maintenance and truncate actions, a single-element list containing V(ALL) targets every partition.
    type: list
    elements: str
  value:
    description:
      - Partition boundary expression, written as raw SQL.
      - For RANGE partitions, this is the expression used in C(VALUES LESS THAN), for example
        V(2024), V(MAXVALUE), or V('2024-07-01').
      - For LIST partitions, this is the expression used in C(VALUES IN), for example V(7,8,9).
      - Required when O(action=add) for RANGE and LIST partition types.
    type: str
  number:
    description:
      - Number of partitions to add.
      - Used only when O(action=add) for HASH and KEY partition types.
    type: int
  into:
    description:
      - List of target partition definitions for reorganize.
      - Each element is a dictionary with O(into[].name) and O(into[].value) keys.
      - Required when O(action=reorganize).
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - Name of the target partition.
        type: str
        required: true
      value:
        description:
          - Partition boundary expression for the target partition, written as raw SQL.
        type: str
        required: true

notes:
  - MariaDB is not supported. The module fails with an error on MariaDB servers.
  - C(DROP PARTITION) is only supported for RANGE and LIST partition types.
    HASH and KEY partitions cannot be dropped individually.
  - C(REORGANIZE PARTITION) with value definitions is only supported for RANGE and LIST types.
  - The O(value) and O(into[].value) parameters accept raw SQL expressions.
    They are validated against common SQL injection patterns but are not parameterized.
  - Each invocation runs a single C(ALTER TABLE ... PARTITION) statement.
  - For O(action=add) on HASH or KEY partitions, each call increases the partition count and is not idempotent.
  - Reducing HASH and KEY partition counts with C(COALESCE PARTITION) is not currently supported.

attributes:
  check_mode:
    support: full
  idempotent:
    support: partial
    details:
      - O(action=add) for RANGE and LIST types is idempotent when the partition already exists.
      - O(action=drop) is idempotent when the partition does not exist.
      - O(action=reorganize) is idempotent when the target partition layout already matches O(into).
      - Maintenance operations and truncate always report C(changed=true).
      - O(action=add) for HASH and KEY types always reports C(changed=true).

seealso:
  - module: ansible.mysql.mysql_db
  - module: ansible.mysql.mysql_query
  - name: MySQL ALTER TABLE Partition Operations
    description: Complete reference of MySQL partition management statements.
    link: https://dev.mysql.com/doc/refman/8.4/en/alter-table-partition-operations.html

author:
  - Ron Gershburg (@rgershbu)

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Add a RANGE partition for the next year
  ansible.mysql.mysql_partition:
    table: events
    schema: mydb
    action: add
    name: p2025
    value: "2026"
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Add a LIST partition for new regions
  ansible.mysql.mysql_partition:
    table: sales
    schema: mydb
    action: add
    name: p_south
    value: "10, 11, 12"
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Add partitions to a HASH-partitioned table
  ansible.mysql.mysql_partition:
    table: sessions
    schema: mydb
    action: add
    number: 4
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Drop an old partition
  ansible.mysql.mysql_partition:
    table: events
    schema: mydb
    action: drop
    name:
      - p2020
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Reorganize a partition into two
  ansible.mysql.mysql_partition:
    table: events
    schema: mydb
    action: reorganize
    name:
      - p2024
    into:
      - name: p2024h1
        value: "2024"
      - name: p2024h2
        value: "2025"
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Truncate a partition
  ansible.mysql.mysql_partition:
    table: events
    schema: mydb
    action: truncate
    name:
      - p2020
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Analyze all partitions
  ansible.mysql.mysql_partition:
    table: events
    schema: mydb
    action: analyze
    name:
      - ALL
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Monthly partition rotation
  block:
    - name: Add next month partition
      ansible.mysql.mysql_partition:
        table: events
        schema: mydb
        action: add
        name: p202502
        value: "'2025-03-01'"
        login_unix_socket: /run/mysqld/mysqld.sock

    - name: Drop oldest partition
      ansible.mysql.mysql_partition:
        table: events
        schema: mydb
        action: drop
        name:
          - p202401
        login_unix_socket: /run/mysqld/mysqld.sock
'''

RETURN = r'''
queries:
  description: List of SQL queries executed (or that would be executed in check mode).
  returned: always
  type: list
  elements: str
  sample: ["ALTER TABLE `mydb`.`events` ADD PARTITION (PARTITION `p2025` VALUES LESS THAN (2026))"]
partition_info:
  description: Partition metadata from C(INFORMATION_SCHEMA.PARTITIONS) after the operation.
  returned: success
  type: list
  elements: dict
  contains:
    PARTITION_NAME:
      description: Name of the partition.
      returned: success
      type: str
      sample: p2025
    PARTITION_METHOD:
      description: Partitioning method used by the table.
      returned: success
      type: str
      sample: RANGE
    PARTITION_EXPRESSION:
      description: Expression used by the table partition definition.
      returned: success
      type: str
      sample: created_year
    PARTITION_DESCRIPTION:
      description: Partition boundary or value list as reported by C(INFORMATION_SCHEMA.PARTITIONS).
      returned: success
      type: str
      sample: '2026'
    PARTITION_ORDINAL_POSITION:
      description: Position of the partition within the table definition.
      returned: success
      type: int
      sample: 4
    TABLE_ROWS:
      description: Estimated number of rows stored in the partition.
      returned: success
      type: int
      sample: 0
msg:
  description: Human-readable description of the result.
  returned: always
  type: str
  sample: "Partition p2025 added."
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.ansible.mysql.plugins.module_utils.database import (
    check_input,
    mysql_quote_identifier,
)
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)


PARTITION_QUERY = (
    "SELECT PARTITION_NAME, PARTITION_METHOD, PARTITION_EXPRESSION, "
    "PARTITION_DESCRIPTION, PARTITION_ORDINAL_POSITION, TABLE_ROWS "
    "FROM INFORMATION_SCHEMA.PARTITIONS "
    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
    "AND PARTITION_NAME IS NOT NULL "
    "AND SUBPARTITION_NAME IS NULL "
    "ORDER BY PARTITION_ORDINAL_POSITION"
)

HASH_KEY_METHODS = frozenset(('HASH', 'LINEAR HASH', 'KEY', 'LINEAR KEY'))
RANGE_METHODS = frozenset(('RANGE', 'RANGE COLUMNS'))
LIST_METHODS = frozenset(('LIST', 'LIST COLUMNS'))
MAINTENANCE_ACTIONS = frozenset(('check', 'repair', 'analyze', 'optimize'))


def quote_partition(name):
    return '`%s`' % name.replace('`', '``')


def get_table_ref(schema, table):
    if schema:
        return mysql_quote_identifier('%s.%s' % (schema, table), 'table')
    return mysql_quote_identifier(table, 'table')


def get_current_schema(cursor):
    cursor.execute("SELECT DATABASE()")
    row = cursor.fetchone()
    if row:
        return row.get('DATABASE()')
    return None


def get_partition_info(cursor, schema, table):
    cursor.execute(PARTITION_QUERY, (schema, table))
    return [dict(row) for row in cursor.fetchall()]


def partition_exists(partitions, name):
    return any(p['PARTITION_NAME'] == name for p in partitions)


def get_partition(partitions, name):
    for partition in partitions:
        if partition['PARTITION_NAME'] == name:
            return partition
    return None


def get_partition_method(partitions):
    if not partitions:
        return None
    return partitions[0]['PARTITION_METHOD']


def normalize_partition_description(value):
    return ','.join(str(value).strip().split(','))


def reorganize_matches_current_state(current_partitions, source_names, into):
    if any(partition_exists(current_partitions, source_name) for source_name in source_names):
        return False

    for target in into:
        current_partition = get_partition(current_partitions, target['name'])
        if current_partition is None:
            return False
        if normalize_partition_description(current_partition['PARTITION_DESCRIPTION']) != normalize_partition_description(target['value']):
            return False

    return True


def build_add_query(table_ref, partition_method, partition_name, value, number):
    if partition_method in HASH_KEY_METHODS:
        return 'ALTER TABLE %s ADD PARTITION PARTITIONS %d' % (table_ref, number)

    pname = quote_partition(partition_name)
    if partition_method in RANGE_METHODS:
        return 'ALTER TABLE %s ADD PARTITION (PARTITION %s VALUES LESS THAN (%s))' % (
            table_ref, pname, value)

    return 'ALTER TABLE %s ADD PARTITION (PARTITION %s VALUES IN (%s))' % (
        table_ref, pname, value)


def build_drop_query(table_ref, partitions):
    quoted = ', '.join(quote_partition(p) for p in partitions)
    return 'ALTER TABLE %s DROP PARTITION %s' % (table_ref, quoted)


def build_reorganize_query(table_ref, partition_method, source_partitions, into):
    source = ', '.join(quote_partition(p) for p in source_partitions)

    defs = []
    for part in into:
        pname = quote_partition(part['name'])
        val = part['value']
        if partition_method in RANGE_METHODS:
            defs.append('PARTITION %s VALUES LESS THAN (%s)' % (pname, val))
        else:
            defs.append('PARTITION %s VALUES IN (%s)' % (pname, val))

    return 'ALTER TABLE %s REORGANIZE PARTITION %s INTO (%s)' % (
        table_ref, source, ', '.join(defs))


def build_truncate_query(table_ref, partitions):
    if len(partitions) == 1 and partitions[0].upper() == 'ALL':
        return 'ALTER TABLE %s TRUNCATE PARTITION ALL' % table_ref
    quoted = ', '.join(quote_partition(p) for p in partitions)
    return 'ALTER TABLE %s TRUNCATE PARTITION %s' % (table_ref, quoted)


def build_maintenance_query(table_ref, action, partitions):
    if len(partitions) == 1 and partitions[0].upper() == 'ALL':
        return 'ALTER TABLE %s %s PARTITION ALL' % (table_ref, action.upper())
    quoted = ', '.join(quote_partition(p) for p in partitions)
    return 'ALTER TABLE %s %s PARTITION %s' % (table_ref, action.upper(), quoted)


def validate_inputs(module, action, partition_method, names, value, number, into):
    if action == 'add':
        if partition_method in HASH_KEY_METHODS:
            if number is None:
                module.fail_json(msg='number is required when adding %s partitions.' % partition_method)
            if number < 1:
                module.fail_json(msg='number must be at least 1.')
        else:
            if not names:
                module.fail_json(msg='name is required when adding %s partitions.' % partition_method)
            if len(names) != 1:
                module.fail_json(msg='exactly one name is required when adding %s partitions.' % partition_method)
            if value is None:
                module.fail_json(msg='value is required when adding %s partitions.' % partition_method)

    elif action == 'drop':
        if not names:
            module.fail_json(msg='name is required for drop.')
        if partition_method in HASH_KEY_METHODS:
            module.fail_json(
                msg='DROP PARTITION is not supported for %s partitions.' % partition_method)

    elif action == 'reorganize':
        if not names:
            module.fail_json(msg='name is required for reorganize (source partitions).')
        if not into:
            module.fail_json(msg='into is required for reorganize (target partition definitions).')
        if partition_method in HASH_KEY_METHODS:
            module.fail_json(
                msg='REORGANIZE PARTITION with value definitions is not supported for %s partitions.' % partition_method)

    elif action == 'truncate' or action in MAINTENANCE_ACTIONS:
        if not names:
            module.fail_json(msg='name is required for %s.' % action)


def handle_add(module, cursor, table_ref, schema, table, partition_method, current_partitions):
    names = module.params['name'] or []
    value = module.params['value']
    number = module.params['number']

    if partition_method in HASH_KEY_METHODS:
        query = build_add_query(table_ref, partition_method, None, None, number)
    else:
        partition_name = names[0]
        if partition_exists(current_partitions, partition_name):
            module.exit_json(
                changed=False, queries=[],
                partition_info=current_partitions,
                msg='Partition %s already exists.' % partition_name)

        query = build_add_query(table_ref, partition_method, partition_name, value, None)

    queries = [query]
    if module.check_mode:
        module.exit_json(
            changed=True, queries=queries,
            partition_info=current_partitions,
            msg='Partition would be added.')

    try:
        cursor.execute(query)
    except Exception as e:
        module.fail_json(msg='Failed to add partition: %s' % to_native(e), queries=queries)

    return queries


def handle_drop(module, cursor, table_ref, schema, table, current_partitions):
    partitions = module.params['name']

    existing = [p for p in partitions if partition_exists(current_partitions, p)]
    if not existing:
        module.exit_json(
            changed=False, queries=[],
            partition_info=current_partitions,
            msg='No matching partitions to drop.')

    query = build_drop_query(table_ref, existing)
    queries = [query]

    if module.check_mode:
        module.exit_json(
            changed=True, queries=queries,
            partition_info=current_partitions,
            msg='Partitions would be dropped.')

    try:
        cursor.execute(query)
    except Exception as e:
        module.fail_json(msg='Failed to drop partition: %s' % to_native(e), queries=queries)

    return queries


def handle_reorganize(module, cursor, table_ref, partition_method, current_partitions):
    partitions = module.params['name']
    into = module.params['into']

    if reorganize_matches_current_state(current_partitions, partitions, into):
        module.exit_json(
            changed=False, queries=[],
            partition_info=current_partitions,
            msg='Partitions already match requested layout.')

    missing = [partition for partition in partitions if not partition_exists(current_partitions, partition)]
    if missing:
        module.fail_json(
            msg='Source partitions do not exist: %s.' % ', '.join(missing),
            partition_info=current_partitions)

    query = build_reorganize_query(table_ref, partition_method, partitions, into)
    queries = [query]

    if module.check_mode:
        module.exit_json(
            changed=True, queries=queries,
            partition_info=current_partitions,
            msg='Partitions would be reorganized.')

    try:
        cursor.execute(query)
    except Exception as e:
        module.fail_json(msg='Failed to reorganize partitions: %s' % to_native(e), queries=queries)

    return queries


def handle_truncate(module, cursor, table_ref, current_partitions):
    partitions = module.params['name']

    query = build_truncate_query(table_ref, partitions)
    queries = [query]

    if module.check_mode:
        module.exit_json(
            changed=True, queries=queries,
            partition_info=current_partitions,
            msg='Partitions would be truncated.')

    try:
        cursor.execute(query)
    except Exception as e:
        module.fail_json(msg='Failed to truncate partition: %s' % to_native(e), queries=queries)

    return queries


def handle_maintenance(module, cursor, table_ref, action, current_partitions):
    partitions = module.params['name']

    query = build_maintenance_query(table_ref, action, partitions)
    queries = [query]

    if module.check_mode:
        module.exit_json(
            changed=True, queries=queries,
            partition_info=current_partitions,
            msg='%s PARTITION would be executed.' % action.upper())

    try:
        cursor.execute(query)
    except Exception as e:
        module.fail_json(msg='Failed to %s partition: %s' % (action, to_native(e)), queries=queries)

    return queries


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        table=dict(type='str', required=True),
        schema=dict(type='str'),
        action=dict(type='str', required=True, choices=[
            'add', 'drop', 'reorganize', 'truncate',
            'check', 'repair', 'analyze', 'optimize',
        ]),
        name=dict(type='list', elements='str'),
        value=dict(type='str'),
        number=dict(type='int'),
        into=dict(type='list', elements='dict', options=dict(
            name=dict(type='str', required=True),
            value=dict(type='str', required=True),
        )),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    action = module.params['action']
    table = module.params['table']
    schema = module.params['schema']

    check_input(module, table, schema, module.params['value'])
    if module.params['name']:
        check_input(module, module.params['name'])
    if module.params['into']:
        for item in module.params['into']:
            check_input(module, item['name'], item['value'])

    try:
        cursor, db_conn = mysql_connect(
            module,
            module.params['login_user'],
            module.params['login_password'],
            module.params['config_file'],
            module.params['client_cert'],
            module.params['client_key'],
            module.params['ca_cert'],
            connect_timeout=module.params['connect_timeout'],
            check_hostname=module.params['check_hostname'],
            cursor_class='DictCursor',
            autocommit=True,
        )
    except Exception as e:
        module.fail_json(msg='unable to connect to database: %s' % to_native(e))

    if get_server_implementation(module, cursor) != 'mysql':
        module.fail_json(msg='mysql_partition is supported only by MySQL. MariaDB is not supported.')

    if not schema:
        schema = get_current_schema(cursor)
        if not schema:
            module.fail_json(msg='No database selected and schema parameter not specified.')

    current_partitions = get_partition_info(cursor, schema, table)
    if not current_partitions:
        module.fail_json(msg='Table %s.%s does not exist or is not partitioned.' % (schema, table))

    partition_method = get_partition_method(current_partitions)
    table_ref = get_table_ref(schema, table)

    validate_inputs(
        module, action, partition_method,
        module.params['name'], module.params['value'],
        module.params['number'], module.params['into'])

    if action == 'add':
        queries = handle_add(module, cursor, table_ref, schema, table, partition_method, current_partitions)
    elif action == 'drop':
        queries = handle_drop(module, cursor, table_ref, schema, table, current_partitions)
    elif action == 'reorganize':
        queries = handle_reorganize(module, cursor, table_ref, partition_method, current_partitions)
    elif action == 'truncate':
        queries = handle_truncate(module, cursor, table_ref, current_partitions)
    else:
        queries = handle_maintenance(module, cursor, table_ref, action, current_partitions)

    updated_partitions = get_partition_info(cursor, schema, table)

    module.exit_json(
        changed=True,
        queries=queries,
        partition_info=updated_partitions,
        msg='%s partition operation completed.' % action.upper(),
    )


if __name__ == '__main__':
    main()
