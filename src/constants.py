import re


SUPPORTED_VERSIONS = [ '2.9', '3', '4', '5']
SUPPORTED_VERSIONS_KEYS = { '2.9' : '2x', '3': '3x', '4' : '4x', '5' : '5x' }


CACHE_FILE_PATTERN = re.compile(".*\\.cache\\.y[a]?ml")

ANSIBLE_FILE_PATTERN = re.compile(".*\\.y[a]?ml")
MIGRATED_FILE_PATTERN = re.compile(".*\\.migrated\\.y[a]?ml")


LOG_ALWAYS = 0
LOG_FATAL = 0
LOG_ERROR = 1
LOG_WARNING = 2
LOG_INFO = 3
LOG_FINE = 4
LOG_DEBUG = 5
LOG_DEBUG_FINE = 6
LOG_DEBUG_FINER = 7
LOG_DEBUG_FINEST = 8
LOG_DEBUG_METHOD = 9
LOG_COLOR = {
    "FATAL": "31m",
    "ERROR": "31m",
    "WARN" : "33m",
    "INFO" : "36m",
    "FINE" : "34m",
    "DEBUG": "35m",
    "PRINT": "0m",
    "DEFAULT": "0m",
}


DEFAULT_OPTIONS = {
    "path": None,
    "source": None,
    "overwrite_source": False,
    "log_path": None,
    "show_logs": False,
    "process_hidden_files":False,
    "verbosity": 0,
    "quietness": 0,
    "source_version": 2.9,
    "target_version": "latest",
    "cache_downloaded_modules": False,
    "cache_path": ["./cache"],
    "generate_cache_for_collection": [],
    "generate_cache_for_module": [],
    "no_logs_in_files": False,
    "raw_to_any_ok": True,
    "complex_is_dictionary": True,
    "ignore_file_patterns": [
        re.compile('\\.'),         # Ignore current folder pointer
        re.compile('\\.\\.'),      # Ignore parent folder pointer
        re.compile('\\.git'),      # Ignore .git folder
        CACHE_FILE_PATTERN,
        MIGRATED_FILE_PATTERN
    ],
    "logging_verbosity": LOG_INFO,
}


PLAYBOOK_TASK_KEYWORDS = [
    "tasks",
    "handlers",
    "pre_tasks",
    "post_tasks",
    "roles",
]

TASK_GENERIC_ATTRIBUTES = [
    re.compile(x) for x in ("any_errors_fatal", "args", "async", "become", "become_exe", "become_flags", "become_method","become_user","changed_when", "check_mode","collections","connection","debugger","delay","delegate_facts","delegate_to","diff","environment","failed_when","ignore_errors","ignore_unreachable","local_action","loop","loop_control","module_defaults","name","no_log","notify","poll","port","register","remote_user","retries","run_once","tags","throttle","timeout","until","vars","when","with_.*")
]


URL_ANSIBLE_MODULE = "https://docs.ansible.com/ansible/{version}/modules/{id}_module.html"
URL_ANSIBLE_COLLECTION = "https://docs.ansible.com/ansible/{version}/collections/{id}_module.html"
URL_ANSIBLE_COLLECTION_INDEX = "https://docs.ansible.com/ansible/{version}/collections/{id}/index.html"


HTML_OOPS = "Oops!"


COMMENT_PREFIX = "*** MIG *** "
UUID_COMMENT_PREFIX = f"# {COMMENT_PREFIX} UUID : "


TYPES_ORDER = ('boolean','integer', 'float', 'string', 'path', 'dictionary', 'raw', 'any')

