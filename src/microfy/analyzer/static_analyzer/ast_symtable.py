import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional, List
from .const import builtin_funcs


# 根据AST构建符号表

@dataclass
class Symbol:
    """
    表示一个符号的类，用于存储符号的相关信息。

    Attributes:
        name (str): 符号的名称。
        type (str): 符号的类型，如 'function', 'class', 'variable' 等。
        node (ast.AST): 与符号关联的抽象语法树（AST）节点。
        is_local (bool, optional): 指示符号是否为局部变量，默认为 False。
        is_declared_global (bool, optional): 指示符号是否为声明的全局变量，默认为 False。
        is_nonlocal (bool, optional): 指示符号是否为非局部变量，默认为 False。
    """
    name: str
    full_name: str
    type: str
    node: ast.AST
    is_local: bool = False
    is_declared_global: bool = False
    is_nonlocal: bool = False

    def symbol_to_json(self) -> Dict:
        return {
            'symbol_name': self.name,
            # 'full_name': self.full_name,
            'type': self.type,
            'is_local': self.is_local,
            'is_declared_global': self.is_declared_global,
            'is_nonlocal': self.is_nonlocal,
            'node_type': self.node.__class__.__name__,
            'lineno': self.node.lineno
        }


class Scope:
    """表示一个作用域，包含符号及其子作用域。"""

    def __init__(self, name, parent=None, node=None):
        self.name: str = name  # 作用域名称（如函数名、类名或模块名）
        self.parent: str = parent  # 父作用域
        self.node: ast.AST = node  # 关联的AST节点（针对函数/类）
        self.symbols: Dict[str, Symbol] = defaultdict(Symbol)  # 符号字典
        self.nonlocals: Dict[str, Symbol] = defaultdict(Symbol)  # 非局部变量
        self.declared_globals: Dict[str, Symbol] = defaultdict(Symbol)  # 全局变量
        self.children: List[Scope] = []  # 子作用域

    def add_child(self, child) -> None:
        """添加子作用域"""
        self.children.append(child)

    def add_symbol(self, name: str, symbol_type: str, node: ast.AST, is_local=False, is_declared_global=False,
                   is_nonlocal=False) -> None:
        """在当前作用域添加符号"""
        full_name = f"{self.name}.{name}"
        symbol = Symbol(name, full_name, symbol_type, node, is_local, is_declared_global, is_nonlocal)
        if is_nonlocal:
            self.nonlocals[name] = symbol
        elif is_declared_global:
            self.declared_globals[name] = symbol
        else:
            self.symbols[name] = symbol

    def scope_to_json(self) -> Dict:
        """将作用域及其子作用域转换为JSON格式"""
        return {
            'scope_name': self.name,
            'ast_node': str(self.node.__class__.__name__) if self.node else None,
            'symbols': [symbol.symbol_to_json() for symbol in self.symbols.values()],
            'nonlocals': [symbol.symbol_to_json() for symbol in self.nonlocals.values()],
            'declared_globals': [symbol.symbol_to_json() for symbol in self.declared_globals.values()],
            'children': [child.scope_to_json() for child in self.children],
        }


class SymbolTableBuilder(ast.NodeVisitor):
    """使用AST遍历构建符号表"""

    def __init__(self, module_name: str = 'global'):
        self.root_scope: Scope = Scope(module_name, node=None)  # 全局作用域
        self.current_scope: Scope = self.root_scope
        self.scope_stack: List[Scope] = [self.current_scope]  # 作用域栈
        self.node_to_scope: Dict[ast.AST, Scope] = {}  # AST节点到作用域的映射

    def _clear(self) -> None:
        self.current_scope = self.root_scope
        self.scope_stack = [self.current_scope]
        self.node_to_scope = {}

    def _enter_scope(self, name: str, node: ast.AST) -> None:
        """进入新作用域"""
        full_name = f"{self.current_scope.name}.{name}"
        new_scope = Scope(full_name, self.current_scope, node)
        self.current_scope.add_child(new_scope)
        self.scope_stack.append(new_scope)
        self.current_scope = new_scope
        self.node_to_scope[node] = new_scope  # 记录节点到作用域的映射

    def _leave_scope(self) -> None:
        """离开当前作用域"""
        self.scope_stack.pop()
        self.current_scope = self.scope_stack[-1] if self.scope_stack else None

    def resolve_symbol(self, name: str, cur_scope: Scope, check_global: bool = False) -> Optional[Symbol]:
        """解析符号所在作用域"""
        scope = cur_scope
        if check_global:
            while scope.parent is not None:
                scope = scope.parent
            return scope.symbols.get(name)

        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """处理函数定义"""
        self.current_scope.add_symbol(node.name, 'function', node)
        self._enter_scope(node.name, node)
        # 处理参数
        args = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            *([node.args.vararg] if node.args.vararg else []),
            *([node.args.kwarg] if node.args.kwarg else [])
        ]
        for arg in args:
            self.current_scope.add_symbol(arg.arg, 'argument', arg)
        self.generic_visit(node)  # 继续遍历函数体
        self._leave_scope()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """处理类定义"""
        self.current_scope.add_symbol(node.name, 'class', node)
        self._enter_scope(node.name, node)
        self.generic_visit(node)  # 继续遍历类体
        self._leave_scope()

    # def visit_Call(self, node: ast.Call) -> None:
    #     """处理函数调用"""
    #     if isinstance(node.func, ast.Name):
    #         func_name = node.func.id
    #         if func_name not in builtin_funcs:
    #             if not self.resolve_symbol(func_name, self.current_scope):
    #                 raise Exception(f"Undefined function '{func_name}' at line {node.lineno}")
    #     # 属性调用暂时不处理
    #     self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        """处理非局部变量"""
        for name in node.names:
            self.current_scope.add_symbol(name, 'variable', node, is_nonlocal=True)
            # 验证外层作用域是否存在
            outer = self.current_scope.parent
            found = False
            while outer and outer.parent is not None:  # 只检查非全局外层
                if name in outer.symbols:
                    found = True
                    break
                outer = outer.parent
            if not found:
                raise Exception(f"Nonlocal '{name}' not found (line {node.lineno})")

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self.current_scope.add_symbol(name, 'variable', node, is_declared_global=True)
            if not self.resolve_symbol(name, self.current_scope, check_global=True):
                raise Exception(f"Global '{name}' not defined (line {node.lineno})")

    def visit_Assign(self, node: ast.Assign) -> None:
        """处理赋值语句"""
        for target in node.targets:
            self._handle_assignment(target, node)
        self.generic_visit(node)

    def _handle_assignment(self, target: ast.expr, node: ast.AST) -> None:
        if isinstance(target, ast.Name):
            name = target.id
            if self.current_scope.nonlocals.get(name):
                return  # 跳过非局部变量
            if self.current_scope.declared_globals.get(name):
                return  # 跳过全局变量
            self.current_scope.add_symbol(name, 'variable', node, is_local=True)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._handle_assignment(elt, node)

    def visit_For(self, node: ast.For) -> None:
        """处理for循环变量"""
        self._handle_assignment(node.target, node)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """处理with语句变量"""
        for item in node.items:
            if item.optional_vars:
                self._handle_assignment(item.optional_vars, node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """处理import语句"""
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.current_scope.add_symbol(name, 'module', node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """处理from...import语句"""
        for alias in node.names:
            name = alias.asname or alias.name
            self.current_scope.add_symbol(name, 'module', node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """处理异常处理程序"""
        if node.name is not None:
            self.current_scope.add_symbol(node.name, 'variable', node)
        self.generic_visit(node)


# 示例用法
if __name__ == "__main__":
    code = """
import sys
y = 10

# 装饰器函数
def decorate(func):
    def wrapper(*args):
        print('调用装饰器函数')
        print(z)
        return func(*args)
    return wrapper

@decorate
def func(a, b=2):
    global y
    x = a + b
    y = 6
    class Inner:
        def method(self, c):
            d = c
    for i in range(10):
        pass
"""
    tree = ast.parse(code)
    """构建符号表"""
    builder = SymbolTableBuilder('test_demo')
    builder.visit(tree)
    # 保存到文件中
    with open('symtable.json', 'w') as f:
        json.dump(builder.root_scope.scope_to_json(), f, indent=4)
