"""Pytest configuration for PsychAgent tests/agents/.

The standalone test script (test_agents_standalone.py) uses sys.exit() and
is designed to be run directly rather than collected by pytest.  This
conftest excludes it from pytest collection.
"""

collect_ignore = ["test_agents_standalone.py"]
