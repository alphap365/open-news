"""Date parsing that understands the timezone abbreviations news feeds use."""
import warnings
from datetime import datetime, timezone
from typing import Optional, Union

from dateutil import parser as _dp

# Ambiguous codes are resolved to the reading most common in news feeds
# (CST -> US Central, BST -> British Summer Time).
TZINFOS = {
    "UTC": 0, "GMT": 0, "Z": 0,
    "IST": 19800, "PKT": 18000, "NPT": 20700, "BDT": 21600, "SLST": 19800,
    "SGT": 28800, "HKT": 28800, "PHT": 28800, "WIB": 25200,
    "JST": 32400, "KST": 32400,
    "AEST": 36000, "AEDT": 39600, "ACST": 34200, "AWST": 28800,
    "NZST": 43200, "NZDT": 46800,
    "CET": 3600, "CEST": 7200, "EET": 7200, "EEST": 10800, "BST": 3600, "MSK": 10800,
    "EST": -18000, "EDT": -14400, "CST": -21600, "CDT": -18000,
    "MST": -25200, "MDT": -21600, "PST": -28800, "PDT": -25200,
}


def parse_datetime(raw: Union[str, datetime, None], to_utc: bool = True) -> Optional[datetime]:
    """to_utc=True -> always aware UTC (naive input assumed UTC);
    to_utc=False -> keep the parsed offset, naive stays naive."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")      # UnknownTimezoneWarning
                dt = _dp.parse(str(raw), tzinfos=TZINFOS)
        except (ValueError, OverflowError, TypeError):
            return None
    if not to_utc:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)