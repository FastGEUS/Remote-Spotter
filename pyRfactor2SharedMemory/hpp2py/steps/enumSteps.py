import hpp2py


@when(u'the enum is translated')
def step_impl(context):
    context.python = hpp2py.translateEnum(context.CPPstring)


@when(u'the enumOpen is translated')
def step_impl(context):
    context.python = hpp2py.translateEnumOpen(context.CPPstring)


@when(u'the enumItem is translated')
def step_impl(context):
    context.python = hpp2py.translateEnumItem(context.CPPstring)


@when(u'the enumClose is translated')
def step_impl(context):
    context.python = hpp2py.translateEnumClose(context.CPPstring)


"""
@given(u'I have a line "{string}"')
def step_impl(context, string):
    context.CPPstring = string


@then(u'I see line "{string}"')
def step_impl(context, string):
  _result = r'\n'.join(context.python.split('\n'))
  assert _result == string, \
    "Got '%s'" % context.python

@then(u'I see line None')
def step_impl(context):
  assert context.python == None
"""
