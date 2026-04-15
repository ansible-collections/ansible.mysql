# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Andrew Klychkov (@Andersson007) <andrew.a.klychkov@gmail.com>

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.community.mysql.plugins.module_utils.implementations.mysql.replication import uses_replica_terminology
from ..utils import dummy_cursor_class, MockCursor


@pytest.mark.parametrize(
    'f_output,c_output,c_ret_type',
    [
        (False, '5.5.1-mysql', 'list'),
        (False, '5.7.0-mysql', 'dict'),
        (False, '8.0.0-mysql', 'list'),
        (False, '8.0.11-mysql', 'dict'),
        (False, '8.0.21-mysql', 'list'),
        (True, '8.0.22-mysql', 'list'),
        (True, '8.1.2-mysql', 'dict'),
        (True, '9.0.0-mysql', 'list'),
    ]
)
def test_uses_replica_terminology(f_output, c_output, c_ret_type):
    cursor = dummy_cursor_class(c_output, c_ret_type)
    assert uses_replica_terminology(cursor) == f_output


@pytest.mark.parametrize(
    'user,password,expected_query',
    [
        (None, None, "START GROUP_REPLICATION "),
        ("repl_user", None, "START GROUP_REPLICATION USER='repl_user'"),
        (None, "repl_pass", "START GROUP_REPLICATION PASSWORD='repl_pass'"),
        ("repl_user", "repl_pass", "START GROUP_REPLICATION USER='repl_user',PASSWORD='repl_pass'"),
    ]
)
def test_start_group_replication(user, password, expected_query):
    """Test startgroupreplication function with different parameters."""
    from ansible_collections.community.mysql.plugins.modules.mysql_replication import startgroupreplication

    cursor = MockCursor()
    module = type('obj', (object,), {
        'fail_json': lambda msg: None,
    })

    chm = []
    if user:
        chm.append("USER='%s'" % user)
    if password:
        chm.append("PASSWORD='%s'" % password)

    result = startgroupreplication(module, cursor, chm, False)

    assert result is True
    assert cursor.executed_queries[0] == expected_query


def test_stop_group_replication():
    """Test stopgroupreplication function."""
    from ansible_collections.community.mysql.plugins.modules.mysql_replication import stopgroupreplication

    cursor = MockCursor()
    module = type('obj', (object,), {
        'fail_json': lambda msg: None,
    })

    result = stopgroupreplication(module, cursor, False)

    assert result is True
    assert cursor.executed_queries[0] == "STOP GROUP_REPLICATION"


def test_start_group_replication_fail():
    """Test startgroupreplication function with failure."""
    from ansible_collections.community.mysql.plugins.modules.mysql_replication import startgroupreplication
    from ..utils import MockWarning

    # Create a mock mysql_driver with a Warning attribute
    class MockDriver:
        Warning = MockWarning

    # Save the original mysql_driver
    from ansible_collections.community.mysql.plugins.modules import mysql_replication
    original_driver = mysql_replication.mysql_driver

    try:
        # Replace with our mock driver
        mysql_replication.mysql_driver = MockDriver

        cursor = MockCursor(status="ERROR")
        module = type('obj', (object,), {
            'fail_json': lambda msg: None,
        })

        result = startgroupreplication(module, cursor, [], True)

        assert result is False
    finally:
        # Restore the original driver
        mysql_replication.mysql_driver = original_driver


def test_stop_group_replication_fail():
    """Test stopgroupreplication function with failure."""
    from ansible_collections.community.mysql.plugins.modules.mysql_replication import stopgroupreplication
    from ..utils import MockWarning

    # Create a mock mysql_driver with a Warning attribute
    class MockDriver:
        Warning = MockWarning

    # Save the original mysql_driver
    from ansible_collections.community.mysql.plugins.modules import mysql_replication
    original_driver = mysql_replication.mysql_driver

    try:
        # Replace with our mock driver
        mysql_replication.mysql_driver = MockDriver

        cursor = MockCursor(status="ERROR")
        module = type('obj', (object,), {
            'fail_json': lambda msg: None,
        })

        result = stopgroupreplication(module, cursor, True)

        assert result is False
    finally:
        # Restore the original driver
        mysql_replication.mysql_driver = original_driver
