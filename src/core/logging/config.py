LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "asgi_correlation_id.CorrelationIdFilter",
            "uuid_length": 8,
            "default_value": "-",
        },
    },
    "formatters": {
        "default": {
            "class": "logging.Formatter",
            "datefmt": "%H:%M:%S",
            "format": "%(levelname)s [%(correlation_id)s] %(name)s %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(correlation_id)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
            },
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["default"],
    },
}
