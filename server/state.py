"""Shared server-side singletons accessed by tool handlers.

Imported by both server/main.py (where they are started) and server/tools/*
(where they are read). Using module-level singletons avoids threading globals
while keeping import order simple.
"""

from server.auth.token_store import token_store as _token_store
from server.vw.poller import data_poller as _data_poller

token_store = _token_store
data_poller = _data_poller
