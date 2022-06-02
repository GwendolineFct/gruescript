import os
import shutil
from behave import *
from main import *
from step_utils import cleanup_indent, diff


@given('I have folder "{folder}"')
def step_impl(context, folder):
    os.makedirs(folder, exist_ok=True)

@given('I have empty folder "{folder}"')
def step_impl(context, folder):
    os.makedirs(folder, exist_ok=True)
    for files in os.listdir(folder):
        path = os.path.join(folder, files)
        try:
            shutil.rmtree(path)
        except OSError:
            os.remove(path)

@given('I have the following task')
def step_impl(context):
    try:
        context.migration_source += "\n"
    except:
        context.migration_source = ""
    context.migration_source += context.text


@given('I have a copy of file "{file}" in folder "{folder}" with name "{name}"')
def step_impl(context, file, folder, name):

    with open(file, "rt") as f:
        source = "".join(f.readlines())

    if "/" in file:
        file = file[file.rindex("/")+1:]

    os.makedirs(folder, exist_ok=True)
    
    with open(f"{folder}/{name}", "wt") as f:
        f.write(source)



@given('I have a copy of file "{file}" in folder "{folder}"')
def step_impl(context, file, folder):

    with open(file, "rt") as f:
        source = "".join(f.readlines())

    if "/" in file:
        file = file[file.rindex("/")+1:]

    os.makedirs(folder, exist_ok=True)

    with open(f"{folder}/{file}", "wt") as f:
        f.write(source)

@given('I set flag "{flag}"')
def step_impl(context, flag):
    context.migration_args[flag] = True

@given('I set incremental flag "{flag}"')
def step_impl(context, flag):
    if flag not in context.migration_args:
        context.migration_args[flag] = 0
    context.migration_args[flag] += 1

@given('I set incremental flag "{flag}" twice')
def step_impl(context, flag):
    if flag not in context.migration_args:
        context.migration_args[flag] = 0
    context.migration_args[flag] += 2

@given('I set incremental flag "{flag}" {count} times')
def step_impl(context, flag, count):
    if flag not in context.migration_args:
        context.migration_args[flag] = 0
    context.migration_args[flag] += int(count)

@given('I set option "{option}" to "{value}"')
def step_impl(context, option, value):
    try:
        args = context.migration_args
    except:
        args = {}
        context.migration_args = args

    args[option] = value

@given('I set option "{option}" to list "{value}"')
def step_impl(context, option, value):
    try:
        args = context.migration_args
    except:
        args = {}
        context.migration_args = args

    args[option] = list(map(lambda x: x.strip(), value.split(',')))

@when('I migrate')
def step_impl(context):

    try:
        context.stdout_capture.truncate()
    except:
        pass

    if "path" in context.migration_args:
        exec_options = {"path": context.migration_args['path']}
    else:
        exec_options = {"source": context.migration_source}

    exec_options.update(context.migration_args)

    logs, result = execute(exec_options)

    context.migration_ran = True
    context.migration_logs = logs
    context.migration_result = result

@when('I migrate "{path}"')
def step_impl(context, path):

    try:
        context.stdout_capture.truncate()
    except:
        pass

    exec_options = {}
    exec_options.update(context.migration_args)

    # path might have been set by previous options, we want to use what is explicetly specified
    exec_options.update({"path": path})

    logs, result = execute(exec_options)

    context.migration_ran = True
    context.migration_logs = logs
    context.migration_result = result


@then('I must find file "{file}" that matches "{anotherfile}"')
def step_impl(context, file, anotherfile):
    expected = f"file not found : {anotherfile}"

    assert context.migration_ran

    try:
        with open(file, "rt") as f:
            actual = "".join(f.readlines())
    except Exception as e:
        raise e

    try:
        with open(anotherfile, "rt") as f:
            expected = "".join(f.readlines())
    except Exception as e:
        raise e

    actual = cleanup_indent(actual)
    expected = cleanup_indent(expected)

    if actual != expected:
        print(diff(actual, expected))

    assert actual == expected

@then('it must be migrated as such')
def step_impl(context):

    assert context.migration_ran and context.migration_result is not None

    actual = cleanup_indent(context.migration_result)
    expected = cleanup_indent(context.text)

    if actual != expected:
        print("--------========[ WANTED ]========--------")
        print(expected)
        print("--------========[ ACTUAL ]========--------")
        print(actual)
        print("--------========[  DIFF  ]========--------")
        print(diff(actual, expected))
        print("--------========~~~~~~~~~~========--------")

    assert actual == expected

@then('logs must contain "{text}"')
def step_impl(context, text):

    assert context.migration_ran and context.migration_logs is not None
    
    found = False
    for log in context.migration_logs:
        print(log.message)
        if text in log.message:
            found = True
            break
    
    assert found

@then('log at line {line} must contain "{text}"')
def step_impl(context, line, text):

    assert context.migration_ran and context.migration_logs is not None
    
    found = False
    for log in context.migration_logs:
        if log.line == int(line) and text in log.message:
            found = True
            break
    
    assert found


@then('it fails')
def step_impl(context):

    assert False
