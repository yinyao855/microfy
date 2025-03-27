import ast
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Set, Dict, Optional, Tuple, List
from .ast_symtable import SymbolTableBuilder, Scope, Symbol
from .const import builtin_funcs


# 记录函数依赖
@dataclass
class DependencyNode:
    name: str  # 依赖的名称
    full_name: str  # 依赖的全名, 会加上作用域
    type: str  # 依赖的类型, 如function, class, variable, module
    node: ast.AST
    args: Set[str] = field(default_factory=set)  # 依赖的参数, 只有函数有
    dependencies: Dict[str, "DependencyNode"] = field(default_factory=dict)

    def depend_to_json(self) -> Dict:
        return {
            'name': self.name,
            'full_name': self.full_name,
            'type': self.type,
            'args': list(self.args),
            'node_type': self.node.__class__.__name__,
            'lineno': self.node.lineno,
            'dependencies': [dep.depend_to_sim_json() for dep in self.dependencies.values()]
        }

    def depend_to_sim_json(self) -> Dict:
        return {
            'name': self.name,
            'full_name': self.full_name,
            'type': self.type,
            'lineno': self.node.lineno,
        }


class DependencyTracer(ast.NodeVisitor):
    def __init__(self, source_code: str, module_name: str = "main"):
        self.source_code: str = source_code
        self.module_name: str = module_name
        self.sym_table: SymbolTableBuilder = SymbolTableBuilder(module_name)
        self.tree: Optional[ast.AST] = None
        # 依赖关系图，键是符号的全局名字
        self.depend_map: Dict[str, DependencyNode] = defaultdict(DependencyNode)
        # 当前作用域节点，追踪类和函数的依赖
        self.scope_node: Optional[ast.AST] = None
        # 记录当前符号
        self.cur_sym: List[Symbol] = []
        # 记录需要拆分的函数
        self.obj_func: Dict[str, ast.AST] = {}

    @property
    def cur_scope(self) -> Scope:
        return self.sym_table.node_to_scope[self.scope_node]

    def get_syms_info(self) -> None:
        self.sym_table.node_to_scope[self.tree] = self.sym_table.root_scope
        self.sym_table.visit(self.tree)

    def get_node_source(self, node: ast.AST) -> str:
        """Extract source code for a given AST node"""
        lines = self.source_code.splitlines()
        return '\n'.join(lines[node.lineno - 1:node.end_lineno])

    def get_symbol(self, sym_name: str) -> Optional[Symbol]:
        return self.sym_table.resolve_symbol(sym_name, self.cur_scope)

    def undefined_sym_error(self, sym_name: str, sym_node: ast.AST) -> ValueError:
        return ValueError(f"Symbol {sym_name} not defined ({self.module_name} line {sym_node.lineno})")

    # 根据symbol在依赖图中添加节点
    def new_depend_node(self, symbol: Symbol) -> DependencyNode:
        if not self.depend_map.get(symbol.full_name):
            self.depend_map[symbol.full_name] = DependencyNode(symbol.name, symbol.full_name, symbol.type, symbol.node)
        return self.depend_map[symbol.full_name]

    def add_dependency(self, symbols: List[Symbol], depend_node: DependencyNode) -> None:
        for symbol in symbols:
            if not self.depend_map.get(symbol.full_name):
                self.depend_map[symbol.full_name] = depend_node
            self.depend_map[symbol.full_name].dependencies[depend_node.full_name] = depend_node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # 处理函数定义节点
        if node.name == "get_user":
            self.obj_func[node.name] = node
        symbol = self.get_symbol(node.name)
        if not symbol:
            self.undefined_sym_error(node.name, node)
        depend = self.new_depend_node(symbol)
        # 这里不考虑变长参数
        for arg in node.args.args:
            depend.args.add(arg.arg)
        tmp_node = self.scope_node
        tmp_sym = self.cur_sym
        self.scope_node = node
        self.cur_sym = [symbol]
        self.generic_visit(node)
        self.scope_node = tmp_node
        self.cur_sym = tmp_sym

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # 处理类定义节点
        symbol = self.get_symbol(node.name)
        if not symbol:
            self.undefined_sym_error(node.name, node)
        self.new_depend_node(symbol)
        tmp_node = self.scope_node
        tmp_sym = self.cur_sym
        self.scope_node = node
        self.cur_sym = [symbol]
        self.generic_visit(node)
        self.scope_node = tmp_node
        self.cur_sym = tmp_sym

    def visit_Assign(self, node: ast.Assign) -> None:
        # 处理赋值节点
        sym_list = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                symbol = self.get_symbol(target.id)
                if not symbol:
                    self.undefined_sym_error(target.id, node)
                sym_list.append(symbol)
                self.new_depend_node(symbol)

        tmp_sym = self.cur_sym
        self.cur_sym = sym_list
        self.generic_visit(node)
        self.cur_sym = tmp_sym

    def visit_Import(self, node: ast.Import) -> None:
        # 记录导入的库
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            symbol = self.get_symbol(name)
            if not symbol:
                self.undefined_sym_error(name, node)
            depend = self.new_depend_node(symbol)
            if self.cur_sym:
                self.add_dependency(self.cur_sym, depend)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # 若在目标函数内，记录从指定模块导入的库
        for alias in node.names:
            name = alias.asname or alias.name
            symbol = self.get_symbol(name)
            if not symbol:
                self.undefined_sym_error(name, node)
            depend = self.new_depend_node(symbol)
            if self.cur_sym:
                self.add_dependency(self.cur_sym, depend)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id not in builtin_funcs:
            symbol = self.get_symbol(node.id)
            if not symbol:
                self.undefined_sym_error(node.id, node)
            depend = self.new_depend_node(symbol)
            if self.cur_sym:
                self.add_dependency(self.cur_sym, depend)
        self.generic_visit(node)

    def analyze(self, root_node: ast.AST) -> Tuple[Dict[str, DependencyNode], Dict[str, ast.AST]]:
        self.tree = root_node
        self.get_syms_info()
        self.scope_node = root_node
        self.visit(root_node)
        return self.depend_map, self.obj_func

    def save_analysis(self, output_file: str = "dependency.json") -> None:
        # 用json库导出
        with open(output_file, "w") as f:
            json.dump([node.depend_to_json() for node in self.depend_map.values()], f, indent=4)
