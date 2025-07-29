from typing import Any

from langchain_core.tools import tool

from model.employee import Employee
from model.employee_efficiency_summary import EmployeeBasicSummary
from model.time_on_task import TimeOnTask
from util.http_util import http_get


@tool
def get_employee(employee_name, workplace_code, work_group_code):
    """根据员工姓名、工作点编码、工作组编码查找员工的信息，包含姓名、工号、所属工作点编码、所属工作组编码"""
    res = http_get(f"/employee/findByName?workplaceCode={workplace_code}&workGroupCode={work_group_code}&employeeName={employee_name}")
    data: dict[str, Any] = res["data"]

    employee = Employee(data["name"], data["number"], data["workplaceCode"], data["workGroupCode"])

    return employee.to_desc()

@tool
def get_group_employee(workplace_code, work_group_code):
    """根据工作点编码，工作组编码查找组内全体员工的信息，包含姓名、工号、所属工作点编码、所属工作组编码"""
    res = http_get(f"/employee/findByWorkGroupCode?workplaceCode={workplace_code}&workGroupCode={work_group_code}")
    dataArray :[] = res["data"]

    list = []
    for data in iter(dataArray):
        employee = Employee(data["name"], data["number"], data["workplaceCode"], data["workGroupCode"])
        list.append(employee.to_desc() + " ")

    return list

@tool
def get_employee_time_on_task(operate_day, employee_number):
    """根据工作日期、工号查找员工一天的工作情况"""
    res = http_get(f"/efficiency/timeOnTask?operateDay={operate_day}&employeeNumber={employee_number}")
    data = res["data"]

    time_on_task = TimeOnTask.model_validate(data)

    desc = time_on_task.to_desc()
    return desc

@tool
def get_employee_efficiency(workplace_code, employee_number_list:list[str], operate_day):
    """根据工作点编码、人员工号列表、工作日日期(YYYY-MM-DD格式)获取当天全员的工作效率"""
    employee_numbers_str = ",".join(employee_number_list)
    res = http_get(f"/efficiency/employee?workplaceCode={workplace_code}&startDate={operate_day}&endDate={operate_day}&employeeNumber={employee_numbers_str}&aggregateDimension=process&isCrossPosition=all&currentPage=1&pageSize=200")
    data = res["data"]
    data_list = data["tableDataList"]

    desc = ""
    for d in data_list:
        employee_basic_summary = EmployeeBasicSummary.model_validate(d)
        desc += employee_basic_summary.to_desc()
    return desc


