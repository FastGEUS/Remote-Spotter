import hpp2py


@when(u'the public is translated')
def step_impl(context):
    context.python = hpp2py.translateCSpublic(context.CPPstring)


@when(u'the JsonIgnore is translated')
def step_impl(context):
    context.python = hpp2py.translateCSjsonIgnore(context.CPPstring)


@when(u'the CSstructItem is fullytranslated')
def step_impl(context):
    context.python = hpp2py.translateComment(context.CPPstring)
    context.python = hpp2py.translateCSMarshalAsAttribute(context.python)
    context.python = hpp2py.translateCSpublic(context.python)
    context.python = hpp2py.translateCSjsonIgnore(context.python)
    context.python = hpp2py.translateStructItem(context.python)


@when(u'the MarshalAsAttribute is translated')
def step_impl(context):
    context.python = hpp2py.translateCSMarshalAsAttribute(context.CPPstring)
