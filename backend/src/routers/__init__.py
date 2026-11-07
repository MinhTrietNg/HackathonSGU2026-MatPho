"""
Routers Package
"""

from . import health
from . import auth
from . import users
from . import groups
from . import invitations
from . import cameras
from . import settings
from . import websocket_router
from . import internal_ai
from . import alerts

__all__ = [
    "health",
    "auth",
    "users",
    "groups",
    "invitations",
    "cameras",
    "settings",
    "websocket_router",
    "internal_ai",
    "alerts",
]
