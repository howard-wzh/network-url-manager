CURRENCIES = ["global", "RB", "NPR", "XX", "BT"]
FIELDS = ["aggregatorPage", "gamePage", "downloadUrl", "downloadBase64Url", "testUrl"]
ENVIRONMENTS = ["247as", "1688", "test"]

FIELD_LABELS = {
    "aggregatorPage": "aggregatorPage",
    "gamePage": "gamePage",
    "downloadUrl": "download url",
    "downloadBase64Url": "download base64 url",
    "testUrl": "testUrl (temp)",
}

ENV_FILE_PATHS = {
    "247as": "env/gcp247as.json",
    "1688":  "env/gcp1688.json",
    "test":  "env/test.json",       # temporary test entry
}

DL_FILE_PATHS = {
    "247as": "secured/dl_gcp247as.json",
    "1688":  "secured/dl_gcp1688.json",
    "test":  "env/test.json",       # not used (no dl fields for test)
}

# Which JSON file each field is stored in
FIELD_SOURCE = {
    "aggregatorPage":    "env",
    "gamePage":          "env",
    "downloadUrl":       "dl",
    "downloadBase64Url": "dl",
    "testUrl":           "env",     # temporary
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
    "testUrl": {                    # temporary — reads envObj.report from env/test.json
        "global": ["envObj", "report"],
        "RB":     None,
        "NPR":    None,
        "XX":     None,
        "BT":     None,
    },
}

# Availability matrix — which env/currency/field combinations actually exist
_OFF = {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False, "testUrl": False}

AVAILABILITY: dict[str, dict[str, dict[str, bool]]] = {
    "247as": {
        "global": {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "RB":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "NPR":    {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": False, "downloadBase64Url": False, "testUrl": False},
        "XX":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "BT":     {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False, "testUrl": False},
    },
    "1688": {
        "global": {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "RB":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "NPR":    {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False, "testUrl": False},
        "XX":     {"aggregatorPage": False, "gamePage": False, "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
        "BT":     {"aggregatorPage": True,  "gamePage": True,  "downloadUrl": True,  "downloadBase64Url": True,  "testUrl": False},
    },
    # ── temporary test environment ─────────────────────────────────────────────
    "test": {
        "global": {"aggregatorPage": False, "gamePage": False, "downloadUrl": False, "downloadBase64Url": False, "testUrl": True},
        "RB":     _OFF.copy(),
        "NPR":    _OFF.copy(),
        "XX":     _OFF.copy(),
        "BT":     _OFF.copy(),
    },
}
