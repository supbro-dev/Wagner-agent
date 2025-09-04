from datetime import datetime


def parse_datetime_iso(str):
    return datetime.fromisoformat(str)

def format_datatime(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_iso_2_datetime(iso_str):
    return format_datatime(parse_datetime_iso(iso_str))