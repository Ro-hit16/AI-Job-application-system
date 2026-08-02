class AppException(Exception):
    pass


class DatabaseException(AppException):
    pass


class AuthenticationException(AppException):
    pass


class VectorDBException(AppException):
    pass


class LLMException(AppException):
    pass


class ResumeParseException(AppException):
    pass


class JobScrapingException(AppException):
    pass


class ApplicationException(AppException):
    pass
