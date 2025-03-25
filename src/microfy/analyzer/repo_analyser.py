import ast
import fnmatch
from pathlib import Path
from typing import Dict, List
from .static_analyzer.dependency_tracer import DependencyNode, DependencyTracer


def should_ignore(path, rules, base_path):
    """
    判断路径是否应被忽略
    """
    relative_path = path.relative_to(base_path)
    for rule in rules:
        if rule.startswith('/'):
            # 绝对路径规则
            if fnmatch.fnmatch(str(relative_path), rule[1:]):
                return True
        else:
            # 相对路径规则
            if fnmatch.fnmatch(str(relative_path), f'**/{rule}'):
                return True
    return False


def extract_file_tree(repo_path: Path, ignore_rules: List[str] = None) -> List[Path]:
    """
    提取仓库的文件树
    """
    file_tree = []
    for path in repo_path.rglob('*'):
        # if not should_ignore(path, ignore_rules, repo_path):
        #     file_tree.append(str(path))
        if any(folder in path.parts for folder in ignore_rules):
            continue
        if path.is_file() and path.suffix == '.py':
            file_tree.append(path)
    return file_tree


def resolve_module_name(path: Path, repo_path: Path) -> str:
    """
    从文件路径中解析模块名
    """
    relative_path = path.relative_to(repo_path)
    # 将/替换为.，去掉.py后缀
    return str(relative_path).replace('/', '.').replace('.py', '')


class RepoAnalyzer:
    def __init__(self, repo_path: str, ignore_rules: List[str] = None):
        self.repo_path: Path = Path(repo_path)
        self.modules: Dict[str, DependencyNode] = {}
        self.file_tree: List[Path] = extract_file_tree(self.repo_path, ignore_rules)
        self.global_depend_map: Dict[str, DependencyNode] = {}
        self.obj_funcs: Dict[str, ast.AST] = {}

    def analyze(self):
        """
        Analyze the repository and generate a report.
        """
        for file_path in self.file_tree:
            with open(file_path, 'r') as f:
                code = f.read()

            module_name = resolve_module_name(file_path, self.repo_path)
            tracer = DependencyTracer(code, module_name)
            tree = ast.parse(code)
            res, funcs = tracer.analyze(tree)
            self.global_depend_map.update(res)
            self.obj_funcs.update(funcs)
            # tracer.save_analysis(f"{module_name}.json")

        # # 下面将以user.py下的get_user为例，展示如何将其函数化
        # get_user_func = self.global_depend_map[self.obj_funcs['get_user']]
        # # print(ast.unparse(get_user_func.node))
        # # 分析其依赖，先去掉局部变量
        # keys_to_remove = [dep.name for dep in get_user_func.dependencies.values() if
        #                   dep.full_name.startswith(get_user_func.full_name)]
        #
        # for key in keys_to_remove:
        #     get_user_func.dependencies.pop(key)
        # print(get_user_func.dependencies.keys())
        # for dep in get_user_func.dependencies.values():
        #     print(ast.unparse(dep.node))
