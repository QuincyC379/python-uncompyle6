# Python 3.6 changes, yet again, the way deafult pairs are handled
def foo1(bar, baz=1):
    return 1
def foo2(bar, baz, qux=1):
    return 2
def foo3(bar, baz=1, qux=2):
    return 3
def foo4(bar, baz, qux=1, quux=2):
    return 4
