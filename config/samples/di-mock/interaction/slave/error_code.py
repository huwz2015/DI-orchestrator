from enum import unique, IntEnum


@unique
class SlaveErrorCode(IntEnum):
    SUCCESS = 0

    SYSTEM_SHUTTING_DOWN = 101

    CHANNEL_NOT_FOUND = 201
    CHANNEL_INVALID = 202

    MASTER_TOKEN_NOT_FOUND = 301
    MASTER_TOKEN_INVALID = 302

    SELF_TOKEN_NOT_FOUND = 401
    SELF_TOKEN_INVALID = 402

    SLAVE_ALREADY_CONNECTED = 501
    SLAVE_NOT_CONNECTED = 502
    SLAVE_CONNECTION_REFUSED = 503
    SLAVE_DISCONNECTION_REFUSED = 504

    TASK_ALREADY_EXIST = 601
    TASK_REFUSED = 602
