import ast
import os
import argparse
from collections import defaultdict
from neo4j import GraphDatabase

def extract_module_info(source_code):
    """
    Returns:
        classes: {class_name: {'bases': [base_class_names], 'attributes': set(attr_names)}}
        functions: {func_name: set(called_func_names)}
    """
    classes = defaultdict(lambda: {'bases': [], 'attributes': set(), 'attr_types': {}})
    functions = defaultdict(set)
    class ModuleVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_class = None
            self.current_function = None
        def visit_ClassDef(self, node):
            self.current_class = node.name
            # Base classes
            bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
            classes[node.name]['bases'] = bases
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    # Check if it's self.attr: Type = ...
                    target = stmt.target
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = target.attr
                        # Get type hint as string
                        type_hint = ast.unparse(stmt.annotation) if hasattr(ast, 'unparse') else None
                        classes[node.name]['attr_types'][attr_name] = type_hint
            self.generic_visit(node)
        def visit_FunctionDef(self, node):
            prev_function = self.current_function
            self.current_function = node.name
            if self.current_class is None:
                functions[node.name] = set()
            self.generic_visit(node)
            self.current_function = prev_function
        def visit_Attribute(self, node):
            if self.current_class and isinstance(node.value, ast.Name) and node.value.id == 'self':
                classes[self.current_class]['attributes'].add(node.attr)
            self.generic_visit(node)
        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                    if self.current_class:
                        classes[self.current_class]['attributes'].add(target.attr)
                        # Try to get type if possible
                        attr_type = None
                        def get_full_type(val):
                            if isinstance(val, ast.Call):
                                # Handles self.attr = ClassName(...) or self.attr = module.ClassName(...)
                                if isinstance(val.func, ast.Name):
                                    return val.func.id
                                elif isinstance(val.func, ast.Attribute):
                                    # module.ClassName -> get the full name
                                    parts = []
                                    curr = val.func
                                    while isinstance(curr, ast.Attribute):
                                        parts.append(curr.attr)
                                        curr = curr.value
                                    if isinstance(curr, ast.Name):
                                        parts.append(curr.id)
                                    return '.'.join(reversed(parts))
                            # elif isinstance(val, ast.Name):
                            #    return val.id
                            elif isinstance(val, ast.Attribute):
                                # Handles self.attr = module.ClassName or deeper
                                parts = []
                                curr = val
                                while isinstance(curr, ast.Attribute):
                                    parts.append(curr.attr)
                                    curr = curr.value
                                if isinstance(curr, ast.Name):
                                    parts.append(curr.id)
                                return '.'.join(reversed(parts))
                            return "unknown"
                        attr_type = get_full_type(node.value)
                        classes[self.current_class]['attr_types'][target.attr] = attr_type
            self.generic_visit(node)
        def visit_Call(self, node):
            if self.current_function:
                if isinstance(node.func, ast.Name):
                    functions[self.current_function].add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    functions[self.current_function].add(node.func.attr)
            self.generic_visit(node)
    tree = ast.parse(source_code)
    ModuleVisitor().visit(tree)
    return classes, functions

def build_graph(module_info_by_module):
    # Returns a dict with all relationships
    graph = {
        'type_hierarchy': defaultdict(set),  # (module, class) -> set(base_class)
        'call_hierarchy': defaultdict(set),  # (module, function) -> set((module, called_function))
        'attributes': defaultdict(set),      # (module, class) -> set(attributes)
    }
    # Type hierarchy and attributes
    for mod, info in module_info_by_module.items():
        classes = info['classes']
        functions = info['functions']
        for cls, cinfo in classes.items():
            graph['attributes'][(mod, cls)] = cinfo['attributes']
            # print(f"{mod}.{cls}: {graph['attributes'][(mod, cls)]}")
            #for att in cinfo['attributes']:
            #    print(f"{att}/{cinfo.get('attr_types').get(att)}")
            
            graph.setdefault('attr_types', {})[(mod, cls)] = cinfo.get('attr_types', {})

            for base in cinfo['bases']:
                graph['type_hierarchy'][(mod, cls)].add(base)
        for func, calls in functions.items():
            for callee in calls:
                graph['call_hierarchy'][(mod, func)].add((mod, callee))
    return graph

def store_graph_in_neo4j(graph, uri, user, password):
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        # Create module nodes
        modules = set([mod for (mod, _) in graph['attributes'].keys()] + [mod for (mod, _) in graph['call_hierarchy'].keys()])
        for mod in modules:
            session.run("MERGE (m:Module {name: $mod}) SET m.description = $desc", mod=mod, desc="This node represents a Python module.")
        # Classes and attributes
        # Gather all (module, class) pairs for lookup
        all_class_nodes = set(graph['attributes'].keys())  # (mod, cls)
        class_name_to_mods = defaultdict(list)
        fq_class_name_to_mods = defaultdict(list)
        for mod, cls in all_class_nodes:
            class_name_to_mods[cls].append(mod)
            fq_class_name_to_mods[f"{mod}.{cls}"].append(mod)
        attr_types = graph.get('attr_types', {})
        for (mod, cls), attrs in graph['attributes'].items():
            session.run("MERGE (c:Class {name: $cls, module: $mod}) SET c.description = $desc", cls=cls, mod=mod, desc="This node represents a Python class.")
            for attr in attrs:
                session.run("MERGE (a:Attribute {name: $attr}) SET a.description = $desc MERGE (c:Class {name: $cls, module: $mod}) MERGE (c)-[:contains_object]->(a)", attr=attr, cls=cls, mod=mod, desc="This node represents a Python attribute of a class.")
        # Type hierarchy
        for (mod, cls), bases in graph['type_hierarchy'].items():
            for base in bases:
                session.run(
                    "MERGE (c1:Class {name: $cls}) MERGE (c2:Class {name: $base}) MERGE (c1)-[r:inherits_from]->(c2) SET r.description = $desc",
                    cls=cls, base=base, desc="This relationship represents class inheritance."
                )
        # Functions and calls
        for (mod, func), callees in graph['call_hierarchy'].items():
            session.run("MERGE (f:Function {name: $func}) SET f.description = $desc MERGE (m:Module {name: $mod}) MERGE (m)-[r:contains_function]->(f) SET r.description = $rel_desc", func=func, mod=mod, desc="This node represents a Python function.", rel_desc="This relationship represents that a module contains a function.")
            for (callee_mod, callee_func) in callees:
                session.run("MERGE (f1:Function {name: $func}) MERGE (f2:Function {name: $callee_func}) MERGE (f1)-[r:calls]->(f2) SET r.description = $desc", func=func, callee_func=callee_func, desc="This relationship represents a function call.")
    driver.close()

def clear_neo4j_database(uri, user, password):
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    driver.close()

def parse_args():
    parser = argparse.ArgumentParser(description="Build and optionally store a Python module graph in Neo4j.")
    parser.add_argument("--srcDirs", nargs='+', type=str, help="List of source code directories to process", default=[])
    parser.add_argument("--log", type=str, default="INFO", help="Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--neo4jUri", type=str, default="bolt://localhost:7687", help="Neo4j connection URI.")
    parser.add_argument("--neo4jUser", type=str, default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4jPassword", type=str, default="password", help="Neo4j password.")
    parser.add_argument("--store", action="store_true", help="Store the graph in Neo4j.")
    parser.add_argument("--print", action="store_true", help="Print the graph to stdout.")
    parser.add_argument("--clear", action="store_true", help="Clear the Neo4j database before storing the graph.")
    return parser.parse_args()

def print_graph(graph):
    print("Type Hierarchy:")
    for (mod, cls), bases in graph['type_hierarchy'].items():
        if bases:
            print(f"{mod}.{cls} inherits: {', '.join(bases)}")
    print("\nAttributes:")
    for (mod, cls), attrs in graph['attributes'].items():
        if attrs:
            print(f"{mod}.{cls} has: {', '.join(attrs)}")
    print("\nCall Hierarchy:")
    for (mod, func), callees in graph['call_hierarchy'].items():
        if callees:
            call_str = ', '.join([f"{callee_mod}.{callee_func}" for (callee_mod, callee_func) in callees])
            print(f"{mod}.{func} calls: {call_str}")

def main():
    import logging
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger("graph_store")
    logger.info("Building Python module graph...")
    module_info_by_module = {}  # mod -> {'classes': ..., 'functions': ...}
    for package_dir in args.srcDirs:
        for root, _, files in os.walk(package_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, package_dir)
                    rel_module = rel_path.replace(os.sep, ".")
                    if rel_module.endswith(".py"):
                        rel_module = rel_module[:-3]
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    classes, functions = extract_module_info(code)
                    module_info_by_module[rel_module] = {'classes': classes, 'functions': functions}
    graph = build_graph(module_info_by_module)
    num_modules = len(set([mod for (mod, _) in graph['attributes'].keys()] + [mod for (mod, _) in graph['call_hierarchy'].keys()]))
    num_classes = len(graph['attributes'])
    num_functions = len(graph['call_hierarchy'])
    num_attributes = sum(len(attrs) for attrs in graph['attributes'].values())
    logger.info(f"Graph summary: {num_modules} modules, {num_classes} classes, {num_functions} functions, {num_attributes} attributes")
    if args.print:
        print_graph(graph)
    if args.clear and args.store:
        clear_neo4j_database(args.neo4jUri, args.neo4jUser, args.neo4jPassword)
    if args.store:
        logger.info("Storing graph in Neo4j...")
        store_graph_in_neo4j(
            graph,
            uri=args.neo4jUri,
            user=args.neo4jUser,
            password=args.neo4jPassword
        )

if __name__ == "__main__":
    main()
