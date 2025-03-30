import json
import re
from typing import List, Dict, Optional

import numpy as np
from antlr4 import InputStream, CommonTokenStream

from lang.java.JavaLexer import JavaLexer
from lang.java.JavaParser import JavaParser
from lang.java.JavaParserVisitor import JavaParserVisitor
from .const import java_lang

name2index = {}
index2name = {}
# java basic data types
java_basic_types = ["void", "int", "long", "short", "byte", "char", "float", "double", "boolean"]


def get_all_text(ctx) -> str:
    """
    Get all text of ctx
    """
    token_stream = ctx.parser.getTokenStream()
    lexer = token_stream.tokenSource
    input_stream = lexer.inputStream
    start = ctx.start.start
    stop = ctx.stop.stop
    return input_stream.getText(start, stop)


class JavaSymbol:
    """
    Java symbol info
    - sym_type: type of symbol, including class, interface, method ...
    - short_name: short name of symbol
    - full_name: global unique name of symbol
    - file_path: file path of symbol
    - start_lineno: start line number of symbol
    - stop_lineno: stop line number of symbol
    - params: method parameters
    - methods: method list
    - hierarchy: parent class or interface list
    - dependency: dependency symbol list
    """

    def __init__(self, sym_type: str, short_name: str, full_name: str, file_path: str,
                 start_lineno: int, stop_lineno: int, code: str):
        self.sym_type = sym_type
        self.short_name = short_name
        self.full_name = full_name
        self.file_path = file_path
        self.start_lineno = start_lineno
        self.stop_lineno = stop_lineno
        self.params = []
        self.methods = {}
        self.code = code
        self.hierarchy = []
        self.dependency = []

    def sym_to_dict(self):
        return {
            "sym_type": self.sym_type,
            "short_name": self.short_name,
            "full_name": self.full_name,
            "file_path": self.file_path,
            "start_lineno": self.start_lineno,
            "stop_lineno": self.stop_lineno,
            "params": self.params,
            "methods": [m.sym_to_dict() for m in self.methods.values()],
            "code": self.code,
            "hierarchy": self.hierarchy,
            "dependency": self.dependency
        }


class JavaClassCollector(JavaParserVisitor):
    """
    Java class info collector
    1. collect class info
    2. collect method info
    3. collect method params info
    This class will determine the following fields of JavaSymbol:
    (Only for instance Class, Interface, Method)
    - sym_type
    - short_name
    - full_name
    - file_path
    - start_lineno
    - stop_lineno
    - params
    - methods
    - code
    """

    def __init__(self, file_path: str):
        self.package_name = ""
        self.file_path = file_path
        self.classes: Dict[str, JavaSymbol] = {}
        self.symbols: Dict[str, JavaSymbol] = {}
        self.current_scope_symbol: Optional[JavaSymbol] = None
        self.short2full: Dict[str, str] = {}

    def _full_name(self, name: str):
        if self.current_scope_symbol:
            return f"{self.current_scope_symbol.full_name}.{name}"
        elif self.package_name:
            return f"{self.package_name}.{name}"
        else:
            return name

    def get_full_name(self, name: str):
        delimiters = r'([\[\].,<>])'
        parts = re.split(delimiters, name)
        for i in range(0, len(parts)):
            parts[i] = self.short2full.get(parts[i], parts[i])
        return ''.join(parts)

    def visitPackageDeclaration(self, ctx: JavaParser.PackageDeclarationContext):
        self.package_name = ctx.qualifiedName().getText()
        self.short2full.update(java_lang)

    def visitImportDeclaration(self, ctx: JavaParser.ImportDeclarationContext):
        full_name = ctx.qualifiedName().getText()
        if ctx.STATIC():
            raise ValueError("Static import not supported")
        if full_name.endswith(".*"):
            # 通配符导入不支持
            raise ValueError("Wildcard import not supported")
        class_name = full_name.split('.')[-1]
        self.short2full[class_name] = full_name

    def visitClassDeclaration(self, ctx: JavaParser.ClassDeclarationContext):
        class_name = ctx.identifier().getText()
        full_name = self._full_name(class_name)
        self.symbols[full_name] = JavaSymbol("Class", class_name, full_name, self.file_path,
                                             ctx.start.line, ctx.stop.line, get_all_text(ctx))
        self.classes[full_name] = self.symbols[full_name]
        self.short2full[class_name] = full_name
        original_scope_symbol = self.current_scope_symbol
        self.current_scope_symbol = self.symbols[full_name]
        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol

    def visitInterfaceDeclaration(self, ctx: JavaParser.InterfaceDeclarationContext):
        interface_name = ctx.identifier().getText()
        full_name = self._full_name(interface_name)
        self.symbols[full_name] = JavaSymbol("Interface", interface_name, full_name, self.file_path,
                                             ctx.start.line, ctx.stop.line, get_all_text(ctx))
        self.classes[full_name] = self.symbols[full_name]
        self.short2full[interface_name] = full_name
        original_scope_symbol = self.current_scope_symbol
        self.current_scope_symbol = self.symbols[full_name]
        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol

    def visit_method(self, ctx):
        param_list = []
        method_name = ctx.identifier().getText()
        # if method has parameters
        if ctx.formalParameters().formalParameterList():
            params = ctx.formalParameters().formalParameterList().formalParameter()
            param_list = [p.variableDeclaratorId().getText() for p in params]
            param_type_list = [self.get_full_name(p.typeType().getText()) for p in params]
            method_name += "(" + ",".join(param_type_list) + ")"
        full_name = self._full_name(method_name)
        self.symbols[full_name] = JavaSymbol("Method", method_name, full_name, self.file_path,
                                             ctx.start.line, ctx.stop.line, get_all_text(ctx))
        self.symbols[full_name].params = param_list
        self.short2full[method_name] = full_name
        # add method to current class or interface
        self.current_scope_symbol.methods[full_name] = self.symbols[full_name]
        original_scope_symbol = self.current_scope_symbol
        self.current_scope_symbol = self.symbols[full_name]
        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol

    def visitMethodDeclaration(self, ctx: JavaParser.MethodDeclarationContext):
        self.visit_method(ctx)

    def visitInterfaceCommonBodyDeclaration(self, ctx: JavaParser.InterfaceCommonBodyDeclarationContext):
        # interface method
        self.visit_method(ctx)


class JavaStructureVisitor(JavaParserVisitor):
    """
    Java code structure analyzer
    1. collect symbol dependency
    2. collect class interactions
    It is used to analyze the structural relationships between classes in Java code.
    This class will determine the following fields of JavaSymbol:
    - hierarchy
    - dependency
    """

    def __init__(self, file_path: str, class_stats: Dict[str, JavaSymbol], symbol_stats: Dict[str, JavaSymbol],
                 short2full: Dict[str, str], interaction_matrix: np.ndarray = None):
        self.current_package = ""
        self.file_path = file_path
        self.interaction_matrix = interaction_matrix
        self.classes = class_stats
        self.symbols = symbol_stats
        self.short2full = short2full
        # used by dependency graph
        self.current_scope_symbol: Optional[JavaSymbol] = None
        # used by interaction matrix
        self.current_class = ""

    def _short2full(self, name: str):
        if name in self.short2full:
            return self.short2full[name]
        return name

    def _add_interaction(self, source: str, target_list: List[str]):
        global name2index
        global index2name
        for target in target_list:
            if source == target:
                continue
            if not self.classes.get(source) or not self.classes.get(target):
                continue
            # add current interaction
            self.interaction_matrix[name2index[source]][name2index[target]] += 1

    def _add_dependency(self, symbol: JavaSymbol, dependency_list: List[str]):
        for dependency in dependency_list:
            # print(dependency)
            if dependency in java_lang.values() or dependency in java_basic_types:
                continue
            if dependency not in self.symbols:
                raise ValueError(f"Dependency {dependency} not found")
            symbol.dependency.append(dependency)

    def get_full_name(self, name: str):
        delimiters = r'([\[\].,<>])'
        parts = re.split(delimiters, name)
        for i in range(0, len(parts)):
            parts[i] = self.short2full.get(parts[i], parts[i])
        full_name = ''.join(parts)
        delimiters = r'[\[\]\.,<>]'
        parts = re.split(delimiters, name)
        for i in range(0, len(parts)):
            parts[i] = self.short2full.get(parts[i], parts[i])
        # remove the void part
        parts = [part for part in parts if part]
        return full_name, parts

    def visitPackageDeclaration(self, ctx: JavaParser.PackageDeclarationContext):
        self.current_package = ctx.qualifiedName().getText()

    def visitImportDeclaration(self, ctx: JavaParser.ImportDeclarationContext):
        full_name = ctx.qualifiedName().getText()
        if not self.classes.get(full_name):
            import_name = full_name.split('.')[-1]
            if not self.symbols.get(full_name):
                self.symbols[full_name] = JavaSymbol("Import", import_name, full_name, self.file_path,
                                                     ctx.start.line, ctx.stop.line, get_all_text(ctx))

    def visitClassDeclaration(self, ctx: JavaParser.ClassDeclarationContext):
        original_scope_symbol = self.current_scope_symbol
        class_name = ctx.identifier().getText()
        class_symbol = self.classes[self.short2full[class_name]]

        if ctx.EXTENDS():
            super_type, super_type_list = self.get_full_name(ctx.typeType().getText())
            class_symbol.hierarchy.append(super_type)
            self._add_dependency(class_symbol, super_type_list)
            self._add_interaction(class_symbol.full_name, super_type_list)

        if ctx.IMPLEMENTS():
            for interface in ctx.typeList():
                interface_name, interface_type_list = self.get_full_name(interface.getText())
                class_symbol.hierarchy.append(interface_name)
                self._add_dependency(class_symbol, interface_type_list)
                self._add_interaction(class_symbol.full_name, interface_type_list)

        original_class = self.current_class
        self.current_scope_symbol = class_symbol
        self.current_class = class_symbol.full_name
        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol
        self.current_class = original_class

    def visitInterfaceDeclaration(self, ctx: JavaParser.InterfaceDeclarationContext):
        original_scope_symbol = self.current_scope_symbol
        interface_name = ctx.identifier().getText()
        interface_symbol = self.classes[self.short2full[interface_name]]

        if ctx.EXTENDS():
            for interface in ctx.typeList():
                interface_name, interface_type_list = self.get_full_name(interface.getText())
                interface_symbol.hierarchy.append(interface_name)
                self._add_dependency(interface_symbol, interface_type_list)
                self._add_interaction(interface_symbol.full_name, interface_type_list)

        original_class = self.current_class
        self.current_scope_symbol = interface_symbol
        self.current_class = interface_symbol.full_name
        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol
        self.current_class = original_class

    def visitFieldDeclaration(self, ctx: JavaParser.FieldDeclarationContext):
        """like code: private String name;"""
        _, field_type_list = self.get_full_name(ctx.typeType().getText())
        self._add_dependency(self.current_scope_symbol, field_type_list)
        self._add_interaction(self.current_class, field_type_list)

    def visit_method(self, ctx):
        original_scope_symbol = self.current_scope_symbol
        method_name = ctx.identifier().getText()
        params = ctx.formalParameters().formalParameterList()
        if params:
            param_type_list = [self.get_full_name(p.typeType().getText())[0] for p in params.formalParameter()]
            method_name += "(" + ",".join(param_type_list) + ")"
        method_symbol = self.symbols[self.short2full[method_name]]
        self._add_dependency(self.current_scope_symbol, [method_symbol.full_name])
        self.current_scope_symbol = method_symbol

        # handle return type
        _, return_type_list = self.get_full_name(ctx.typeTypeOrVoid().getText())
        self._add_dependency(method_symbol, return_type_list)
        self._add_interaction(self.current_class, return_type_list)

        # handle params type
        if params:
            for param in params.formalParameter():
                _, param_type_list = self.get_full_name(param.typeType().getText())
                self._add_dependency(method_symbol, param_type_list)
                self._add_interaction(self.current_class, param_type_list)

        self.visitChildren(ctx)
        self.current_scope_symbol = original_scope_symbol

    def visitMethodDeclaration(self, ctx: JavaParser.MethodDeclarationContext):
        self.visit_method(ctx)

    def visitInterfaceCommonBodyDeclaration(self, ctx: JavaParser.InterfaceCommonBodyDeclarationContext):
        # interface method
        self.visit_method(ctx)

    def visitLocalVariableDeclaration(self, ctx: JavaParser.LocalVariableDeclarationContext):
        _, var_type_list = self.get_full_name(ctx.typeType().getText())
        self._add_dependency(self.current_scope_symbol, var_type_list)
        self._add_interaction(self.current_class, var_type_list)

    def visitMethodCall(self, ctx: JavaParser.MethodCallContext):
        # _, method_type_list = self.get_full_name(ctx.expression().getText())
        # self._add_dependency(self.current_scope_symbol, method_type_list)
        # self._add_interaction(self.current_class, method_type_list)
        # print(ctx.getText())
        self.visitChildren(ctx)


class JavaStaticProfiler:
    """
    Java 代码结构分析
    结构交互矩阵（Structural Interactions Matrix）：
        数据来源：源代码中的结构关系（继承、参数类型、方法调用等）
        计算：统计类间结构交互次数，形成 N * N 矩阵（N为总类数）
    """

    def __init__(self, files_list: List[str]):
        # project files list
        self.files_list = files_list
        self.project_class_stats: Dict[str, JavaSymbol] = {}
        self.project_symbol_stats: Dict[str, JavaSymbol] = {}
        self.project_short2full: Dict[str, Dict[str, str]] = {}
        self.interaction_matrix: Optional[np.ndarray] = None

    def _name_to_index(self):
        global name2index
        name2index = {cls: i for i, cls in enumerate(self.project_class_stats.keys())}

    def _index_to_name(self):
        global index2name
        index2name = {i: cls for i, cls in enumerate(self.project_class_stats.keys())}

    def collect_class_stats(self) -> Dict[str, JavaSymbol]:
        for java_file in self.files_list:
            collector = JavaClassCollector(java_file)
            with open(java_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
            try:
                input_stream = InputStream(source_code)
                lexer = JavaLexer(input_stream)
                token_stream = CommonTokenStream(lexer)
                parser = JavaParser(token_stream)
                tree = parser.compilationUnit()
                tree.accept(collector)
                tree.accept(collector)
                self.project_class_stats.update(collector.classes)
                self.project_symbol_stats.update(collector.symbols)
                self.project_short2full[java_file] = collector.short2full
            except Exception as e:
                print(f"[JavaStaticProfiler::collect_class_stats] analyzing {java_file} occurs error: {e}")
        self._name_to_index()
        self._index_to_name()
        class_num = len(self.project_class_stats)
        self.interaction_matrix = np.zeros((class_num, class_num), dtype=int)
        return self.project_class_stats

    def analyze_structure(self):
        for java_file in self.files_list:
            tracer = JavaStructureVisitor(java_file, self.project_class_stats, self.project_symbol_stats,
                                          self.project_short2full[java_file], self.interaction_matrix)
            with open(java_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
            try:
                input_stream = InputStream(source_code)
                lexer = JavaLexer(input_stream)
                token_stream = CommonTokenStream(lexer)
                parser = JavaParser(token_stream)
                tree = parser.compilationUnit()
                tree.accept(tracer)
            except Exception as e:
                print(f"[JavaStaticProfiler::analyze_structure] analyzing {java_file} occurs error: {e}")

    def profile(self, inherited: bool = False):
        self.collect_class_stats()
        self.analyze_structure()
        # if child class inherited interactions from father class
        if inherited:
            for stats in self.project_class_stats.values():
                self.solve_inherited_interaction(stats)
        return self.project_class_stats

    def solve_inherited_interaction(self, cls: JavaSymbol):
        if not cls.hierarchy:
            return self.interaction_matrix[name2index[cls.full_name]]
        else:
            for super_cls in cls.hierarchy:
                self.interaction_matrix[name2index[cls.full_name]] += self.solve_inherited_interaction(
                    self.project_class_stats[super_cls])

    def print_interaction_matrix(self):
        for i, row in enumerate(self.interaction_matrix):
            cls = index2name[i]
            row_text = [f"{index2name[j]}({count})" for j, count in enumerate(row) if count > 0]
            print(f"{cls} -> {row_text}")

    def save_class_stats(self, save_path):
        with open(save_path, 'w', encoding='utf-8') as file:
            json.dump([v.sym_to_dict() for v in self.project_class_stats.values()], file, indent=4)

    def save_symbol_stats(self, save_path):
        with open(save_path, 'w', encoding='utf-8') as file:
            json.dump([v.sym_to_dict() for v in self.project_symbol_stats.values()], file, indent=4)

    def save_interaction_matrix(self, save_path):
        np.save(save_path, self.interaction_matrix)
