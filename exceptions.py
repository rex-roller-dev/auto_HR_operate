class VolunteerVerifyError(Exception):
    """志愿时长校验异常（业务异常基类）"""
    pass


class NameMismatchError(VolunteerVerifyError):
    pass


class HourMismatchError(VolunteerVerifyError):
    pass

class FileError(Exception):
    """文件验证失败时抛出的错误"""
    pass