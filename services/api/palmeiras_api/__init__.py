"""Shared backend implementation for all Palmeiras Agenda clients."""

from .routes import API_ROUTE_ALIASES, dispatch_request

__all__ = ["API_ROUTE_ALIASES", "dispatch_request"]
