#!/usr/bin/env python3

import os
import re
import argparse
import inspect

from constants import *
from cache import Cache
from logger import *
from migrator import Migrator
from utils import *

logger = Logger("Main")


def main():
    """
    The entry point for CLI
    """

    # if main is called by behave then exit quietly
    # we want to call `execute` method when testing with behave

    for f in inspect.stack():
        if "behave/runner_util" in f.filename:
            return

    parser = argparse.ArgumentParser(description=f"Migrate ansible scripts from one version to another")
    parser.add_argument("path", metavar='PATH', default=None, nargs='?', help="Path to migrate")
    parser.add_argument("-O", "--overwrite-source", dest="overwrite_source", action="store_true", default=False, help="Overwrite source file without backup")
    parser.add_argument("-L", "--store-logs", dest="log_path", default=None, help="Output logs into specified file")
    parser.add_argument("-l", "--logs", dest="show_logs",  action="store_true", default=False, help="Show logs after execution")
    parser.add_argument("-N", "--no-logs-in-files", dest="no_logs_in_files",  action="store_true", default=False, help="Prevents from inserting logs in migrated files")
    parser.add_argument("-H", "--hidden-files", dest="process_hidden_files", action="store_true", default=False, help="Process hidden files")
    parser.add_argument("-v", "--verbose", dest="verbosity", action="count", default=0, help="increase output verbosity. Can be specified more than once to increase verbosity even more")
    parser.add_argument("-q", "--quiet", dest="quietness", action="count", default=0, help="decrease output verbosity. Can be specified more than once to decrease verbosity even more")
    parser.add_argument("-s", "--source-version", dest="source_version", metavar="VERSION", default="2.9", help="source version (default to 2.9)")
    parser.add_argument("-t", "--target-version", dest="target_version", metavar="VERSION", default="latest", help="target version (default to latest)")
    parser.add_argument("-c", "--cache-downloaded-modules", dest="cache_downloaded_modules", action="store_true", default=False, help="Generate a cache of downloaded modules in current directory")
    parser.add_argument("-C", "--cache-path", dest="cache_path", metavar="PATH", default=[], action="append", help="Where to look for and store collections cache files (default [./cache]). Can be specified more than once to load from multiple pathes")
    parser.add_argument("-G", "--generate-cache-for-collection", dest="generate_cache_for_collection", default=[], action="append", metavar="COLLECTION", help="Generate a cache for specified collection. Can be specified more than once to generate cache for multiple collections")
#    parser.add_argument("-M", "--generate-cache-for-module", dest="generate_cache_for_module", default=[], action="append", metavar="MODULE", help="Generate a cache for specified module. Can be specified more than once to generate cache for multiple modules")
    args = parser.parse_args()
    
    execute({
        "path": args.path,
        "overwrite_source": args.overwrite_source,
        "log_path": args.log_path,
        "show_logs": args.show_logs,
        "process_hidden_files": args.process_hidden_files,
        "verbosity": args.verbosity,
        "quietness": args.quietness,
        "source_version": args.source_version,
        "target_version": args.target_version,
        "cache_downloaded_modules": args.cache_downloaded_modules,
        "cache_path": args.cache_path,
        "generate_cache_for_collection": args.generate_cache_for_collection,
 #       "generate_cache_for_module": args.generate_cache_for_module,
        "no_logs_in_files": args.no_logs_in_files,
    })


def execute(exec_options={}):
    """
    The main execution method
    """
    
    options = check_exec_options(exec_options)

    cache = Cache(options)

    if len(options["generate_cache_for_collection"]) > 0:
        for collection in options["generate_cache_for_collection"]:
            cache.cache_collection(collection)
        return [], None


    cache.load_caches([*options["cache_path"],"downloaded-modules.cache.yml"])

    migrator = Migrator(options, cache)

    if options["path"] is not None:
        logs = migrator.migrate_path(options["path"])
    else:
        logs, result = migrator.migrate_string(options["source"], force_processing=True)

    if options["show_logs"]:
        prevfile = ""
        for log in logs:
            if log.file != prevfile:
                print(log.file)
                prevfile = log.file
            line = migrator.get_line_by_uuid(str(log.uuid))
            print(f"{(' ' + str(line) if line > 0 else '-----').rjust(5)} {log.level} : {log.message}")

    if options["log_path"] is not None:
        log_path = options["log_path"]
        if os.path.isdir(log_path):
            log_path = f"{log_path}/migration.log"
        logger.info(f"Saving migration logs to {log_path} ...")
        prevfile = ""
        with open(fix_tilde_in_path(log_path), "wt") as file:
            for log in logs:
                if log.file != prevfile:
                    file.write(f"{log.file}\n")
                    prevfile = log.file
                line = cache.uuid_to_line.get(str(log.uuid), -1)
                file.write(f"{(' ' + str(line) if line > 0 else '-----').rjust(5)} {log.level} : {log.message}\n")

    # list collections used by playbooks migrated in this run

    used_collections = cache.get_used_collections()
    logger.info(f"Used collections: {used_collections}")
    #logs.append(InfoLog(None,None, f"Used collections: {used_collections}"))


    if options["cache_downloaded_modules"]:
        cache.save_downloaded_modules()

    logger.info("Migration complete")

    if options["source"] is not None:
        return logs, result
    else:
        return logs, None




def check_exec_options(exec_options: dict) -> dict:
    """
    validate options

    returns validated options
    """
    options = {}

    if exec_options.get("path", None) is not None and len(exec_options["path"]) > 1 and exec_options["path"][-1] == '/':
        exec_options["path"] = options["path"][:-1]
    if len(exec_options["cache_path"]) == 0:
        exec_options["cache_path"] = ['./cache']
    if "ANSIBLE_MIGRATOR_CACHE_PATH" in os.environ:
        ANSIBLE_MIGRATOR_CACHE_PATH = os.environ["ANSIBLE_MIGRATOR_CACHE_PATH"]
        env_cache_path = list(map(lambda x: x.strip(), ANSIBLE_MIGRATOR_CACHE_PATH.split(":")))
        exec_options["cache_path"] = env_cache_path + exec_options["cache_path"]

    options.update(DEFAULT_OPTIONS)
    options.update(exec_options)


    options["logger_verbosity"] = LOG_INFO + int(str(options["verbosity"])) - int(str(options["quietness"]))
    Logger.verbosity = options["logger_verbosity"]
    logger.verbosity = options["logger_verbosity"]


    options["source_version"] = str(options["source_version"])
    options["target_version"] = str(options["target_version"])

    if options["target_version"] == "latest":
        options["target_version"] = SUPPORTED_VERSIONS[-1]

    if options["source_version"] not in SUPPORTED_VERSIONS:
        logger.fatal(f"Source version `{options['source_version']}` is not supported")
        exit(1)

    if options["target_version"] not in SUPPORTED_VERSIONS:
        logger.fatal(f"Target version `{options['target_version']}` is not supported")
        exit(1)

    if options["source_version"] >= options["target_version"]:
        logger.fatal(f"Target version must be greater that source version")
        exit(1)

    options["source_version_key"] = str(SUPPORTED_VERSIONS_KEYS[options["source_version"]])
    options["target_version_key"] = str(SUPPORTED_VERSIONS_KEYS[options["target_version"]])



    if options.get("path", None) is not None and options.get("source", None) is not None:
        logger.fatal("path and source are mutually exclusive")
        exit(1)

    if exec_options.get("generate_cache_for_collection", None) is None or len(exec_options["generate_cache_for_collection"]) == 0:
        if options["path"] is None and options["source"] is None:
            logger.fatal("Either path or source must be specified")
            exit(1)

    return options

if __name__ == '__main__':
    main()
