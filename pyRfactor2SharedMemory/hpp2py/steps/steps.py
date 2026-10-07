import hpp2py


@given(u'I have a line "{string}"')
def step_impl(context, string):
    context.CPPstring = string


@when(u'the comment is translated')
def step_impl(context):
    context.python = hpp2py.translateComment(context.CPPstring)


@then(u'I see line "{string}"')
def step_impl(context, string):
    try:
        _result = r'\n'.join(context.python.split('\n'))
    except BaseException:
        _result = None
    assert _result == string, \
        "Got '%s'" % context.python


@when(u'the struct is translated')
def step_impl(context):
    context.python = hpp2py.translateStruct(context.CPPstring)


@when(u'the structOpen is translated')
def step_impl(context):
    context.python = hpp2py.translateStructOpen(context.CPPstring)


@then(u'I see line None')
def step_impl(context):
    assert context.python is None


@when(u'the structItem is translated')
def step_impl(context):
    context.python = hpp2py.translateStructItem(context.CPPstring)


@when(u'the structItem is fullytranslated')
def step_impl(context):
    context.python = hpp2py.translateComment(context.CPPstring)
    context.python = hpp2py.translateStructItem(context.python)


@when(u'the structClose is translated')
def step_impl(context):
    context.python = hpp2py.translateStructClose(context.CPPstring)
