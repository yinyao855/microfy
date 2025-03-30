from typing import List, Dict

import numpy as np
from antlr4 import InputStream, CommonTokenStream

from stats.java.profiler import JavaSymbol
from lang.java.JavaLexer import JavaLexer
from lang.java.JavaParser import JavaParser
from lang.java.JavaParserVisitor import JavaParserVisitor

"""
Java 代码结构分析
结构交互矩阵（Structural Interactions Matrix）：
    数据来源：源代码中的结构关系（继承、参数类型、方法调用等）
    计算：统计类间结构交互次数，形成 N * N 矩阵（N为总类数）
"""

"""
注意事项
1. 泛型处理
    代码使用 .split('<')[0] 剥离泛型参数，例如：
    - List<User> → 保留 List
    - Map<String, Object> → 保留 Map
2. 包名处理
    实现完整包名处理，包括不同包里的同名类
3. 继承关系
    可以设置子类是否继承父类的结构交互
"""

name2index = {}
index2name = {}


class JavaStructureVisitor(JavaParserVisitor):
    def __init__(self, global_class_stats: Dict[str, JavaSymbol] = None, interaction_matrix: np.ndarray = None):
        # 全局类信息
        self.global_class_stats = global_class_stats
        self.interaction_matrix = interaction_matrix
        self.current_class = None
        self.current_package = ""
        self.import_mappings = {}  # 短类名 -> 全限定名

    def visitPackageDeclaration(self, ctx: JavaParser.PackageDeclarationContext):
        # 获取当前包名
        self.current_package = ctx.qualifiedName().getText()
        self.visitChildren(ctx)

    def visitImportDeclaration(self, ctx: JavaParser.ImportDeclarationContext):
        # 记录完整导入信息
        full_name = ctx.qualifiedName().getText()
        if ctx.STATIC():
            return  # 忽略静态导入

        if full_name.endswith(".*"):
            # 通配符导入未处理完善
            package = full_name[:-2]
            self.import_mappings[package] = package
        else:
            class_name = full_name.split('.')[-1]
            self.import_mappings[class_name] = full_name

    def resolve_type(self, type_name: str) -> str:
        """解析类型全限定名"""
        # 处理数组和泛型
        base_type = type_name.split('<')[0].split('[')[0].strip()

        # 优先检查完整限定名
        if base_type in self.import_mappings:
            return self.import_mappings[base_type]

        return base_type

    def visitClassDeclaration(self, ctx: JavaParser.ClassDeclarationContext):
        # 获取完整类名
        original_class = self.current_class
        class_name = ctx.identifier().getText()
        full_class_name = f"{self.current_package}.{class_name}" if self.current_package else class_name

        # 注册当前类
        self.current_class = full_class_name
        self.import_mappings[class_name] = full_class_name

        # 处理继承关系
        if ctx.EXTENDS():
            super_type = self.resolve_type(ctx.typeType().getText())
            self.global_class_stats[full_class_name].hierarchy.append(super_type)
            self._add_interaction(full_class_name, super_type)

        # 处理接口实现
        if ctx.IMPLEMENTS():
            for interface in ctx.typeList().typeType():
                interface_name = self.resolve_type(interface.getText())
                self.global_class_stats[full_class_name].hierarchy.append(interface_name)
                self._add_interaction(full_class_name, interface_name)

        self.visitChildren(ctx)
        self.current_class = original_class

    def _add_interaction(self, source: str, target: str):
        """添加交互关系并处理继承传递"""
        if source == target:
            return
        if not self.global_class_stats.get(target):
            return
        # 添加当前交互
        self.interaction_matrix[name2index[source]][name2index[target]] += 1

    def visitFieldDeclaration(self, ctx: JavaParser.FieldDeclarationContext):
        if self.current_class:
            field_type = self.resolve_type(ctx.typeType().getText())
            self._add_interaction(self.current_class, field_type)
        self.visitChildren(ctx)

    def visitMethodDeclaration(self, ctx: JavaParser.MethodDeclarationContext):
        if self.current_class:
            # 返回类型
            # return_type = self.resolve_type(ctx.typeTypeOrVoid().getText())
            # self._add_interaction(self.current_class, return_type)

            # 参数类型
            params = ctx.formalParameters().formalParameterList()
            if params:
                for param in params.formalParameter():
                    param_type = self.resolve_type(param.typeType().getText())
                    self._add_interaction(self.current_class, param_type)

        self.visitChildren(ctx)

    def visitLocalVariableDeclaration(self, ctx: JavaParser.LocalVariableDeclarationContext):
        if self.current_class:
            var_type = self.resolve_type(ctx.typeType().getText())
            self._add_interaction(self.current_class, var_type)
        self.visitChildren(ctx)

    # def visitExpression(self, ctx: JavaParser.ExpressionContext):
    #     if self.current_class:
    #         # 处理方法调用
    #         if ctx.methodCall():
    #             method_call = ctx.methodCall()
    #             caller_expr = method_call.expression().getText()
    #             caller_type = self.resolve_type(caller_expr.split('.')[0])
    #             self._add_interaction(self.current_class, caller_type)
    #
    #         # 处理对象创建
    #         if ctx.NEW():
    #             new_type = self.resolve_type(ctx.creator().createdName().getText())
    #             self._add_interaction(self.current_class, new_type)
    #
    #     self.visitChildren(ctx)


class SIMAnalyzer:
    def __init__(self, files_list: List[str], class_stats: Dict[str, JavaSymbol]):
        self.files_list = files_list
        self.global_class_stats = class_stats
        self.interaction_matrix = np.zeros((len(class_stats), len(class_stats)), dtype=int)

    def _name_to_index(self):
        global name2index
        name2index = {cls: i for i, cls in enumerate(self.global_class_stats.keys())}

    def _index_to_name(self):
        global index2name
        index2name = {i: cls for i, cls in enumerate(self.global_class_stats.keys())}

    def generate_structural_interaction_matrix(self, inherited: bool = False) -> np.ndarray:
        self._name_to_index()
        self._index_to_name()
        for java_file in self.files_list:
            # print(f"正在分析文件: {java_file}")
            visitor = JavaStructureVisitor(self.global_class_stats, self.interaction_matrix)
            with open(java_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
            try:
                input_stream = InputStream(source_code)
                lexer = JavaLexer(input_stream)
                stream = CommonTokenStream(lexer)
                parser = JavaParser(stream)
                tree = parser.compilationUnit()
                tree.accept(visitor)
            except Exception as e:
                print(f"解析 {java_file} 时出现错误: {e}")

        # 如果规定子类继承父类的结构交互
        if inherited:
            for stats in self.global_class_stats.values():
                self.solve_inherited_interaction(stats)

        return self.interaction_matrix

    def solve_inherited_interaction(self, cls: JavaSymbol):
        if not cls.hierarchy:
            return self.interaction_matrix[name2index[cls.full_name]]
        else:
            for super_cls in cls.hierarchy:
                self.interaction_matrix[name2index[cls.full_name]] += self.solve_inherited_interaction(
                    self.global_class_stats[super_cls])

    def print_interaction_matrix(self):
        for i, row in enumerate(self.interaction_matrix):
            cls = index2name[i]
            row_text = [f"{index2name[j]}({count})" for j, count in enumerate(row) if count > 0]
            print(f"{cls} -> {row_text}")
