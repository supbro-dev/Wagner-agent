from typing import Any

from langchain_core.tools import tool

from service.tool.wagner.model.employee import Employee
from service.tool.wagner.model.employee_efficiency_summary import EmployeeBasicSummary
from service.tool.wagner.model.time_on_task import TimeOnTask
from util.http_util import http_get


@tool
def get_employee(employee_name, workplace_code, work_group_code):
    """
    根据员工姓名、工作点编码、工作组编码查找员工的信息，结果包含姓名、工号、所属工作点编码、所属工作组编码

    工具名称（可展示给用户）：根据姓名查工号

    输入参数：
    employee_name：员工姓名
    workplace_code：工作点编码
    work_group_code：工作组编码
    """
    res = http_get(f"/employee/findByName?workplaceCode={workplace_code}&workGroupCode={work_group_code}&employeeName={employee_name}")
    data: dict[str, Any] = res["data"]

    if data is not None:
        employee = Employee(data["name"], data["number"], data["workplaceCode"], data["workGroupCode"])
        return employee.to_desc()
    else:
        return "查询不到该员工信息"

@tool
def get_group_employee(workplace_code, work_group_code):
    """
    根据工作点编码，工作组编码查找组内全体员工的信息，包含姓名、工号、所属工作点编码、所属工作组编码

    工具名称（可展示给用户）：获取全组员工信息

    输入参数：
    workplace_code：工作点编码
    work_group_code：工作组编码
    """
    res = http_get(f"/employee/findByWorkGroupCode?workplaceCode={workplace_code}&workGroupCode={work_group_code}")
    dataArray :[] = res["data"]

    if len(dataArray) > 0:
        list = []
        for data in iter(dataArray):
            employee = Employee(data["name"], data["number"], data["workplaceCode"], data["workGroupCode"])
            list.append(employee.to_desc() + " ")

        return list
    else:
        return "工作组中查询不到任何员工"

@tool
def get_employee_time_on_task(operate_day, employee_number):
    """根据工作日期、工号查找员工一天的工作详情，只能查一个人，如果用户需要查多个人，则不要调用这个工具"""
    res = http_get(f"/efficiency/timeOnTask?operateDay={operate_day}&employeeNumber={employee_number}")
    data = res["data"]

    if data is not None:
        time_on_task = TimeOnTask.model_validate(data)
        desc = time_on_task.to_desc()
        return desc
    else:
        return "当天无任何工作情况记录"

@tool
def get_employee_efficiency(workplace_code, employee_number_list:list[str], operate_day):
    """
    根据工作点编码、人员工号列表、工作日日期(YYYY-MM-DD格式)获取当天全员的工作效率

    工具名称（可展示给用户）：查询当天全员的工作效率

    输入参数：
    workplace_code：工作点编码
    employee_number_list：员工工号列表(英文逗号分隔)
    operate_day：工作日日期
    """
    employee_numbers_str = ",".join(employee_number_list)
    res = http_get(f"/efficiency/employee?workplaceCode={workplace_code}&startDate={operate_day}&endDate={operate_day}&employeeNumber={employee_numbers_str}&aggregateDimension=process&isCrossPosition=all&currentPage=1&pageSize=200")
    data = res["data"]
    data_list = data["tableDataList"]

    if len(data_list) > 0:
        desc = ""
        for d in data_list:
            employee_basic_summary = EmployeeBasicSummary.model_validate(d)
            desc += employee_basic_summary.to_desc()
        return desc
    else:
        return "查询不到工作效率记录"


