import time
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

def wait_for_download(download_dir, expected_name, ext, timeout=60):
    """
    等待浏览器下载完成

    参数说明：
    - download_dir : 下载目录（浏览器的默认下载路径）
    - expected_name: 期望的文件名关键字（不要写完整名，防止出现 (1)）
    - ext          : 文件扩展名，例如 ".pdf"
    - timeout      : 最大等待时间（秒）

    返回值：
    - (True, filename)  : 下载成功，返回真实文件名
    - (False, None)     : 超时或下载失败
    """
    start = time.time()

    while time.time() - start < timeout:
        for f in os.listdir(download_dir):
            # 下载完成：目标文件存在，且没有 .crdownload
            if expected_name in f and f.lower().endswith(ext):
                cr_tmp = f + ".crdownload"
                if not os.path.exists(os.path.join(download_dir, cr_tmp)):
                    return True, f

        time.sleep(1)  # 每秒检查一次

    return False, None

def download_file_from_wps(url: str,expected_name: str,ext: str):
    # ===== 1️⃣ EdgeDriver 路径 =====
    EDGE_DRIVER_PATH = r".\msedgedriver.exe"

    # ===== 2️⃣ Edge 用户数据目录（改成你自己的）=====
    EDGE_USER_DATA = r"C:\Users\20391\AppData\Local\Microsoft\Edge\User Data\Default\Cache\Cache_Data"

    # ===== 3️⃣ 下载目录 =====
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print("Download dir =", DOWNLOAD_DIR)
    
    # ===== Edge 配置 =====
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # ⭐ 关键：使用真实 Edge 登录态（免登录）
    options.add_argument(f"--user-data-dir={EDGE_USER_DATA}")
    # 如果你平时用 Default，一般不需要这行
    # options.add_argument("--profile-directory=Default")

    # 下载设置
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(EDGE_DRIVER_PATH)

    # ===== 启动浏览器（只启动一次！）=====
    driver = webdriver.Edge(service=service, options=options)

    # ===== 打开 WPS 分享链接 =====
    driver.get(url)

    # ===== 等页面加载完成 =====
    wait = WebDriverWait(driver, 30)
    time.sleep(3)
    try:
        menu_btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH,
                "//button[contains(@class,'kd-button-icon') and .//i[contains(@class,'kd-icon-menu')]]")
            )
        )
        driver.execute_script("arguments[0].click();", menu_btn)
        print("✅ 已点击 ☰ 菜单")
    except Exception as e:
        print("❌ 菜单按钮没找到：", e)

    # 给菜单一点展开时间
    time.sleep(1.5)

    try:
        # 等“下载”按钮出现
        download_btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[contains(text(),'下载')]")
            )
        )
        download_btn.click()
        print("✅ 已点击【下载】按钮")
    except Exception as e:
        print("❌ 没找到下载按钮：", e)
    # ===== 等待下载完成 =====
    success, filename = wait_for_download(
    download_dir=DOWNLOAD_DIR,
    expected_name=expected_name,
    ext=ext,
    timeout=60
    )
    if success:
        print(f"✅ 文件下载成功：{filename}")
    else:
        print("❌ 文件下载失败")

    driver.quit()

if __name__ == "__main__":
    download_file_from_wps(url="https://www.kdocs.cn/l/ck0BBmRwjKyl",expected_name="志愿深圳",ext=".pdf")
    download_file_from_wps(url="https://www.kdocs.cn/l/cpLuhzT78p6q",expected_name="认证表",ext=".docx")