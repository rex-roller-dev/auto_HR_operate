import os
import time

def wait_and_check_download_strict(
    download_dir: str,
    expected_name: str,
    ext: str,
    timeout: int = 60
):
    start = time.time()
    ext = ext.lower()

    while time.time() - start < timeout:
        for f in os.listdir(download_dir):
            if f.endswith(".crdownload"):
                continue
            if expected_name in f and f.lower().endswith(ext):
                return True, f
        time.sleep(1)

    return False, None

if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")#保证和下载脚本目录一致

    ok, real_name = wait_and_check_download_strict(
    DOWNLOAD_DIR,
    "志愿深圳记录",
    ".pdf"
)
    if ok:
        print(f"✅ 文件下载成功：{real_name}")
    else:
        print("❌ 文件下载失败")
