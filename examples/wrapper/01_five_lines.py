'''
WRAPPER 1 - Five lines. The smallest possible TGAP study.

    python examples/wrapper/01_five_lines.py

A made-up temporal graph, a built-in model and two built-in concepts.
Results: output/examples/wrapper_01_five_lines/
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from tgap_wrapper import Wrapper               # noqa: E402

w = Wrapper.synthetic("wrapper_01_five_lines")  # data (try your own: example 2)
w.model("trend_clustering")                       # the model to explain
w.concept(["bridge_width", "density", "centralization"])        # what to nudge
w.explain()                                     # run + save CSV, PNG, TUTORIAL.md
