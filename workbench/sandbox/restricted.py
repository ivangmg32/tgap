"""Interpret a deliberately small Python AST; never exec participant code.

Only graph operations and elementary data operations cross the interpreter's
boundary. This is a constrained educational language, not arbitrary Python.
The worker also has an external timeout and process memory limit.
"""
import ast
import math
import operator
import networkx as nx


class CodeError(ValueError):
    pass


class ReturnValue(Exception):
    def __init__(self, value):
        self.value = value


class Namespace(dict):
    pass


class Interpreter:
    def __init__(self, code, base):
        if len(code) > 12000:
            raise CodeError("Keep your transformer under 12,000 characters.")
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            raise CodeError(f"Line {error.lineno}: {error.msg}") from None
        allowed = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.arguments, ast.arg,
                   ast.Assign, ast.AugAssign, ast.Return, ast.If, ast.For, ast.Expr,
                   ast.Pass, ast.Import, ast.ImportFrom, ast.alias, ast.Name, ast.Load,
                   ast.Store, ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict,
                   ast.Attribute, ast.Call, ast.keyword, ast.Subscript, ast.Slice,
                   ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
                   ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.comprehension,
                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
                   ast.Pow, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq,
                   ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
                   ast.Is, ast.IsNot)
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise CodeError(f"Line {getattr(node, 'lineno', '?')}: {type(node).__name__} is not supported. See the custom-transformer guide.")
            if isinstance(node, (ast.Name, ast.Attribute, ast.arg)):
                name = getattr(node, 'id', getattr(node, 'attr', getattr(node, 'arg', '')))
                if name.startswith('_'):
                    raise CodeError("Private attributes and names are unavailable.")
            if isinstance(node, ast.Constant) and (not isinstance(node.value, (str, int, float, bool, type(None))) or len(str(node.value)) > 2000):
                raise CodeError("That literal is outside the supported limits.")
            if isinstance(node, ast.Import) and any(a.name != 'networkx' for a in node.names):
                raise CodeError("Only 'import networkx as nx' is supported.")
            if isinstance(node, ast.ImportFrom) and not (node.module == 'core' and all(a.name == 'TemporalGraphTransformation' for a in node.names) and not node.level):
                raise CodeError("Only TemporalGraphTransformation may be imported from core.")
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
                raise CodeError("Decorators are unavailable.")
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if len(classes) != 1 or any(not isinstance(n, (ast.Import, ast.ImportFrom, ast.ClassDef)) for n in tree.body):
            raise CodeError("Define one transformation class; put operations inside its methods.")
        cls = classes[0]
        if len(cls.bases) != 1 or not isinstance(cls.bases[0], ast.Name) or cls.bases[0].id != 'TemporalGraphTransformation' or cls.keywords:
            raise CodeError("Your class must extend TemporalGraphTransformation.")
        self.methods = {}
        self.fields = Namespace(name="Custom concept", deltaMode="relative", preservesEdgeCount=False)
        self.steps = 0
        self.depth = 0
        for node in cls.body:
            if isinstance(node, ast.FunctionDef):
                if node.name not in ('propertyValue', 'transformGraph', 'transform'):
                    raise CodeError("Supported methods: propertyValue, transformGraph, transform.")
                if node.args.vararg or node.args.kwarg or node.args.defaults or node.args.kwonlyargs:
                    raise CodeError("Use simple method arguments without defaults.")
                self.methods[node.name] = node
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in self.fields and isinstance(node.value, ast.Constant):
                self.fields[node.targets[0].id] = node.value.value
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                pass
            elif not isinstance(node, ast.Pass):
                raise CodeError("Class body accepts the three metadata fields and methods only.")
        if not isinstance(self.fields['name'], str) or not 1 <= len(self.fields['name']) <= 60:
            raise CodeError("Choose a concept name of 1–60 characters.")
        if self.fields['deltaMode'] not in ('relative', 'absolute') or type(self.fields['preservesEdgeCount']) is not bool:
            raise CodeError("deltaMode must be relative/absolute and preservesEdgeCount must be True/False.")
        if 'propertyValue' not in self.methods or not {'transformGraph', 'transform'} & self.methods.keys():
            raise CodeError("Implement propertyValue and transformGraph (or transform).")
        expected = {'propertyValue': 2, 'transformGraph': 3, 'transform': 3}
        for name, method in self.methods.items():
            if len(method.args.args) != expected[name] or method.args.posonlyargs:
                raise CodeError(f"Check the arguments of {name}.")
        interp = self

        class Custom(base):
            name = interp.fields['name']
            deltaMode = interp.fields['deltaMode']
            preservesEdgeCount = interp.fields['preservesEdgeCount']

            def propertyValue(self, x):
                value = interp.invoke('propertyValue', [interp.fields, x])
                if value is None:
                    return None
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise CodeError("propertyValue must return a finite number or None.")
                return float(value)

            def transformGraph(self, graph, delta):
                if 'transformGraph' not in interp.methods:
                    raise CodeError("This temporal concept has no single-graph mode.")
                return interp.invoke('transformGraph', [interp.fields, graph, delta])

            def transform(self, graphs, delta):
                if 'transform' in interp.methods:
                    return interp.invoke('transform', [interp.fields, graphs, delta])
                return super().transform(graphs, delta)

        self.instance = Custom()

    def tick(self):
        self.steps += 1
        if self.steps > 120000:
            raise CodeError("Operation budget exceeded. Use smaller loops or a simpler transformer.")

    def bounded(self, value):
        if isinstance(value, (str, list, tuple, set, dict, range)) and len(value) > 10000:
            raise CodeError("Collection limit exceeded (10,000 items).")
        if isinstance(value, (int, float)) and (not math.isfinite(value) or abs(value) > 1e12):
            raise CodeError("Numeric limit exceeded.")
        return value

    def invoke(self, name, values):
        self.depth += 1
        if self.depth > 12:
            raise CodeError("Recursive calls are too deep.")
        node = self.methods[name]
        env = {a.arg: v for a, v in zip(node.args.args, values)}
        env.update(self.builtins())
        try:
            self.block(node.body, env)
        except ReturnValue as returned:
            return returned.value
        finally:
            self.depth -= 1

    def builtins(self):
        def safe_range(*args):
            return self.bounded(range(*args))
        return dict(nx=Namespace(density=nx.density, isolates=lambda g: list(nx.isolates(g)),
                                 number_of_selfloops=nx.number_of_selfloops,
                                 average_clustering=nx.average_clustering),
                    self=self.fields, len=len, sum=sum, min=min, max=max, abs=abs,
                    round=round, float=float, int=int, bool=bool, list=list,
                    set=set, tuple=tuple, sorted=sorted, range=safe_range,
                    enumerate=lambda x: list(enumerate(x)), zip=lambda *x: list(zip(*x)),
                    isinstance=lambda x, t: isinstance(x, t), any=any, all=all)

    def assign(self, node, value, env):
        if isinstance(node, ast.Name):
            if node.id in self.builtins():
                raise CodeError("Do not overwrite built-in names.")
            env[node.id] = self.bounded(value)
        elif isinstance(node, (ast.Tuple, ast.List)):
            if len(node.elts) != len(value):
                raise CodeError("Unpacking lengths differ.")
            for target, item in zip(node.elts, value):
                self.assign(target, item, env)
        elif isinstance(node, ast.Subscript):
            obj = self.expr(node.value, env)
            if not isinstance(obj, (list, dict)) or isinstance(obj, Namespace):
                raise CodeError("Only local lists and dictionaries can be updated.")
            obj[self.expr(node.slice, env)] = self.bounded(value)
            self.bounded(obj)
        else:
            raise CodeError("Assign to local variables, not attributes.")

    def block(self, nodes, env):
        for node in nodes:
            self.tick()
            if isinstance(node, ast.Return):
                raise ReturnValue(self.expr(node.value, env) if node.value else None)
            elif isinstance(node, ast.Assign):
                value = self.expr(node.value, env)
                for target in node.targets:
                    self.assign(target, value, env)
            elif isinstance(node, ast.AugAssign):
                value = self.binary(node.op, self.expr(node.target, env), self.expr(node.value, env))
                self.assign(node.target, value, env)
            elif isinstance(node, ast.If):
                self.block(node.body if self.expr(node.test, env) else node.orelse, env)
            elif isinstance(node, ast.For):
                values = self.bounded(self.expr(node.iter, env))
                for value in values:
                    self.tick()
                    self.assign(node.target, value, env)
                    self.block(node.body, env)
                self.block(node.orelse, env)
            elif isinstance(node, ast.Expr):
                self.expr(node.value, env)
            elif not isinstance(node, ast.Pass):
                raise CodeError("Unsupported statement.")

    def binary(self, op, a, b):
        if isinstance(op, ast.Pow) and (not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or abs(b) > 10):
            raise CodeError("Exponent must be a small number.")
        if isinstance(op, ast.Mult):
            for seq, count in ((a, b), (b, a)):
                if isinstance(seq, (str, list, tuple)) and isinstance(count, int) and len(seq) * max(0, count) > 10000:
                    raise CodeError("Collection limit exceeded.")
        operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                      ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                      ast.Mod: operator.mod, ast.Pow: operator.pow}
        if isinstance(a, str) and isinstance(op, ast.Mod):
            raise CodeError("String formatting is unavailable.")
        return self.bounded(operations[type(op)](a, b))

    def attr(self, obj, name):
        if isinstance(obj, Namespace):
            if obj is self.fields and name in self.methods:
                return lambda *args: self.invoke(name, [obj, *args])
            if name in obj:
                return obj[name]
        elif isinstance(obj, nx.Graph):
            if name in ('copy', 'number_of_nodes', 'number_of_edges', 'has_edge', 'remove_edge', 'remove_edges_from', 'neighbors'):
                return getattr(obj, name)
            if name in ('nodes', 'edges', 'degree'):
                if name == 'nodes':
                    return lambda: list(obj.nodes())
                if name == 'edges':
                    return lambda: list(obj.edges())
                return lambda n=None: obj.degree(n) if n is not None else list(obj.degree())
            if name in ('add_edge', 'add_edges_from'):
                def add(*args):
                    edges = [args] if name == 'add_edge' else args[0]
                    for edge in self.bounded(edges):
                        if len(edge) != 2 or any(v not in obj for v in edge) or edge[0] == edge[1]:
                            raise CodeError("Add edges only between existing distinct nodes.")
                    obj.add_edges_from(edges)
                return add
        elif isinstance(obj, dict) and name in ('get', 'keys', 'items', 'values', 'copy'):
            return getattr(obj, name)
        elif isinstance(obj, list) and name in ('append', 'pop', 'copy'):
            return getattr(obj, name)
        elif isinstance(obj, set) and name in ('add', 'discard', 'difference', 'intersection', 'union'):
            return getattr(obj, name)
        raise CodeError(f"'{name}' is not an available operation.")

    def expr(self, node, env):
        self.tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise CodeError(f"Unknown name: {node.id}")
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.expr(e, env) for e in node.elts]
            return self.bounded({ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)](values))
        if isinstance(node, ast.Dict):
            return self.bounded({self.expr(k, env): self.expr(v, env) for k, v in zip(node.keys, node.values)})
        if isinstance(node, ast.Attribute):
            return self.attr(self.expr(node.value, env), node.attr)
        if isinstance(node, ast.Call):
            fn = self.expr(node.func, env)
            if not callable(fn):
                raise CodeError("That value cannot be called.")
            if any(k.arg is None for k in node.keywords):
                raise CodeError("Keyword unpacking is unavailable.")
            args = [self.expr(a, env) for a in node.args]
            kwargs = {k.arg: self.expr(k.value, env) for k in node.keywords}
            return self.bounded(fn(*args, **kwargs))
        if isinstance(node, ast.Subscript):
            obj = self.expr(node.value, env)
            if not isinstance(obj, (list, tuple, dict, str, range)):
                raise CodeError("Index only local collections.")
            return obj[self.expr(node.slice, env)]
        if isinstance(node, ast.Slice):
            return slice(*(self.expr(n, env) if n else None for n in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.BinOp):
            return self.binary(node.op, self.expr(node.left, env), self.expr(node.right, env))
        if isinstance(node, ast.UnaryOp):
            return {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}[type(node.op)](self.expr(node.operand, env))
        if isinstance(node, ast.BoolOp):
            result = self.expr(node.values[0], env)
            for n in node.values[1:]:
                if isinstance(node.op, ast.And) and not result or isinstance(node.op, ast.Or) and result:
                    return result
                result = self.expr(n, env)
            return result
        if isinstance(node, ast.Compare):
            comparisons = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
                           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
                           ast.In: lambda a,b: a in b, ast.NotIn: lambda a,b: a not in b,
                           ast.Is: operator.is_, ast.IsNot: operator.is_not}
            a = self.expr(node.left, env)
            for op, n in zip(node.ops, node.comparators):
                b = self.expr(n, env)
                if not comparisons[type(op)](a, b):
                    return False
                a = b
            return True
        if isinstance(node, ast.IfExp):
            return self.expr(node.body if self.expr(node.test, env) else node.orelse, env)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            values = []
            def visit(index, scope):
                if index == len(node.generators):
                    values.append(self.expr(node.elt, scope))
                    self.bounded(values)
                    return
                gen = node.generators[index]
                if gen.is_async:
                    raise CodeError("Async operations are unavailable.")
                for value in self.bounded(self.expr(gen.iter, scope)):
                    self.tick()
                    child = dict(scope)
                    self.assign(gen.target, value, child)
                    if all(self.expr(n, child) for n in gen.ifs):
                        visit(index+1, child)
            visit(0, dict(env))
            return set(values) if isinstance(node, ast.SetComp) else values
        raise CodeError(f"Unsupported expression: {type(node).__name__}")
