"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""

import os
import random
import time
import functools
from loguru import logger
from DrissionPage import ChromiumOptions, Chromium
from tabulate import tabulate
from bs4 import BeautifulSoup
from notify import NotificationManager

def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    else:
                        logger.warning(f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}")
                        time.sleep(random.uniform(min_delay, max_delay))
            return None
        return wrapper
    return decorator

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ["false", "0", "off"]

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"

class LinuxDoBrowser:
    def __init__(self) -> None:
        from sys import platform
        platformIdentifier = "X11; Linux x86_64"
        if platform == "darwin": platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32": platformIdentifier = "Windows NT 10.0; Win64; x64"

        co = ChromiumOptions()
        co.headless(True)
        co.incognito(True)
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-gpu")
        co.set_user_agent(f"Mozilla/5.0 ({platformIdentifier}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
        
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.notifier = NotificationManager()

    def login(self):
        logger.info("开始登录流程 (浏览器模式)")
        try:
            self.page.get(LOGIN_URL)
            time.sleep(random.uniform(3, 5))

            # 检查是否已经是登录状态
            if self.page.ele("@id=current-user", timeout=2):
                logger.info("已经是登录状态")
                return True

            # 填写账号
            logger.info("正在输入凭据...")
            # 兼容多种可能的选择器
            user_input = self.page.ele("@placeholder=用户名或邮箱") or self.page.ele("#login-account-name")
            if user_input:
                user_input.input(USERNAME)
                time.sleep(random.uniform(1, 2))
                
                pass_input = self.page.ele("@placeholder=密码") or self.page.ele("#login-account-password")
                pass_input.input(PASSWORD)
                time.sleep(random.uniform(1, 2))
                
                # 点击登录按钮
                login_btn = self.page.ele("tag:button@text()=登录") or self.page.ele(".btn-primary")
                login_btn.click()
                
                logger.info("已提交登录信息，等待跳转...")
                time.sleep(8) # 给 Cloudflare 和跳转留时间
            else:
                logger.error("未找到登录输入框，可能是被 Cloudflare 拦截")
                return False

            # 验证登录结果
            if self.page.ele("@id=current-user", timeout=10):
                logger.info("登录成功!")
                self.print_connect_info()
                return True
            else:
                logger.error("登录验证失败：未找到用户头像组件")
                return False

        except Exception as e:
            logger.error(f"登录异常: {str(e)}")
            return False

    def click_topic(self):
        logger.info("准备浏览主题帖...")
        self.page.get(HOME_URL)
        time.sleep(5)
        
        # 定位主题列表
        list_area = self.page.ele("@id=list-area")
        if not list_area:
            logger.error("无法加载主题列表区域")
            return False
            
        topic_list = list_area.eles("tag:a")
        # 过滤出真实的帖子链接
        valid_topics = [t.attr("href") for t in topic_list if "/t/topic/" in (t.attr("href") or "")]
        
        if not valid_topics:
            logger.error("未找到有效的主题帖链接")
            return False
            
        sample_size = min(len(valid_topics), 10)
        selected_topics = random.sample(valid_topics, sample_size)
        
        logger.info(f"发现 {len(valid_topics)} 个主题，随机浏览其中 {sample_size} 个")
        for url in selected_topics:
            self.click_one_topic(url)
        return True

    @retry_decorator()
    def click_one_topic(self, topic_url):
        new_tab = self.browser.new_tab()
        try:
            new_tab.get(topic_url)
            time.sleep(random.uniform(2, 4))
            logger.info(f"正在浏览: {new_tab.title}")
            
            # 模拟滚动
            for _ in range(random.randint(3, 6)):
                dist = random.randint(400, 800)
                new_tab.run_js(f"window.scrollBy(0, {dist})")
                time.sleep(random.uniform(1, 2))
                
        finally:
            new_tab.close()

    def print_connect_info(self):
        try:
            self.page.get("https://connect.linux.do/")
            time.sleep(5)
            # 简单抓取表格数据
            html = self.page.html
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table tr")
            info = []
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 3:
                    info.append([cells[0].text.strip(), cells[1].text.strip(), cells[2].text.strip()])
            
            if info:
                print("\n-------------- Connect Info -----------------")
                print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.warning(f"无法获取 Connect 详情: {e}")

    def run(self):
        try:
            if self.login():
                if BROWSE_ENABLED:
                    self.click_topic()
                    logger.info("所有浏览任务已完成")
                self.send_notifications(True)
            else:
                self.send_notifications(False)
        finally:
            self.browser.quit()

    def send_notifications(self, success):
        status = "✅ 签到成功" if success else "❌ 签到失败"
        msg = f"{status}: {USERNAME}"
        self.notifier.send_all("LINUX DO 助手", msg)

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        logger.error("错误: 请在 Secrets 中设置 LINUXDO_USERNAME 和 LINUXDO_PASSWORD")
        exit(1)
    
    bot = LinuxDoBrowser()
    bot.run()
