class ProviderError(RuntimeError):
    """User-safe provider failure, with no upstream body or credentials."""
