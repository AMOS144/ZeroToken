"""ZeroToken - AI Agent browser automation MCP engine"""
try:
    from importlib.metadata import version

    __version__ = version("zerotoken")
except Exception:
    __version__ = "2.0.0-dev"
