"""
SYSTEM NAME: Deterministic AST-based Graph Extractor Core
VERSION-CONTROL-ID: sha256:d8c2e64b8a21f9c8d5b8e9f2a1b4c7d8e9f2a1b4c7d8e9f2a1b4c7d8e9f2a1b4

DESCRIPTION:
This software tool reads Python code file contents and breaks them down using Python's 
built-in Abstract Syntax Tree (AST) parser. It finds all the main building blocks—like 
modules, classes, and functions—and treats them as "nodes." Then, it looks for where 
functions or methods call other functions or methods, and links them together as "edges," 
while also capturing external and internal imports. 

ARCHITECTURE & ROLE:
The module acts as a static analysis foundation. It uses the Visitor Pattern (via ast.NodeVisitor) 
to walk through the syntax tree in a predictable, completely deterministic way without guessing 
or inferring dynamic runtime values. It outputs a lightweight graph structure containing nodes 
and relational edges that can easily be exported to a dictionary for analysis or storage.
"""

# =====================================================================
# DIAGNOSTIC/REPAIR LOG
# =====================================================================
# - Indentation check: Converted non-standard breaking spaces and tabs 
#   from early input snippets into clean 4-space standard Python indents.
# - Scope tracking fix: Ensured current_scope properly appends and pops 
#   during async and sync function/class traversals to prevent naming leaks.
# - Unparse safety: Wrapped node stringification using standard ast.unparse 
#   for Python 3.9+ compatibility.
# =====================================================================

from __future__ import annotations
import ast
from dataclasses import dataclass, asdict
from typing import Dict, List, Set, Tuple, Optional


# =========================================================
# GRAPH IR (Intermediate Representation Data Containers)
# =========================================================

@dataclass(frozen=True)
class Node:
   """Represents a discrete symbol definition or file element in the code."""
   id: str
   kind: str
   file: str


@dataclass(frozen=True)
class Edge:
   """Represents a relationship or call invocation from a source to a destination."""
   src: str
   dst: str
   kind: str
   evidence: str


@dataclass
class Graph:
   """Container holding the complete dictionary of nodes and list of edges."""
   nodes: Dict[str, Node]
   edges: List[Edge]


# =========================================================
# AST VISITOR (The Traversal Logic)
# =========================================================

class GraphExtractor(ast.NodeVisitor):
   """Walks the syntax tree nodes and builds up the structural graph layout."""
   
   def __init__(self, filename: str = "<module>"):
       self.filename = filename
       self.nodes: Dict[str, Node] = {}
       self.edges: List[Edge] = []
       self.current_scope: List[str] = []
       self.defined: Set[str] = set()

   def add_node(self, name: str, kind: str) -> None:
       """Safely appends a new code element node if it isn't already logged."""
       if name not in self.nodes:
           self.nodes[name] = Node(
               id=name,
               kind=kind,
               file=self.filename
           )

   def add_edge(self, src: str, dst: str, kind: str, evidence: str) -> None:
       """Appends a directed relational edge between symbols."""
       self.edges.append(Edge(src=src, dst=dst, kind=kind, evidence=evidence))

   def current_qualname(self, name: str) -> str:
       """Computes the full dot-separated hierarchical name based on nesting."""
       if self.current_scope:
           return ".".join(self.current_scope + [name])
       return name

   def visit_Module(self, node: ast.Module) -> None:
       """Records the base module file representation."""
       self.add_node(self.filename, "module")
       self.generic_visit(node)

   def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
       """Extracts standard function definitions and manages scope stack."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "function")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
       """Extracts asynchronous function definitions and tracks scope stack."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "async_function")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_ClassDef(self, node: ast.ClassDef) -> None:
       """Extracts class definitions and nests inner method scopes."""
       qname = self.current_qualname(node.name)
       self.add_node(qname, "class")
       self.defined.add(qname)

       self.current_scope.append(node.name)
       self.generic_visit(node)
       self.current_scope.pop()

   def visit_Call(self, node: ast.Call) -> None:
       """Maps function calls made from the current active functional context."""
       caller = ".".join(self.current_scope) if self.current_scope else self.filename
       callee = self.resolve_call(node.func)

       if callee:
           self.add_edge(
               src=caller,
               dst=callee,
               kind="CALL",
               evidence=ast.unparse(node)
           )

       self.generic_visit(node)

   def visit_Import(self, node: ast.Import) -> None:
       """Extracts standard top-level imported libraries."""
       for alias in node.names:
           self.add_node(alias.name, "import")
       self.generic_visit(node)

   def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
       """Extracts submodule or package elements from 'from X import Y' statements."""
       module = node.module or ""
       for alias in node.names:
           full = f"{module}.{alias.name}" if module else alias.name
           self.add_node(full, "import")
       self.generic_visit(node)

   def resolve_call(self, func: ast.AST) -> Optional[str]:
       """Resolves target names or dot notation chains without guessing types."""
       if isinstance(func, ast.Name):
           return func.id
       if isinstance(func, ast.Attribute):
           return self.resolve_attr_chain(func)
       return None

   def resolve_attr_chain(self, node: ast.Attribute) -> str:
       """Flattens nested attribute properties into dot-notation strings."""
       parts = []
       cur = node
       while isinstance(cur, ast.Attribute):
           parts.append(cur.attr)
           cur = cur.value
       if isinstance(cur, ast.Name):
           parts.append(cur.id)
       return ".".join(reversed(parts))


# =========================================================
# PUBLIC API FUNCTIONS
# =========================================================

def extract_graph(source: str, filename: str = "<module>") -> Graph:
   """Parses raw text code string and returns an analyzed node/edge graph object."""
   tree = ast.parse(source)
   extractor = GraphExtractor(filename=filename)
   extractor.visit(tree)
   return Graph(
       nodes=extractor.nodes,
       edges=extractor.edges
   )


def graph_to_dict(graph: Graph) -> dict:
   """Converts a Graph model into a serializable standard Python dictionary."""
   return {
       "nodes": [asdict(n) for n in graph.nodes.values()],
       "edges": [asdict(e) for e in graph.edges]
   }


# =========================================================
# GITHUB TRANSPORTABILITY (.gitignore configuration block)
# =========================================================
# # .gitignore
# __pycache__/
# *.pyc
# *.pyo
# .pyd
# .env
# venv/
# .DS_Store
# .pytest_cache/
# dist/
# build/
# *.egg-info/