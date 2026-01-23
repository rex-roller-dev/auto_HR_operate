from flask import Flask, request, jsonify

app = Flask(__name__)

def write_to_file(text):#重定向输出到文件
    with open("test.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")

@app.route("/wps_callback", methods=["POST"])
def wps_callback():
    data : dict = request.get_json()
    print("收到：", data)

    # 重定向输出到文件
    #write_to_file(str(data))

    return jsonify({"code": 0, "msg": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
