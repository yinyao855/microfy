import os
from typing import List, Optional
from .profiler import JavaStaticProfiler
from .tfidf import TFIDFAnalyzer
from .dcm import DCMAnalyzer


# java 项目分析器
class JavaAnalyzer:
    def __init__(self, project_path: str = None):
        # 项目路径
        self.project_path = project_path
        # 项目文件列表
        self.files_list = []
        # 静态分析器
        self.static_profiler: Optional[JavaStaticProfiler] = None
        # 类TF-IDF矩阵
        self.tfidf_analyzer: Optional[TFIDFAnalyzer] = None
        # 动态调用矩阵
        self.dcm_analyzer: Optional[DCMAnalyzer] = None

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

    def static_profile(self):
        if self.files_list is None:
            self.get_java_files()
        self.static_profiler = JavaStaticProfiler(self.files_list)
        self.static_profiler.profile()

    # 生成TF-IDF矩阵
    def generate_tfidf_matrix(self):
        if self.files_list is None:
            self.get_java_files()
        self.tfidf_analyzer = TFIDFAnalyzer(self.files_list)
        self.tfidf_analyzer.generate_tfidf_matrix()

    def generate_dcm_matrix(self):
        if not self.static_profiler:
            return

        self.dcm_analyzer = DCMAnalyzer(self.static_profiler)

    def output(self):
        print('\n\033[1;32m======Structure Interaction Matrix======\033[0m')
        self.static_profiler.print_interaction_matrix()
        print('\n\033[1;32m======TF-IDF Matrix======\033[0m')
        self.tfidf_analyzer.print_tfidf_matrix()
