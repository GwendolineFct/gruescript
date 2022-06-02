
import os
import ruamel.yaml

from constants import *
from logger import Logger


logger = Logger("Utils")

def rename_dict_key(dict, old, new):
    """
    renames a dictionary key
    """
    for _ in range(len(dict)):
        k, v = dict.popitem(False)
        dict[new if old == k else k] = v


def fix_tilde_in_path(path) -> str:
    """
    replaces the starting ~ in a path by the user home dir
    """

    if len(path) > 0 and path[0] == '~':
        return f"{os.environ['HOME']}{path[1:]}"
    return path


def new_ruamel_yaml():
    ryaml = ruamel.yaml.YAML()
    ryaml.indent(mapping=2, sequence=4, offset=2)
    ryaml.width = 4096
    ryaml.preserve_quotes = True
    return ryaml



def module_has_doc_version(module, version) -> bool:
    """
    return true if the module contains a valid documentation for the specified version    
    """    
    if version not in SUPPORTED_VERSIONS:
        return False
    return f"doc_{SUPPORTED_VERSIONS_KEYS[version]}" in module


def get_module_doc(module, version) -> bool:
    """
    return the doc_{version} for the specified module and version
    
    returns None if `version` is not in `SUPPORTED_VERSIONS` or module has not a `doc_{version}` key
    """

    if version not in SUPPORTED_VERSIONS:
        return False
    return module.get(f"doc_{SUPPORTED_VERSIONS_KEYS[version]}", None)


def get_module_name_in_version(module, version) -> str:
    """
    return the name of the module for the specified module and version (ie "file" in 2.9 and "ansible.builtin.file" in later versions)

    returns None if `version` is not in `SUPPORTED_VERSIONS` or module has not a `doc_{version}` key nor a name in it's doc_{version}
    """

    if version not in SUPPORTED_VERSIONS:
        return None

    if not isinstance(module, dict):
        raise Exception(f"supplied module is not a dict but a {type(module)}")

    doc = module.get(f"doc_{SUPPORTED_VERSIONS_KEYS[version]}", {})

    return doc.get("name", None)


def is_type_compatible_with(source, target) -> bool:

    if source == "complex":
        source = "dictionary"

    if target == "complex":
        target = "dictionary"

    if source == target:
        return True

    if target == "raw":
        return True

    if source == "raw":
        return True

    if (source == "string" or source == "path") and (target == "string" or target == "path"):
        return True
        
    if target == "dictionary" and source != target:
        return False
    
    if source.startswith("list(") and not target.startswith("list("):
        return False

    if not source.startswith("list(") and target.startswith("list("):
        return is_type_compatible_with(source, target[5:-1])

    if source.startswith("list(") and  target.startswith("list("):
        return is_type_compatible_with(source[5:-1], target[5:-1])

    sindex = TYPES_ORDER.index(source)

    tindex = TYPES_ORDER.index(target)

    if sindex < 0:
        logger.warning(f"Unhandled source type {source}")

    if tindex < 0:
        logger.warning(f"Unhandled target type {target}")

    return sindex <= tindex