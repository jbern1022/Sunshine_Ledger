from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by remote IP. Generous default for normal browsing; individual
# write-capable routes (e.g. POST /flags) apply a stricter limit on top.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
