#!/usr/bin/env python3

import os
import io
import re
import ruamel.yaml
import yaml
import argparse
from uuid import uuid4
from typing import OrderedDict
from lxml import html
import requests
import inspect
import time



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
    "no_logs_in_files": False,
    "raw_to_any_ok": True,
    "complex_is_dictionary": True,
}

CACHE_FILE_PATTERN = re.compile(".*\\.cache\\.y[a]?ml")
ANSIBLE_FILE_PATTERN = re.compile(".*\\.y[a]?ml")
MIGRATED_FILE_PATTERN = re.compile(".*\\.migrated\\.y[a]?ml")


options = {}

modules = {}

uuid_mig = uuid4()

COMMENT_PREFIX = "*** MIG *** "
UUID_COMMENT_PREFIX = f"# {COMMENT_PREFIX} UUID : "

LATEST_VER = "2.12"

PLAYBOOK_TASK_KEYWORDS = [
    "tasks",
    "handlers",
    "pre_tasks",
    "post_tasks",
    "roles",
]
TASK_GENERIC_ATTRIBUTES = [re.compile(x) for x in ("any_errors_fatal", "args", "async", "become","become_exe","become_exe", "become_flags", "become_method","become_user","changed_when", "check_mode","collections","connection","debugger","delay","delegate_facts","delegate_to","diff","environment","failed_when","ignore_errors","ignore_unreachable","local_action","loop","loop_control","module_defaults","name","no_log","notify","poll","port","register","remote_user","retries","run_once","tags","throttle","timeout","until","vars","when","with_.*")]

TYPES_ORDER = ('boolean','integer', 'float', 'string', 'path', 'dictionary', 'raw', 'any')

LOG_ALWAYS = 0
LOG_FATAL = 0
LOG_ERROR = 1
LOG_WARNING = 2
LOG_INFO = 3
LOG_DEBUG = 4
LOG_TRACE = 5
LOG_COLOR = {
    "FATAL": "31m",
    "ERROR": "31m",
    "WARN" : "33m",
    "INFO" : "34m",
    "DEBUG": "35m",
    "TRACE": "36m",
    "PRINT": "0m",
    "DEFAULT": "0m",
}

log_verbosity = LOG_INFO

_prev_log_time = None

def now():
    return round(time.time()*1000)

START_TIME = now()

def _log_message(ilevel, slevel, message):
    if ilevel == LOG_ALWAYS or log_verbosity >= ilevel :
        delta = now() - START_TIME
        color = LOG_COLOR.get(slevel, LOG_COLOR.get("DEFAULT"))
        print(f"{str(delta).rjust(8)} \033[{color}{slevel.rjust(5)}\033[0m : {message}")


def version(v):
    
        return f"{v} version" if str(v) in ["devel","latest"] else f"version {v}"

def source_version():
    global options
    return version(options["source_version"])

def target_version():
    global options
    return version(options["target_version"])

def log_always(message, method=''):
    _log_message(LOG_ALWAYS, "PRINT", message)

def log_fatal(message, method=''):
    _log_message(LOG_FATAL, "FATAL", message)

def log_error(message, method=''):
    _log_message(LOG_ERROR, "ERROR", message)

def log_warning(message, method=''):
    _log_message(LOG_WARNING, "WARN", message)

def log_info(message, method=''):
    _log_message(LOG_INFO, "INFO", message)

def log_debug(message, method=''):
    _log_message(LOG_DEBUG, "DEBUG", message)

def log_trace(message, method=''):
    _log_message(LOG_TRACE, "TRACE", message)

def new_ruamel_yaml():
    ryaml = ruamel.yaml.YAML()
    ryaml.indent(mapping=2, sequence=4, offset=2)
    ryaml.width = 4096
    ryaml.preserve_quotes = True
    return ryaml

_CACHE = {}


def url_to_cache_path(url):
    return url[8:] # strip https://

def uncache(url):
    cache_path = url_to_cache_path(url)
    if cache_path in _CACHE:
        del _CACHE[cache_path]

def cache(url, content):
    cache_path = url_to_cache_path(url)
    _CACHE[cache_path] = content

def sanitizeUrl(url):
    parts = url.split('/')
    stack = []
    for part in parts:
        if part == "..":
            stack.pop()
        else:
            stack.append(part)
    return '/'.join(stack)

def get_url(url):
    url = sanitizeUrl(url)
    cache_url = url_to_cache_path(url)
    
    if cache_url in _CACHE:
        log_trace(f"Using cache for {url} ...")
        content = _CACHE[cache_url]
        if content.startswith("https://"):
            url = content.strip()
            return get_url(url)
        return url, content
    
    log_trace(f"Downloading {url} ...")
    page = requests.get(url, allow_redirects=True)
    newurl = page.url
    newurl = sanitizeUrl(newurl)
    if url != newurl:
        cache(url, newurl)
        return get_url(newurl)

    html = page.text
    _CACHE[cache_url] = html
    return newurl, html

def param_array_to_map(params):
    map = {}
    for param in params:   
        map[param['name']] = param
        if "params" in param:
           param["params"] = param_array_to_map(param["params"])
    return map

def remove_quotes(string):
    if string is None or len(string) == 0:
        return string
    if string[0] == '"' or string[0] == '“' or string[0] == "'":
        return string[1:-1]
    if string[0] == '[':
        return remove_quotes(string[1:-1])
    return string

def dump_stack(stack, before_or_after):
    message = f"{before_or_after} : stack : "
    for e in stack:
        if e['name'] is None:
            message += "{none} > "
        else:
            message += e['name']  + " > "
    log_trace(message)

def singularize(plural):
    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("s"):
        return plural[:-1]
    return plural

def cleanup_type(atype, subtype = None):
    if atype is None or atype == "-" or atype == "None" or atype == "NoneType" or atype == "":
        return "raw"
    if atype == "dict":
        return "dictionary"
    elif atype == "list":
        return f"list({singularize(cleanup_type(subtype))})"
    elif atype.startswith("list of "):
        subtype = atype[len('list of '):].strip()
        return cleanup_type("list", subtype)
    return atype


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
    log_fatal(f"unhandled type {type(value)}")
    exit(1)

def params_yo_yaml(parent, params, depth):
    yml = ""
    for key in params:
        param = params[key]
        if yml != "":
            yml += ", "
        yml += "{ "
        yml += f"name: \"{key}\""
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
            yml += f", params: {params_yo_yaml(parent+'.'+key, param['params'], depth+2).rstrip()}"
        yml += " }"
    return "[ " + yml + " ]"

def to_yaml(modules):
    flatten = True
    depth = 1
    if flatten:
        paramstart = " "
    else:
        paramstart = "\n"
    indent = ' ' * (2*depth)
    yml = "---\nmodules:\n"
    for key in modules:
        module = modules[key]
        if module is None:
            #log_warning(f"modules[{key}] is None !")
            continue
        yml += f"{indent}- name: {key}\n"
        if not "fqcn" in module or "deleted" in module and module['deleted']:
            yml += f"{indent}  deleted: true\n\n"
            continue
        yml += f"{indent}  fqcn: {module['fqcn']}\n"
        yml += f"{indent}  collection: {module['fqcn'][:module['fqcn'].rindex('.')]}\n"
        if "downloaded" in module and module['downloaded']:
            yml += f"{indent}  downloaded: true\n"
        if "breaking" in module and module['breaking']:
            yml += f"{indent}  breaking: true\n"
        if "breaking_params" in module and module['breaking_params']:
            yml += f"{indent}  breaking_params: true\n"
        if "breaking_return" in module and module['breaking_return']:
            yml += f"{indent}  breaking_return: true\n"
        if "breaking_facts" in module and module['breaking_facts']:
            yml += f"{indent}  breaking_facts: true\n"
        if "params_source" in module and len(module['params_source']) > 0:
            yml += f"{indent}  params_source:{paramstart}{params_yo_yaml(key+'.params_source', module['params_source'], depth+1).rstrip()}\n"
        if "return_source" in module and len(module['return_source']) > 0:
            yml += f"{indent}  return_source:{paramstart}{params_yo_yaml(key+'.return_source', module['return_source'], depth+1).rstrip()}\n"
        if "facts_source" in module and len(module['facts_source']) > 0:
            yml += f"{indent}  facts_source:{paramstart}{params_yo_yaml(key+'.facts_source', module['facts_source'], depth+1).rstrip()}\n"
        if "params_target" in module and len(module['params_target']) > 0:
            yml += f"{indent}  params_target:{paramstart}{params_yo_yaml(key+'.params_target', module['params_target'], depth+1).rstrip()}\n"
        if "return_target" in module and len(module['return_target']) > 0:
            yml += f"{indent}  return_target:{paramstart}{params_yo_yaml(key+'.return_target', module['return_target'], depth+1).rstrip()}\n"
        if "facts_target" in module and len(module['facts_target']) > 0:
            yml += f"{indent}  facts_target:{paramstart}{params_yo_yaml(key+'.facts_target', module['facts_target'], depth+1).rstrip()}\n"
        yml += "\n"

    return yml

def parse_old_doc(tr, stack, div_id):

    tds = tr.xpath("td")
    
    depth = 0
    while tds[depth].get('class') is not None and 'elbow-placeholder' in tds[depth].get('class'):
        depth = depth + 1
    td1 = tds[depth]
    td2 = tds[depth+1]

    while len(stack) > depth+1:
        stack.pop()

    parent = stack[-1]

    name = td1.xpath(".//b/text()")[0]
    type = td1.xpath(".//div/span/text()")[0]

    subtype = None
    if type == "list":
        subtype = td1.xpath(".//div/span[contains(@style,'purple')]/text()") 
        if len(subtype) > 2:
            subtype = subtype[1]
            subtype = subtype[subtype.index('=')+1:].strip()
        else:
            subtype = None
    try:
        type = cleanup_type(type, subtype)
    except AttributeError as e:
        log_fatal(f"    {' '*(2*depth)}{name} ({type} ({subtype}))")
        raise e
    if type == "list(dict)":
        type = "list(dictionary)"

    if div_id != 'parameters':
        param = {"name":name, "type":type, "params":[]}
    else:
        td3 = tds[depth+2]
        aliases = []
        if name != "aliases":
            aliases = td3.xpath(".//div[contains(text(),'aliases')]/text()")
            if len(aliases) > 0:
                aliases = list(map(lambda x: x.strip(), aliases[0][8:].split(',')))
            else:
                aliases = []
        required = len(td1.xpath(".//div/span[text()='required']")) > 0
        choices = []
        default = None
        if len(td2.xpath(".//b/text()")) > 0:
            choice_or_default = td2.xpath(".//b/text()")[0]
            if choice_or_default == 'Default:':
                default = remove_quotes(td2.xpath("div/text()")[0])
            elif choice_or_default == 'Choices:':
                for li in td2.xpath(".//ul/li"):
                    b = li.xpath(".//b/text()")
                    if len(b) > 0:
                        text = b[0]
                        default = text
                    elif len(li.xpath("./text()")) > 0:
                        text = li.xpath("./text()")[0]
                    else:
                        text = None
                    if text is not None:
                        choices.append(text)
            else:
                log_fatal(f"unhandled choice/default value '{choice_or_default}'")
                exit(1)

        choices.sort()
        param = { "name":name, "type":type,"required":required, "choices":choices, "default":default, "params":[], "aliases": aliases }

    return parent, param



def parse_new_doc(tr, stack, div_id):
    tds = tr.xpath("td")
    td1 = tds[0]
    td2 = tds[1]
    depth = len(td1.xpath("div[@class='ansible-option-indent']"))
    td1 = td1.xpath("div[@class='ansible-option-cell']")[0]

    while len(stack) > depth+1:
        stack.pop()

    parent = stack[-1]

    name = td1.xpath(".//p[@class='ansible-option-title']//strong/text()")[0]
    type = td1.xpath(".//span[@class='ansible-option-type']/text()")[0]

    subtype = None
    if type == "list":
        subtype = td1.xpath(".//span[@class='ansible-option-elements']/text()")
        if len(subtype) > 0:
            subtype = subtype[0]
            subtype = subtype[subtype.index('=')+1:].strip()
        else:
            subtype = None                    
    type = cleanup_type(type, subtype)

    if div_id != 'parameters':
        param = {"name":name, "type":type, "params":[]}
    else:
        required = len(td1.xpath(".//span[@class='ansible-option-required']/text()")) > 0
        aliases = td1.xpath(".//span[@class='ansible-option-aliases']/text()")
        if len(aliases) > 0:
            aliases = list(map(lambda x: x.strip(), aliases[0][8:].split(',')))
        else:
            aliases = []
        choices = []
        default = None
        if len(td2.xpath(".//span[@class='ansible-option-choices']")) > 0:
            for span in td2.xpath(".//span[@class='ansible-option-choices-entry']/text()"):
                choices.append(span)
            if len(td2.xpath(".//span[@class='ansible-option-default-bold']")) > 0:
                temp = remove_quotes(td2.xpath(".//span[@class='ansible-option-default-bold']/text()")[0])
                if temp != "Default:":
                    default = temp
                    choices.append(default)
        if len(td2.xpath(".//span[@class='ansible-option-default']")) > 0:
            temp = remove_quotes(td2.xpath(".//span[@class='ansible-option-default']/text()")[0])
            if temp != "← (default)":
                default = temp

        if len(choices) > 0 and default is not None:
            choices.append(default)

        choices = list(dict.fromkeys(choices))
        choices.sort()

        param = {"name":name, "type":type,"required":required, "choices":choices, "default":default, "params":[], "aliases": aliases }

    return parent, param

def get_module_parameters_or_return_values(tree, version, div_id='parameters'):
    div = tree.find(f".//div[@id='{div_id}']")
    if div is None:
        return {}
    table = div.find(".//table")
    if table is None:
        return {}
    if table.find("tbody") is None:
        trs = table.findall("tr")[1:]
    else:
        trs = table.findall("tbody/tr")

    params = []
    stack = [{"name":"/", "params":params},{"name":None}]
    for tr in trs:
        if version < "4":
            # up to version 3 (aka 2.10)
            parent, param = parse_old_doc(tr, stack, div_id)
        else:
            parent, param = parse_new_doc(tr, stack, div_id)
        
        parent["params"].append(param)
        stack.append(param)    

    params = param_array_to_map(params)

    return params



def check_params(parent, params_source, params_target, breaking_change = False, type = "parameter"):
    empty_array = []
    if parent is not None:
        parent = f"{parent}."
    else:
        parent = ""

    for k_source in params_source:
        param = params_source[k_source]

        if not k_source in params_target:
            log_debug(f"    {type} {parent}{k_source} has been removed in latest")
            params_source[k_source].update({"removed":True})
            breaking_change = True
            continue

        # ok we have the parameter in both versions
        latest = params_target[k_source]

        if param["type"] != "-" and param["type"] != latest["type"]:
            # the type of the parameter/return value as changed
            log_debug(f"    {type} {parent}{k_source} type changed from {param['type']} to {latest['type']}")
            breaking_change = True

        if type == "parameter":
            # the following don't apply to return values

            if param.get("required", False) and latest.get("required", False):
                # the parameter was not required in source version and is now required in target version
                log_debug(f"    {type} {parent}{k_source} is now required")            
                breaking_change = True

            if param.get("default") is not None and param.get("default") != latest.get("default"):
                # the parameter has a default value in source version that is different in target
                log_debug(f"    {type} {parent}{k_source} default changed from {param.get('default')} to {latest.get('default')}")
                breaking_change = True

            if len( param.get("choices", empty_array) ) == 0 and len(latest.get("choices", empty_array)) > 0 \
                or len(latest.get("choices", empty_array)) > 0 and not all(c in latest.get("choices", empty_array) for c in param.get("choices",empty_array)):
                # the parameter has a different set of available choices in source and target
                log_debug(f"    {type} {parent}{k_source} options changed from {param['choices']} to {latest['choices']}")
                breaking_change = True

        # check any sub parameters/return values
        breaking_change = breaking_change or check_params(f"{parent}{k_source}", param["params"], latest["params"], breaking_change, type)
    
    return breaking_change


def is_type_compatible_with(source, target) -> bool:

    if source == "complex" and options["complex_is_dictionary"]:
        source = "dictionary"

    if target == "complex" and options["complex_is_dictionary"]:
        target = "dictionary"

    if source == target:
        return True

    if target == "raw":
        return True

    if options["raw_to_any_ok"] and source == "raw":
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
        log_warning(f"Unhandled source type {source}")

    if tindex < 0:
        log_warning(f"Unhandled target type {target}")

    return sindex <= tindex

def check_module_params(parent, params_source, params_target, type = "parameter"):
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
            log_error(f"{parent}{k_source} type {param['type']} -> {latest['type']}")
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
        breaking_change = breaking_change or check_module_params(f"{parent}{k_source}", param.get("params",[]), latest.get("params",[]), type)
    
    return breaking_change

def get_module(key, cache_it = True):
    # global options
    if cache_it and key in modules:
        log_debug(f"module {key} is in cache")
        # it has been cached, let's return it
        modules[key].update({'used':True})
        return modules[key]
    

    log_info(f"  Retrieving doc for module {key} ...")
    url_source, html_source = get_url(f"https://docs.ansible.com/ansible/{options['source_version']}/modules/{key}_module.html")
    if "Oops!" in html_source:
        # does not exist in source version
        log_debug(f"can't find module {key} from {source_version()} online doc")

        # maybe we used a fully qualified module name ...
        urllatest, htmllatest = get_url(f"https://docs.ansible.com/ansible/{options['target_version']}/collections/{key.replace('.','/')}_module.html")
        if "Oops!" in htmllatest:
            # does not exist in target version either
            log_debug(f"can't find module {key} from {target_version()} online doc")
            return None
        else:
            log_debug(f"Found module {key} in {target_version()}")

        # let's try finding it in source version
        url_source, html_source = get_url(f"https://docs.ansible.com/ansible/{options['source_version']}/collections/{key.replace('.','/')}_module.html")
        if "Oops!" in html_source:
            # does not exist in source version at all
            log_warning(f"module {key} does not exist in {source_version()}")
            return None
        else:
            log_debug(f"Found module {key} in {source_version()}")

        key = url_source[url_source.rindex('/')+1:url_source.rindex('_module.html')]

    module = {"name": key, "downloaded": cache_it, "used": True}
    if cache_it:
        modules[key] = module

    tree_source = html.fromstring(html_source).xpath("//div[@class='wy-nav-content']")[0]
    params_source = get_module_parameters_or_return_values(tree_source, options['source_version'], "parameters")
    return_source = get_module_parameters_or_return_values(tree_source, options['source_version'], "return-values")
    facts_source = get_modu29le_parameters_or_return_values(tree_source, options['source_version'], "returned-facts")
    module.update({"params_source": params_source})
    module.update({"return_source": return_source})
    module.update({"facts_source": facts_source})

    urllatest = url_source.replace(options['source_version'], options['target_version'])
    
    while urllatest != "":
        urllatest, htmllatest = get_url(urllatest)
        treelatest = html.fromstring(htmllatest).xpath("//div[@class='wy-nav-content']")[0]

        removed = treelatest.xpath("//h1[contains(text(),'Oops!')]")
        if len(removed) > 0:
            log_warning(f"\n  *** Breaking change !\n module removed from ({target_version()}")
            module.update({"deleted": True,"breaking": True})
            return module

        redirect = treelatest.xpath("//li/p[starts-with(text(),'This is a redirect to the')]")
        if len(redirect) > 0:
            href = redirect[0].find(".//a").attrib['href']
            href = href[:href.index('#')]
            newurl = sanitizeUrl(urllatest[:urllatest.rindex('/')+1] + href)
            urllatest = newurl
        else:
            urllatest = ""

    if len(treelatest.xpath("//div[@id='parameters']")) == 0 and \
       len(treelatest.xpath("//div[@id='return-values']")) == 0 and \
       len(treelatest.xpath("//div[@id='returned-facts']")) == 0:
       module.update({"deleted": True,"breaking": True})
       return module

    h1 = treelatest.xpath("//h1/text()")[0]
    id = h1[:h1.index(" ")]
    collection = id[:id.rindex('.')]

    module.update({"fqcn": id, "collection": collection})
    params_target = get_module_parameters_or_return_values(treelatest, options['target_version'], "parameters")
    return_target = get_module_parameters_or_return_values(treelatest, options['target_version'], "return-values")
    facts_target = get_module_parameters_or_return_values(treelatest, options['target_version'], "returned-facts")
    module.update({"params_target" : params_target})
    module.update({"return_target" : return_target})
    module.update({"facts_target" : facts_target})

    if cache_it:
        if "params_source" in module:
            param_aliases = {}
            for param_name in module["params_source"]:
                for alias in module["params_source"][param_name].get("aliases", []):
                    param_aliases.update({alias : module["params_source"][param_name]})
            module["params_source"].update(param_aliases)
        if "params_target" in module:
            param_aliases = {}
            for param_name in module["params_target"]:
                for alias in module["params_target"][param_name].get("aliases", []):
                    param_aliases.update({alias : module["params_target"][param_name]})
            module["params_target"].update(param_aliases)
        if "fqcn" in module and module["fqcn"] not in modules:
            modules.update({module["fqcn"]:module})
    
    param_breaking_change = check_module_params(None, module.get("params_source", {}), module.get("params_target", {}), "parameter")

    return_breaking_change = check_module_params(None, module.get("return_source", {}), module.get("return_target", {}), "return value")

    facts_breaking_change = check_module_params(None, module.get("facts_source", {}), module.get("facts_target", {}), "fact")

    module.update({"breaking": param_breaking_change or return_breaking_change or facts_breaking_change})
    module.update({"breaking_params": param_breaking_change})
    module.update({"breaking_return": return_breaking_change})
    module.update({"breaking_facts": facts_breaking_change})            

    if cache_it:
        modules[id] = module

    return module

def fix_tilde_in_path(path):
    if len(path) > 0 and path[0] == '~':
        return f"/home/{os.environ['USER']}{path[1:]}"
    return path

def save_cache(cache, filename):
    for module in cache:
        if "used" in module:
            del module["used"]
    with open(f"{fix_tilde_in_path(filename)}.cache.yml", "wt") as file:
        file.write(to_yaml(cache))
    
def load_cache(filename):
    with open(fix_tilde_in_path(filename), "rt") as file:
        try:
            tmp = yaml.load(file, yaml.CLoader)
            if isinstance(tmp, dict) and len(tmp) > 0 and "modules" in tmp and tmp["modules"] is not None:
                log_debug("Converting to dict ...")
                return array_to_dict(tmp["modules"], "name", 0, ("params", "params_source", "params_target", "return_source", "return_target", "facts_source", "facts_target"))
            else:
                log_warning("Ignoring empty cache file ...")
                return {}
        except Exception as e:
            raise e

def load_cache_file(path, modules) -> dict:
    log_info(f"Loading cache from {path} ...")
    temp = load_cache(path)
    modules.update(temp)

def load_cache_dir(path, modules) -> dict:
    log_info(f"Scanning for cache in {path} ...")

    for f in os.listdir(fix_tilde_in_path(path)):
        if f == '.' or f == '..':
            continue
        if f.startswith('.') and not options["process_hidden_files"]:
            continue
        fp = f"{path}/{f}"
        if os.path.isdir(fp):
            # load_cache_dir(fp, modules)
            pass
        elif os.path.isfile(fp) and CACHE_FILE_PATTERN.fullmatch(f):
            load_cache_file(fp, modules)


def load_caches(pathes) -> dict:
    modules = {}
    for path in pathes:
        path = fix_tilde_in_path(path)
        if os.path.isdir(path):
            load_cache_dir(path, modules)
        elif os.path.isfile(path):
            load_cache_file(path, modules)
        else:
            log_warning(f"IGNORING {path} has it is not a dir nor a file")
                
    if len(modules) > 0:
        log_info(f"{len(modules)} modules loaded from cache")

        log_debug(f"Optimizing modules with current options ...")
        aliases = []
        for module_name in modules:
            module = modules[module_name]
            if module is None:
#                log_warning(f"module {module_name} is None")
                continue
            if "params_source" in module:
                param_aliases = {}
                for param_name in module["params_source"]:
                    for alias in module["params_source"][param_name].get("aliases", []):
                        param_aliases.update({alias : module["params_source"][param_name]})
                module["params_source"].update(param_aliases)
            if "params_target" in module:
                param_aliases = {}
                for param_name in module["params_target"]:
                    for alias in module["params_target"][param_name].get("aliases", []):
                        param_aliases.update({alias : module["params_target"][param_name]})
                module["params_target"].update(param_aliases)                
            if "fqcn" in module and module["fqcn"] not in modules:
                aliases.append({module["fqcn"]:module})

                        
            param_breaking_change = check_module_params(None, module.get("params_source", {}), module.get("params_target", {}), "parameter")

            return_breaking_change = check_module_params(None, module.get("return_source", {}), module.get("return_target", {}), "return value")

            facts_breaking_change = check_module_params(None, module.get("facts_source", {}), module.get("facts_target", {}), "fact")

            module.update({"breaking": param_breaking_change or return_breaking_change or facts_breaking_change})
            module.update({"breaking_params": param_breaking_change})
            module.update({"breaking_return": return_breaking_change})
            module.update({"breaking_facts": facts_breaking_change})            

        for alias in aliases:
            modules.update(alias)

    return modules


def cache_collection(collection):
    url, html_source = get_url(f"https://docs.ansible.com/ansible/latest/collections/{collection.replace('.','/')}/index.html")
    if "Oops!" in html_source:
        # does not exist in source version
        log_error(f"can't find collection {collection} from {target_version()} online doc")    
        return

    tree_source = html.fromstring(html_source).xpath("//div[@class='wy-nav-content']")[0]
    lis = tree_source.xpath(".//div[@id='modules']/ul/li")
    if len(lis) == 0:
        log_info(f"collection {collection} has no modules")
        return

    log_info(f"Downloading modules for collection {collection} ...")
    count = 0
    modules = {}
    for li in lis:
        module_name = li.xpath("./p/a/span/text()")[0]
        module_name = module_name[:module_name.rindex(' ')]
        count += 1
        log_info(f"Dowloading module {count}/{len(lis)} : {module_name} ...")
        module = get_module(f"{collection}.{module_name}", False)
        if module is not None:
            modules.update({module_name: module})

    log_info(f"Saving cache for collection {collection} ...")

    save_cache(modules, f"{options['cache_path'][0]}/{collection}")


def change_key(self, old, new):
    for _ in range(len(self)):
        k, v = self.popitem(False)
        self[new if old == k else k] = v

def rename_dict_key(dict : OrderedDict, old, new) -> OrderedDict:
    mytype = type(dict) 
    newdic = mytype()
    for key in dict:
        if key == old:
            newdic[new] = dict[old]
        else:
            newdic[key] = dict[key]
    return newdic

def array_to_dict(array, key, depth, subkeys):
    indent = ' ' * (3*depth)
    dict = {}
    for elem in array:
        dict[elem[key]] = elem
        #del elem[key]
        for subkey in subkeys:
            if subkey in elem:
                elem[subkey] = array_to_dict(elem[subkey], key, depth+1, subkeys)
    return dict

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





class Log:
    time = now()
    file = ""
    uuid = None
    line = 0
    level = None
    message = ""
    def __init__(self, file, uuid, level, message) -> None:
        self.file = file
        self.uuid = uuid
        self.level = level
        self.message = message
        pass

class DebugLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "DEBUG", message)    

class InfoLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "INFO ", message)    

class WarnLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "WARN ", message)    

class ErrorLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "ERROR", message)    

def yaml_add_comment(yml, key, level, message):
    global options
    if options["no_logs_in_files"]:
        return
    if key is None:
        yml.yaml_set_start_comment(f"{COMMENT_PREFIX} {level} : {message}")
    else:
        yml.yaml_set_comment_before_after_key(key, f"{COMMENT_PREFIX} {level} : {message}")

def log_and_comment_info(yml, key, logs, path, uuid, message):
    logs.append(InfoLog(path, uuid, message.split('\n')[0]))
    yaml_add_comment(yml, key, "INFO", message)

def log_and_comment_warning(yml, key, logs, path, uuid, message):
    logs.append(WarnLog(path, uuid, message.split('\n')[0]))
    yaml_add_comment(yml, key, "WARNING", message)

def log_and_comment_error(yml, key, logs, path, uuid, message):
    logs.append(ErrorLog(path, uuid, message.split('\n')[0]))
    yaml_add_comment(yml, key, "ERROR", message)


def analyse_parameters(path, uuid, module, parent, key, params_source, params_target, logs, depth):
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
                log_trace(f"{p} -> {p_source}")
                if not "name" in p_source:
                    log_fatal(f"attribute `name` is not present in parameter `{p_source}`")
                    raise AttributeError
                aliases.update({p : f"{p_source['name']}"})

        for alias in aliases:
            # rename it to real name
            realname = aliases[alias]
            change_key(module, alias, realname)
            log_and_comment_info(module, realname, logs, path, uuid, f"alias parameter `{alias}` renamed to `{realname}`")

 
        for p in module:
            if p == '_':
                continue
            
            try:
                line = module[p].lc.line
            except:
                pass

            log_trace(f"{' '*(depth*2)}{p}")

            if p not in params_source:
                if not p in params_target:
                    log_and_comment_warning(module, p, logs, path, uuid, f"Unknown parameter `{p}`")
                continue

            # our parameter must exist in latest version
            if p not in params_target:
                log_and_comment_error(module, p, logs, path, uuid, f"unknown module parameter `{p}` in {target_version()}")
                continue

            # now that we have checked the parameter let's take care of it's value 
            v = module[p]

            if isinstance(v, str) and "{{" in v:
                # handle case where parameter is a variable expression
                if "choices" in params_source[p] and "choices" in params_target[p] and not all(c in params_target[p]["choices"] for c in params_source[p]['choices']):
                    # some choices available in 2.9 are not available in latest
                    log_and_comment_warning(module, p, logs, path, uuid, f"Some possible values for parameter `{p}` have been removed in {target_version()}. Allowed values are : [`{'`, `'.join(params_target[p]['choices'])}`]")
                elif "choices" not in params_source[p] and "choices" in params_target[p]:
                    # 2.9 was open bar and is not a closed list in latest
                    log_and_comment_warning(module, p, logs, path, uuid, f"Possible values for parameter `{p}` have been restricted to a closed list of choices in {target_version()} : [`{'`, `'.join(params_target[p]['choices'])}`]")
                elif not is_type_compatible_with(params_source[p]["type"], params_target[p]["type"]):
                    log_and_comment_warning(module, p, logs, path, uuid, f"type of parameter `{p}` changed from `{params_source[p]['type']}` in {source_version()} to `{params_target[p]['type']}` in {target_version()}")
                else:
                    # looks ok
                    pass
            elif "params" in params_source[p] and len(params_source[p]["params"]) > 0:
                # nested parameters
                analyse_parameters(path, uuid, params_source[p], module, p, params_source[p]["params"], params_target[p].get("params",{}), logs, depth+1)
            elif "choices" in params_target[p]:
                handled = False
                # if parameter as a list of choice, then our value must be in it
                if v in params_target[p]["choices"]:
                    # we're fine
                    handled = True
                else:
                    # our value was a (probably) valid choice in 2.9 but not in latest
                    if params_target[p]["type"] == "boolean":
                        # gently migrate true/false to yes/no when possible
                        if (v == True or v == 'True' or v == 'true') and "yes" in params_target[p]["choices"]:
                            # 'true' became 'yes'
                            if migrate_booleans:
                                log_and_comment_info(module, p, logs, path, uuid, f"replaced value `true` for parameter `{p}` by `yes`")
                                module[p] = 'yes'
                            handled = True
                        elif (v == False or v == 'False' or v == 'false') and "no" in params_target[p]["choices"]:
                            # 'false' became 'no'
                            if migrate_booleans:
                                log_and_comment_info(module, p, logs, path, uuid, f"replaced value `false` for parameter `{p}` by `no`")
                                module[p] = 'no'
                            handled = True

                if not handled:
                    log_and_comment_error(module, p, logs, path, uuid, f"value `{v}` for parameter `{p}` is not valid in {target_version()}. Allowed values are : [`{'`, `'.join(params_target[p]['choices'])}`]")

            if not is_type_compatible_with(params_source[p]["type"], params_target[p]["type"]):
                log_and_comment_warning(module, p, logs, path, uuid, f"type of parameter `{p}` changed from `{params_source[p]['type']}` in {source_version()} to `{params_target[p]['type']}` in {target_version()}")


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
                log_and_comment_error(parent, key, logs, path, uuid, f"missing parameter `{p}` is required in {target_version()}")
            elif p_source is not None and p_source.get("default", None) != pl.get("default", None):
                # we've got a parameter that is not specified with a default value that has changed
                log_and_comment_warning(parent, key, logs, path, uuid, f"default value for missing parameter `{p}` changed from `{p_source.get('default', None)}` in version 2.9 to `{pl.get('default', None)}` in {target_version()} ")


def migrate_task(path, task, logs = [], depth=1):

    uuid = uuid4()
    task.yaml_set_start_comment(f"{UUID_COMMENT_PREFIX}{str(uuid)}")

    for attr in task:
        skip = False
        for filter in TASK_GENERIC_ATTRIBUTES:
            skip = skip or filter.fullmatch(attr)
        if skip:
            continue
        log_debug(f"{' '*(depth*2)}{attr}")
        if attr in ("block", "rescue", "always"):
            if task[attr] is None:
                log_and_comment_info(task, attr, logs, path, uuid, f"empty `{attr}`")
            else:
                migrate_play(path, task[attr], logs, depth+1)
            continue
        if attr == "action":
            if not isinstance(task[attr], str) or "{{" in task[attr]:
                log_warning(f"unable to handle action that is not a literal")
                log_and_comment_warning(task, attr, logs, path, uuid, f"unable to handle action that is not a literal")
                return
            attr = task[attr]
        
        module = get_module(attr)
        if module is None:
            log_warning(f"unknown module `{attr}`")
            log_and_comment_error(task, attr, logs, path, uuid, f"unknown module `{attr}`")
            break

        if "removed" in module and module["removed"] or "fqcn" not in module:
            log_and_comment_error(task, attr, logs, path, uuid, f"module `{attr}` does not exist in {target_version()}")
            break

        if task[attr] is None:
            task[attr] = ruamel.yaml.comments.CommentedMap()
            task[attr].insert(0, '_', '')
            task[attr].yaml_add_eol_comment(f"# REMOVE ME {uuid_mig}", '_', column=0)
            
        # our module exists in 2.9 and latest
        if attr != module['fqcn']:
            # module name does not match latest name
            # let's rename it
            logs.append(InfoLog(path, uuid, f"module {attr} renamed to {module['fqcn']}"))
            change_key(task, attr, module['fqcn'])
            attr = module['fqcn']

        if isinstance(task[attr], str):
            # free form parameters
            if "param_target" in module and "free-form" not in module["param_target"]:
                # latest version does not support free-form
                log_and_comment_error(task, attr, logs, path, uuid, f"module {attr} does not support free-form parameters in {target_version()}") #\nPlease check documentation for latest version of module `{attr}`\nhttps://docs.ansible.com/ansible/latest/collections/{ module['fqcn'].replace('.','/') }_module.html")
            else:
                # don't handle free-form
                log_and_comment_warning(task, attr, logs, path, uuid, f"Cannot perform migration checks on free-form parameters")
                if module.get("breaking_params"):
                    log_and_comment_warning(task, attr, logs, path, uuid, f"There are some breaking changes in the parameters from version 2.9 to {target_version()}") #.\nPlease check documentation for latest version of module `{attr}`\nhttps://docs.ansible.com/ansible/latest/collections/{ module['fqcn'].replace('.','/') }_module.html")

        elif module.get("params_source", {}) is not None or module.get("params_target", {}) is not None:
            analyse_parameters(path, uuid, task[attr], task, attr, module.get("params_source", {}), module.get("params_target", {}), logs, depth+1)

        if "register" in task:
            if module.get('breaking_return', False):
                log_and_comment_warning(task, "register", logs, path, uuid, f"There is a breaking change in the returned values") #\nPlease check documentation for {target_version()} of module `{attr}`\nhttps://docs.ansible.com/ansible/latest/collections/{ module['fqcn'].replace('.','/') }_module.html")

        if module.get("breaking_facts"):
            log_and_comment_warning(task, None, logs, path, uuid, f"There is a breaking change in the facts returned.\nPlease check documentation for {target_version()} of module `{attr}`\nhttps://docs.ansible.com/ansible/latest/collections/{ module['fqcn'].replace('.','/') }_module.html")

        break


def is_generic_task_attribute(attribute) -> bool:
    for r in TASK_GENERIC_ATTRIBUTES:
        if r.fullmatch(attribute):
            return True
    return False

def is_known_module_name(attribute) -> bool:
    return attribute in modules


def is_ansible_playbook(path, yml, logs) -> bool:
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

def is_ansible_play(path, yml, logs) -> bool:
    if yml is None:
        return False

    # does it look like a list of tasks ?
    nb_unknown_attributes = 0
    nb_attributes = 0
    for node in yml:
        for attribute in node:
            nb_attributes += 1
            nb_unknown_attributes += 1
            if is_generic_task_attribute(attribute):
                nb_unknown_attributes -= 1
                break
            elif is_known_module_name(attribute):
                nb_unknown_attributes -= 1
                break

    if nb_attributes == 0:
        # empty file ?
        return False
    
    return (nb_attributes - nb_unknown_attributes) / nb_attributes > 0.95


def is_ansible_yaml(path, yml, logs) -> bool:
    if yml is None:
        return False
    
    # Does it look like a play ?
    if is_ansible_playbook(path, yml, logs):
        return True

    elif is_ansible_play(path, yml, logs):
        return True

    return False

def migrate_play(path, yml, logs, depth=1):
    for task in yml:
        migrate_task(path, task, logs, depth)
    
def migrate_ansible_yaml(path, yml, logs, depth=1):
    if yml is None:
        logs.append(InfoLog(path, None, "No nodes in YAML file"))
        return False
    elif is_ansible_playbook(path, yml, logs):
        logs.append(InfoLog(path, None, "Migrating as playbook file"))
        for node in yml:
            for task_keyword in PLAYBOOK_TASK_KEYWORDS:
                if task_keyword == 'roles':
                    continue
                if task_keyword in node:
                    log_debug(f"{' '*(depth*2)}{task_keyword}")
                    migrate_play(path, node[task_keyword], logs, depth+1)
    elif is_ansible_play(path, yml, logs):
        logs.append(InfoLog(path, None, "Migrating as play file"))
        migrate_play(path, yml, logs)


def migrate_yaml(path, yml,logs):
    """
    Migrate a YAML object
    """

    if not is_ansible_yaml(path, yml, logs):
        logs.append(InfoLog(path, None, "doesn't look like an ansible play or playbook: skipping"))
        return None
    
    migrate_ansible_yaml(path, yml, logs)

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
            uuid_to_line.update({uuid: lineNo})
        else:
            lineNo += 1
            output.write(line)

    output.seek(0)
    return new_ruamel_yaml().load(output)

def migrate_raw(data, logs = [], path = "in-memory-data"):


    log_debug(f"Processing {path} ...")

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
        log_warning(f"Skipping {path} : doesn't look like a valid yml")
        logs.append(WarnLog(path, None,"doesn't look like a valid yml: skipping"))
        return logs, None
    
    log_info(f"Migrating {path} ...")

    yml = migrate_yaml(path, yml, logs)

    log_debug(f"Serializing migrated YAML ...")
    
    stream.seek(0)
    new_ruamel_yaml().dump(yml, stream)

    # remove our blank line preservers
    stream.seek(0)
    remove_me = f"# REMOVE ME {uuid_mig}"
    result = ""
    for line in stream.readlines():
        if remove_me in line:
            continue
        result += line.replace(blank_line_preserver, "")

    return logs, result

def migrate_file(path, logs = []):
    log_debug(f"Reading {path} ...")

    #path = path[:path.rindex('/')]
    source = ""
    try:
        with open(path, "rt") as file:
            source = file.read()
    except Exception as e:
        logs.append(WarnLog(path, None,f"Failed to load file : {e}"))
        return logs

    logs, result = migrate_raw(source, logs, path)

    if result is not None:
        # if we did migrate the file
        outfilename = path if options["overwrite_source"] else (path[:path.rindex('.')]+".migrated."+path[path.rindex('.')+1:])
        log_debug(f"Writing to {outfilename}")
        with open(fix_tilde_in_path(outfilename), "wt") as outfile:
            outfile.write(result)
        return logs

def migrate_dir(path, logs = []):
    log_info(f"Scanning {path} ...")
    for f in os.listdir(fix_tilde_in_path(path)):
        if f == '.' or f == '..' or f == '.git' or MIGRATED_FILE_PATTERN.fullmatch(f) or CACHE_FILE_PATTERN.fullmatch(f):
            continue
        if f.startswith('.') and not options["process_hidden_files"]:
            continue
        fp = f"{fix_tilde_in_path(path)}/{f}"
        if os.path.isdir(fp):
            migrate_dir(fp, logs)
        elif os.path.isfile(fp) and ANSIBLE_FILE_PATTERN.fullmatch(f):
            migrate_file(fp, logs)

    return logs
 

def execute(exec_options={}):

    global options, log_verbosity, modules, migrate_booleans, uuid_to_line, yml, START_TIME
    
    START_TIME = now()

    logs = []

    options.update(DEFAULT_OPTIONS)
    options.update(exec_options)

    options["source_version"] = str(options["source_version"])
    options["target_version"] = str(options["target_version"])

    log_verbosity += int(str(options["verbosity"])) - int(str(options["quietness"]))

    if options["path"] is None and options["source"] is None:
        log_error("Either path or source must be specified")
        exit(1)

    if options["path"] is not None and options["source"] is not None:
        log_error("path and source are mutually exclusive")
        exit(1)

    if len(options["generate_cache_for_collection"]) > 0:
        for collection in options["generate_cache_for_collection"]:
            cache_collection(collection)

        return logs, None


    modules = load_caches([*options["cache_path"],"downloaded-modules.cache.yml"])

    migrate_booleans = False

    uuid_to_line = {}
    
    if options["path"] is not None:
        if os.path.isdir(options["path"]):
            logs = migrate_dir(options["path"], logs)
        else:
            logs = migrate_file(options["path"], logs)
    else:
        logs, result = migrate_raw(options["source"], logs)

    if options["show_logs"]:
        prevfile = ""
        for log in logs:
            if log.file != prevfile:
                print(log.file)
                prevfile = log.file
            line = uuid_to_line.get(str(log.uuid), -1)
            print(f"{(' ' + str(line) if line > 0 else '-----').rjust(5)} {log.level} : {log.message}")

    if options["log_path"] is not None:
        log_path = options["log_path"]
        if os.path.isdir(log_path):
            log_path = f"{log_path}/migration.log"
        log_info(f"Saving migration logs to {log_path} ...")
        prevfile = ""
        with open(fix_tilde_in_path(log_path), "wt") as file:
            for log in logs:
                if log.file != prevfile:
                    file.write(f"{log.file}\n")
                    prevfile = log.file
                line = uuid_to_line.get(str(log.uuid), -1)
                file.write(f"{(' ' + str(line) if line > 0 else '-----').rjust(5)} {log.level} : {log.message}\n")

    # list collections used by playbooks migrated in this run
    used_collections = []
    for key in modules:
        module = modules[key]
        if module is None or "used" not in module or not module["used"]:
            # log_warning(f"Weird : module {key} is None")
            continue
        if "collection" in module and module["collection"] not in used_collections:
            used_collections.append(module["collection"])
    used_collections.sort()
    log_info(f"Used collections: {used_collections}")
    logs.append(InfoLog(None,None, f"Used collections: {used_collections}"))


    if options["cache_downloaded_modules"]:
        # cache downloaded modules
        log_debug("Cleaning cache ...")
        to_remove = []
        for key in modules:
            module = modules[key]
            if module is None:
                continue
            if key == module["fqcn"] or not module.get("downloaded", False):
                to_remove.append(key)
                continue
            remove_param_aliases(module, "params_source")
            remove_param_aliases(module, "teturn_source")
            remove_param_aliases(module, "facts_source")
            remove_param_aliases(module, "params_target")
            remove_param_aliases(module, "teturn_target")
            remove_param_aliases(module, "facts_target")
        for key in to_remove:
            del modules[key]

        log_info("Saving cache ...")
        save_cache(modules, "downloaded-modules")

    log_info("Migration complete")

    if options["source"] is not None:
        return logs, result
    else:
        return logs, None

def main():
    for f in inspect.stack():
        if "behave/runner_util" in f.filename:
            return

    parser = argparse.ArgumentParser(description=f"Migrate ansible 2.9 scripts to ansible {LATEST_VER}")
    parser.add_argument("path", metavar='PATH', default=".", help="Path to migrate")
    parser.add_argument("-O", "--overwrite-source", dest="overwrite_source", action="store_true", default=False, help="Overwrite source file without backup")
    parser.add_argument("-L", "--store-logs", dest="log_path", default=None, help="Output logs into specified file")
    parser.add_argument("-l", "--logs", dest="show_logs",  action="store_true", default=False, help="Show logs after execution")
    parser.add_argument("-N", "--no-logs-in-files", dest="no_logs_in_files",  action="store_true", default=False, help="Prevents from inserting logs in migrated files")
    parser.add_argument("-H", "--hidden-files", dest="process_hidden_files", action="store_true", default=False, help="Process hidden files")
    parser.add_argument("-v", "--verbose", dest="verbosity", action="count", default=0, help="increase output verbosity. Can be specified more than once to increase verbosity even more")
    parser.add_argument("-q", "--quiet", dest="quietness", action="count", default=0, help="decrease output verbosity. Can be specified more than once to decrease verbosity even more")
#    parser.add_argument("-s", "--source-version", dest="source_version", metavar="VERSION", default="2.9", help="source version (default to 2.9)")
#    parser.add_argument("-t", "--target-version", dest="target_version", metavar="VERSION", default="latest", help="target version (default to latest)")
    parser.add_argument("-c", "--cache-downloaded-modules", dest="cache_downloaded_modules", action="store_true", default=False, help="Generate a cache of downloaded modules in current directory")
    parser.add_argument("-C", "--cache-path", dest="cache_path", metavar="PATH", default=[], action="append", help="Where to look for and store collections cache files (default [./cache]). Can be specified more than once to load from multiple pathes")
    parser.add_argument("-G", "--generate-cache-for-collection", dest="generate_cache_for_collection", default=[], action="append", metavar="COLLECTION", help="Generate a cache for specified collection. Can be specified more than once to generate cache for multiple collections")
    args = parser.parse_args()
        
    if len(args.path) > 0 and args.path[-1] == '/':
        args.path = args.path[:-1]
    if len(args.cache_path) == 0:
        args.cache_path = ['./cache']
    if "ANSIBLE_MIGRATOR_CACHE_PATH" in os.environ:
        ANSIBLE_MIGRATOR_CACHE_PATH = os.environ["ANSIBLE_MIGRATOR_CACHE_PATH"]
        env_cache_path = list(map(lambda x: x.strip(), ANSIBLE_MIGRATOR_CACHE_PATH.split(":")))
        args.cache_path = env_cache_path + args.cache_path
    
    execute({
        "path": args.path,
        "overwrite_source": args.overwrite_source,
        "log_path": args.log_path,
        "show_logs": args.show_logs,
        "process_hidden_files": args.process_hidden_files,
        "verbosity": args.verbosity,
        "quietness": args.quietness,
#        "source_version": args.source_version,
#        "target_version": args.target_version,
        "cache_downloaded_modules": args.cache_downloaded_modules,
        "cache_path": args.cache_path,
        "generate_cache_for_collection": args.generate_cache_for_collection,
        "no_logs_in_files": args.no_logs_in_files,
    })

if __name__ == '__main__':
    main()