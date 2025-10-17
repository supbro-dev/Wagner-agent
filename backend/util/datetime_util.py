from datetime import datetime

def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")

def parse_datetime_iso(str):
    return datetime.fromisoformat(str)

def format_datatime(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_iso_2_datetime(iso_str):
    return format_datatime(parse_datetime_iso(iso_str))