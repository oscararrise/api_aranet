class AranetETLError(Exception):
    """Base exception for the synchronization service."""


class ConfigurationError(AranetETLError):
    """Raised when required environment configuration is invalid."""


class AranetAPIError(AranetETLError):
    """Raised when Aranet Cloud returns an invalid or unsuccessful response."""


class DatabaseBootstrapError(AranetETLError):
    """Raised when the target PostgreSQL database cannot be prepared."""


class ConcurrentSyncError(AranetETLError):
    """Raised when another process already owns the global synchronization lock."""
