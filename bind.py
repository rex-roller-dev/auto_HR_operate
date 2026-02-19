from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    # 打印一下，方便你调试后续正式数据
    try:
        data = request.get_json(force=True, silent=True)
        print("收到数据：", data, flush=True)
    except Exception as e:
        print("JSON 解析失败：", e, flush=True)

    # ✅ 无条件返回 bind_code（验证靠这个）
    return jsonify({"bind_code":"20260123201242397174053"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
