"""Two kinds of failure, because they need opposite handling.

TransientJobError: might work if we try again (rate limit, timeout, network).
    -> the worker retries with exponential backoff, up to JOB_MAX_TRIES.
PermanentJobError: will fail the same way every time (unreadable PDF, bad API key).
    -> fail immediately; retrying only wastes time and money.
"""


class TransientJobError(Exception):
    pass


class PermanentJobError(Exception):
    pass


class JobCancelled(Exception):
    pass
