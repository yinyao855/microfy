# 项目依赖图构建

项目依赖图的数据来源于skywalking的监控数据，具体使用方法如下：
在项目根目录下创建tests文件夹，再创建一个test_graph.py文件，将以下代码复制到test_graph.py中，用pycharm运行即可。
```python
from src.microfy.analyzer.stats.graph import GraphBuilder, generate_echarts_html

api_file_path = "./flask_demo_apis.json"

graph_builder = GraphBuilder("flask-app", api_file_path)
# 收集动态信息，有两个参数，分别是skywalking的地址和时间间隔，单位为小时，24表示最近一天内的数据
graph_builder.collect_dynamic_info('http://192.168.103.117:8080', 24)
# 也可以从文件中读取动态信息
# graph_builder.load_dynamic_info("dynamic_info.json")
# 保存动态信息，格式为json
graph_builder.save_dynamic_info("dynamic_info.json")
graph_builder.generate_graph()
# 生成 ECharts HTML 文件
generate_echarts_html(graph_builder.G, "graph.html")
# 保存图数据，以json格式导出
graph_builder.sava_graph("graph.json", save_format="json")
# 保存识别到的api信息
graph_builder.save_apis("api_info.json")
```

这段代码实现了从skywalking中获取监控数据，生成项目依赖图的功能。其中`api_file_path`是一个json文件， 用于自定义项目中的API信息，
还可以设置API的权重。`/api/orders/{int}`代表会将`/api/orders/1`、`/api/orders/2`等都视为同一个模式进行匹配，否则就会被视为单独的API。
```json
[
    {
        "name": "/api/orders/{int}",
        "weight": 2
    },
    {
        "name": "/api/users/{int}",
        "weight": 1
    },
    {
        "name": "/api/products/{int}",
        "weight": 1
    }
]
```

