"""
SYSTEM_NAME: STRIDE (Secure Telemetry Runtime and Intelligence Deterministic Engine)
SUB_MODULE: AST-Based Deterministic Graph Extractor & Structural Analyzer
VERSION-CONTROL-ID: STRIDE-AST-GRAPH-V7.0.0-SHA256-F8E9D2

SYSTEM_DESCRIPTION:
This script converts Python source code into an intermediate graph representation (IR)
consisting of nodes (modules, classes, async/sync functions, and imports) and directed edges
(representing direct function or method calls). It utilizes the native `ast` module 
without performing speculative type inference.
"""

from __future__ import annotations



import ast
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Set


# =========================================================
# GRAPH INTERMEDIATE REPRESENTATION (IR) DATA STRUCTURES
# =========================================================

@dataclass(frozen=True)
class Node:
   """Represents a discrete structural symbol or module file within the parsed code."""
   id: str
   kind: str
   file: str


@dataclass(frozen=True)
class Edge:
   """Represents a directed relationship (e.g., function call) from source to destination."""
   src: str
   dst: str
   kind: str
   evidence: str


@dataclass
class Graph:
   """Container holding the global symbol dictionary and directed edge list."""
   nodes: Dict[str, Node]
   edges: List[Edge]


# =========================================================
# AST VISITOR LOGIC ENGINE
# =========================================================

class GraphExtractor(ast.NodeVisitor):
   """Walks the Abstract Syntax Tree to extract declarations, calls, and relationships."""
   
   def __init__(self, filename: str = "<module>"):
       self.filename = filename
       self.nodes: Dict[str, Node] = {}
       self.edges: List[Edge] = []
       self.current_scope: List[str] = []
       self.defined: Set[str] = set()

   def add_node(self, name: str, kind: str):
       """Registers a unique symbol node if it does not already exist."""
       if name not in self.nodes:
           self.nodes[name] = Node(id=name, kind=kind, file=self.filename)

   def add_edge(self, src: str, dst: str, kind: str, evidence: str):
       """Appends a directed edge documenting a specific invocation relationship."""
       self.edges.append(Edge(src=src, dst=dst, kind=kind, evidence=evidence))

   def current_qualname(self, name: str) -> str:
       """Computes the fully qualified path name for scoped symbols."""
       if self.current_scope:
           return ".".join(self.current_scope + [name])
       return name

   def visit_Module(self, node: ast.Module):
       """Visits root module declarations."""
       self.add_node(self.filename, "module")
       self.generic_visit(node)

   def visit_FunctionDef(self, node: ast.FunctionDef):
       """Visits standard synchronous function definitions."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "function")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
       """Visits asynchronous function definitions."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "async_function")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_ClassDef(self, node: ast.ClassDef):
       """Visits structural object-oriented class definitions."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "class")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_Call(self, node: ast.Call):
       """Extracts functional invocation edges from callable expressions."""
       caller = ".".join(self.current_scope) if self.current_scope else self.filename
       callee = self.resolve_call(node.func)

       if callee:
           self.add_edge(src=caller, dst=callee, kind="CALL", evidence=ast.unparse(node))

       self.generic_visit(node)

   def visit_Import(self, node: ast.Import):
       """Extracts direct module import statements."""
       for alias in node.names:
           self.add_node(alias.name, "import")
       self.generic_visit(node)

   def visit_ImportFrom(self, node: ast.ImportFrom):
       """Extracts localized import items from parent modules."""
       module = node.module or ""
       for alias in node.names:
           full = f"{module}.{alias.name}" if module else alias.name
           self.add_node(full, "import")
       self.generic_visit(node)

   def resolve_call(self, func: ast.AST) -> Optional[str]:
       """Deterministically resolves direct naming call targets or attribute hierarchies."""
       if isinstance(func, ast.Name):
           return func.id
       if isinstance(func, ast.Attribute):
           return self.resolve_attr_chain(func)
       return None

   def resolve_attr_chain(self, node: ast.Attribute) -> str:
       """Unwinds dotted attribute naming sequences (e.g., obj.sub.method)."""
       parts = []
       cur = node
       while isinstance(cur, ast.Attribute):
           parts.append(cur.attr)
           cur = cur.value
       if isinstance(cur, ast.Name):
           parts.append(cur.id)
       return ".".join(reversed(parts))


# =========================================================
# PUBLIC EXTRACTION INTERFACES
# =========================================================

def extract_graph(source: str, filename: str = "<module>") -> Graph:
   """Parses raw source strings and executes the extraction visitor pattern."""
   tree = ast.parse(source)
   extractor = GraphExtractor(filename=filename)
   extractor.visit(tree)
   return Graph(nodes=extractor.nodes, edges=extractor.edges)


def graph_to_dict(graph: Graph) -> dict:
   """Serializes extracted graph models into a dictionary representation."""
   return {
       "nodes": [asdict(n) for n in graph.nodes.values()],
       "edges": [asdict(e) for e in graph.edges]
   }


# =========================================================
# REPOSITORY HYGIENE (.gitignore)
# =========================================================
"""
# .gitignore
__pycache__/
*.pyc
*.env
ast_graph_output/
.DS_Store
"""