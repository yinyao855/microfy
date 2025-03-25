import os
from typing import List

from src.microfy.analyzer.stats.java.collector import ClassAnalyzer
from src.microfy.analyzer.stats.java.sim import SIMAnalyzer
from src.microfy.analyzer.stats.java.tfidf import TFIDFAnalyzer


# java 项目分析器
class JavaAnalyzer:
    def __init__(self, project_path: str = None):
        # 项目路径
        self.project_path = project_path
        # 项目文件列表
        self.files_list = []
        # 全局类信息
        self.class_analyzer: ClassAnalyzer = None
        # 类结构交互矩阵
        self.sim_analyzer: SIMAnalyzer = None
        # 类TF-IDF矩阵
        self.tfidf_analyzer: TFIDFAnalyzer = None

    def set_project_path(self, project_path: str):
        self.project_path = project_path
        self.get_java_files()

    # 获取 Java 项目中的所有 Java 文件
    def get_java_files(self):
        java_files: List[str] = []
        for root, _, files in os.walk(self.project_path):
            for file in files:
                if file.endswith('.java'):
                    java_files.append(os.path.join(root, file))
        self.files_list = java_files

    # 收集项目中的所有Java类信息
    def collect_class_stats(self):
        if self.files_list is None:
            self.get_java_files()
        self.class_analyzer = ClassAnalyzer(self.files_list)
        self.class_analyzer.collect_class_stats()

    # 生成类结构交互矩阵
    def generate_interaction_matrix(self, inherited: bool = False):
        if self.files_list is None:
            self.get_java_files()
        self.sim_analyzer = SIMAnalyzer(self.files_list, self.class_analyzer.global_class_stats)
        self.sim_analyzer.generate_structural_interaction_matrix(inherited)

    # 生成TF-IDF矩阵
    def generate_tfidf_matrix(self):
        if self.files_list is None:
            self.get_java_files()
        self.tfidf_analyzer = TFIDFAnalyzer(self.files_list)
        self.tfidf_analyzer.generate_tfidf_matrix()

    def output(self):
        print('\033[1;32m======Java Class Stats======\033[0m')
        self.class_analyzer.print_class_stats()
        print('\n\033[1;32m======Structure Interaction Matrix======\033[0m')
        self.sim_analyzer.print_interaction_matrix()
        print('\n\033[1;32m======TF-IDF Matrix======\033[0m')
        self.tfidf_analyzer.print_tfidf_matrix()
