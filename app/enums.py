from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class IMProvider(str, Enum):
    WECOM = "wecom"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    DISCORD = "discord"


class SortField(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    STORAGE_ERROR = "STORAGE_ERROR"
    LLM_ERROR = "LLM_ERROR"
    EMBEDDING_ERROR = "EMBEDDING_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
