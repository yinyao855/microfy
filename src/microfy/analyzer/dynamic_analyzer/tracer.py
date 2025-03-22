import sys
import threading
import time
import json
import importlib.util
from collections import defaultdict
import shutil
import os
import re
from sqlalchemy import Engine

# 获取 Python 标准库路径
python_lib_path = os.path.dirname(os.__file__)


def is_library_function(frame):
    filename = frame.f_code.co_filename
    return python_lib_path in filename


class Config:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = None
        self.load_config()
        self.task_type = self.config['task_type']

    def load_config(self):
        with open(self.config_path) as f:
            self.config = json.load(f)


class UniversalTracer:
    def __init__(self, config):
        self.thread_local = threading.local()
        self.trace_data = defaultdict(list)
        self.io_data = defaultdict(list)  # 用于存储普通 I/O 操作的追踪数据
        self.db_data = defaultdict(list)  # 用于存储数据库操作的追踪数据
        self.enabled = False
        self.has_saved = threading.local()
        self.save_count = 0
        self.config = config

    def start_tracing(self):
        if not self.enabled:
            sys.settrace(self.trace_calls)
            self.enabled = True

    def stop_tracing(self):
        if self.enabled:
            sys.settrace(None)
            self.enabled = False

    def extract_table_name(self, sql):
        """
        从 SQL 语句中提取表名。
        """
        # 组合多个 SQL 子句的正则表达式
        pattern = r'(?:FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+["\']?(\w+)["\']?'
        match = re.search(pattern, sql, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def trace_calls(self, frame, event, arg):
        if is_library_function(frame):
            return None

        if event == 'call':
            if not hasattr(self.thread_local, 'call_stack'):
                self.thread_local.call_stack = []
                self.thread_local.start_time = time.time()

            caller_frame = frame.f_back
            caller_first_lineno = None
            if caller_frame:
                caller_function_name = caller_frame.f_code.co_name
                caller_file = caller_frame.f_code.co_filename
                caller_lineno = caller_frame.f_lineno
                caller_first_lineno = caller_frame.f_code.co_firstlineno
            else:
                caller_function_name = None
                caller_file = None
                caller_lineno = None

            called_function_name = frame.f_code.co_name
            called_file = frame.f_code.co_filename
            called_lineno = frame.f_lineno

            call_info = {
                'caller_function_name': caller_function_name,
                'caller_file': caller_file,
                'caller_lineno': caller_lineno,
                'called_function_name': called_function_name,
                'called_file': called_file,
                'called_lineno': called_lineno,
                'start_time': time.time(),
                'caller_first_lineno': caller_first_lineno,
                'io_nodes': [],
                'db_nodes': []

            }
            self.thread_local.call_stack.append(call_info)

            if called_function_name in ('open', 'read', 'write', 'close'):
                io_info = {
                    'io_function': called_function_name,
                    'file': called_file,
                    'line': called_lineno,
                    'start_time': time.time(),
                    'call_stack': [f"{c['called_function_name']} ({c['called_file']}:{c['called_lineno']})"
                                   for c in self.thread_local.call_stack],
                    'exec_time': 0
                }
                self.io_data[threading.current_thread().name].append(io_info)

        elif event == 'return':
            if hasattr(self.thread_local, 'call_stack') and self.thread_local.call_stack:
                call_info = self.thread_local.call_stack.pop()
                exec_time = time.time() - call_info['start_time']
                call_info['exec_time'] = exec_time
                self.trace_data[threading.current_thread().name].append(call_info)

                if call_info['called_function_name'] in ('open', 'read', 'write', 'close'):
                    # 构建一个映射，提高查找效率
                    io_info_map = {
                        (io_info['io_function'], io_info['file'], io_info['line']): io_info
                        for io_info in self.io_data[threading.current_thread().name]
                    }
                    key = (call_info['called_function_name'], call_info['called_file'], call_info['called_lineno'])
                    if key in io_info_map:
                        io_info = io_info_map[key]
                        io_info['exec_time'] = exec_time
                        call_stack = self.thread_local.call_stack
                        if call_stack and len(call_stack) > 0:
                            for item in reversed(call_stack):
                                if (self.config.config['task_dir'] in item['called_file'] and
                                        self.config.config['venv_dir'] not in item['called_file']):
                                    item.setdefault("io_nodes", []).append(io_info)
                                    break

        return self.trace_calls

    def save_to_json(self, filename=None):
        save_dir = self.config.config['trace_output_dir']
        if filename is None:
            filename = f"{save_dir}/{self.save_count}_trace_output.json"
        os.makedirs(save_dir, exist_ok=True)

        result = {
            'trace_data': self.trace_data,
            'io_data': self.io_data,
            'db_data': self.db_data
        }

        with open(filename, 'w') as f:
            json.dump(result, f, indent=4)
        print(f"Trace data saved to {filename}.")
        self.save_count += 1

    def import_module_from_path(self, module_path: str):
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run(self, config):
        import argparse

        if config.task_type == 'django':
            patch_django(self)
        elif config.task_type == 'flask':
            patch_flask(self)
            setup_sqlalchemy_events(codeTracer)

        task_config = {}
        task_args = {}
        if 'task_config' in config.config:
            task_config = config.config['task_config']
        if 'default_args' in task_config:
            task_args.update(task_config['default_args'])
        parser = argparse.ArgumentParser()
        args = parser.parse_args([])
        for key, value in task_args.items():
            setattr(args, key.replace('-', '_'), value)

        if 'task_file' in config.config:
            module_path = config.config['task_file']
            module = self.import_module_from_path(module_path)
            module.main(args)


def patch_flask(tracer):
    from flask import Flask

    original_dispatch_request = Flask.dispatch_request

    def dispatch_request(self):
        tracer.start_tracing()
        try:
            result = original_dispatch_request(self)
        finally:
            tracer.stop_tracing()
            tracer.save_to_json()
        return result

    Flask.dispatch_request = dispatch_request


def patch_django(tracer):
    from django.core.handlers.wsgi import WSGIHandler
    original_call = WSGIHandler.__call__

    def traced_call(self, environ, start_response):
        tracer.start_tracing()
        try:
            result = original_call(self, environ, start_response)
        finally:
            tracer.stop_tracing()
            tracer.save_to_json()
        return result

    WSGIHandler.__call__ = traced_call


def setup_sqlalchemy_events(tracer):
    from sqlalchemy import event

    @event.listens_for(Engine, "before_execute")
    def before_execute(conn, clauseelement, multiparams, params):
        sql = str(clauseelement)
        table_name = tracer.extract_table_name(sql)
        if table_name:
            print(f"Executing SQL on table: {table_name}")
            db_info = {
                'db_function': 'execute',
                'table': table_name,
                'sql': sql,
                'start_time': time.time(),
                'exec_time': None
            }
            call_stack = getattr(tracer.thread_local, "call_stack", None)
            if call_stack and len(call_stack) > 0:
                for item in reversed(call_stack):
                    if tracer.config.config['task_dir'] in item['called_file'] and tracer.config.config[
                        'venv_dir'] not in item['called_file']:
                        item.setdefault("db_nodes", []).append(db_info)
                        print(item)
                        break
            else:
                tracer.db_data[threading.current_thread().name].append(db_info)

    @event.listens_for(Engine, "after_execute")
    def after_execute(conn, clauseelement, multiparams, params, result):
        end_time = time.time()
        sql_str = str(clauseelement)
        call_stack = getattr(tracer.thread_local, "call_stack", None)
        updated = False
        if call_stack and len(call_stack) > 0:
            for item in reversed(call_stack):
                if (tracer.config.config['task_dir'] in item['called_file'] and
                        tracer.config.config['venv_dir'] not in item['called_file']):
                    for db_info in item.get("db_nodes", []):
                        if db_info["sql"] == sql_str and db_info["exec_time"] is None:
                            db_info["exec_time"] = end_time - db_info["start_time"]
                            updated = True
                            break
        if not updated:
            for db_info in tracer.db_data[threading.current_thread().name]:
                if db_info["sql"] == sql_str and db_info["exec_time"] is None:
                    db_info["exec_time"] = end_time - db_info["start_time"]
                    break


if __name__ == '__main__':
    config_path = '../../examples/flask_demo/config.json'
    config = Config(config_path)
    shutil.rmtree(config.config['trace_output_dir'], ignore_errors=True)
    codeTracer = UniversalTracer(config)
    codeTracer.run(config)
