import json
import networkx as nx

# node sym_type to color
NODE_COLOR = {
    'Class': '#91cc75',
    'Interface': '#5470c6',
    'Method': '#61a0a8',
    'Import': '#fac858',
}


class StaticGraphBuilder:
    def __init__(self, project_name: str, data=None):
        self.project_name = project_name
        self.data = data
        self.G = nx.DiGraph()

    def save_data(self, save_path: str):
        with open(save_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def load_data(self, data_path: str):
        with open(data_path, 'r') as f:
            loaded_data = json.load(f)

        # keep sym_type, short_name, full_name, dependency ...
        self.data = [
            {
                'sym_type': node['sym_type'],
                'short_name': node['short_name'],
                'full_name': node['full_name'],
                'start_lineno': node['start_lineno'],
                'stop_lineno': node['stop_lineno'],
                'dependency': node['dependency'],
                'color': NODE_COLOR.get(node['sym_type'], '#f8ac59')
            }
            for node in loaded_data
        ]

    def build_graph(self):
        for node in self.data:
            self.G.add_node(node['full_name'], **node)

        for node in self.data:
            for dep in node['dependency']:
                if self.G.has_edge(node['full_name'], dep):
                    self.G[node['full_name']][dep]['weight'] += 1
                else:
                    self.G.add_edge(node['full_name'], dep, weight=1)

    def save_graph(self, save_path: str, save_format: str = "graphml"):
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

    def visualize_graph(self, output_file: str = "dependency.html"):
        # 生成节点数据
        nodes = [{
            'id': node,
            'name': node,
            'symbolSize': 50,
            'value': self.G.nodes[node],
            'itemStyle': {
                'color': self.G.nodes[node]['color'],
                'shadowBlur': 10,
                'shadowColor': 'rgba(0, 0, 0, 0.3)'
            },
            'label': {
                'show': True  # 默认显示标签
            }
        } for node in self.G.nodes]

        # 生成边数据
        links = [{
            'source': src,
            'target': dst,
            'value': self.G[src][dst]['weight'],
            'lineStyle': {
                'width': self.G[src][dst]['weight'] / 2 + 1,
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
        } for src, dst in self.G.edges]

        categories = [
            {
                'name': '类节点',
                'itemStyle': {'color': NODE_COLOR['Class']}
            },
            {
                'name': '接口节点',
                'itemStyle': {'color': NODE_COLOR['Interface']}
            },
            {
                'name': '方法节点',
                'itemStyle': {'color': NODE_COLOR['Method']}
            },
            {
                'name': '导入节点',
                'itemStyle': {'color': NODE_COLOR['Import']}
            }
        ]

        # ECharts template
        template = f"""
        <!DOCTYPE html>
        <html style="height:100%">
        <head>
            <meta charset="utf-8">
            <title>{self.project_name}静态依赖关系图</title>
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
                        text: '{self.project_name}静态依赖关系图',
                        left: 'center',
                        textStyle: {{ color: '#666', fontSize: 24 }}
                    }},
                    tooltip: {{
                        trigger: 'item',
                        formatter: function(params) {{
                            if(params.dataType === 'node') {{
                                return `符号：${{params.name}}<br>
                                        符号类型：${{params.data.value.sym_type}}<br>
                                        起始行：${{params.data.value.start_lineno}}<br>
                                        结束行：${{params.data.value.stop_lineno}}`;
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
                        categories: {json.dumps(categories, indent=4)}
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

