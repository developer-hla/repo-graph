"""Cache scanner regexes and method sets."""

from __future__ import annotations

import re

CACHE_NAME_RE = r"[A-Za-z_][\w.]*"
CACHE_METHOD_RE = re.compile(
    rf"(?:(?P<receiver>{CACHE_NAME_RE})\s*\.\s*)?"
    r"(?P<method>getString|setString|get_many|set_many|mget|mset|get|set|setex|"
    r"exists|delete|del|hget|hset)\s*\(",
    re.IGNORECASE,
)
CACHE_FIRST_ARG_RE = re.compile(
    r"\(\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)

READ_METHODS = frozenset({"exists", "get", "get_many", "getstring", "hget", "mget"})
WRITE_METHODS = frozenset({"del", "delete", "hset", "mset", "set", "set_many", "setex", "setstring"})
RECEIVER_HINTS = ("cache", "redis", "memcache", "memorycache", "distributedcache")
