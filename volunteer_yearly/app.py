"""SCF WebServer镜像入口：在请求结束前完成处理，不依赖响应后的后台线程。"""
import hmac
import logging
import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from yearly.config import Settings
from yearly.cosio import Busy
from yearly.forms import unwrap, parse_submission
from yearly.models import UserError, ServiceError
from yearly.service import Processor, SHANGHAI
from datetime import datetime

logger = logging.getLogger("volunteer_yearly")


def create_app(settings=None, processor_factory=None):
    cfg = settings or Settings.from_env()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    factory = processor_factory or (lambda headers: Processor.for_request(cfg, headers))

    def bind_response():
        if not cfg.bind_code:
            return jsonify(code=503, msg="请先配置WPS_BIND_CODE"), 503
        return jsonify(bind_code=cfg.bind_code)

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.route("/", methods=["GET", "POST"])
    @app.route("/event-invoke", methods=["GET", "POST"])
    def callback():
        try:
            if cfg.callback_secret:
                supplied = request.headers.get("X-Callback-Secret") or request.args.get("secret", "")
                if not hmac.compare_digest(supplied, cfg.callback_secret):
                    return jsonify(code=403, msg="回调校验失败"), 403
            # 绑定探测可以没有 JSON 请求体，应在解析答卷之前返回绑定码。
            if request.method == "GET" or not request.get_data().strip():
                return bind_response()
            data = unwrap(request.get_json(force=True))
            if data.get("event") == "bind" or "answerContents" not in data:
                return bind_response()
            submission = parse_submission(data, cfg, datetime.now(SHANGHAI).date())
            result = factory(request.headers).run(submission)
            logger.info("event=%s status=%s", submission.event_id, result["status"])
            return jsonify(code=0, msg="Success", data=result)
        except (UserError, BadRequest):
            # 无法安全识别收件人的表单错误通过HTTP反馈；不猜测邮箱，也不记录原始表单。
            return jsonify(code=400, msg="表单字段或JSON格式错误，请检查配置及填写内容"), 400
        except RequestEntityTooLarge:
            return jsonify(code=413, msg="回调请求体过大"), 413
        except Busy:
            return jsonify(code=503, msg="任务正在处理，请稍后重试"), 503
        except ServiceError as exc:
            logger.error("processing_error=%s", str(exc))
            return jsonify(code=503, msg="处理暂未完成，请稍后重试或联系管理员"), 503
        except Exception as exc:
            logger.error("unexpected_error_type=%s", type(exc).__name__)
            return jsonify(code=503, msg="处理暂未完成，请联系管理员"), 503

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "9000")))
