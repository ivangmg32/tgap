'''
A small registry of transformations for the pipeline layer.

WHY THIS EXISTS, AND WHAT IT IS NOT
    The TgapExplainer is already generic: it calls name, propertyValue,
    deltaMode and transform, and nothing else. Adding a transformation has
    never required editing it.

    The problem was one layer up. Pipeline code listed the five concept
    names as literals (for example in compare_datasets), so a new concept
    would run through the explainer but then vanish from the cross-dataset
    figures. This registry is the fix for THAT, and nothing more.

    It is NOT a plugin framework. There is no discovery of files, no entry
    points, no import hooks. A registry entry is a name, a factory and some
    metadata; the explainer is untouched and unaware of it.

CAPABILITY METADATA INSTEAD OF STRING COMPARISON
    The pipeline needs to know two things that are properties of a
    transformation, not of its name:

      preservesEdgeCount   whether the edge-count invariant applies
      needsTrendGating     whether the bridge-trend saturation check applies

    Both were previously decided with `== "Bridge Trend"` style tests. They
    are now declared per entry, so a user transformation that reshapes a
    trajectory can request the same gating without anyone editing a
    conditional.

REGISTERING YOUR OWN
    from core.TransformationRegistry import register

    register("My Concept", MyTransformation, needsTrendGating=False)

    Nothing in core/ imports user transformations; registration happens in
    the user's own module or experiment script.
'''

from .Transformations import (
    BridgeTrendTransformation,
    BridgeWidthTransformation,
    CentralizationTransformation,
    ChurnTransformation,
    DensityTransformation,
)


class TransformationEntry:
    ''' One registered concept: how to build it, and what the pipeline
    needs to know about it. '''

    def __init__(self, name, factory, preservesEdgeCount=True,
                 needsTrendGating=False, temporal=False, description="",
                 builtin=False):
        self.name = name
        self.factory = factory
        self.preservesEdgeCount = preservesEdgeCount
        self.needsTrendGating = needsTrendGating
        self.temporal = temporal
        self.description = description
        self.builtin = builtin

    def build(self, communities=None, **kwargs):
        ''' Instantiate. communities is passed only when the factory takes
        it, so a transformation that needs no partition can be registered
        unchanged. '''
        try:
            return self.factory(communities, **kwargs)
        except TypeError:
            return self.factory(**kwargs)

    def __repr__(self):
        return (f"TransformationEntry({self.name!r}, "
                f"temporal={self.temporal}, "
                f"preservesEdgeCount={self.preservesEdgeCount})")


_REGISTRY = {}


def register(name, factory, preservesEdgeCount=None, needsTrendGating=False,
             temporal=False, description="", builtin=False, replace=False):
    ''' Add a transformation to the registry.

    preservesEdgeCount defaults to the class's own declaration, so the
    single source of truth stays the transformation itself; pass it
    explicitly only to override.
    '''
    if name in _REGISTRY and not replace:
        raise ValueError(f"{name!r} is already registered; pass replace=True "
                         f"to override it deliberately")
    if preservesEdgeCount is None:
        preservesEdgeCount = bool(getattr(factory, "preservesEdgeCount", True))
    _REGISTRY[name] = TransformationEntry(
        name, factory, preservesEdgeCount=preservesEdgeCount,
        needsTrendGating=needsTrendGating, temporal=temporal,
        description=description, builtin=builtin)
    return _REGISTRY[name]


def unregister(name):
    ''' Remove an entry. Mainly for tests, so one test cannot leak a
    registration into another. '''
    return _REGISTRY.pop(name, None)


def get(name):
    if name not in _REGISTRY:
        raise KeyError(f"{name!r} is not registered; known: {names()}")
    return _REGISTRY[name]


def names():
    ''' Registered names, in registration order. '''
    return list(_REGISTRY)


def entries(builtinOnly=False):
    return [e for e in _REGISTRY.values() if e.builtin or not builtinOnly]


def buildAll(communities=None, builtinOnly=False, **kwargs):
    ''' Instantiate every registered transformation.

    This is what pipeline code should call instead of writing the five
    concepts out by hand.
    '''
    return [entry.build(communities, **kwargs)
            for entry in entries(builtinOnly=builtinOnly)]


def conceptNames(builtinOnly=False):
    ''' The concept labels a figure or table should iterate over. Replaces
    the hard-coded five-name lists in the pipeline. '''
    return [entry.name for entry in entries(builtinOnly=builtinOnly)]


# --- the five shipped transformations ---------------------------------
# Registered here as a convenience so the pipeline has them by default.
# A user transformation is registered from the user's own module; nothing
# below is a requirement for a transformation to work with the explainer.

register("Bridge Width", BridgeWidthTransformation, builtin=True,
         description="ties between two communities")
register("Centralization", CentralizationTransformation, builtin=True,
         description="concentration of ties on the largest hub")
register("Density", DensityTransformation, builtin=True,
         description="overall number of edges")
register("Bridge Trend", BridgeTrendTransformation, builtin=True,
         temporal=True, needsTrendGating=True,
         description="slope of bridge width across snapshots")
register("Churn", ChurnTransformation, builtin=True, temporal=True,
         description="how much history differs from the present")
