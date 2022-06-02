from lxml import html
import requests

from constants import *
from logger import Logger

logger = Logger("Scrapper")

class Scrapper:

    _cache = {}

    def get_module_version_data(self, key, version):

        logger.info(f"Retrieving doc for module `{key}` in version {version} ...")

        if "." in key:
            # we have a FQCN
            url = URL_ANSIBLE_COLLECTION.format(version=version, id=key.replace('.','/'))
        else:
            url = URL_ANSIBLE_MODULE.format(version=version, id=key)

        while True:
            url, content = self.get_url(url)
            tree = html.fromstring(content).xpath("//div[@class='wy-nav-content']")[0]

            removed = tree.xpath(f"//h1[contains(text(),'{HTML_OOPS}!')]")
            if len(removed) > 0:
                # we hit a Oops page : the module does not exist in specified version
                logger.warning(f"Module {key} does not exist in version {version}")
                return {"missing": True}

            redirect = tree.xpath("//li/p[starts-with(text(),'This is a redirect to the')]")
            if len(redirect) > 0:
                # we hit a redirection page, let's follow it
                href = redirect[0].find(".//a").attrib['href']
                href = href[:href.index('#')]
                url = sanitizeUrl(url[:url.rindex('/')+1] + href)
            else:
                break

        if HTML_OOPS in content:
            # module does not exist in such version
            logger.warning(f"Module `{key}` does not exist in version {version}")
            return None
    
        # parse the (interesting) content of the page we retrieved
        tree = html.fromstring(content).xpath("//div[@class='wy-nav-content']")[0]
        h1 = tree.xpath("//h1/text()")[0]
        name = h1[:h1.index(" ")]
        params = get_module_parameters_or_return_values(tree, version, "parameters")
        retrn = get_module_parameters_or_return_values(tree, version, "return-values")
        facts = get_module_parameters_or_return_values(tree, version, "returned-facts")

        return {"name": name, "params": params, "return": retrn, "facts": facts, "url": url}

    def uncache(self, url):
        if url in self._cache:
            del self._cache[url]

    def cache(self, url, content):
        self._cache[url] = content



    def get_collection_module_names(self, collection: str, version: str) -> list:
        """
        retrieves names of the modules in a specified collection
        """
        
        _, html_source = self.get_url(URL_ANSIBLE_COLLECTION_INDEX.format(version=version, id=collection.replace('.','/')))
        
        if HTML_OOPS in html_source:
            # does not exist in source version
            logger.error(f"can't find collection {collection} from {version} online doc")
            return

        logger.fine(f"Retrieving modules names for collection {collection} ...")

        tree_source = html.fromstring(html_source).xpath("//div[@class='wy-nav-content']")[0]
        lis = tree_source.xpath(".//div[@id='modules']/ul/li")

        module_names = []

        for li in lis:
            module_name = li.xpath("./p/a/span/text()")[0]
            module_name = module_name[:module_name.rindex(' ')]
            module_names.append(module_name)

        return module_names



    def get_url(self, url):
        """
        retrieve the content of a URL

        if the URL is in cache, it uses the content in cache

        otherwise it will download thea actual content from the URL

        returns the actual URL matching the content (ie we might have followed some redirects) AND its content

        `url, content = cache.get_url(some_url)`

        """

        url = sanitizeUrl(url)
        
        if url in self._cache:
            logger.debug(f"Using cache for {url} ...")
            content = self._cache[url]
            if content.startswith("https://"):
                url = content.strip()
                return self.get_url(url)
            return url, content
        
        logger.fine(f"Downloading {url} ...")
        page = requests.get(url, allow_redirects=True)
        newurl = page.url
        newurl = sanitizeUrl(newurl)
        if url != newurl:
            self.cache(url, newurl)
            return self.get_url(newurl)

        html = page.text
        self.cache(url, html)
        return newurl, html



def is_missing_module_page(html):
    return HTML_OOPS in html


def get_module_parameters_or_return_values(tree, version, div_id='parameters'):
    """
    retrieves parameters, return values or facts in a module's documentation according to the version of the doc
    """
    
    div = tree.find(f".//div[@id='{div_id}']")
    if div is None:
        return []
    table = div.find(".//table")
    if table is None:
        return []
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

    return params


def parse_old_doc(tr, stack, div_id):
    """
    parse a module's documentation in version 2.x to 3.x
    """

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
        logger.fatal(f"    {' '*(2*depth)}{name} ({type} ({subtype}))")
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
                logger.fatal(f"unhandled choice/default value '{choice_or_default}'")
                exit(1)

        param = { "name" : name, "type" : type, "params" : [] }

        if required:
            param.update({ "required" : True })
        if default is not None and default != "None" and default != "":
            param.update({ "default" : default })
        if len(choices) > 0:
            param.update({ "choices" : choices })
        if len(aliases) > 0:
            param.update({ "aliases" : aliases })

    return parent, param



def parse_new_doc(tr, stack, div_id):
    """
    parse a module's documentation in version 4.x onward
    """

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

        param = { "name" : name, "type" : type, "params" : [] }
        if required:
            param.update({ "required" : True })
        if default is not None and default != "None" and default != "":
            param.update({ "default" : default })
        if len(choices) > 0:
            param.update({ "choices" : choices })
        if len(aliases) > 0:
            param.update({ "aliases" : aliases })

    return parent, param

def remove_quotes(string: str) -> str:
    """
    remove quotes around literal or in a list of literals

    "foo" -> foo
    ["spam",'eggs',“rabbit“] -> [spam, eggs, rabbit]
    """

    if string is None or len(string) == 0:
        return string
    if string[0] == '"' or string[0] == '“' or string[0] == "'":
        return string[1:-1]
    if string[0] == '[':
        return remove_quotes(string[1:-1])
    return string



def singularize(plural: str) -> str:
    """
    return singular of a plural
    used to turn `list of strings` in `list(string)`
    """

    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("s"):
        return plural[:-1]
    return plural

def cleanup_type(atype: str, subtype: str = None) -> str:
    """
    Cleans up type that was provided by ansible doc
        `-`, `None` or blank -> `raw`
        `dict` -> `dictionary`
        `list(things)` -> `list(thing)`
        `list of things` -> `list(thing)`
    """

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


def sanitizeUrl(url: str) -> str:
    """
    sanitize URL by removing .. and double //
    """

    parts = url.split('/')
    stack = []
    for part in parts:
        if part == "..":
            stack.pop()
        else:
            stack.append(part)
    return '/'.join(stack)


