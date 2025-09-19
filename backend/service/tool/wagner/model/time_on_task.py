from typing import List, Optional

from pydantic import BaseModel
from pydantic.alias_generators import to_snake, to_camel

from util.datetime_util import format_iso_2_datetime


class Attendance(BaseModel):
    start_time:str
    end_time:str

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"考勤上班时间:{"上班缺卡" if self.start_time is None else format_iso_2_datetime(self.start_time)}，考勤下班时间:{"下班缺卡" if self.end_time is None else format_iso_2_datetime(self.end_time)};"

class Rest(BaseModel):
    start_time: str
    end_time: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class Scheduling(BaseModel):
    start_time: str
    end_time: str
    rest_list:List[Rest]

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        scheduling_info = f"班次上班时间:{format_iso_2_datetime(self.start_time)},班次下班时间:{format_iso_2_datetime(self.end_time)}。"
        if self.rest_list is not None:
            scheduling_info += "休息时间段为："
            for i, one_rest in enumerate(self.rest_list):
                rest_info = f"第{i + 1}段休息开始时间:{format_iso_2_datetime(one_rest.start_time)}、结束时间:{format_iso_2_datetime(one_rest.end_time)};"
                scheduling_info += rest_info
        return scheduling_info



class ProcessDuration(BaseModel):
    start_time: str
    end_time: str
    action_type: str
    process_name:str
    work_load_desc:Optional[str] = None
    duration: int

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def action_type_2_desc(self):
        if self.action_type == "DirectWork":
            return "直接作业"
        elif self.action_type == "IndirectWork":
            return "间接作业"
        elif self.action_type == "Idle":
            return "闲置"
        elif self.action_type == "Rest":
            return "闲置"
        else:
            return None

    def to_desc(self):
        if self.action_type_2_desc() == "闲置":
            return f"从{format_iso_2_datetime(self.start_time)}开始至{format_iso_2_datetime(self.end_time)}结束，员工处于闲置"
        elif self.action_type_2_desc() == "休息":
            return f"从{format_iso_2_datetime(self.start_time)}开始至{format_iso_2_datetime(self.end_time)}结束，员工在进行休息"
        else:
            return f"完成一次{self.process_name}环节的{self.action_type_2_desc()},从{format_iso_2_datetime(self.start_time)}开始至{format_iso_2_datetime(self.end_time)}结束，完成工作量:{"无" if self.work_load_desc == "" else self.work_load_desc}，工作时长{self.duration}分钟"


class TimeOnTask(BaseModel):
    operate_day: str
    employee_number: str
    employee_name: str
    attendance:Optional[Attendance] = None
    scheduling:Optional[Scheduling]
    process_duration_list:list[ProcessDuration]

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        if self.process_duration_list is None:
            process_duration_info = "无详细工作内容"
        else:
            process_duration_info = ""
            for process_duration in self.process_duration_list:
                process_duration_info += process_duration.to_desc() + "\n"

        return f"""
        排班信息：{"无排班" if self.scheduling is None else self.scheduling.to_desc()},
        考勤信息：{"无考勤" if self.attendance is None else self.attendance.to_desc()},
        详细工作内容：
        {"无" if len(self.process_duration_list) == 0 else process_duration_info}
        """







