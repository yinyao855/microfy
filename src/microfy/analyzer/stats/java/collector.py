import json
from collections import defaultdict
from typing import List, Dict

from antlr4 import InputStream, CommonTokenStream

from src.microfy.lang.java.JavaLexer import JavaLexer
from src.microfy.lang.java.JavaParser import JavaParser
from src.microfy.lang.java.JavaParserVisitor import JavaParserVisitor

global_class_index = 0  # 全局类索引


# java 类信息
class JavaClassStats:
    def __init__(self, index: int = None, short_name: str = None, full_name: str = None):
        self.index = index  # 类索引
        self.short_name = short_name  # 短类名
        self.full_name = full_name  # 全限定名
        self.methods = []  # 方法列表
        self.hierarchy = []  # 父类/继承接口列表


# 用于收集Java类的信息
class JavaClassCollector(JavaParserVisitor):
    def __init__(self):
        self.package_name = ""  # 包名
        self.classes = defaultdict(JavaClassStats)  # 类信息字典

    def visitPackageDeclaration(self, ctx: JavaParser.PackageDeclarationContext):
        self.package_name = ctx.qualifiedName().getText()

    def visitClassDeclaration(self, ctx: JavaParser.ClassDeclarationContext):
        global global_class_index
        class_name = ctx.identifier().getText()
        full_name = f"{self.package_name}.{class_name}" if self.package_name else class_name
        self.classes[full_name] = JavaClassStats(global_class_index, class_name, full_name)
        global_class_index += 1
        return self.visitChildren(ctx)

    def visitInterfaceDeclaration(self, ctx: JavaParser.InterfaceDeclarationContext):
        global global_class_index
        interface_name = ctx.identifier().getText()
        full_name = f"{self.package_name}.{interface_name}" if self.package_name else interface_name
        self.classes[full_name] = JavaClassStats(global_class_index, interface_name, full_name)
        global_class_index += 1
        return self.visitChildren(ctx)


class ClassAnalyzer:
    def __init__(self, files_list: List[str]):
        # 项目文件列表
        self.files_list = files_list
        # 全局类信息
        self.global_class_stats = defaultdict(JavaClassStats)

    # 收集项目中的所有Java类信息
    def collect_class_stats(self) -> Dict[str, JavaClassStats]:
        global global_class_index
        global_class_index = 0
        for java_file in self.files_list:
            # print(f"正在分析文件: {java_file}")
            collector = JavaClassCollector()
            with open(java_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
            try:
                input_stream = InputStream(source_code)
                lexer = JavaLexer(input_stream)
                token_stream = CommonTokenStream(lexer)
                parser = JavaParser(token_stream)
                tree = parser.compilationUnit()
                tree.accept(collector)
                self.global_class_stats.update(collector.classes)
            except Exception as e:
                print(f"解析 {java_file} 时出现错误: {e}")
        return self.global_class_stats

    def print_class_stats(self):
        # 以json格式输出类信息
        for k, v in self.global_class_stats.items():
            print(json.dumps(v.__dict__, indent=4))
