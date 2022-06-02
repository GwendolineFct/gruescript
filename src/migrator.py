import io
import os
from typing import Any
from uuid import uuid4

from ansible_helper import *
from constants import *
from logger import Logger, MigrationLogger
from utils import *


MSG_NOT_AN_ANSIBLE_FILE = "doesn't look like an ansible play or playbook: skipping"

class Migrator:

    uuid_mig = uuid4()
    logs = []
    options = {}
    logger = Logger("Migrator")
    source_version = "source"
    target_version = "latest"
    uuid_to_line = {}
    cache = {}

    def __init__(self, options, cache) -> None:
        self.options.update(options)
        self.migration_logger = MigrationLogger(self.logs, options.get("no_logs_in_files", False))
        self.source_version = options["source_version"]
        self.target_version = options["target_version"]
        self.cache = cache

    def migrate_path(self, *pathes) -> list:
        for path in pathes:
            path = fix_tilde_in_path(path)

            if not os.path.exists(path):
                self.logger.warning(f"path `{path}` does not exist")
            elif os.path.isdir(path):
                self.migrate_dir(path)
            else:
                self.migrate_file(path)
        return self.logs

    
    def migrate_dir(self, path) -> list:
        self.logger.info(f"Scanning {path} ...")
        for filename in os.listdir(fix_tilde_in_path(path)):
            if self.is_to_be_ignored(filename):
                continue
            if filename.startswith('.') and not self.options["process_hidden_files"]:
                continue
            qualified_filename = f"{fix_tilde_in_path(path)}/{filename}"
            if os.path.isdir(qualified_filename):
                self.migrate_dir(qualified_filename)
            elif os.path.isfile(qualified_filename) and ANSIBLE_FILE_PATTERN.fullmatch(filename):
                self.migrate_file(qualified_filename)


    def is_to_be_ignored(self, filename):
        for regex in self.options["ignore_file_patterns"]:
            if regex.fullmatch(filename):
                return True
        return False



    def migrate_file(self, path):
        self.logger.enter()
        self.logger.fine(f"Reading {path} ...")

        #path = path[:path.rindex('/')]
        source = ""
        try:
            with open(path, "rt") as file:
                source = file.read()
        except Exception as e:
            self.migration_logger.warning(path=path, message=f"Failed to load file : {e}")
            return

        _, result = self.migrate_string(source, path)

        if result is not None:
            # if we did migrate the file
            outfilename = path if self.options["overwrite_source"] else (path[:path.rindex('.')]+".migrated."+path[path.rindex('.')+1:])
            self.logger.fine(f"Writing to {outfilename}")
            with open(fix_tilde_in_path(outfilename), "wt") as outfile:
                outfile.write(result)



    def migrate_string(self, data, path = "in-memory-data", force_processing=False):
        """
        migrate a string containing YAML
        """

        self.logger.fine(f"Processing {path} ...")

        # add comments to preserve blank lines and ---
        uuid = uuid4()
        blank_line_preserver = f"# {uuid}"
        instream = io.StringIO(data)
        stream = io.StringIO() 
        for line in instream.readlines():
            if line.isspace() or line.strip().startswith("---"):
                stream.write(blank_line_preserver)
            stream.write(line)
        stream.seek(0)

        # parse YAML
        try:
            yml = new_ruamel_yaml().load(stream)
        except:
            self.logger.warning(f"Skipping {path} : doesn't look like a valid yml")
            self.migration_logger.warning(path=path, message="doesn't look like a valid yml: skipping")
            return self.migration_logger.logs, None
        
        if not force_processing:
            if not is_ansible_yaml(yml, self.cache):
                self.logger.info(f"Skipping {path} : doesn't look like an ansible playbook nor a list of tasks")
                self.migration_logger.info(path=path, yml=None, message="Doesn't look like an ansible playbook nor a list of tasks: skipping")
                return self.migration_logger.logs, None

        self.logger.info(f"Migrating {path} ...")

        yml = self.migrate_yaml(path, yml)

        self.logger.fine(f"Serializing migrated YAML ...")
        
        stream.seek(0)
        new_ruamel_yaml().dump(yml, stream)

        # remove our blank line preservers
        stream.seek(0)
        remove_me = f"# REMOVE ME {self.uuid_mig}"
        result = ""
        for line in stream.readlines():
            if remove_me in line:
                continue
            result += line.replace(blank_line_preserver, "")

        return self.migration_logger.logs, result



    def migrate_yaml(self, path, yml):
        """
        Migrate a YAML object
        """

  
        
        self.migrate_ansible_yaml(path, yml)

        temp = io.StringIO()
        
        new_ruamel_yaml().dump(yml, temp)
        temp.seek(0)
        
        output = io.StringIO()
        lineNo = 1
        while True:
            # Get next line from file
            line = temp.readline()
        
            # if line is empty
            # end of file is reached
            if not line:
                break

            if line.startswith(UUID_COMMENT_PREFIX):
                uuid = line[len(UUID_COMMENT_PREFIX):].strip()
                self.uuid_to_line.update({uuid: lineNo})
            else:
                lineNo += 1
                output.write(line)

        output.seek(0)
        return new_ruamel_yaml().load(output)



    def migrate_ansible_yaml(self, path, yml, depth=1):
        if yml is None:
            self.migration_logger.info(path=path, message="No nodes in YAML file")
            return False
        elif is_ansible_playbook(yml):
            self.migration_logger.info(path=path, message="Migrating as playbook file")
            for node in yml:
                for task_keyword in PLAYBOOK_TASK_KEYWORDS:
                    if task_keyword == 'roles':
                        continue
                    if task_keyword in node:
                        self.logger.debug(f"{' '*(depth*2)}{task_keyword}")
                        self.migrate_task_list(path, node[task_keyword], depth+1)
        elif is_ansible_task_list(yml, self.cache):
            self.migration_logger.info(path=path, message="Migrating as a list of tasks")
            self.migrate_task_list(path, yml)



    def migrate_task_list(self, path, yml, depth=1):
        for task in yml:
            self.migrate_task(path, task, depth)
    

    
    def migrate_task(self, path, task, depth=1):
        """
        Migrates an ansible task

        `path` (str) : path to the file being migrated, used for migration logs
        `task` (CommentedMap) : the task being migrated. a YAML node from ruamel.yaml
        `logs` (list) : the migration logs
        """

        uuid = uuid4()
        task.yaml_set_start_comment(f"{UUID_COMMENT_PREFIX}{str(uuid)}")

        # let's find a name for our task
        task_name = ""
        if "name" in task:
            task_name = task["name"]
        if task_name is None or task_name == "":
            task_name = "unmaned task"
        else:
            task_name = f"task \"{task_name}\""

        # handle case of a task made of block/rescue/always recursively
        shortcut = False
        for attr in ["block", "rescue", "always"]:
            if attr in task:
                shortcut = True
                if task[attr] is None:
                    self.migration_logger.info(path=path, message=f"empty `{attr}`", yml=task, key=attr, uuid=uuid)
                else:
                    self.migrate_task_list(path, task[attr], depth+1)
        if shortcut:
            # if we have block/rescue/always in a task then we cannot have a module
            return

        # handle case module is declared with an action attribute
        if "action" in task:
            self.logger.warning(f"unable to handle action clause in {task_name}")
            self.migration_logger.warning(path=path, message=f"unable to handle action clause", yml=task, key="action", uuid=uuid)
            return
        
        # let's try to find module name in task   
        module_name = self.find_module_name_in_task(task)

        if module_name is None or module_name == "":
            # oops couldn't find it
            self.migration_logger.warn(path=path, message=f"Could not identify module", yml=task, key=None, uuid=uuid)
        
        # retrieve module from cache / internet
        module = self.cache.get_module(module_name, cache_it=True)

        if module is None:
            # the module could not be found in ansible doc / cache
            # tell user and leave as is
            self.logger.error(f"Unknown module `{module_name}` in {task_name}")
            self.migration_logger.error(path=path, message=f"unknown module `{module_name}`", yml=task, key=module_name, uuid=uuid)
            return

        if module.get("id_target") is None:
            # the module does not exist in target version
            # tell user and leave as is
            self.migration_logger.error(path=path, message=f"module `{module_name}` does not exist in version {self.target_version}", yml=task, key=module_name, uuid=uuid)
            return
            
        if task[module_name] is None:
            # ruamel is picky when a module has no attributes/free-form
            # so we add a dummy comment that we be removed when saving
            task[module_name] = ruamel.yaml.comments.CommentedMap()
            task[module_name].insert(0, '_', '')
            task[module_name].yaml_add_eol_comment(f"# REMOVE ME {self.uuid_mig}", '_', column=0)
            
        # our module exists in source and target versions
        if module_name != module['id_target']:
            # module name does not match target name, let's rename it
            rename_dict_key(task, module_name, module['id_target'])
            module_name = module['id_target']


        link_to_doc = False
        if isinstance(task[module_name], str):
            # free form parameters
            if "param_target" in module and "free-form" not in module["param_target"]:
                # latest version does not support free-form
                link_to_doc = True
                self.migration_logger.error(path=path, message=f"module {module_name} does not support free-form parameters in {self.target_version}", yml=task, key=module_name, uuid=uuid)
            else:
                # don't handle free-form
                self.migration_logger.warning(path=path, message=f"Cannot perform migration checks on free-form parameters", yml=task, key=module_name, uuid=uuid)
                if module.get("breaking_params"):
                    # but can warn that there are some breaking changes in the module's parameters
                    link_to_doc = True
                    self.migration_logger.warning(path=path, message=f"There are some breaking changes in the parameters from version {self.source_version} to version {self.target_version}", yml=task, key=module_name, uuid=uuid)

        elif module_name == "ansible.builtin.set_fact" or module_name == "set_fact":
            # dont handle set_fact parameters
            pass

        elif module.get("params_source", {}) is not None or module.get("params_target", {}) is not None:
            # we have parameters in both versions, let's check they are correct
            self.analyse_parameters(path, uuid, task[module_name], task, module_name, module.get("params_source", {}), module.get("params_target", {}), depth+1)

        if "register" in task:
            # our task registers the modules results
            if module.get('breaking_return', False):
                # there are breaking changes in the module returned values
                link_to_doc = True
                self.migration_logger.warning(path=path, message=f"There is a breaking change in the returned values", yml=task, key=module_name, uuid=uuid)

        if module.get("breaking_facts"):
            # there are breaking facts in the module returned values            
            link_to_doc = True
            self.migration_logger.warning(path=path, message=f"There is a breaking change in the facts returned", yml=task, key=module_name, uuid=uuid)

        if link_to_doc:
            if '.' in module['id_target']:
                doc_url = URL_ANSIBLE_COLLECTION.format(version=self.target_version, id=module['id_target'].replace('.','/'))
            else:
                doc_url = URL_ANSIBLE_MODULE.format(version=self.target_version, id=module['id_target'])
            self.migration_logger.warning(path=path, message=f"Please check version {self.target_version}'s documentation for module `{module_name}`\n{doc_url}", yml=task, key=module_name, uuid=uuid)



    def find_module_name_in_task(self, task) -> str:
        for attr in task:
            skip = False
            for filter in TASK_GENERIC_ATTRIBUTES:
                skip = skip or filter.fullmatch(attr)
            if skip:
                continue
            return attr
        
        return None

    def analyse_parameters(self, path, uuid, module, parent, key, params_source, params_target, depth):
        """
            analyse parameters for module or subparameters (to do) of a parameter
            will try to migrate automaticaly some obvious values
        """

        if not module is None:
            # check for aliases
            # rename them before and and out of parameters iteration
            # to avoid mutating during iteration
            aliases = {}
            for p in module:
                # our parameter must exist in 2.9
                if p == '_' or p not in params_source:
                    continue

                p_source = params_source[p]
                if p in p_source.get("aliases",[]):
                    self.logger.debug(f"{p} -> {p_source}")
                    if not "name" in p_source:
                        self.logger.fatal(f"attribute `name` is not present in parameter `{p_source}`")
                        raise AttributeError
                    aliases.update({p : f"{p_source['name']}"})

            for alias in aliases:
                # rename it to real name
                realname = aliases[alias]
                rename_dict_key(module, alias, realname)
                self.migration_logger.info(path=path, message=f"alias parameter `{alias}` renamed to `{realname}`", yml=module, key=realname, uuid=uuid)

    
            for p in module:
                if p == '_':
                    continue
                
                try:
                    line = module[p].lc.line
                except:
                    pass

                self.logger.debug(f"{' '*(depth*2)}{p}")

                if p not in params_source and not p in params_target:
                    self.migration_logger.warning(path=path, message=f"Unknown module parameter `{p}` in both versions", yml=module, key=p, uuid=uuid)
                    continue

                # our parameter must exist in latest version
                if p not in params_target:
                    self.migration_logger.error(path=path, message=f"unknown module parameter `{p}` in version {self.target_version}", yml=module, key=p, uuid=uuid)
                    continue

                # now that we have checked the parameter let's take care of it's value 
                v = module[p]

                if isinstance(v, str) and "{{" in v:
                    # handle case where parameter is a variable expression
                    if "choices" in params_source[p] and "choices" in params_target[p] and not all(c in params_target[p]["choices"] for c in params_source[p]['choices']):
                        # some choices available in 2.9 are not available in latest
                        self.migration_logger.warning(path=path, message=f"Some possible values for parameter `{p}` have been removed in version {self.target_version}. Allowed values are : [`{'`, `'.join(params_target[p]['choices'])}`]", yml=module, key=p, uuid=uuid)
                    elif "choices" not in params_source[p] and "choices" in params_target[p]:
                        # 2.9 was open bar and is not a closed list in latest
                        self.migration_logger.warning(path=path, message=f"Possible values for parameter `{p}` have been restricted to a closed list of choices in version {self.target_version} : [`{'`, `'.join(params_target[p]['choices'])}`]", yml=module, key=p, uuid=uuid)
                    elif not is_type_compatible_with(params_source[p]["type"], params_target[p]["type"]):
                        self.migration_logger.warning(path=path, message=f"type of parameter `{p}` changed from `{params_source[p]['type']}` in version {self.source_version} to `{params_target[p]['type']}` in version {self.target_version}", yml=module, key=p, uuid=uuid)
                    else:
                        # looks ok
                        pass
                elif "params" in params_source[p] and len(params_source[p]["params"]) > 0:
                    # nested parameters
                    self.analyse_parameters(path, uuid, params_source[p], module, p, params_source[p]["params"], params_target[p].get("params",{}), depth+1)
                elif "choices" in params_target[p]:
                    handled = False
                    # if parameter as a list of choice, then our value must be in it
                    if v in params_target[p]["choices"]:
                        # we're fine
                        handled = True
                    else:
                        # our value was a (probably) valid choice in 2.9 but not in latest
                        if params_target[p]["type"] == "boolean":
                            # boolean is easy
                            handled = True

                    if not handled:
                        self.migration_logger.error(path=path, message=f"value `{v}` for parameter `{p}` is not valid in version {self.target_version}. Allowed values are : [`{'`, `'.join(params_target[p]['choices'])}`]", yml=module, key=p, uuid=uuid)

                if not is_type_compatible_with(params_source[p]["type"], params_target[p]["type"]):
                    self.migration_logger.warning(path=path, message=f"type of parameter `{p}` changed from `{params_source[p]['type']}` in version {self.source_version} to `{params_target[p]['type']}` in version {self.target_version}", yml=module, key=p, uuid=uuid)


        for p in params_target:
            pl = params_target[p]
            p_source = params_source[p] if p in params_source else None
            if module is None or p not in module:
                if pl.get("required", False):
                    handled = False
                    if p in pl.get("aliases", []):
                        # don't put required error on aliases
                        continue
                    for a in pl.get("aliases", []):
                        if not module is None and a in module:
                            # required param p was specified via one of it's aliases (a)
                            handled = True
                    if handled:
                        continue
                    # we've got a parameter that is required in latest but is missing in our code
                    self.migration_logger.error(path=path, message=f"missing parameter `{p}` is required in version {self.target_version}", yml=parent, key=key, uuid=uuid)
                elif p_source is not None and p_source.get("default", None) != pl.get("default", None):
                    # we've got a parameter that is not specified with a default value that has changed
                    self.migration_logger.warning(path=path, message=f"default value for missing parameter `{p}` changed from `{p_source.get('default', None)}` in version {self.source_version} to `{pl.get('default', None)}` in version {self.target_version} ", yml=parent, key=key, uuid=uuid)


    def get_line_by_uuid(self, uuid: str) -> int:
        return self.uuid_to_line.get(uuid, -1)
 
