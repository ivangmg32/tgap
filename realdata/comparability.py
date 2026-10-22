"""The perturbation-semantics comparability rule, in a module with no heavy
dependencies so that light consumers (the web workbench) can use it without
importing PyTorch. realdata.run_tgn_stability re-exports it unchanged."""


def comparabilityOf(first, second):
    ''' Decide whether two concepts may be compared at all.

    The rule is a property of the transformations, not a list of names:

      * different deltaMode -> NOT comparable. One achieved change is a
        ratio, the other is in the property's own units; matching them
        would equate a percentage with a slope.
      * CentralizationTransformation -> NOT comparable to anything by
        matched achieved delta. Its delta is the FRACTION OF EDGES REWIRED
        (a mechanism knob), while its propertyValue is Freeman
        centralization, so an achieved change of 1.5 is not the same kind
        of quantity as a 0.1 relative change in bridge width. This is
        documented in the class itself.
      * otherwise -> comparable in principle; whether a match EXISTS is
        then decided by the sweep and the tolerance.
    '''
    if getattr(first, "deltaMode", "relative") != getattr(second, "deltaMode",
                                                          "relative"):
        return False, (f"different delta units ({first.deltaMode} vs "
                       f"{second.deltaMode}); achieved changes are not "
                       f"expressed in the same quantity")
    for transformation in (first, second):
        if type(transformation).__name__ == "CentralizationTransformation":
            return False, ("Centralization's delta is a rewiring fraction "
                           "(a mechanism knob), not a relative change of "
                           "the measured property, so its achieved delta "
                           "is not commensurable with the others")
    return True, None
