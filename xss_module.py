import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qsl
import threading
import time

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

COMMON_PARAMS = [
    "q", "s", "search", "query", "keyword", "id", "item", "page", "ref",
    "lang", "cat", "type", "view", "next", "redirect", "url", "dest",
    "image", "file", "src", "input", "name", "title"
]

class XSSScan:
    def __init__(self, callback_url=None, timeout=10, use_selenium=False, headers=None):
        self.name = "XSS Scan"
        self.timeout = timeout
        self.callback_url = callback_url
        self.headers = headers or {}
        self.vulnerable = []
        self.lock = threading.Lock()
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE

        self.CONTEXT_PAYLOADS = {
            "html": [
                "<script>alert('XSS')</script>",
                "<img src=x onerror=alert(1)>",
                "<svg/onload=alert(1)>",
            ],
            "attribute": [
                '" onmouseover="alert(1)"',
                "' onerror='alert(1)'"
            ],
            "js": [
                '");alert(1);//',
                "';alert(1);//"
            ],
            "css": [
                "<style>*{background:url(javascript:alert(1))}</style>"
            ]
        }

    def log(self, message):
        print(f"[XSS] {message}")

    def find_forms(self, url):
        try:
            res = requests.get(url, headers=self.headers, timeout=self.timeout)
            soup = BeautifulSoup(res.content, "html.parser")
            return soup.find_all("form")
        except Exception as e:
            self.log(f"خطا در دریافت فرم‌ها: {e}")
            return []

    def form_details(self, form):
        details = {}
        details['action'] = form.attrs.get("action", "")
        details['method'] = form.attrs.get("method", "get").lower()
        inputs = []
        for input_tag in form.find_all(["input", "textarea", "select"]):
            input_type = input_tag.attrs.get("type", "text")
            input_name = input_tag.attrs.get("name")
            inputs.append({"type": input_type, "name": input_name})
        details['inputs'] = inputs
        return details

    def scan_url_params(self, url, params_to_test=None):
        parsed = urlparse(url)
        query_params = parse_qsl(parsed.query)
        if params_to_test:
            query_params = [p for p in query_params if p[0] in params_to_test]
        if not query_params:
            return []

        vulnerable = []
        for param_key, _ in query_params:
            for context, payloads in self.CONTEXT_PAYLOADS.items():
                for payload in payloads:
                    test_payload = payload
                    if self.callback_url:
                        test_payload = payload.replace("CALLBACK_URL", self.callback_url)

                    test_params = []
                    for key, value in query_params:
                        if key == param_key:
                            test_params.append((key, test_payload))
                        else:
                            test_params.append((key, value))

                    test_query = "&".join([f"{k}={v}" for k, v in test_params])
                    test_url = parsed._replace(query=test_query).geturl()

                    try:
                        res = requests.get(test_url, headers=self.headers, timeout=self.timeout)
                        if test_payload in res.text:
                            vulnerable.append({
                                'url': test_url,
                                'param': param_key,
                                'payload': test_payload,
                                'method': 'GET',
                                'context': context,
                                'type': 'Reflected (Param)'
                            })
                            break
                    except Exception as e:
                        self.log(f"خطا در درخواست GET: {e}")
                        continue
        return vulnerable

    def test_form(self, url):
        forms = self.find_forms(url)
        vulnerable = []
        for form in forms:
            details = self.form_details(form)
            target_url = urljoin(url, details['action'])
            for context, payloads in self.CONTEXT_PAYLOADS.items():
                for payload in payloads:
                    data = {}
                    for input_field in details['inputs']:
                        if input_field['name']:
                            data[input_field['name']] = payload
                    try:
                        if details['method'] == "post":
                            res = requests.post(target_url, data=data, headers=self.headers, timeout=self.timeout)
                        else:
                            res = requests.get(target_url, params=data, headers=self.headers, timeout=self.timeout)
                        if payload in res.text:
                            vulnerable.append({
                                "url": target_url,
                                "payload": payload,
                                "method": details['method'],
                                "context": context,
                                "type": "Reflected (Form)"
                            })
                            break
                    except Exception as e:
                        self.log(f"خطا در ارسال فرم: {e}")
                        continue
        return vulnerable

    def scan_dom_xss(self, url, params_to_test=None):
        if not self.use_selenium:
            self.log("Selenium نصب نیست یا فعال نشده، اسکن DOM انجام نمی‌شود.")
            return []

        options = Options()
        options.headless = True
        driver = webdriver.Chrome(options=options)
        vulnerable = []
        try:
            parsed = urlparse(url)
            query_params = parse_qsl(parsed.query)
            if params_to_test:
                query_params = [p for p in query_params if p[0] in params_to_test]
            if not query_params:
                return []

            for param_key, _ in query_params:
                for payload in sum(self.CONTEXT_PAYLOADS.values(), []):
                    test_params = []
                    for key, value in query_params:
                        if key == param_key:
                            test_params.append((key, payload))
                        else:
                            test_params.append((key, value))
                    query_string = "&".join([f"{k}={v}" for k, v in test_params])
                    test_url = parsed._replace(query=query_string).geturl()
                    driver.get(test_url)
                    time.sleep(2)
                    if payload in driver.page_source:
                        vulnerable.append({
                            "url": test_url,
                            "payload": payload,
                            "param": param_key,
                            "type": "DOM-based",
                            "method": "GET"
                        })
                        break
        except Exception as e:
            self.log(f"خطا در اسکن DOM XSS: {e}")
        finally:
            driver.quit()
        return vulnerable

    def generate_param_urls(self, base_url, payload="xss_test"):
        urls = []
        for param in COMMON_PARAMS:
            if "?" not in base_url:
                urls.append(f"{base_url}?{param}={payload}")
            else:
                urls.append(f"{base_url}&{param}={payload}")
        return urls

    def run(self, url, params_to_test=None):
        self.vulnerable.clear()
        self.log(f"شروع اسکن XSS روی {url}")

        parsed = urlparse(url)
        if not parsed.query and not params_to_test:
            test_urls = self.generate_param_urls(url)
            for test_url in test_urls:
                self.log(f"تست روی {test_url}")
                param_vulns = self.scan_url_params(test_url)
                with self.lock:
                    self.vulnerable.extend(param_vulns)
        else:
            form_vulns = self.test_form(url)
            with self.lock:
                self.vulnerable.extend(form_vulns)

            param_vulns = self.scan_url_params(url, params_to_test)
            with self.lock:
                self.vulnerable.extend(param_vulns)

            if self.use_selenium:
                dom_vulns = self.scan_dom_xss(url, params_to_test)
                with self.lock:
                    self.vulnerable.extend(dom_vulns)

        if self.vulnerable:
            self.log(f"{len(self.vulnerable)} مورد آسیب‌پذیری یافت شد!")
            return self.vulnerable
        else:
            self.log("هیچ آسیب‌پذیری XSS پیدا نشد.")
            return "ایمن"
