# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.ansible.mysql.plugins.modules.mysql_partition import (
    build_add_query,
    build_drop_query,
    build_maintenance_query,
    build_reorganize_query,
    build_truncate_query,
    get_current_schema,
    get_partition_info,
    get_partition_method,
    get_table_ref,
    handle_add,
    handle_drop,
    handle_maintenance,
    handle_reorganize,
    handle_truncate,
    main,
    partition_exists,
    quote_partition,
    validate_inputs,
)


SAMPLE_RANGE_PARTITIONS = [
    {'PARTITION_NAME': 'p2020', 'PARTITION_METHOD': 'RANGE',
     'PARTITION_EXPRESSION': 'year', 'PARTITION_DESCRIPTION': '2021',
     'PARTITION_ORDINAL_POSITION': 1, 'TABLE_ROWS': 10},
    {'PARTITION_NAME': 'p2021', 'PARTITION_METHOD': 'RANGE',
     'PARTITION_EXPRESSION': 'year', 'PARTITION_DESCRIPTION': '2022',
     'PARTITION_ORDINAL_POSITION': 2, 'TABLE_ROWS': 20},
]

SAMPLE_LIST_PARTITIONS = [
    {'PARTITION_NAME': 'p_east', 'PARTITION_METHOD': 'LIST',
     'PARTITION_EXPRESSION': 'region', 'PARTITION_DESCRIPTION': '1,2,3',
     'PARTITION_ORDINAL_POSITION': 1, 'TABLE_ROWS': 5},
]

SAMPLE_HASH_PARTITIONS = [
    {'PARTITION_NAME': 'p0', 'PARTITION_METHOD': 'HASH',
     'PARTITION_EXPRESSION': 'id', 'PARTITION_DESCRIPTION': None,
     'PARTITION_ORDINAL_POSITION': 1, 'TABLE_ROWS': 0},
    {'PARTITION_NAME': 'p1', 'PARTITION_METHOD': 'HASH',
     'PARTITION_EXPRESSION': 'id', 'PARTITION_DESCRIPTION': None,
     'PARTITION_ORDINAL_POSITION': 2, 'TABLE_ROWS': 0},
]


class DummyModule(object):
    def __init__(self, params=None):
        self.msg = None
        self.exit_kwargs = None
        self.check_mode = False
        self.params = params or {}

    def fail_json(self, msg=None, **kwargs):
        self.msg = msg
        raise RuntimeError(msg)

    def exit_json(self, **kwargs):
        self.exit_kwargs = kwargs
        raise SystemExit(kwargs)


class DummyCursor(object):
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []

    def close(self):
        return None


class FailingCursor(DummyCursor):
    def __init__(self, error_message, trigger_prefix='ALTER TABLE'):
        super(FailingCursor, self).__init__()
        self.error_message = error_message
        self.trigger_prefix = trigger_prefix

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if query.startswith(self.trigger_prefix):
            raise RuntimeError(self.error_message)


class DummyConnection(object):
    def close(self):
        return None


# ── quote_partition ───────────────────────────────────────────────


@pytest.mark.parametrize(
    'name,expected',
    [
        ('p2020', '`p2020`'),
        ('my`part', '`my``part`'),
        ('simple', '`simple`'),
    ]
)
def test_quote_partition(name, expected):
    assert quote_partition(name) == expected


# ── get_table_ref ─────────────────────────────────────────────────


def test_get_table_ref_with_schema():
    assert get_table_ref('mydb', 'events') == '`mydb`.`events`'


def test_get_table_ref_without_schema():
    assert get_table_ref(None, 'events') == '`events`'


# ── get_current_schema ────────────────────────────────────────────


def test_get_current_schema_returns_database():
    cursor = DummyCursor(fetchone_results=[{'DATABASE()': 'testdb'}])

    assert get_current_schema(cursor) == 'testdb'


def test_get_current_schema_returns_none_when_no_database():
    cursor = DummyCursor(fetchone_results=[{'DATABASE()': None}])

    assert get_current_schema(cursor) is None


def test_get_current_schema_returns_none_when_no_row():
    cursor = DummyCursor(fetchone_results=[None])

    assert get_current_schema(cursor) is None


# ── get_partition_info ────────────────────────────────────────────


def test_get_partition_info_returns_list_of_dicts():
    rows = [
        {'PARTITION_NAME': 'p0', 'PARTITION_METHOD': 'RANGE'},
        {'PARTITION_NAME': 'p1', 'PARTITION_METHOD': 'RANGE'},
    ]
    cursor = DummyCursor(fetchall_results=[rows])

    result = get_partition_info(cursor, 'mydb', 'events')

    assert result == rows
    assert cursor.executed[0][1] == ('mydb', 'events')


def test_get_partition_info_returns_empty_for_non_partitioned():
    cursor = DummyCursor(fetchall_results=[[]])

    result = get_partition_info(cursor, 'mydb', 'plain')

    assert result == []


# ── partition_exists ──────────────────────────────────────────────


def test_partition_exists_returns_true():
    assert partition_exists(SAMPLE_RANGE_PARTITIONS, 'p2020') is True


def test_partition_exists_returns_false():
    assert partition_exists(SAMPLE_RANGE_PARTITIONS, 'p9999') is False


def test_partition_exists_empty_list():
    assert partition_exists([], 'p2020') is False


# ── get_partition_method ──────────────────────────────────────────


def test_get_partition_method_returns_method():
    assert get_partition_method(SAMPLE_RANGE_PARTITIONS) == 'RANGE'


def test_get_partition_method_returns_none_for_empty():
    assert get_partition_method([]) is None


def test_get_partition_method_hash():
    assert get_partition_method(SAMPLE_HASH_PARTITIONS) == 'HASH'


# ── build_add_query ───────────────────────────────────────────────


def test_build_add_query_range():
    result = build_add_query('`mydb`.`events`', 'RANGE', 'p2023', '2024', None)

    assert result == (
        "ALTER TABLE `mydb`.`events` ADD PARTITION "
        "(PARTITION `p2023` VALUES LESS THAN (2024))"
    )


def test_build_add_query_range_columns():
    result = build_add_query('`mydb`.`events`', 'RANGE COLUMNS', 'p2023', "'2024-01-01'", None)

    assert result == (
        "ALTER TABLE `mydb`.`events` ADD PARTITION "
        "(PARTITION `p2023` VALUES LESS THAN ('2024-01-01'))"
    )


def test_build_add_query_list():
    result = build_add_query('`mydb`.`sales`', 'LIST', 'p_south', '7, 8, 9', None)

    assert result == (
        "ALTER TABLE `mydb`.`sales` ADD PARTITION "
        "(PARTITION `p_south` VALUES IN (7, 8, 9))"
    )


def test_build_add_query_list_columns():
    result = build_add_query('`mydb`.`sales`', 'LIST COLUMNS', 'p_south', "'x', 'y'", None)

    assert result == (
        "ALTER TABLE `mydb`.`sales` ADD PARTITION "
        "(PARTITION `p_south` VALUES IN ('x', 'y'))"
    )


def test_build_add_query_hash():
    result = build_add_query('`mydb`.`sessions`', 'HASH', None, None, 4)

    assert result == 'ALTER TABLE `mydb`.`sessions` ADD PARTITION PARTITIONS 4'


def test_build_add_query_linear_hash():
    result = build_add_query('`t`', 'LINEAR HASH', None, None, 2)

    assert result == 'ALTER TABLE `t` ADD PARTITION PARTITIONS 2'


def test_build_add_query_key():
    result = build_add_query('`t`', 'KEY', None, None, 3)

    assert result == 'ALTER TABLE `t` ADD PARTITION PARTITIONS 3'


def test_build_add_query_linear_key():
    result = build_add_query('`t`', 'LINEAR KEY', None, None, 1)

    assert result == 'ALTER TABLE `t` ADD PARTITION PARTITIONS 1'


def test_build_add_query_range_maxvalue():
    result = build_add_query('`t`', 'RANGE', 'pmax', 'MAXVALUE', None)

    assert result == (
        "ALTER TABLE `t` ADD PARTITION "
        "(PARTITION `pmax` VALUES LESS THAN (MAXVALUE))"
    )


# ── build_drop_query ──────────────────────────────────────────────


def test_build_drop_query_single():
    result = build_drop_query('`mydb`.`events`', ['p2020'])

    assert result == 'ALTER TABLE `mydb`.`events` DROP PARTITION `p2020`'


def test_build_drop_query_multiple():
    result = build_drop_query('`mydb`.`events`', ['p2020', 'p2021'])

    assert result == 'ALTER TABLE `mydb`.`events` DROP PARTITION `p2020`, `p2021`'


# ── build_reorganize_query ────────────────────────────────────────


def test_build_reorganize_query_range_split():
    into = [
        {'name': 'p2022h1', 'value': '2022'},
        {'name': 'p2022h2', 'value': '2023'},
    ]

    result = build_reorganize_query('`db`.`t`', 'RANGE', ['p2022'], into)

    assert result == (
        "ALTER TABLE `db`.`t` REORGANIZE PARTITION `p2022` INTO "
        "(PARTITION `p2022h1` VALUES LESS THAN (2022), "
        "PARTITION `p2022h2` VALUES LESS THAN (2023))"
    )


def test_build_reorganize_query_range_merge():
    into = [{'name': 'p_merged', 'value': '2023'}]

    result = build_reorganize_query('`db`.`t`', 'RANGE', ['p2021', 'p2022'], into)

    assert result == (
        "ALTER TABLE `db`.`t` REORGANIZE PARTITION `p2021`, `p2022` INTO "
        "(PARTITION `p_merged` VALUES LESS THAN (2023))"
    )


def test_build_reorganize_query_range_columns():
    into = [{'name': 'pa', 'value': "'2023-01-01'"}]

    result = build_reorganize_query('`t`', 'RANGE COLUMNS', ['px'], into)

    assert 'VALUES LESS THAN' in result


def test_build_reorganize_query_list():
    into = [
        {'name': 'p_a', 'value': '1, 2'},
        {'name': 'p_b', 'value': '3, 4'},
    ]

    result = build_reorganize_query('`db`.`t`', 'LIST', ['p_old'], into)

    assert result == (
        "ALTER TABLE `db`.`t` REORGANIZE PARTITION `p_old` INTO "
        "(PARTITION `p_a` VALUES IN (1, 2), "
        "PARTITION `p_b` VALUES IN (3, 4))"
    )


def test_build_reorganize_query_list_columns():
    into = [{'name': 'px', 'value': "'a', 'b'"}]

    result = build_reorganize_query('`t`', 'LIST COLUMNS', ['py'], into)

    assert 'VALUES IN' in result


# ── build_truncate_query ──────────────────────────────────────────


def test_build_truncate_query_named():
    result = build_truncate_query('`db`.`t`', ['p2020'])

    assert result == 'ALTER TABLE `db`.`t` TRUNCATE PARTITION `p2020`'


def test_build_truncate_query_multiple():
    result = build_truncate_query('`db`.`t`', ['p1', 'p2'])

    assert result == 'ALTER TABLE `db`.`t` TRUNCATE PARTITION `p1`, `p2`'


def test_build_truncate_query_all():
    result = build_truncate_query('`db`.`t`', ['ALL'])

    assert result == 'ALTER TABLE `db`.`t` TRUNCATE PARTITION ALL'


def test_build_truncate_query_all_lowercase():
    result = build_truncate_query('`db`.`t`', ['all'])

    assert result == 'ALTER TABLE `db`.`t` TRUNCATE PARTITION ALL'


# ── build_maintenance_query ───────────────────────────────────────


@pytest.mark.parametrize('action', ['check', 'repair', 'analyze', 'optimize'])
def test_build_maintenance_query_named(action):
    result = build_maintenance_query('`db`.`t`', action, ['p0'])

    assert result == 'ALTER TABLE `db`.`t` %s PARTITION `p0`' % action.upper()


@pytest.mark.parametrize('action', ['check', 'repair', 'analyze', 'optimize'])
def test_build_maintenance_query_all(action):
    result = build_maintenance_query('`db`.`t`', action, ['ALL'])

    assert result == 'ALTER TABLE `db`.`t` %s PARTITION ALL' % action.upper()


def test_build_maintenance_query_multiple_partitions():
    result = build_maintenance_query('`t`', 'check', ['p0', 'p1', 'p2'])

    assert result == 'ALTER TABLE `t` CHECK PARTITION `p0`, `p1`, `p2`'


# ── validate_inputs ───────────────────────────────────────────────


def test_validate_inputs_add_range_missing_partition_name():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='partition_name is required'):
        validate_inputs(module, 'add', 'RANGE', None, '2024', None, None, None)


def test_validate_inputs_add_range_missing_value():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='value is required'):
        validate_inputs(module, 'add', 'RANGE', 'p2023', None, None, None, None)


def test_validate_inputs_add_hash_missing_number():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='number is required'):
        validate_inputs(module, 'add', 'HASH', None, None, None, None, None)


def test_validate_inputs_add_hash_number_zero():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='number must be at least 1'):
        validate_inputs(module, 'add', 'HASH', None, None, 0, None, None)


def test_validate_inputs_add_linear_key_missing_number():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='number is required'):
        validate_inputs(module, 'add', 'LINEAR KEY', None, None, None, None, None)


def test_validate_inputs_add_range_valid():
    module = DummyModule()

    validate_inputs(module, 'add', 'RANGE', 'p2023', '2024', None, None, None)


def test_validate_inputs_add_hash_valid():
    module = DummyModule()

    validate_inputs(module, 'add', 'HASH', None, None, 4, None, None)


def test_validate_inputs_drop_missing_partitions():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='partitions is required for drop'):
        validate_inputs(module, 'drop', 'RANGE', None, None, None, None, None)


def test_validate_inputs_drop_hash_rejected():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='not supported for HASH'):
        validate_inputs(module, 'drop', 'HASH', None, None, None, ['p0'], None)


def test_validate_inputs_drop_linear_hash_rejected():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='not supported for LINEAR HASH'):
        validate_inputs(module, 'drop', 'LINEAR HASH', None, None, None, ['p0'], None)


def test_validate_inputs_drop_key_rejected():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='not supported for KEY'):
        validate_inputs(module, 'drop', 'KEY', None, None, None, ['p0'], None)


def test_validate_inputs_drop_range_valid():
    module = DummyModule()

    validate_inputs(module, 'drop', 'RANGE', None, None, None, ['p2020'], None)


def test_validate_inputs_reorganize_missing_partitions():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='partitions is required for reorganize'):
        validate_inputs(module, 'reorganize', 'RANGE', None, None, None, None,
                        [{'name': 'px', 'value': '1'}])


def test_validate_inputs_reorganize_missing_into():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='into is required for reorganize'):
        validate_inputs(module, 'reorganize', 'RANGE', None, None, None, ['p0'], None)


def test_validate_inputs_reorganize_hash_rejected():
    module = DummyModule()

    with pytest.raises(RuntimeError, match='not supported for HASH'):
        validate_inputs(module, 'reorganize', 'HASH', None, None, None,
                        ['p0'], [{'name': 'px', 'value': '1'}])


def test_validate_inputs_reorganize_valid():
    module = DummyModule()

    validate_inputs(module, 'reorganize', 'LIST', None, None, None,
                    ['p_old'], [{'name': 'px', 'value': '1, 2'}])


@pytest.mark.parametrize('action', ['truncate', 'check', 'repair', 'analyze', 'optimize'])
def test_validate_inputs_maintenance_missing_partitions(action):
    module = DummyModule()

    with pytest.raises(RuntimeError, match='partitions is required for %s' % action):
        validate_inputs(module, action, 'RANGE', None, None, None, None, None)


@pytest.mark.parametrize('action', ['truncate', 'check', 'repair', 'analyze', 'optimize'])
def test_validate_inputs_maintenance_valid(action):
    module = DummyModule()

    validate_inputs(module, action, 'RANGE', None, None, None, ['p0'], None)


# ── handle_add ────────────────────────────────────────────────────


def test_handle_add_range_existing_partition_is_idempotent():
    module = DummyModule(params={
        'partition_name': 'p2020', 'value': '2021', 'number': None,
    })
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_add(module, cursor, '`db`.`t`', 'db', 't', 'RANGE', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is False
    assert 'already exists' in result['msg']


def test_handle_add_range_new_partition():
    module = DummyModule(params={
        'partition_name': 'p2023', 'value': '2024', 'number': None,
    })
    cursor = DummyCursor()

    queries = handle_add(module, cursor, '`db`.`t`', 'db', 't', 'RANGE', SAMPLE_RANGE_PARTITIONS)

    assert len(queries) == 1
    assert 'ADD PARTITION' in queries[0]
    assert 'p2023' in queries[0]
    assert len(cursor.executed) == 1


def test_handle_add_range_check_mode():
    module = DummyModule(params={
        'partition_name': 'p2023', 'value': '2024', 'number': None,
    })
    module.check_mode = True
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_add(module, cursor, '`db`.`t`', 'db', 't', 'RANGE', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'would be added' in result['msg']
    assert len(cursor.executed) == 0


def test_handle_add_hash():
    module = DummyModule(params={
        'partition_name': None, 'value': None, 'number': 2,
    })
    cursor = DummyCursor()

    queries = handle_add(module, cursor, '`t`', 'db', 't', 'HASH', SAMPLE_HASH_PARTITIONS)

    assert 'ADD PARTITION PARTITIONS 2' in queries[0]


def test_handle_add_execute_error():
    module = DummyModule(params={
        'partition_name': 'p2023', 'value': '2024', 'number': None,
    })
    cursor = FailingCursor('Duplicate partition name')

    with pytest.raises(RuntimeError, match='Failed to add partition'):
        handle_add(module, cursor, '`t`', 'db', 't', 'RANGE', SAMPLE_RANGE_PARTITIONS)


# ── handle_drop ───────────────────────────────────────────────────


def test_handle_drop_no_matching_partitions():
    module = DummyModule(params={'partitions': ['p9999']})
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_drop(module, cursor, '`db`.`t`', 'db', 't', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is False
    assert 'No matching' in result['msg']


def test_handle_drop_filters_to_existing():
    module = DummyModule(params={'partitions': ['p2020', 'p9999']})
    cursor = DummyCursor()

    queries = handle_drop(module, cursor, '`db`.`t`', 'db', 't', SAMPLE_RANGE_PARTITIONS)

    assert len(queries) == 1
    assert 'p2020' in queries[0]
    assert 'p9999' not in queries[0]


def test_handle_drop_check_mode():
    module = DummyModule(params={'partitions': ['p2020']})
    module.check_mode = True
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_drop(module, cursor, '`db`.`t`', 'db', 't', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'would be dropped' in result['msg']
    assert len(cursor.executed) == 0


def test_handle_drop_executes():
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = DummyCursor()

    queries = handle_drop(module, cursor, '`db`.`t`', 'db', 't', SAMPLE_RANGE_PARTITIONS)

    assert 'DROP PARTITION' in queries[0]
    assert len(cursor.executed) == 1


def test_handle_drop_execute_error():
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = FailingCursor('Cannot remove all partitions')

    with pytest.raises(RuntimeError, match='Failed to drop partition'):
        handle_drop(module, cursor, '`t`', 'db', 't', SAMPLE_RANGE_PARTITIONS)


# ── handle_reorganize ────────────────────────────────────────────


def test_handle_reorganize_executes():
    module = DummyModule(params={
        'partitions': ['p2020', 'p2021'],
        'into': [{'name': 'p_merged', 'value': '2022'}],
    })
    cursor = DummyCursor()

    queries = handle_reorganize(module, cursor, '`db`.`t`', 'RANGE', SAMPLE_RANGE_PARTITIONS)

    assert 'REORGANIZE PARTITION' in queries[0]
    assert '`p2020`, `p2021`' in queries[0]
    assert 'p_merged' in queries[0]
    assert len(cursor.executed) == 1


def test_handle_reorganize_check_mode():
    module = DummyModule(params={
        'partitions': ['p2020'],
        'into': [{'name': 'pa', 'value': '2020'}, {'name': 'pb', 'value': '2021'}],
    })
    module.check_mode = True
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_reorganize(module, cursor, '`t`', 'RANGE', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'would be reorganized' in result['msg']
    assert len(cursor.executed) == 0


def test_handle_reorganize_execute_error():
    module = DummyModule(params={
        'partitions': ['p2020'],
        'into': [{'name': 'px', 'value': '2021'}],
    })
    cursor = FailingCursor('VALUES LESS THAN value must be strictly increasing')

    with pytest.raises(RuntimeError, match='Failed to reorganize'):
        handle_reorganize(module, cursor, '`t`', 'RANGE', SAMPLE_RANGE_PARTITIONS)


# ── handle_truncate ───────────────────────────────────────────────


def test_handle_truncate_executes():
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = DummyCursor()

    queries = handle_truncate(module, cursor, '`db`.`t`', SAMPLE_RANGE_PARTITIONS)

    assert 'TRUNCATE PARTITION' in queries[0]
    assert len(cursor.executed) == 1


def test_handle_truncate_all():
    module = DummyModule(params={'partitions': ['ALL']})
    cursor = DummyCursor()

    queries = handle_truncate(module, cursor, '`t`', SAMPLE_RANGE_PARTITIONS)

    assert 'TRUNCATE PARTITION ALL' in queries[0]


def test_handle_truncate_check_mode():
    module = DummyModule(params={'partitions': ['p2020']})
    module.check_mode = True
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_truncate(module, cursor, '`t`', SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'would be truncated' in result['msg']
    assert len(cursor.executed) == 0


def test_handle_truncate_execute_error():
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = FailingCursor('Unknown partition')

    with pytest.raises(RuntimeError, match='Failed to truncate'):
        handle_truncate(module, cursor, '`t`', SAMPLE_RANGE_PARTITIONS)


# ── handle_maintenance ────────────────────────────────────────────


@pytest.mark.parametrize('action', ['check', 'repair', 'analyze', 'optimize'])
def test_handle_maintenance_executes(action):
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = DummyCursor()

    queries = handle_maintenance(module, cursor, '`db`.`t`', action, SAMPLE_RANGE_PARTITIONS)

    assert '%s PARTITION' % action.upper() in queries[0]
    assert len(cursor.executed) == 1


@pytest.mark.parametrize('action', ['check', 'repair', 'analyze', 'optimize'])
def test_handle_maintenance_check_mode(action):
    module = DummyModule(params={'partitions': ['p2020']})
    module.check_mode = True
    cursor = DummyCursor()

    with pytest.raises(SystemExit) as exc:
        handle_maintenance(module, cursor, '`t`', action, SAMPLE_RANGE_PARTITIONS)

    result = exc.value.args[0]
    assert result['changed'] is True
    assert action.upper() in result['msg']
    assert len(cursor.executed) == 0


def test_handle_maintenance_execute_error():
    module = DummyModule(params={'partitions': ['p2020']})
    cursor = FailingCursor('Table not found')

    with pytest.raises(RuntimeError, match='Failed to check partition'):
        handle_maintenance(module, cursor, '`t`', 'check', SAMPLE_RANGE_PARTITIONS)


def test_handle_maintenance_all():
    module = DummyModule(params={'partitions': ['ALL']})
    cursor = DummyCursor()

    queries = handle_maintenance(module, cursor, '`t`', 'analyze', SAMPLE_RANGE_PARTITIONS)

    assert 'ANALYZE PARTITION ALL' in queries[0]


# ── main ──────────────────────────────────────────────────────────


def _make_main_module(action='check', table='events', schema='mydb', **overrides):
    params = {
        'login_user': 'root',
        'login_password': 'secret',
        'config_file': '~/.my.cnf',
        'client_cert': None,
        'client_key': None,
        'ca_cert': None,
        'check_hostname': None,
        'connect_timeout': 30,
        'table': table,
        'schema': schema,
        'action': action,
        'partition_name': None,
        'value': None,
        'number': None,
        'partitions': ['p2020'],
        'into': None,
    }
    params.update(overrides)
    return DummyModule(params=params)


def _patch_main(monkeypatch, module, cursor, server_impl='mysql', partition_rows=None):
    if partition_rows is None:
        partition_rows = SAMPLE_RANGE_PARTITIONS

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.mysql_connect',
        lambda *args, **kwargs: (cursor, DummyConnection()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.get_server_implementation',
        lambda _cursor: server_impl,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.check_input',
        lambda *args: None,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.get_partition_info',
        lambda _cursor, _schema, _table: list(partition_rows),
    )


def test_main_rejects_mariadb(monkeypatch):
    module = _make_main_module()
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor, server_impl='mariadb')

    with pytest.raises(RuntimeError, match='MariaDB is not supported'):
        main()


def test_main_fails_when_no_schema_and_no_default(monkeypatch):
    module = _make_main_module(schema=None)
    cursor = DummyCursor(fetchone_results=[{'DATABASE()': None}])
    _patch_main(monkeypatch, module, cursor)

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.get_current_schema',
        lambda _cursor: None,
    )

    with pytest.raises(RuntimeError, match='No database selected'):
        main()


def test_main_fails_for_non_partitioned_table(monkeypatch):
    module = _make_main_module()
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor, partition_rows=[])

    with pytest.raises(RuntimeError, match='does not exist or is not partitioned'):
        main()


def test_main_check_mode_add(monkeypatch):
    module = _make_main_module(
        action='add', partition_name='p2023', value='2024',
        partitions=None,
    )
    module.check_mode = True
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'would be added' in result['msg']


def test_main_successful_drop(monkeypatch):
    module = _make_main_module(action='drop', partitions=['p2020'])
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True
    assert 'DROP' in result['msg']


def test_main_successful_truncate(monkeypatch):
    module = _make_main_module(action='truncate', partitions=['ALL'])
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True


def test_main_successful_reorganize(monkeypatch):
    module = _make_main_module(
        action='reorganize',
        partitions=['p2020', 'p2021'],
        into=[{'name': 'p_merged', 'value': '2022'}],
    )
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True


@pytest.mark.parametrize('action', ['check', 'repair', 'analyze', 'optimize'])
def test_main_successful_maintenance(monkeypatch, action):
    module = _make_main_module(action=action, partitions=['p2020'])
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True
    assert action.upper() in result['msg']


def test_main_resolves_schema_from_connection(monkeypatch):
    module = _make_main_module(action='check', schema=None, partitions=['p2020'])
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_partition.get_current_schema',
        lambda _cursor: 'resolved_db',
    )

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is True


def test_main_add_idempotent_existing_partition(monkeypatch):
    module = _make_main_module(
        action='add', partition_name='p2020', value='2021',
        partitions=None,
    )
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is False
    assert 'already exists' in result['msg']


def test_main_drop_idempotent_missing_partition(monkeypatch):
    module = _make_main_module(action='drop', partitions=['p9999'])
    cursor = DummyCursor()
    _patch_main(monkeypatch, module, cursor)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result['changed'] is False
    assert 'No matching' in result['msg']
