class VolunteerVerifyError(Exception):
    """志愿时长校验异常（业务异常基类）"""
    pass


class NameMismatchError(VolunteerVerifyError):
    pass


# class HourMismatchError(VolunteerVerifyError):
#     pass

class FileError(Exception):
    """文件验证失败时抛出的错误"""
    pass

class szvHourMismatchError(VolunteerVerifyError):
    pass

class ivolHourMismatchError(VolunteerVerifyError):
    pass

class szuHourMismatchError(VolunteerVerifyError):
    pass

class timeValueError(VolunteerVerifyError):
    pass

class VolunteerFileError(Exception):
    """志愿时文件处理的基类异常"""
    pass