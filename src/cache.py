from copy import deepcopy
import os
import yaml

from constants import *
from logger import Logger
from scrapper import Scrapper
from utils import *


class Cache:
    """
    This class handles caching of modules used for migration

    It can read cache files and write them.
    
    When it can't find a module it will try to download it's documentation from ansible website

    """

    modules = {}
    options = {}
    logger = Logger("Cache")
    scrapper = Scrapper()
    
    def __init__(self, options) -> None:
        self.options.update(options)
        self.source_version = options["source_version"]
        self.target_version = options["target_version"]
        self.logger.verbosity = options["logger_verbosity"]


    def load_caches(self, pathes) -> None:
        self.modules = {}
        for path in pathes:
            path = fix_tilde_in_path(path)
            if os.path.isdir(path):
                self.load_cache_dir(path)
            elif os.path.isfile(path):
                self.load_cache_file(path)
            else:
                self.logger.warning(f"IGNORING {path} has it is not a dir nor a file (does it even exist ?)")
        

        self.logger.info(f"{len(self.modules)} modules loaded from cache")

        if len(self.modules) == 0:
            return

        self.logger.fine(f"Optimizing modules with current options ...")
        aliases = []
        for module_name in self.modules:
            module = self.modules[module_name]
            if module is None:
                # self.logger.warning(f"module {module_name} is None")
                continue
            self.optimize_module(module)

            if module.get("id_source") is not None:
                self.logger.debug_finest(f"{module['id_source']} -> {module['name']}")
                aliases.append({module["id_source"] : module})
            if module.get("id_target") is not None:
                self.logger.debug_finest(f"{module['id_target']} -> {module['name']}")
                aliases.append({module["id_target"] : module})
                        
            param_breaking_change = self.check_module_params(None, module.get("params_source", {}), module.get("params_target", {}), "parameter")

            return_breaking_change = self.check_module_params(None, module.get("return_source", {}), module.get("return_target", {}), "return value")

            facts_breaking_change = self.check_module_params(None, module.get("facts_source", {}), module.get("facts_target", {}), "fact")

            module.update({"breaking": param_breaking_change or return_breaking_change or facts_breaking_change})
            module.update({"breaking_params": param_breaking_change})
            module.update({"breaking_return": return_breaking_change})
            module.update({"breaking_facts": facts_breaking_change})

        for alias in aliases:
            self.modules.update(alias)


    def is_known_module_name(self, name) -> bool:
        return name in self.modules


    def get_module(self, key, cache_it = True, force_reload = False, versions=None):
        """
        retrieves a module from cache or from ansible website

        if the module is in cache and both source and target versions of documentation are present the cached version is returned

        if not it will delegate to the scrapper to retrieve missing documentation(s)
        """

        self.logger.enter()

        if versions is None or len(versions) == 0:
            versions = [ self.options['source_version'], self.options['target_version'] ]

        module = None
        if cache_it:
            module = self.modules.get(key, None)
            
        if module is None:
            module = {"name": key, "downloaded": cache_it, "used": True}

        self.logger.debug_finer(f"{module}")

        is_missing_version = False
        for version in versions:
            if f"doc_{SUPPORTED_VERSIONS_KEYS[version]}" not in module:
                self.logger.debug_fine(f"module {key} is missing doc for version {version}")
                is_missing_version = True

        if not is_missing_version:
            self.logger.debug(f"using module {key} from cache")
            # it has been cached, let's return it
            module.update({'used':True})
            self.logger.returns(module)
            return module

        for version in versions:
            version_key = SUPPORTED_VERSIONS_KEYS[version]
            if force_reload and f"doc_{version_key}" in module:
                del module[f"doc_{version_key}"]

            if not f"doc_{version_key}" in module:
                doc = self.scrapper.get_module_version_data(key, version)
                if doc is not None:
                    module.update({f"doc_{version_key}": doc})
                else:
                    # store the doc is missing
                    module.update({f"doc_{version_key}": {"missing" : True}})

                # if we downloaded a module's documentation during migration
                # the must mark it to be able to save it if required
                module[f"doc_{version_key}"].update({ "downloaded" : cache_it })

        if cache_it:
            # we have downloaded the module during migration
            # we need to optimize it like others
            module.update({"downloaded": True})
            self.optimize_module(module)
            # make sure we have pointers for source id and target id in the cache
            if module.get('id_source', "") != "":
                self.modules.update({ module.get('id_source', "") : module })
            if module.get('id_target', "") != "":
                self.modules.update({ module.get('id_target', "") : module })
            
        self.logger.returns(module)
        return module


    def cache_collection(self, collection):

        self.logger.enter()
        
        module_names = self.scrapper.get_collection_module_names(collection, self.options['target_version'])

        if len(module_names) == 0:
            self.logger.info(f"Collection {collection} has no modules")
            return

        self.logger.info(f"Downloading modules for collection {collection} ...")
        count = 0
        modules = []
        for module_name in module_names:
            count += 1
            self.logger.info(f"Dowloading module {count}/{len(module_names)} : {module_name} ...")
            module = self.get_module(f"{collection}.{module_name}", cache_it=False, versions=SUPPORTED_VERSIONS)
            if module is not None:
                modules.append(module)

        self.logger.info(f"Saving cache for collection {collection} ...")

        save_cache(modules, f"{self.options['cache_path'][0]}/{collection}")


    def get_used_collections(self):
        used_collections = []
        for module in self.modules.values():
            if module is None or not module.get("used", False):
                continue
            if "collection" in module and module["collection"] not in used_collections:
                used_collections.append(module["collection"])
            used_collections.sort()
        return used_collections

    def save_downloaded_modules(self):
        """
        save the modules documentation that were downloaded during the migration
        it can then be reused as cache for next run
        """

        # cache downloaded modules
        self.logger.fine("Cleaning cache ...")
        downloaded_modules = {}
        processed_modules = set()
        for key in self.modules:
            module = self.modules[key]
            if module is None or not module.get("downloaded", False) or id(module) in processed_modules:
                continue
            processed_modules.add(id(module))
            downloaded_module = deepcopy(module)
            for version in SUPPORTED_VERSIONS:
                # exclude versions from provided cache
                vk = SUPPORTED_VERSIONS_KEYS[version]
                if downloaded_module.get(f"doc_{vk}") is not None and not downloaded_module.get(f"doc_{vk}", {}).get("downloaded", False):
                    del downloaded_module[f"doc_{vk}"]
            remove_param_aliases(downloaded_module, "params_source")
            remove_param_aliases(downloaded_module, "return_source")
            remove_param_aliases(downloaded_module, "facts_source")
            remove_param_aliases(downloaded_module, "params_target")
            remove_param_aliases(downloaded_module, "return_target")
            remove_param_aliases(downloaded_module, "facts_target")
            downloaded_modules[key] = downloaded_module

        self.logger.info("Saving cache ...")
        save_cache(downloaded_modules, "downloaded-modules")


    def load_cache_dir(self, path):
        self.logger.info(f"Scanning for cache in {path} ...")

        for filename in os.listdir(fix_tilde_in_path(path)):
            if filename == '.' or filename == '..':
                continue
            if filename.startswith('.') and not self.options["process_hidden_files"]:
                continue
            qualified_filename = f"{path}/{filename}"
            if os.path.isdir(qualified_filename):
                # we dont search recursively for cache
                pass
            elif os.path.isfile(qualified_filename) and CACHE_FILE_PATTERN.fullmatch(filename):
                self.load_cache_file(qualified_filename)


    def load_cache_file(self, path):
        self.logger.info(f"Loading cache from {path} ...")
        cache = load_cache(path)
        processed = set()
        for module in cache.values():
            if id(module) in processed:
                continue
            processed.add(id(module))
            for version in SUPPORTED_VERSIONS: 
                vname = get_module_name_in_version(module, version)
                if vname is not None:
                    if vname in self.modules:
                        # there is a cached moduile with that name
                        if id(self.modules[vname]) != id(module):
                            # it's not the same object so
                            # update (overwrite) the documentation for version of the existing module with the one from this cache file
                            self.modules[vname].update({f"doc_{SUPPORTED_VERSIONS_KEYS[version]}" : get_module_doc(module, version)})
                            # don't forget to updated the downloaded status of the module
                            self.modules[vname].update({"downloaded" : module.get("downloaded", False)})
                    else:
                        # module is not cached under that name so add it to cache
                        self.modules.update({vname : module})


    def optimize_module(self, module):
        """
        This method optimizes the module for the current job
        - create params_source, return_source, facts_source, params_target, return_target, facts_target
        - expand aliases for attributes
        - computes breaking changes
        """

        # remove any previous params_source, return_source, facts_source, params_target, return_target, facts_target
        for kind in [ "params", "return", "facts" ]:
            if f"{kind}_source" in module:
                del module[f"{kind}_source"]
            if f"{kind}_target" in module:
                del module[f"{kind}_target"]

        # creates params_source, return_source, facts_source, params_target, return_target, facts_target
        # for appropriate versions
        source_doc = deepcopy(module.get(f"doc_{self.options['source_version_key']}", {}))
        target_doc = deepcopy(module.get(f"doc_{self.options['target_version_key']}", {}))

        module.update({"id_source": source_doc.get("name", None)})
        module.update({"id_target": target_doc.get("name", None)})
        
        module.update({"missing_source": True, "missing_target": True})

        for kind in [ "params", "return", "facts"]:
            if kind in source_doc:
                module.update({f"{kind}_source": param_list_to_dict(source_doc[kind])})
                module["missing_source"] = False
            else:
                module.update({f"{kind}_source": {}})

            if kind in target_doc:
                module.update({f"{kind}_target": param_list_to_dict(target_doc[kind])})
                module["missing_target"] = False
            else:
                module.update({f"{kind}_target": {}})

        # expand aliases 
        param_aliases = {}
        for param_name in module[f"params_source"]:
            for alias in module[f"params_source"][param_name].get("aliases", []):
                param_aliases.update({alias : module["params_source"][param_name]})
        module["params_source"].update(param_aliases)
        param_aliases = {}
        for param_name in module["params_target"]:
            for alias in module["params_target"][param_name].get("aliases", []):
                param_aliases.update({alias : module["params_target"][param_name]})
        module["params_target"].update(param_aliases)

        # compute breaking changes
        param_breaking_change = self.check_module_params(None, module.get("params_source", {}), module.get("params_target", {}), "parameter")

        return_breaking_change = self.check_module_params(None, module.get("return_source", {}), module.get("return_target", {}), "return value")

        facts_breaking_change = self.check_module_params(None, module.get("facts_source", {}), module.get("facts_target", {}), "fact")

        module.update({"breaking": param_breaking_change or return_breaking_change or facts_breaking_change})
        module.update({"breaking_params": param_breaking_change})
        module.update({"breaking_return": return_breaking_change})
        module.update({"breaking_facts": facts_breaking_change})




    def check_module_params(self, parent, params_source, params_target, type = "parameter"):
        breaking_change = False
        empty_array = []
        if parent is not None:
            parent = f"{parent}."
        else:
            parent = ""

        for k_source in params_source:
            param = params_source[k_source]

            if not k_source in params_target:
                # the parameter/return value has been removed in latest version
                params_source[k_source].update({"removed":True})
                breaking_change = True
                continue

            # ok we have the parameter in both versions
            latest = params_target[k_source]

            try:
                if not is_type_compatible_with(param["type"], latest["type"]):
                    # the type of the parameter/return value as changed
                    breaking_change = True
            except (RuntimeError, ValueError) as e:
                self.logger.error(f"{parent}{k_source} type {param['type']} -> {latest['type']}")
                raise e

            if type == "parameter":
                # the following don't apply to return values

                if param.get("required", False) and latest.get("required", False):
                    # the parameter was not required in 2.9 and now required
                    breaking_change = True

                if param.get("default") is not None and param.get("default") != latest.get("default"):
                    # the parameter has a default value in 2.9 that is different in latest
                    breaking_change = True

                if len( param.get("choices", empty_array) ) == 0 and len(latest.get("choices", empty_array)) > 0 \
                    or len(latest.get("choices", empty_array)) > 0 and not all(c in latest.get("choices", empty_array) for c in param.get("choices",empty_array)):
                    # the parameter has a different set of available choices in 2.9 and latest
                    breaking_change = True

            # check any sub parameters/return values
            breaking_change = breaking_change or self.check_module_params(f"{parent}{k_source}", param.get("params",[]), latest.get("params",[]), type)
        
        return breaking_change




    

def param_list_to_dict(params):
    dict = {}
    for param in params:   
        dict[param['name']] = param
        if "params" in param:
           param["params"] = param_list_to_dict(param["params"])
    return dict

def save_cache(cache, filename) -> None:
    Cache.logger.enter()

    for module in cache:
        if "used" in module:
            del module["used"]
    
    with open(f"{fix_tilde_in_path(filename)}.cache.yml", "wt") as file:
            file.write(to_yaml(cache))


def load_cache(filename) -> dict:
    tmp = {}
    try:
        with open(fix_tilde_in_path(filename), "rt") as file:
            tmp = yaml.load(file, yaml.CLoader)
    except Exception as e:
        Cache.logger.warning(f"Failed to load cache from {filename} : {e}")

    dico = {}
    modules = tmp.get("modules", [])
    if len(modules) == 0:
        Cache.logger.warning("Ignoring empty cache file ...")
    
    # convert the list of modules into a dict
    # add entries for each names  of the module in the various versions
    # (ie "file" and "ansible.builtin.file" )
    for module in modules:
        for version in SUPPORTED_VERSIONS:
            vname = get_module_name_in_version(module, version)
            if vname is not None and vname not in dico:
                dico.update({ vname : module} )

    return dico



def to_yaml(modules):
    yml = "---\nmodules:\n"

    if isinstance(modules, dict):
        for key in modules:
            module = modules[key]
            if module is not None and module['name'] == key:
                yml += module_to_yaml(module)
    else:
        for module in modules:
            if module is not None:
                yml += module_to_yaml(module)

    return yml

def module_to_yaml(module):
    paramstart = " "
    indent = '    '

    yml = f"{indent}- name: {module['name']}\n"
    if "downloaded" in module and module['downloaded']:
        yml += f"{indent}  downloaded: true\n"
    for version in SUPPORTED_VERSIONS:
        doc_version_key = f"doc_{SUPPORTED_VERSIONS_KEYS[version]}"
        if doc_version_key in module:
            yml += f"{indent}  {doc_version_key}:\n"
            doc_version = module[doc_version_key]
            if "missing" in doc_version and doc_version["missing"]:
                yml += f"{indent}    missing: true\n"
            else:
                yml += f"{indent}    name: {doc_version['name']}\n"
                if doc_version.get('downloaded', False):
                    yml += f"{indent}    downloaded: true\n"
                for kind in ["params", "return", "facts"]:
                    if kind in doc_version and len(doc_version[kind]) > 0:
                        yml += f"{indent}    {kind}:{paramstart}{params_to_yaml(module['name']+'.'+doc_version_key, doc_version[kind], 2).rstrip()}\n"

    return yml


def params_to_yaml(parent, params, depth):
    yml = ""
    for param in params:
        if yml != "":
            yml += ", "
        yml += "{ "
        yml += f"name: \"{param['name']}\""
        if "aliases" in param and param['aliases'] and param['aliases'] != []:
            yml += f", aliases: [{', '.join(map(lambda x: str(to_yaml_value(x, True)), param['aliases']))}]"
        if "required" in param and param['required']:
            yml += f", required: true"
        if "type" in param and param['type'] and param['type'] != '-':
            yml += f", type: \"{param['type']}\""
        if "default" in param and param['default'] is not None:
            yml += f", default: {to_yaml_value(param['default'], True)}"
        if "choices" in param and param['choices'] is not None and len(param['choices']) > 0:
            yml += f", choices: [{', '.join(map(lambda x: str(to_yaml_value(x, True)), param['choices']))}]"
        if "params" in param and param['params'] is not None and len(param['params']) > 0:
            yml += f", params: {params_to_yaml(parent+'.'+param['name'], param['params'], depth+2).rstrip()}"
        yml += " }"
    return "[ " + yml + " ]"


def to_yaml_value(value, forcequotes=False):
    if value is None:
        return "None"
    if isinstance(value, bool): # or str(value).lower() == 'true' or str(value).lower() == 'false' or str(value).lower() == 'yes' or str(value).lower() == 'no':
        return str(value).lower()
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if str(value).isnumeric():
        return value
    if isinstance(value, str):
        return '"' + value.replace("\\","\\\\").replace('"',"\\\"") + '"'
    if isinstance(value, list):
        return "[" + ", ".join(map(lambda x: to_yaml_value(x, forcequotes), value)) + "]"
    Cache.logger.fatal(f"unhandled type {type(value)}")
    exit(1)



def remove_param_aliases(module, key):
    if key in module:
        params = module[key]
        aliases = []
        for p in params:
            param = params[p]
            if "aliases" in param and p in param["aliases"]:
                aliases.append(p)
        for p in aliases:
            del params[p]
