'''
The TGAP wrapper - explain YOUR model with a few lines of code.

TSAP (the time-series ancestor of TGAP) is easy to use because a model is
just "something with predict(series)" and a transformation is just a
function (series, delta) -> series. This wrapper gives TGAP the same feel:
no classes to write, no base classes to know. A model is a function, a
concept is a function (or two), and the wrapper does everything else -
loading data, running the explainer, checking your functions for the usual
mistakes, and writing the CSV / PNG / TUTORIAL.md outputs.

    from tgap_wrapper import Wrapper

    w = Wrapper.fromCsv("my_study", "messages.csv", groups="teams.csv")

    @w.model
    def predict(snapshots):                  # YOUR model: history -> one number
        last = snapshots[-1]
        return last.number_of_edges() / last.number_of_nodes()

    @w.concept                               # YOUR concept: change a graph
    def triangle_closing(graph, delta):
        ...                                  # edit `graph` (a copy) and return it

    w.concept("density")                     # built-in concepts, by name
    w.explain()                              # prints + writes output/examples/my_study/

What the pieces are
    snapshots   a list of networkx graphs, oldest first (the temporal graph)
    model       any function / object with predict(snapshots) -> number
    concept     a function change(graph, delta) -> graph, where delta is a
                ratio (0.1 = "10% more of the concept", -0.1 = "10% less").
                Optionally also measure(graph) -> number, so TGAP can tell
                how far the concept REALLY moved (graphs are discrete, so a
                requested 10% is rarely exactly 10%).

Everything is checked before the explainer runs (check()), and problems are
reported in plain English: a model that fails or returns text, a concept that
edits the input in place, one that is not repeatable, one that changes the
people in the graph, one that breaks its tie-count promise.
'''

import copy
import inspect
import math
import numbers
import os
import random

import paths
from core import TemporalGraphTransformation
from examples import toolkit

__all__ = ["Wrapper", "FunctionConcept", "FunctionModel"]


# --------------------------------------------------------------------------
#  Your functions, dressed up as TGAP objects
# --------------------------------------------------------------------------

class FunctionModel(object):
    ''' Any function (or object with .predict) as a TGAP model.

    on="all"   the function receives the whole list of snapshots (default)
    on="last"  the function receives only the latest graph - for models that
               look at the present and ignore history '''

    def __init__(self, function, on="all", description=""):
        if on not in ("all", "last"):
            raise ValueError("on must be 'all' or 'last', not {0!r}."
                             .format(on))
        if hasattr(function, "predict") and callable(function.predict):
            self.owner, function = function, function.predict
        else:
            self.owner = None
        if not callable(function):
            raise TypeError("A model must be a function (or an object with a "
                            "predict method); got {0!r}.".format(function))
        self.function = function
        self.on = on
        self.description = description
        self.__name__ = getattr(function, "__name__", "model")

    def predict(self, snapshots):
        return self.function(snapshots[-1] if self.on == "last"
                             else snapshots)


class FunctionConcept(TemporalGraphTransformation):
    ''' A concept written as plain functions - see Wrapper.concept().

    change(graph, delta)            change ONE snapshot (you may edit the
                                    graph you receive: it is already a
                                    copy) and return it; or
    change(graph, delta, rng)       the same, with a seeded random.Random
                                    for any random choices (keeps results
                                    repeatable); or
    overTime(snapshots, delta)      instead of change: reshape the whole
                                    history at once, returning new snapshots.
    measure(graph) -> number        optional: the concept's value in one
                                    snapshot (averaged over the history).
                                    With overTime it is measure(snapshots)
                                    instead - one number for the history. '''

    def __init__(self, name, change=None, measure=None, overTime=None,
                 keepsEdgeCount=True, absolute=False, seed=42,
                 description=""):
        if (change is None) == (overTime is None):
            raise ValueError("Give a concept either change(graph, delta) or "
                             "overTime(snapshots, delta), not both or "
                             "neither.")
        self.name = name
        self.change = change
        self.measure = measure
        self.overTime = overTime
        self.preservesEdgeCount = bool(keepsEdgeCount)
        self.deltaMode = "absolute" if absolute else "relative"
        self.seed = seed
        self.description = description
        self._wantsRng = change is not None and _positionalCount(change) >= 3

    def propertyValue(self, x):
        if self.measure is None:
            return None            # the explainer falls back to the request
        graphs = x if isinstance(x, list) else [x]
        if self.overTime is not None:             # a property of the history
            return float(self.measure(graphs))
        values = [float(self.measure(g)) for g in graphs]
        return sum(values) / len(values)

    def transformGraph(self, graph, delta):
        if self.change is None:
            raise NotImplementedError(
                "{0} reshapes the whole history (overTime) and has no "
                "single-graph meaning.".format(self.name))
        g = graph.copy()                           # your edits are safe
        if self._wantsRng:
            result = self.change(g, delta, random.Random(self.seed))
        else:
            result = self.change(g, delta)
        return g if result is None else result     # in-place style is fine

    def transform(self, temporalGraph, delta):
        if self.overTime is None:
            return TemporalGraphTransformation.transform(
                self, temporalGraph, delta)
        result = self.overTime([g.copy() for g in temporalGraph], delta)
        return list(temporalGraph if result is None else result)


def _positionalCount(function):
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return 2
    if any(p.kind == p.VAR_POSITIONAL for p in parameters):
        return 3
    return sum(1 for p in parameters
               if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))


def _signature(graph):
    return (sorted(map(str, graph.nodes())),
            sorted(tuple(sorted(map(str, e))) for e in graph.edges()))


# --------------------------------------------------------------------------
#  The wrapper
# --------------------------------------------------------------------------

class Wrapper(object):
    ''' One study: data + a model + concepts -> an explanation.

    Build it with fromCsv(...), synthetic(...) or Wrapper(name, snapshots),
    then add a model and concepts, then call explain(). '''

    def __init__(self, name, snapshots, groups=None):
        if not isinstance(snapshots, (list, tuple)) or len(snapshots) < 2:
            raise ValueError(
                "A temporal graph is a list of at least 2 networkx graphs "
                "(snapshots, oldest first).")
        self.name = name
        self.snapshots = list(snapshots)
        self._groups = [set(g) for g in groups] if groups else None
        self._model = None
        self._concepts = []

    # ---- data ------------------------------------------------------------

    @classmethod
    def fromCsv(cls, name, edges, groups=None, snapshots=6, howManyGroups=2,
                source="source", target="target", time="time",
                person="person", group="group"):
        ''' Your data: a CSV of interactions (who, with whom, when) cut into
        `snapshots` equal time windows, and optionally a CSV of known groups
        (who, group). Without `groups`, TGAP finds `howManyGroups` for you
        when a built-in concept or model needs them. '''
        graphs = toolkit.loadEdgeList(edges, source, target, time, snapshots)
        known = (toolkit.loadGroups(groups, person, group, graphs)
                 if groups else None)
        return cls(name, graphs, known)

    @classmethod
    def synthetic(cls, name="synthetic", snapshots=6, peoplePerGroup=10,
                  bridgeWidth=8, bridgeDecay=0, seed=42):
        ''' A made-up temporal graph with two groups - to try things out. '''
        graphs, groups = toolkit.syntheticGraph(
            snapshots, peoplePerGroup, bridgeWidth, bridgeDecay, seed)
        return cls(name, graphs, groups)

    @property
    def groups(self):
        ''' The communities. Detected on first use when none were given. '''
        if self._groups is None:
            self._groups = [set(g) for g in
                            toolkit.findCommunities(self.snapshots)]
            print("      (no groups given: TGAP found {0} groups of sizes "
                  "{1})".format(len(self._groups), "/".join(
                      str(len(g)) for g in self._groups)))
        return self._groups

    # ---- the model -------------------------------------------------------

    def model(self, what=None, on="all", description=""):
        ''' Set the model. Use it any of these ways:

            @w.model                        a decorator on your function
            @w.model(on="last")             ... that only needs the latest graph
            w.model(my_function)            a function or an object with .predict
            w.model("trend_bridge_width")   a built-in model, by name

        The model receives the snapshots (a list of graphs, oldest first)
        and returns ONE number. '''
        if what is None:
            return lambda function: self.model(function, on, description)
        if isinstance(what, str):
            self._model = toolkit.model(what, self.groups)
            self._model.description = toolkit.MODELS[what][0]
        else:
            self._model = FunctionModel(what, on, description or
                                        _firstLine(what))
        return what if callable(what) else self._model

    # ---- concepts --------------------------------------------------------

    def concept(self, what=None, name=None, measure=None, overTime=None,
                keepsEdgeCount=True, absolute=False, seed=42,
                description=""):
        ''' Add a concept to test. Use it any of these ways:

            w.concept("density")            a built-in concept, by name
            w.concept(["density", "churn"]) several built-ins at once

            @w.concept                      a decorator: change(graph, delta)
            def triangle_closing(graph, delta): ...

            @w.concept(measure=clustering_of, keepsEdgeCount=False)
            def triangle_closing(graph, delta, rng): ...   # rng: seeded random

            w.concept(overTime=fn, name="Fade")     reshape the whole history

            w.concept(MyTransformationClass())      a full TGAP transformation

        name            label in the results (default: from the function name)
        measure         measure(graph) -> number: lets TGAP normalise by how
                        far the concept REALLY moved. Strongly recommended.
                        (With overTime: measure(snapshots) -> number.)
                        delta > 0 must make the measured value go UP.
        keepsEdgeCount  True if your change keeps the number of ties fixed
                        (checked for you); False if it adds / removes ties.
        absolute        True when the concept can legitimately be 0 (a slope,
                        a count) so "10% of it" has no meaning: delta is then
                        added to the concept instead of multiplied.
        '''
        if what is None and overTime is None:
            return lambda function: self.concept(
                function, name, measure, overTime, keepsEdgeCount, absolute,
                seed, description)
        if isinstance(what, (list, tuple)):
            for item in what:
                self.concept(item)
            return what
        if isinstance(what, str):
            self._add(toolkit.transformations([what], self.groups)[0])
            return what
        if isinstance(what, TemporalGraphTransformation):
            self._add(what)
            return what
        if what is not None and not callable(what):
            raise TypeError("A concept is a built-in name, a function "
                            "change(graph, delta), or a transformation "
                            "object; got {0!r}.".format(what))
        label = name or (_prettify(what.__name__) if what is not None
                         else "My Concept")
        self._add(FunctionConcept(
            label, change=what, measure=measure, overTime=overTime,
            keepsEdgeCount=keepsEdgeCount, absolute=absolute, seed=seed,
            description=(description or (_firstLine(what) if what else "")
                         or "a concept you defined")))
        return what

    def _add(self, transformation):
        if any(t.name == transformation.name for t in self._concepts):
            raise ValueError("A concept called {0!r} was already added. "
                             "Give one of them another name."
                             .format(transformation.name))
        self._concepts.append(transformation)

    @property
    def concepts(self):
        return list(self._concepts)

    # ---- checking --------------------------------------------------------

    def check(self, quiet=False):
        ''' Try your model and concepts on your data and report the usual
        mistakes in plain English. Returns a list of warnings; raises
        ValueError for problems that would make the explanation wrong. '''
        self._require()
        warnings = []

        def say(text):
            if not quiet:
                print("      " + text)

        # the model
        try:
            value = self._model.predict(self.snapshots)
        except Exception as error:
            raise ValueError(
                "Your model failed on your data: {0}: {1}\n"
                "The model is called as predict(snapshots) with a list of {2} "
                "networkx graphs (oldest first) and must return one number."
                .format(type(error).__name__, error, len(self.snapshots)))
        if isinstance(value, bool) or not isinstance(value, numbers.Real) \
                or not math.isfinite(float(value)):
            raise ValueError(
                "Your model must return ONE finite number, but returned "
                "{0!r}. (If it returns a numpy array or a list, return its "
                "value with float(...).)".format(value))
        say("model: ok - predicts {0:.4f} on your data".format(float(value)))

        # the concepts
        before = [_signature(g) for g in self.snapshots]
        for concept in self._concepts:
            problems = self._checkConcept(concept, before)
            for text in problems:
                warnings.append("{0}: {1}".format(concept.name, text))
            say("concept {0!r}: {1}".format(
                concept.name, "ok" if not problems else
                "{0} warning(s) - see below".format(len(problems))))
        for text in warnings:
            say("  ! " + text)
        return warnings

    def _checkConcept(self, concept, before):
        problems = []
        for delta in (0.25, -0.25):
            try:
                first = concept.transform(self.snapshots, delta)
                second = concept.transform(self.snapshots, delta)
            except Exception as error:
                raise ValueError(
                    "Your concept {0!r} failed with delta={1:+g}: {2}: {3}\n"
                    "It is called as change(graph, delta) on ONE snapshot (a "
                    "networkx graph) and must return a graph."
                    .format(concept.name, delta, type(error).__name__,
                            error))
            if not isinstance(first, list) or len(first) != len(
                    self.snapshots) or not all(hasattr(g, "edges")
                                               for g in first):
                raise ValueError(
                    "Your concept {0!r} must return a graph for each "
                    "snapshot (change returns ONE graph; overTime returns a "
                    "list of graphs of the same length).".format(
                        concept.name))
            if [_signature(g) for g in self.snapshots] != before:
                raise ValueError(
                    "Your concept {0!r} changed the ORIGINAL data. Copy the "
                    "graph first (graph = graph.copy()) - or use "
                    "@w.concept, which already gives you a copy."
                    .format(concept.name))
            if [_signature(g) for g in first] != [_signature(g)
                                                  for g in second]:
                problems.append(
                    "gives different graphs on two identical calls (delta="
                    "{0:+g}). Use the seeded `rng` argument for random "
                    "choices so explanations are repeatable.".format(delta))
            if any(set(a.nodes()) != set(b.nodes())
                   for a, b in zip(self.snapshots, first)):
                problems.append(
                    "adds or removes PEOPLE (nodes). TGAP keeps the people "
                    "fixed and changes only ties.")
            if concept.preservesEdgeCount and any(
                    a.number_of_edges() != b.number_of_edges()
                    for a, b in zip(self.snapshots, first)):
                problems.append(
                    "promised to keep the number of ties (keepsEdgeCount="
                    "True) but changed it at delta={0:+g}. Say keepsEdgeCount"
                    "=False if adding / removing ties is the point (on a "
                    "sparse graph there can also be no room to move ties "
                    "without changing their number)."
                    .format(delta))
        if concept.propertyValue(self.snapshots) is None:
            problems.append(
                "has no measure(graph): impacts will be divided by the "
                "REQUESTED change, not the achieved one. Add measure=... "
                "for exact results.")
        else:
            low = concept.propertyValue(concept.transform(self.snapshots,
                                                          -0.25))
            high = concept.propertyValue(concept.transform(self.snapshots,
                                                           0.25))
            if low == high:
                problems.append(
                    "its measure did not move between delta=-25% and +25% "
                    "on your data - the concept may be stuck (nothing to "
                    "change?) or measure() may not match what change() "
                    "does.")
        return list(dict.fromkeys(problems))

    # ---- explain ---------------------------------------------------------

    def explain(self, deltas=(0.1, 0.25), sweep=True, folder=None,
                check=True, figures=True, figureBudget=40):
        ''' Run TGAP. Prints a small table and writes explanation.csv/.png,
        sensitivity.csv/.png, graph_over_time.csv/.png, the paper-style
        pictures (what_changed, when_it_mattered, edge_impact, edge_over_time,
        node_impact, impact_heatmap) and TUTORIAL.md to `folder` (default
        output/examples/<name>/). Returns the explanation as a DataFrame.

        figures=False skips the paper-style pictures, which re-ask your model
        up to `figureBudget` times per picture (use it for a very slow
        model). '''
        self._require()
        print()
        print("  {0}".format(self.name))
        print("      {0} snapshots, {1} people{2}; model: {3}; concepts: {4}"
              .format(len(self.snapshots),
                      self.snapshots[0].number_of_nodes(),
                      "" if self._groups is None else
                      ", {0} groups".format(len(self._groups)),
                      getattr(self._model, "__name__", None) or
                      type(self._model).__name__,
                      ", ".join(c.name for c in self._concepts)))
        if check:
            self.check()
        return toolkit.explainAndSave(
            self.name, self._model, self._concepts, self.snapshots,
            self._groups, deltas=tuple(deltas), sweep=sweep, folder=folder,
            modelDescription=getattr(self._model, "description", "") or None,
            figures=figures, figureBudget=figureBudget)

    def _require(self):
        if self._model is None:
            raise ValueError(
                "No model yet. Add one with @w.model (a function "
                "predict(snapshots) -> number) or w.model(\"trend_bridge_"
                "width\").")
        if not self._concepts:
            raise ValueError(
                "No concepts yet. Add one with w.concept(\"density\") or "
                "@w.concept (a function change(graph, delta) -> graph).")


def _prettify(identifier):
    return " ".join(w.capitalize() for w in identifier.strip("_").split("_"))


def _firstLine(function):
    doc = (getattr(function, "__doc__", None) or "").strip().splitlines()
    return doc[0].strip() if doc else ""
