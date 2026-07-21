"""YiCloud command-line entry point."""

from .auth import AuthenticationError, ClientConfig, build_client, load_credentials

__all__ = [
    "AuthenticationError",
    "ClientConfig",
    "build_client",
    "load_credentials",
]


def main() -> int:
    """Run the CLI entry point."""
    build_client()
    return 0
