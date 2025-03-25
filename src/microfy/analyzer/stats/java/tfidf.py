import re
from typing import List

import nltk
import numpy as np
from antlr4 import InputStream, CommonTokenStream
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import TfidfVectorizer

from src.microfy.lang.java.JavaLexer import JavaLexer
from src.microfy.lang.java.JavaParser import JavaParser
from src.microfy.lang.java.JavaParserVisitor import JavaParserVisitor

# 下载停用词数据
nltk.download('stopwords')


def camel_case_split(identifier: str) -> List[str]:
    matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return [m.group(0).lower() for m in matches]


# 预处理文本
def preprocess_text(text: str) -> str:
    stop_words = set(stopwords.words('english'))
    stemmer = PorterStemmer()
    # 转换为小写
    text = text.lower()
    # 拆分单词
    words = text.split()
    # 过滤停用词
    filtered_words = [word for word in words if word not in stop_words]
    # 词干化
    stemmed_words = [stemmer.stem(word) for word in filtered_words]
    return ' '.join(stemmed_words)


# 提取类和接口的语义信息
class JavaSemanticVisitor(JavaParserVisitor):
    def __init__(self):
        self.class_texts = []
        self.current_class = None
        self.current_interface = None

    def visitClassDeclaration(self, ctx: JavaParser.ClassDeclarationContext):
        # 提取类名
        class_name = ctx.identifier().getText()
        self.current_class = {'name': class_name, 'methods': [], 'fields': []}

        # 遍历类体
        self.visitClassBody(ctx.classBody())

        # 拼接文本
        text_parts = camel_case_split(class_name)
        text_parts += [m for method in self.current_class['methods'] for m in camel_case_split(method)]
        text_parts += [f for field in self.current_class['fields'] for f in camel_case_split(field)]
        self.class_texts.append(' '.join(text_parts))
        return self.class_texts

    def visitMethodDeclaration(self, ctx: JavaParser.MethodDeclarationContext):
        if self.current_class:
            method_name = ctx.identifier().getText()
            self.current_class['methods'].append(method_name)
        self.visitChildren(ctx)

    def visitFieldDeclaration(self, ctx: JavaParser.FieldDeclarationContext):
        # 检查当前是否有正在处理的类
        if self.current_class:
            # 遍历字段声明中的所有变量声明符
            for declarator in ctx.variableDeclarators().variableDeclarator():
                # 获取变量声明符的标识符（即字段名）
                field_name = declarator.variableDeclaratorId().identifier().getText()
                # 将字段名添加到当前类的字段列表中
                self.current_class['fields'].append(field_name)
        # 继续访问当前节点的子节点
        self.visitChildren(ctx)

    # 处理接口
    def visitInterfaceDeclaration(self, ctx: JavaParser.InterfaceDeclarationContext):
        # 提取接口名
        interface_name = ctx.identifier().getText()
        self.current_interface = {'name': interface_name, 'methods': []}

        # 遍历接口体
        self.visitInterfaceBody(ctx.interfaceBody())

        # 拼接文本
        text_parts = camel_case_split(interface_name)
        text_parts += [m for method in self.current_interface['methods'] for m in camel_case_split(method)]
        self.class_texts.append(' '.join(text_parts))

    def visitInterfaceMethodDeclaration(self, ctx: JavaParser.InterfaceMethodDeclarationContext):
        if self.current_interface:
            method_name = ctx.interfaceCommonBodyDeclaration().identifier().getText()
            self.current_interface['methods'].append(method_name)
        self.visitChildren(ctx)


class TFIDFAnalyzer:
    def __init__(self, files_list: List[str]):
        self.files_list = files_list
        self.tfidf_matrix = None
        self.all_class_texts = []

    def generate_tfidf_matrix(self) -> np.ndarray:
        for java_file in self.files_list:
            # print(f"正在分析文件: {java_file}")
            visitor = JavaSemanticVisitor()
            with open(java_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
            try:
                input_stream = InputStream(source_code)
                lexer = JavaLexer(input_stream)
                token_stream = CommonTokenStream(lexer)
                parser = JavaParser(token_stream)
                tree = parser.compilationUnit()
                tree.accept(visitor)
                class_texts = visitor.class_texts
                preprocessed_texts = [preprocess_text(text) for text in class_texts]
                self.all_class_texts.extend(preprocessed_texts)
            except Exception as e:
                print(f"解析 {java_file} 时出现错误: {e}")

        vectorizer = TfidfVectorizer()
        self.tfidf_matrix = vectorizer.fit_transform(self.all_class_texts)
        return self.tfidf_matrix.toarray()

    def print_tfidf_matrix(self):
        print(self.tfidf_matrix.toarray())


if __name__ == '__main__':
    test_name = 'CamelCaseSplitTest'
    print(f"驼峰命名拆分测试: {test_name} -> {camel_case_split(test_name)}")
