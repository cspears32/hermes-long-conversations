try:
    from .long_conversations import register
except (ImportError, ValueError):
    from long_conversations import register

__all__ = ["register"]
