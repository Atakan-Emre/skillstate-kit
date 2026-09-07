"""Small duration formatting utility."""


def format_seconds(seconds: int) -> str:
    if type(seconds) is not int or seconds < 0:
        raise ValueError("seconds must be a nonnegative integer")
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"
