CURRENCIES = ["global", "RB", "NPR", "XX", "BT"]
FIELDS = ["aggregatorPage", "gamePage", "downloadUrl", "downloadBase64Url"]
ENVIRONMENTS = ["247as", "1688"]

FIELD_LABELS = {
    "aggregatorPage": "aggregatorPage",
    "gamePage": "gamePage",
    "downloadUrl": "download url",
    "downloadBase64Url": "download base64 url",
}

ENV_FILE_PATHS = {
    "247as": "env/gcp247as.json",
    "1688":  "env/gcp1688.json",
}

DL_FILE_PATHS = {
    "247as": "secured/dl_gcp247as.json",
    "1688":  "secured/dl_gcp1688.json",
}

# Which JSON file each field is stored in
FIELD_SOURCE = {
    "aggregatorPage":    "env",
    "gamePage":          "env",
    "downloadUrl":       "dl",
    "downloadBase64Url": "dl",
}

# JSON path to reach the value for each field/currency combination.
# None means the currency has no such field in the JSON.
FIELD_PATHS: dict[str, dict[str, list[str] | None]] = {
    "aggregatorPage": {
        "global": ["envObj", "aggregatorPage"],
        "RB":     ["aggregatorPageByCurrency", "RB"],
        "NPR":    ["aggregatorPageByCurrency", "NPR"],
        "XX":     ["aggregatorPageByCurrency", "XX"],
        "BT":     ["aggregatorPageByCurrency", "BT"],
    },
    "gamePage": {
        "global": ["envObj", "gamePage"],
        "RB":     ["gamePageByCurrency", "RB"],
        "NPR":    ["gamePageByCurrency", "NPR"],
        "XX":     ["gamePageByCurrency", "XX"],
        "BT":     ["gamePageByCurrency", "BT"],
    },
    "downloadUrl": {
        "global": ["dl"],
        "RB":     ["dlByCurrency", "RB"],
        "NPR":    None,
        "XX":     ["dlByCurrency", "XX"],
        "BT":     ["dlByCurrency", "BT"],
    },
    "downloadBase64Url": {
        "global": ["dlBase64"],
        "RB":     ["dlBase64ByCurrency", "RB"],
        "NPR":    None,
        "XX":     ["dlBase64ByCurrency", "XX"],
        "BT":     ["dlBase64ByCurrency", "BT"],
    },
}

# Availability matrix — which env/currency/field combinations actually exist
AVAILABILITY: dict[str, dict[str, dict[str, bool]]] = {
    "247as": {
        "global": {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
        "RB":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
        "NPR":    {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": False, "downloadBase64Url": False},
        "XX":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
        "BT":     {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False},
    },
    "1688": {
        "global": {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
        "RB":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
        "NPR":    {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False},
        "XX":     {"aggregatorPage": False, "gamePage": False, "downloadUrl": True,  "downloadBase64Url": True},
        "BT":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True},
    },
}
