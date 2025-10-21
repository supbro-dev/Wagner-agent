from datetime import datetime

import pytz


def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")

def parse_datetime_iso(str):
    return datetime.fromisoformat(str)

def format_datatime(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_iso_2_datetime(iso_str):
    return format_datatime(parse_datetime_iso(iso_str))

def format_iso_2_datetime_at_zone(iso_str):
    # 原始时间字符串
    #time_str = '2025-10-19T20:44:20.000000-07:00'

    # 解析为带时区的datetime对象（Python 3.7+）
    dt_utc_offset = datetime.fromisoformat(iso_str)

    # 转换为UTC时间（可选中间步骤）
    dt_utc = dt_utc_offset.astimezone(pytz.utc)

    # 定义目标时区（例如：北京时间）
    target_timezone = pytz.timezone('Asia/Shanghai')

    # 转换为目标时区
    dt_target = dt_utc.astimezone(target_timezone)

    # 格式化输出（可选）
    formatted = dt_target.strftime('%Y-%m-%d %H:%M:%S')
    return formatted