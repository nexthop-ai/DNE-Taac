# pyre-unsafe
"""EBB BGP++ conveyor package.

Kept side-effect-free: submodules (``conveyor_constants``,
``conveyor_node_test_configs``, etc.) are imported directly. Eager
re-exports here closed a circular import chain through
``taac.playbooks.playbook_definitions`` ↔
``taac.testconfigs.routing.ebb`` on strict Python — see
``conveyor_node_test_configs`` for the aggregated TestConfig list
that previously lived here.
"""
