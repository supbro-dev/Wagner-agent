from typing import Dict

from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class EmployeeBasicSummary(BaseModel):
    employee_number: str
    employee_name: str
    operate_day: str
    process_name: str
    position_name: str
    dept_name: str
    direct_work_time: float  # 直接作业时长（小时）
    indirect_work_time: float  # 间接作业时长（小时）
    idle_time: float  # 闲置时长（小时）
    rest_time: float # 休息时长（小时）
    attendance_time: float  # 出勤时长（小时）
    work_load_desc: Dict[str, float] |None # 工作量编码 -> 工作量
    idle_time_rate: float

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        if self.work_load_desc is not None:
            desc = f"{self.operate_day}，{self.employee_name}在{self.process_name}环节上完成工作量{self.work_load_desc}，"
        else:
            desc = f"{self.operate_day}，{self.employee_name}在{self.process_name}环节上"

        if self.direct_work_time > 0.0:
            desc += f"工作{self.direct_work_time}小时"
        elif self.indirect_work_time > 0.0:
            desc += f"工作{self.indirect_work_time}小时"
        elif self.rest_time > 0.0:
            desc += f"休息{self.rest_time}小时"

        if self.idle_time > 0.0:
            desc += f" 闲置{self.idle_time}小时"
        desc += "\n"

        return desc



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