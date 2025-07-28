from typing import Dict


class EmployeeBasicSummary:
    employee_number: str
    employee_name: str
    operate_day: str
    process_name: str
    position_name: str
    dept_name: str
    direct_work_time: float  # 直接作业时长（秒）
    indirect_work_time: float  # 间接作业时长（秒）
    idle_time: float  # 闲置时长（秒）
    rest_time: float # 休息时长（秒）
    attendance_time: float  # 出勤时长（秒）
    work_load: Dict[str, float] # 工作量编码 -> 工作量
    idle_time_rate: float

class EmployeeSummary:
    employee_number: str
    employee_name: str
    operate_day: str
    process_code: str
    process_name: str
    position_code: str  # 作业岗位编码
    position_name: str
    dept_name: str
    workplace_code: str
    workplace_name: str
    employee_position_code: str
    work_group_code: str  # 员工工作组编码
    region_code: str  # 工作点所属区域
    industry_code: str  # 工作点所属行业
    sub_industry_code: str  # 工作点所属子行业
    direct_work_time: float  # 直接作业时长（秒）
    indirect_work_time: float  # 间接作业时长
    idle_time: float  # 闲置时长
    rest_time: float
    attendance_time: float  # 出勤时长
    process_property: str  # 环节额外属性
    work_load: Dict[str, float]
    direct_work_time_rate: float
    indirect_work_time_rate: float
    idle_time_rate: float