from cache import Cache
from constants import *
from logger import Logger

logger = Logger("Utils")

def is_generic_task_attribute(attribute) -> bool:
    for r in TASK_GENERIC_ATTRIBUTES:
        if r.fullmatch(attribute):
            return True
    return False

def is_ansible_playbook(yml) -> bool:
    if yml is None:
        return False
    for node in yml:
        if "hosts" in node:
            # looks like a playbook
            for keyword in PLAYBOOK_TASK_KEYWORDS:
                if keyword in node:
                    return True
            # a playbook must have a "hosts" and at least one task to execute
    return False

def is_ansible_task_list(yml, cache: Cache) -> bool:
    if yml is None:
        return False

    # does it look like a list of tasks ?
    nb_known_attributes = 0
    nb_attributes = 0
    nb_modules = 0
    nb_nodes = 0
    for node in yml:
        nb_nodes += 1
        for attribute in node:
            nb_attributes += 1
            if is_generic_task_attribute(attribute) or attribute in ("block","rescue","always"):
                nb_known_attributes += 1
            if cache.is_known_module_name(attribute):
                nb_modules += 1

    logger.debug(f"nb_nodes={nb_nodes}, nb_modules={nb_modules}, nb_attributes={nb_attributes}, nb_known_attributes={nb_known_attributes}")
    if nb_nodes == 0:
        # empty file ?
        return False
    
    if nb_modules / nb_nodes < 0.42 and nb_known_attributes / nb_attributes < 0.666:
        # magic numbers, we needed some of these
        return False
    
    return True


def is_ansible_yaml(yml, cache: Cache) -> bool:
    if yml is None:
        return False
    
    # Does it look like a play ?
    if is_ansible_playbook(yml):
        return True

    elif is_ansible_task_list(yml, cache):
        return True

    return False



