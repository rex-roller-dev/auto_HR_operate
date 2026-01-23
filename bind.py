from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    # 检查 Content-Type 是否为 JSON
    if not request.is_json:
        return "Invalid Content-Type", 400

    data = request.get_json()
    
    # 获取 challenge
    challenge = data.get("challenge")
    if not challenge:
        return "Missing challenge", 400

    # 原样返回 challenge
    return jsonify({"challenge": challenge}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
