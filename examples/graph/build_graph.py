import os
from microfy.analyzer.stats.graph import GraphBuilder, generate_echarts_html

if not os.path.exists("res"):
    os.mkdir("res")
else:
    for file in os.listdir("res"):
        os.remove(os.path.join("res", file))

# springboot demo

api_file_path = "./springboot_demo_apis.json"

graph_builder = GraphBuilder("java-app", api_file_path)
graph_builder.load_dynamic_info("dynamic_info.json")
graph_builder.generate_graph()
# generate ECharts HTML
generate_echarts_html(graph_builder.G, "./res/graph_springboot.html")

# flask demo

api_file_path = "./flask_demo_apis.json"

graph_builder = GraphBuilder("flask-app", api_file_path)
# collect info from skywalking
graph_builder.collect_dynamic_info('http://192.168.103.117:8080', 5)
# graph_builder.save_dynamic_info("dynamic_info.json")
graph_builder.generate_graph()
generate_echarts_html(graph_builder.G, "./res/graph_flask.html")
graph_builder.sava_graph("./res/graph_flask.json", save_format="json")
graph_builder.save_apis("./res/flask_apis_info.json")
