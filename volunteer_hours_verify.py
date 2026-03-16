from exceptions import (
    VolunteerVerifyError,
    NameMismatchError,
    szvHourMismatchError,
    ivolHourMismatchError,
    szuHourMismatchError,
    FileError)
from text_normalizer import name_nomalizer


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
    # print(certificate_data,flush=True)
    # print(sz_volunteer_data,flush=True)
    # print(f"i志愿时长: {ivolunteer_hours}",flush=True)
    # print(f"深大义工时长: {szu_volunteer_hours}",flush=True)
    # print(f"是否包含i志愿: {contain_ivolunteer}",flush=True)
    # print(f"是否包含深大义工: {contain_szu_volunteer}",flush=True)

    name = certificate_data['name']
    cert_sz_hours = certificate_data['volunteer_shenzhen_hours']
    cert_ivol_hours = certificate_data['i_volunteer_hours']
    cert_szu_hours = certificate_data['szu_volunteer_hours']


    # 1️⃣ 姓名
    if sz_volunteer_data is not None:
        if sz_volunteer_data['姓名'] is None or sz_volunteer_data['义工号'] is None or sz_volunteer_data['服务时长'] is None:
            raise  FileError(
                f"志愿深圳数据错误，请从服务明细-导出明细中获取文件，详情请查看公众号"
                )
        
        name = name_nomalizer(name)
        sz_volunteer_data['姓名'] = name_nomalizer(sz_volunteer_data['姓名'])
    
        if sz_volunteer_data['姓名'] != name:
            raise NameMismatchError(
                f"姓名不匹配: 证书({name}) vs 志愿深圳({sz_volunteer_data['姓名']})"
            )

    # 2️⃣ 志愿深圳
    if cert_sz_hours is not None and sz_volunteer_data is not None:
        if abs(cert_sz_hours - sz_volunteer_data['服务时长']) > 1:
            raise szvHourMismatchError(
                f"志愿深圳服务时长不匹配: 深圳大学志愿时长认证表志愿深圳时长({cert_sz_hours}) "
                f"vs 志愿深圳证明材料时长({sz_volunteer_data['服务时长']})"
            )

    # 3️⃣ iVolunteer
    if contain_ivolunteer or cert_ivol_hours is not None:
        if abs(cert_ivol_hours - ivolunteer_hours) > 1:
            raise ivolHourMismatchError(
                f"i志愿服务时长不匹配: 深圳大学志愿时长认证表i志愿时长({cert_ivol_hours}) "
                f"vs i志愿证明材料时长({ivolunteer_hours})"
            )

    # 4️⃣ 深大志愿
    if contain_szu_volunteer and cert_szu_hours is not None:
        if abs(cert_szu_hours - szu_volunteer_hours) > 1:
            raise szuHourMismatchError(
                f"深大义工志愿服务时长不匹配: 深圳大学志愿时长认证表深大义工时长({cert_szu_hours}) "
                f"vs 深大义工真实时长({szu_volunteer_hours})"
            )

    # 能走到这里 = 全部 OK
    return
