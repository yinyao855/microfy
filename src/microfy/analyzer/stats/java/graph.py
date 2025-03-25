import json
import re

import networkx as nx
from sqlglot import parse, exp


def to_regex(name):
    # print("name:", name)
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
    def __init__(self, trace_file: str, entry_file: str = None):
        self.trace_file = trace_file
        self.entry_file = entry_file
        self.G = nx.DiGraph()
        self.entries = []
        self.traces = []

    def generate_graph(self, to_json=False):
        with open(self.trace_file, "r") as json_file:
            self.traces = json.load(json_file)

        if self.entry_file:
            with open(self.entry_file, "r") as json_file:
                self.entries = json.load(json_file)

        for trace in self.traces:
            self.add_to_graph(trace, to_json)

    def sava_graph(self, save_path: str):
        nx.write_graphml(self.G, save_path)

    def match_entry(self, name):
        tmp_entry = {}
        # print(entries)
        for entry in self.entries:
            if entry["name"] == name:
                return entry
            elif re.fullmatch(to_regex(entry["name"]), name):
                # print("hihi!")
                tmp_entry = entry
        return tmp_entry

    def get_node_id(self, node):
        node_id = node["endpointName"]
        if node["spanId"] == 0:
            entry = self.match_entry(node_id)
            node_id = entry["name"] if entry else node_id
        return node_id

    def get_attributes(self, span):
        forbid_names = ["HikariCP"]
        if span["endpointName"].split("/")[0] in forbid_names:
            return None
        endpoint_names = [span["endpointName"]]
        type = "service"
        if span["layer"] == "Database":
            type = "database"
            tags = {tag["key"]: tag["value"] for tag in span["tags"]}
            sql = tags["db.statement"]
            if not sql:
                return None
            # print(json.dumps(span, indent=1))
            tables = []
            try:
                parsed_sqls = parse(sql)
            except Exception as e:
                print(e)
                return None
            for parsed_sql in parsed_sqls:
                # print(parsed_sql.sql(pretty=True))
                tables += [table.this.sql() for table in parsed_sql.find_all(exp.Table)]
                # print("Tables:", tables)
            if not tables:
                return None
            endpoint_names = [f'{tags["db.type"]}.{tags["db.instance"]}.{table}' for table in tables]
            # print("EndpointNames:", endpointNames)

        keys = ["traceId", "segmentId", "spanId", "parentSpanId", "startTime", "endTime"]
        nodes = []
        for endpoint_name in endpoint_names:
            attributes = {"endpointName": endpoint_name, "type": type}
            for key in keys:
                attributes[key] = span[key]
            # print(json.dumps(attributes, indent=1))
            nodes += [attributes]
        return nodes

    def add_to_graph(self, trace, to_json=False):
        weight = 1
        for span in trace:
            nodes = self.get_attributes(span)
            if not nodes:
                continue

            for node in nodes:
                node_id = self.get_node_id(node)
                execution_time = node["endTime"] - node["startTime"]

                if self.G.has_node(node_id):
                    self.G.nodes[node_id]["execution_time"] += execution_time
                    self.G.nodes[node_id]["count"] += 1
                else:
                    self.G.add_node(node_id, execution_time=execution_time, count=1, type=node["type"])

                # 如果 parentSpanId 不是 -1，则添加边
                if node["parentSpanId"] != -1:
                    parent_node = next((n for n in trace if n["spanId"] == node["parentSpanId"]), None)
                    if parent_node:
                        parent_node_id = self.get_node_id(parent_node)
                        if self.G.has_edge(node_id, parent_node_id):
                            self.G[node_id][parent_node_id]["weight"] += weight
                        else:
                            self.G.add_edge(node_id, parent_node_id, weight=weight)
                else:
                    if to_json:
                        self.entries += [node]
                    else:
                        name = node["endpointName"]
                        entry = self.match_entry(name)
                        weight = entry["weight"] if entry else 1


def generate_echarts_html(graph: nx.DiGraph, output_file: str = "dag.html"):
    # 识别服务端口（没有出度的节点）
    entry_nodes = [node for node in graph.nodes if graph.out_degree(node) == 0]

    # 生成节点数据
    nodes = [{
        'id': node,
        'name': node,
        'symbolSize': min(graph.nodes[node]['count'] / 5 + 30, 100),  # 限制最大尺寸
        'value': graph.nodes[node]['execution_time'],
        'itemStyle': {
            'color': '#91cc75' if node in entry_nodes else  # 端口绿色
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
                                    调用次数：${{params.data.symbolSize}}<br>
                                    总耗时：${{Math.round(params.data.value)}}us`;
                        }}
                        return `调用次数：${{params.value}}次`;
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
                        position: 'inside',
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
