import json
import re
from datetime import timedelta, datetime

import networkx as nx
import requests
from sqlglot import parse, exp, ErrorLevel


# 从skywalking收集监控信息
class DynamicCollector:
    def __init__(self, skywalking_backend_url: str = 'http://localhost:8080', time_gap: int = 72):
        self.backend_url = skywalking_backend_url
        self.query_url = f"{self.backend_url}/graphql"
        self.time_gap = timedelta(hours=time_gap)
        self.services = None
        self.traces = None
        self.traces_full_info = []

    def query_graphql(self, query, variables):
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            self.query_url,
            json={"query": query, "variables": variables},
            headers=headers
        )

        # 检查响应
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def query_services(self):
        query = """
        query queryServices($layer: String!) {
            services: listServices(layer: $layer) {
                id
                value: name
                label: name
                group
                layers
                normal
                shortName
            }
        }
        """

        variables = {"layer": "GENERAL"}
        data = self.query_graphql(query, variables)
        self.services = data.get("data").get("services")

    def query_traces(self, service_id: str):
        query = """
        query queryTraces($condition: TraceQueryCondition) {
            data: queryBasicTraces(condition: $condition) {
                traces {
                key: segmentId
                endpointNames
                duration
                start
                isError
                traceIds
                }
            }
        }
        """

        current_time = datetime.now()
        former_time = current_time - self.time_gap

        variables = {
            "condition": {
                "queryDuration": {
                    "start": former_time.strftime("%Y-%m-%d %H%M"),
                    "end": current_time.strftime("%Y-%m-%d %H%M"),
                    "step": "MINUTE"
                },
                "traceState": "ALL",
                "queryOrder": "BY_START_TIME",
                "paging": {
                    "pageNum": 1,
                    "pageSize": 100
                },
                "minTraceDuration": None,
                "maxTraceDuration": None,
                "serviceId": service_id
            }
        }

        data = self.query_graphql(query, variables)
        self.traces = data.get("data").get("data").get("traces")

    def query_trace(self, trace_id: str):
        query = """
        query queryTrace($traceId: ID!) {
            trace: queryTrace(traceId: $traceId) {
                spans {
                    traceId
                    segmentId
                    spanId
                    parentSpanId
                    refs {
                        traceId
                        parentSegmentId
                        parentSpanId
                        type
                    }
                    serviceCode
                    serviceInstanceName
                    startTime
                    endTime
                    endpointName
                    type
                    peer
                    component
                    isError
                    layer
                    tags {
                        key
                        value
                    }
                    logs {
                        time
                        data {
                            key
                            value
                        }
                    }
                    attachedEvents {
                        startTime {
                            seconds
                            nanos
                        }
                        event
                        endTime {
                            seconds
                            nanos
                        }
                        tags {
                            key
                            value
                        }
                        summary {
                            key
                            value
                        }
                    }
                }
            }
        }
        """

        variables = {"traceId": trace_id}
        data = self.query_graphql(query, variables)
        self.traces_full_info.append(data.get("data").get("trace").get("spans"))

    def query_traces_by_service_name(self, service_name: str):
        target_service_id = None
        self.traces_full_info = []
        self.query_services()
        # print(self.services)
        for service in self.services:
            if service.get("value") == service_name:
                target_service_id = service.get("id")
                break

        self.query_traces(target_service_id)
        # print(json.dumps(self.traces, indent=1))
        for trace in self.traces:
            self.query_trace(trace.get("traceIds")[0])
        # print(json.dumps(self.traces_full_info, indent=1))
        return self.traces_full_info


def to_regex(name):
    patterns = [
        {
            "var": r"{int}",
            "regex": r"\\d+"
        },
        {
            "var": r"{str}",
            "regex": r"[a-zA-Z0-9]+"
        },
    ]

    for pattern in patterns:
        name = re.sub(pattern["var"], pattern["regex"], name)
    # print(name)
    return name


class GraphBuilder:
    def __init__(self, project_name: str, api_config_file: str = None):
        self.project_name = project_name
        self.api_config_file = api_config_file
        self.G = nx.DiGraph()
        self.api_config = []
        self.apis = []
        self.traces = []

    def collect_dynamic_info(self, skywalking_backend_url: str, hour_time_gap: int = 72):
        dynamic_collector = DynamicCollector(skywalking_backend_url, hour_time_gap)
        self.traces = dynamic_collector.query_traces_by_service_name(self.project_name)

    def load_dynamic_info(self, trace_file: str):
        with open(trace_file, "r") as f1:
            self.traces = json.load(f1)

    def save_apis(self, save_path: str):
        with open(save_path, "w") as f2:
            json.dump(self.apis, f2, indent=4)

    def save_dynamic_info(self, save_path: str):
        with open(save_path, "w") as f3:
            json.dump(self.traces, f3, indent=4)

    def generate_graph(self):
        if self.api_config_file:
            with open(self.api_config_file, "r") as json_file:
                self.api_config = json.load(json_file)

        for trace in self.traces:
            self.add_to_graph(trace)

    def sava_graph(self, save_path: str, save_format: str = "graphml"):
        if save_format == "graphml":
            nx.write_graphml(self.G, save_path)
        elif save_format == "gexf":
            nx.write_gexf(self.G, save_path)
        elif save_format == "gml":
            nx.write_gml(self.G, save_path)
        elif save_format == "json":
            # 转换图为节点和边的列表
            nodes = [{"id": node, **self.G.nodes[node]} for node in self.G.nodes()]
            edges = [{"source": u, "target": v, **self.G.edges[u, v]} for u, v in self.G.edges()]
            graph_data = {
                "nodes": nodes,
                "edges": edges
            }
            # 将图数据保存为 JSON 文件
            with open(save_path, 'w') as f:
                json.dump(graph_data, f, indent=4)
        else:
            raise ValueError(f"不支持的格式: {save_format}")

    def match_api(self, name):
        for api in self.api_config:
            if api["name"] == name or re.fullmatch(to_regex(api["name"]), name):
                return api
        return None

    def get_node_id(self, node):
        node_id = node["endpointName"]
        if node["spanId"] == 0:
            api = self.match_api(node_id)
            if api:
                node_id = api["name"]
        return node_id

    # 提取span信息，生成节点信息
    def get_span_info(self, span):
        forbid_names = ["HikariCP"]
        if span["endpointName"].split("/")[0] in forbid_names:
            return None

        endpoint_names = [span["endpointName"]]
        node_type = "service"
        node_weight = 0
        # 提取权重信息
        for tag in span["tags"]:
            if tag["key"] == "weight":
                node_weight = int(tag["value"])

        if span["type"] == "Entry":
            node_type = "api"
            matched_api = self.match_api(span["endpointName"])
            if matched_api:
                endpoint_names = [matched_api["name"]]
                node_weight = matched_api.get("weight", 0)
        elif span["layer"] == "Database":
            node_type = "database"
            tags = {tag["key"]: tag["value"] for tag in span["tags"]}
            sql = tags["db.statement"]
            if not sql:
                return None

            # 去掉 SQL 语句中的换行符
            sql = sql.replace("\n", "")
            parsed_sqls = parse(sql, error_level=ErrorLevel.IGNORE)
            # 提取 SQL 语句中的表名
            tables = [table.this.sql() for parsed_sql in parsed_sqls for table in parsed_sql.find_all(exp.Table)]
            if tables and tables[0] != "`":
                endpoint_names = [f'{tags["db.type"]}.{tags["db.instance"]}.{table}' for table in tables]
            # print("EndpointNames:", endpointNames)

        keys = ["traceId", "segmentId", "spanId", "parentSpanId", "startTime", "endTime"]
        nodes = [
            {
                "endpointName": endpoint_name,
                "type": node_type,
                "weight": node_weight,
                **{key: span[key] for key in keys}
            }
            for endpoint_name in endpoint_names
        ]
        return nodes

    def add_to_graph(self, trace):
        weight = 1
        for span in trace:
            nodes = self.get_span_info(span)
            if not nodes:
                continue

            for node in nodes:
                node_id = node.get("endpointName")
                execution_time = node["endTime"] - node["startTime"]

                if self.G.has_node(node_id):
                    self.G.nodes[node_id]["execution_time"] += execution_time
                    self.G.nodes[node_id]["count"] += 1
                else:
                    self.G.add_node(node_id, execution_time=execution_time, count=1,
                                    type=node["type"], weight=node["weight"])

                # 如果不是api节点
                if node["parentSpanId"] != -1:
                    prev_node = next((n for n in trace if n["spanId"] == node["parentSpanId"]), None)
                    if prev_node:
                        prev_node_id = self.get_node_id(prev_node)
                        if self.G.has_edge(node_id, prev_node_id):
                            self.G[node_id][prev_node_id]["weight"] += weight
                        else:
                            self.G.add_edge(prev_node_id, node_id, weight=weight)
                else:
                    self.apis.append(node)
                    if node.get("weight") > 0:
                        weight = node.get("weight")


def generate_echarts_html(graph: nx.DiGraph, output_file: str = "dag.html"):
    # 生成节点数据
    nodes = [{
        'id': node,
        'name': node,
        'symbolSize': min(graph.nodes[node]['count'] / 5 + 30, 100),  # 限制最大尺寸
        'value': graph.nodes[node],
        'itemStyle': {
            'color': '#91cc75' if graph.nodes[node]['type'] == 'api' else  # 端口绿色
            ('#ff7875' if graph.nodes[node]['type'] == 'database' else '#5470c6'),  # 数据库红色/服务蓝色
            'shadowBlur': 10,
            'shadowColor': 'rgba(0, 0, 0, 0.3)'
        },
        'label': {
            'show': True  # 默认显示标签
        }
    } for node in graph.nodes]

    # 生成边数据
    links = [{
        'source': src,
        'target': dst,
        'value': graph[src][dst]['weight'],
        'lineStyle': {
            'width': graph[src][dst]['weight'] / 2 + 1,
            'color': {
                'type': 'linear',
                'x': 0,
                'y': 0,
                'x2': 1,
                'y2': 0,
                'colorStops': [{
                    'offset': 0, 'color': '#91d5ff'  # 渐变色边
                }, {
                    'offset': 1, 'color': '#096dd9'
                }]
            }
        }
    } for src, dst in graph.edges]

    # ECharts template
    template = f"""
    <!DOCTYPE html>
    <html style="height:100%">
    <head>
        <meta charset="utf-8">
        <title>服务依赖关系图</title>
        <script src="https://cdn.staticfile.org/echarts/5.4.2/echarts.min.js"></script>
        <style>
            body, html {{ margin:0; padding:0; height:100%; width:100%; }}
            #main {{ height:100vh; width:100vw; }}
        </style>
    </head>
    <body>
        <div id="main"></div>
        <script>
            var chart = echarts.init(document.getElementById('main'));

            var option = {{
                title: {{
                    text: '服务依赖关系图',
                    left: 'center',
                    textStyle: {{ color: '#666', fontSize: 24 }}
                }},
                tooltip: {{
                    trigger: 'item',
                    formatter: function(params) {{
                        if(params.dataType === 'node') {{
                            return `服务：${{params.name}}<br>
                                    调用次数：${{params.data.value.count}}<br>
                                    总耗时：${{params.data.value.execution_time/1000}}ms`;
                        }}
                        return `权重：${{params.value}}`;
                    }}
                }},
                animationDuration: 2000,
                series: [{{
                    type: 'graph',
                    layout: 'force',
                    force: {{
                        repulsion: 3000,
                        gravity: 0.1,
                        edgeLength: 150,
                        layoutAnimation: true
                    }},
                    roam: true,
                    focusNodeAdjacency: true,
                    edgeSymbol: ['none', 'arrow'],
                    edgeSymbolSize: [0, 15],
                    label: {{
                        show: true,
                        position: 'right',
                        fontSize: 12,
                        color: '#000',
                        formatter: function(params) {{
                            // 名称截断显示
                            return params.name.length > 15 ? 
                                params.name.substr(0,12)+'...' : 
                                params.name;
                        }},
                        emphasis: {{ show: false }}  // 悬停时不显示标签
                    }},
                    emphasis: {{
                        label: {{ show: false }},
                        itemStyle: {{
                            shadowBlur: 20,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }}
                    }},
                    lineStyle: {{
                        curveness: 0.2,
                        opacity: 0.8
                    }},
                    data: {json.dumps(nodes, indent=4)},
                    links: {json.dumps(links, indent=4)},
                    categories: [{{
                        name: '数据库节点',
                        itemStyle: {{ color: '#ff7875' }}
                    }}, {{
                        name: '端口节点',
                        itemStyle: {{ color: '#91cc75' }}
                    }}, {{
                        name: '服务节点',
                        itemStyle: {{ color: '#5470c6' }}
                    }}]
                }}],
                legend: {{
                    orient: 'vertical',
                    right: 20,
                    top: 60,
                    textStyle: {{ color: '#666' }}
                }}
            }};

            chart.setOption(option);

            // 窗口自适应
            window.addEventListener('resize', () => chart.resize());

            // 双击重置视图
            chart.getZr().on('dblclick', () => {{
                chart.setOption(option);
            }});
        </script>
    </body>
    </html>
    """

    with open(output_file, 'w') as f:
        f.write(template)
