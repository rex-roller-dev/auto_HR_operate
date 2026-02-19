from flask import Flask, request, jsonify
from queue import Queue

app = Flask(__name__)

# ✅ 全局唯一队列
task_queue = Queue()

def write_to_file(text):
    with open("test.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")

@app.route("/event-invoke", methods=["POST"])
def wps_callback():
    global request_id
    # 获取请求头中的 X-Scf-Request-Id
    request_id = request.headers.get('X-Scf-Request-Id')
    print(f"📩 收到 WPS 数据，请求 ID: {request_id}")

    data: dict = request.get_json()

    task_queue.put(data)
    print("📥 数据已入队")

    return jsonify({"bind_code":"20260123201242397174053"}), 200

def write_to_file(text):#重定向输出到文件
    with open("test.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
