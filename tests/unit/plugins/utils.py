from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class dummy_cursor_class():
    """Dummy class for returning an answer for SELECT VERSION()."""
    def __init__(self, output, ret_val_type='dict'):
        self.output = output
        self.ret_val_type = ret_val_type

    def execute(self, query):
        pass

    def fetchone(self):
        if self.ret_val_type == 'dict':
            return {'version': self.output}

        elif self.ret_val_type == 'list':
            return [self.output]


# Define MockWarning at module level to ensure it's a proper exception class
class MockWarning(Exception):
    pass


class MockCursor:
    # Set the Warning class at the class level
    Warning = MockWarning

    def __init__(self, status="ONLINE"):
        self.status = status
        self.executed_queries = []

    def execute(self, query):
        self.executed_queries.append(query)
        if self.status == "ERROR":
            raise MockWarning("Mocked execution error")

    def fetchone(self):
        if len(self.executed_queries) > 0 and "group_replication_status" in self.executed_queries[-1]:
            return ["group_replication_status", self.status]
        return None
