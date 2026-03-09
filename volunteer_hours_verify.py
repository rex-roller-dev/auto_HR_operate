from exceptions import (
    VolunteerVerifyError,
    NameMismatchError,
    HourMismatchError,
    FileError
)

def volunteer_hours_verify(
    certificate_data: dict,
    sz_volunteer_data: dict,
    ivolunteer_hours: float,
    szu_volunteer_hours: float,
    contain_ivolunteer: bool,
    contain_szu_volunteer: bool
) -> None:
    """
    校验通过：什么都不返回
    校验失败：raise 对应异常
    """

    name = certificate_data['name']
    cert_sz_hours = certificate_data['volunteer_shenzhen_hours']
    cert_ivol_hours = certificate_data['i_volunteer_hours']
    cert_szu_hours = certificate_data['szu_volunteer_hours']

    # 1️⃣ 姓名
    if sz_volunteer_data['姓名'] and sz_volunteer_data['义工号'] and sz_volunteer_data['服务时长'] is None:
        raise  FileError(
            f"志愿深圳数据错误，请从服务明细-导出明细中获取文件，详情请查看公众号"
            )
    
    if sz_volunteer_data['姓名'] != name:
        raise NameMismatchError(
            f"姓名不匹配: 证书({name}) vs 志愿深圳({sz_volunteer_data['姓名']})"
        )

    # 2️⃣ 志愿深圳
    if cert_sz_hours is not None:
        if abs(cert_sz_hours - sz_volunteer_data['服务时长']) > 1:
            raise HourMismatchError(
                f"志愿深圳服务时长不匹配: 证书({cert_sz_hours}) "
                f"vs 志愿深圳({sz_volunteer_data['服务时长']})"
            )

    # 3️⃣ iVolunteer
    if contain_ivolunteer and cert_ivol_hours is not None:
        if abs(cert_ivol_hours - ivolunteer_hours) > 1:
            raise HourMismatchError(
                f"iVolunteer服务时长不匹配: 证书({cert_ivol_hours}) "
                f"vs iVolunteer({ivolunteer_hours})"
            )

    # 4️⃣ 深大志愿
    if contain_szu_volunteer and cert_szu_hours is not None:
        if abs(cert_szu_hours - szu_volunteer_hours) > 1:
            raise HourMismatchError(
                f"深圳大学志愿服务时长不匹配: 证书({cert_szu_hours}) "
                f"vs 深圳大学({szu_volunteer_hours})"
            )

    # 能走到这里 = 全部 OK
    return
