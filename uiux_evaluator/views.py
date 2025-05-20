from rest_framework import generics
from rest_framework.response import Response
from urllib.parse import urlencode, urlparse
import time, json, subprocess, requests
from collections import Counter
from .serializers import WebsiteURLSerializer
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PAGESPEED_API_KEY = "AIzaSyANm28tCwij2AaUN3eF43g98PVE5IWBKJE"
WAVE_API_KEY = "Y9zumtvP5402"

DEFAULT_TIMEOUT = 120


class UIUXRecommendationAPIView(generics.GenericAPIView):
    serializer_class = WebsiteURLSerializer

    # Extract hostname from URL for observatory analysis
    def get_hostname(self, url):
        parsed = urlparse(url)
        return parsed.netloc or parsed.path

    # Helper for requests with retries and exponential backoff
    def _request_with_retries(self, method, url, **kwargs):
        retries = 3
        backoff = 1
        headers = kwargs.pop('headers', {})
        headers.setdefault('User-Agent', 'UIUXAnalyzer/1.0 (+https://yourdomain.com)')
        for attempt in range(retries):
            try:
                response = requests.request(method, url, headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                time.sleep(backoff)
                backoff *= 2
        return None

    # Call Google PageSpeed Insights API for both mobile and desktop strategies,
    # returning key performance metrics and Lighthouse audit results for both
    def analyze_pagespeed(self, url):
        def fetch(strategy):
            try:
                params = {
                    'url': url,
                    'key': PAGESPEED_API_KEY,
                    'strategy': strategy,  # 'mobile' or 'desktop'
                    'category': ['performance', 'accessibility', 'best-practices', 'seo'],
                    'locale': 'en_US',
                }
                api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?{urlencode(params, doseq=True)}"
                response = self._request_with_retries('GET', api_url)
                data = response.json()

                lighthouse = data.get('lighthouseResult', {})
                audits = lighthouse.get('audits', {})
                categories = lighthouse.get('categories', {})

                details = {
                    'overall_score': int(categories.get('performance', {}).get('score', 0) * 100),
                    'first_contentful_paint': audits.get('first-contentful-paint', {}).get('displayValue', 'N/A'),
                    'speed_index': audits.get('speed-index', {}).get('displayValue', 'N/A'),
                    'time_to_interactive': audits.get('interactive', {}).get('displayValue', 'N/A'),
                    'total_blocking_time': audits.get('total-blocking-time', {}).get('displayValue', 'N/A'),
                    'largest_contentful_paint': audits.get('largest-contentful-paint', {}).get('displayValue', 'N/A'),
                    'cumulative_layout_shift': audits.get('cumulative-layout-shift', {}).get('displayValue', 'N/A'),
                    'mobile_friendly': audits.get('viewport', {}).get('score', 1),
                    'render_blocking_resources': audits.get('render-blocking-resources', {}).get('score', 1),
                    'uses_rel_preconnect': audits.get('uses-rel-preconnect', {}).get('score', 1),
                    'server_response_time': audits.get('server-response-time', {}).get('displayValue', 'N/A'),
                    'uses_text_compression': audits.get('uses-text-compression', {}).get('score', 1),
                    'uses_optimized_images': audits.get('uses-optimized-images', {}).get('score', 1),
                    'uses_webp_images': audits.get('uses-webp-images', {}).get('score', 1),
                    'efficient_animated_content': audits.get('efficient-animated-content', {}).get('score', 1),
                    'unused_javascript': audits.get('unused-javascript', {}).get('details', {}).get('items', []),
                    'unused_css_rules': audits.get('unused-css-rules', {}).get('details', {}).get('items', []),
                    'diagnostics': audits.get('diagnostics', {}).get('details', {}).get('items', []),
                }

                # 🔍 Add detailed UI audit fields
                ui_audits = ['color-contrast', 'font-size', 'tap-targets', 'image-aspect-ratio']
                ui_issues = {}

                for audit_key in ui_audits:
                    audit = audits.get(audit_key)
                    if audit and audit.get('score', 1) < 1:
                        affected_nodes = []
                        details_obj = audit.get('details', {})
                        if details_obj and 'items' in details_obj:
                            for item in details_obj['items']:
                                node = item.get('node', {})
                                if node:
                                    snippet = node.get('snippet')
                                    path = node.get('path') or node.get('selector') or 'unknown'
                                    if snippet:
                                        affected_nodes.append({'path': path, 'snippet': snippet})
                        ui_issues[audit_key] = {
                            'title': audit.get('title'),
                            'description': audit.get('description'),
                            'help': audit.get('helpText'),
                            'nodes': affected_nodes
                        }

                details['ui_issues'] = ui_issues

                return details

            except Exception as e:
                return {'error': f"PageSpeed API error for {strategy}: {str(e)}"}

        mobile_results = fetch('mobile')
        desktop_results = fetch('desktop')

        recommendations = []

        def add_recommendations(details, label):
            if isinstance(details, dict) and 'error' not in details:
                if details.get('overall_score') is not None and details['overall_score'] < 80:
                    recommendations.append(f"{label}: Performance is below optimal. Optimize images, enable compression, and minimize blocking scripts.")
                if details['mobile_friendly'] == 0:
                    recommendations.append(f"{label}: Page is not mobile-friendly. Add a meta viewport and use responsive design.")
                if details['uses_optimized_images'] < 0.9:
                    recommendations.append(f"{label}: Serve images in next-gen formats like WebP or AVIF for better loading speed.")
                if details['render_blocking_resources'] < 0.9:
                    recommendations.append(f"{label}: Eliminate or defer render-blocking resources such as CSS and JS.")
                if details['uses_rel_preconnect'] < 0.9:
                    recommendations.append(f"{label}: Consider using resource hintws like preconnect or dns-prefetch for critical origins.")
                if details['uses_text_compression'] < 0.9:
                    recommendations.append(f"{label}: Enable text compression (gzip, brotli) on your server.")
                if details['uses_webp_images'] < 0.9:
                    recommendations.append(f"{label}: Convert images to WebP format to reduce size.")
                if details['efficient_animated_content'] < 0.9:
                    recommendations.append(f"{label}: Optimize animated content for better performance.")
                if details['unused_javascript']:
                    recommendations.append(f"{label}: Remove unused JavaScript ({len(details['unused_javascript'])} scripts identified).")
                if details['unused_css_rules']:
                    recommendations.append(f"{label}: Remove unused CSS rules ({len(details['unused_css_rules'])} rules identified).")

        add_recommendations(mobile_results, "Mobile")
        add_recommendations(desktop_results, "Desktop")

        def add_ui_issues(details, label):
            ui_issues = details.get("ui_issues", {})
            for key, issue in ui_issues.items():
                title = issue.get("title")
                if title:
                    recommendations.append(f"{label}: {title}")

        add_ui_issues(mobile_results, "General")
        add_ui_issues(desktop_results, "General")

        return {
            'mobile': mobile_results,
            'desktop': desktop_results,
            'recommendations': recommendations
        }

    def analyze_accessibility(self, url):
        api_endpoint = "https://wave.webaim.org/api/request"
        params = {
            'key': WAVE_API_KEY,
            'url': url,
            'reporttype': '4'
        }

        try:
            response = requests.get(api_endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def summarize_accessibility_report(self, data):
        print("\n[DEBUG] Raw data received for summarization:")
        print(json.dumps(data, indent=2))  # <-- View the full JSON from WAVE API

        if 'error' in data:
            print("[DEBUG] Detected 'error' key in data.")
            return f"Accessibility analysis failed with error: {data['error']}"

        # No 'all_results' or 'accessibility' key—access data directly
        status = data.get('status', {})
        print("[DEBUG] Status section:", status)

        if not status.get('success', False):
            print("[DEBUG] Accessibility analysis unsuccessful.")
            return f"Accessibility analysis request was not successful. HTTP Status: {status.get('httpstatuscode', 'Unknown')}"

        stats = data.get('statistics', {})
        print("[DEBUG] Statistics section:", stats)

        page_title = stats.get('pagetitle', 'Unknown page')
        page_url = stats.get('pageurl', 'Unknown URL')
        total_elements = stats.get('totalelements', 0)

        categories = data.get('categories', {})
        print("[DEBUG] Categories section:", categories)

        errors = categories.get('error', {}).get('count', 0)
        error_desc = categories.get('error', {}).get('description', 'Errors')
        contrast_issues = categories.get('contrast', {}).get('count', 0)
        alerts = categories.get('alert', {}).get('count', 0)
        features = categories.get('feature', {}).get('count', 0)
        structure = categories.get('structure', {}).get('count', 0)
        aria_issues = categories.get('aria', {}).get('count', 0)

        return (f"The accessibility analysis for '{page_title}' ({page_url}) examined {total_elements} elements. "
                f"Found {errors} errors related to {error_desc.lower()}, {contrast_issues} contrast issue(s), "
                f"{alerts} alerts, {features} feature(s), {structure} structural element(s), "
                f"and {aria_issues} ARIA issues.")

    def analyze_ssllabs(self, url):
        try:
            host = self.get_hostname(url)
            start_url = f"https://api.ssllabs.com/api/v3/analyze?host={host}&publish=off&all=done"
            status_url = f"https://api.ssllabs.com/api/v3/analyze?host={host}&fromCache=on"

            self._request_with_retries('GET', start_url)

            # Poll for analysis readiness
            for _ in range(15):
                response = self._request_with_retries('GET', status_url)
                data = response.json()
                if data.get("status") == "READY":
                    break
                time.sleep(5)

            endpoints = data.get("endpoints", [])
            if not endpoints:
                return {'error': "No endpoints found from SSL Labs"}

            endpoint = endpoints[0]
            details = endpoint.get("details", {})
            cert = details.get("cert", {})
            hsts = details.get("hstsPolicy", {})

            grade = endpoint.get("grade", "N/A")
            ip = endpoint.get("ipAddress", "N/A")
            server_name = endpoint.get("serverName", "N/A")
            status_message = endpoint.get("statusMessage", "N/A")

            # Collect recommendations based on configuration
            recommendations = []

            if grade in ['A+', 'A']:
                recommendations.append(f"Site has a strong SSL/TLS configuration with a grade of {grade}.")
            if details.get("forwardSecrecy") == 2:
                recommendations.append("Ensure continued support for Forward Secrecy across all modern browsers.")
            if not details.get("supportsRc4", False):
                recommendations.append("RC4 cipher is disabled, which is recommended.")
            if hsts.get("status") == "present":
                recommendations.append("HSTS is enabled.")
                if hsts.get("longMaxAge", False):
                    recommendations.append("HSTS max-age is sufficiently long for preloading (helps maintain A+).")
            if not cert.get("issues"):
                recommendations.append("Certificate chain is complete and valid.")
            if cert.get("notAfter"):
                recommendations.append("Certificate is valid and not expired.")
            if endpoint.get("hasWarnings"):
                recommendations.append("Review non-fatal SSL warnings for further improvement.")

            if not recommendations:
                recommendations = ["No specific recommendations. SSL Labs scan returned no major findings."]

            return {
                'ssllabs_grade': grade,
                'endpoint_info': {
                    'ipAddress': ip,
                    'grade': grade,
                    'serverName': server_name,
                    'statusMessage': status_message
                },
                'recommendations': recommendations
            }

        except Exception as e:
            return {'error': f"SSL Labs API error: {str(e)}"}

    # Combine recommendations from all services and categorize them by source.
    def aggregate_results(self, results):
        categorized_recommendations = {}

        # Iterate over each service's results
        for service_name, service_result in results.items():
            if isinstance(service_result, dict) and 'recommendations' in service_result:
                recs = service_result['recommendations']
                if recs:
                    categorized_recommendations[service_name] = recs

        if not categorized_recommendations:
            return {
                "summary": "No UI/UX feedback could be generated from the analysis.",
                "categories": {}
            }

        return {
            'summary': "UI/UX recommendations categorized by service.",
            'categories': categorized_recommendations
        }

    # Handle POST request with URL, analyze with Wave, Observatory, and PageSpeed APIs, then aggregate results.
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        data = serializer.validated_data

        url = data["url"]
        apply_accessibility = data.get("is_accessibility_applied", False)
        apply_pagespeed = data.get("is_pagespeed_applied", False)
        apply_security = data.get("is_security_applied", False)

        accessibility_result = None
        pagespeed_result = None
        security_result = None

        if apply_accessibility:
            # accessibility_result = data
            data = self.analyze_accessibility(url)
            prompt = f"Analyze the accessibility of the URL: {data}. Provide a summary of the findings, make it in paragraph. Limit it to at most 30 words."
            accessibility_result = self.query_mistral(prompt)
        if apply_pagespeed:
            pagespeed_result = self.analyze_pagespeed(url)
        if apply_security:
            security_result = self.analyze_ssllabs(url)

        results = {
            "accessibility": accessibility_result,
            "pagespeed": pagespeed_result,
            "security": security_result
        }

        final_recommendation = self.aggregate_results(results)

        return Response({
            "final_recommendation": final_recommendation,
            "all_results": results
        })

    def query_mistral(self, prompt):
        try:
            result = subprocess.run(
                ['ollama', 'run', 'mistral'],
                input = prompt,
                capture_output = True,
                text = True,
                encoding = 'utf-8',
                errors = 'ignore',
                check = True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Error running Ollama: {e.stderr.strip() or str(e)}"
        except FileNotFoundError:
            return "Error: 'ollama' command not found. Ensure Ollama is installed and added to your system PATH."

class WebsiteFullScanAPIView(generics.GenericAPIView):
    serializer_class = WebsiteURLSerializer

    def get_internal_links(self, base_url):
        internal_links = set()

        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        driver = webdriver.Chrome(options=options)

        try:
            driver.get(base_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            domain = urlparse(base_url).netloc

            for tag in soup.find_all("a", href=True):
                href = tag['href']
                full_url = urljoin(base_url, href)
                if urlparse(full_url).netloc == domain:
                    internal_links.add(full_url)

        except Exception as e:
            print(f"Error rendering page: {e}")
        finally:
            driver.quit()

        return list(internal_links)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = request.data
        base_url = serializer.validated_data['url']
        apply_accessibility = data.get("is_accessibility_applied", False)
        apply_pagespeed = data.get("is_pagespeed_applied", False)
        apply_security = data.get("is_security_applied", False)

        uiux_analyzer = UIUXRecommendationAPIView()

        scanned_pages = self.get_internal_links(base_url)
        if base_url not in scanned_pages:
            scanned_pages.insert(0, base_url)

        scan_results = []

        for page_url in scanned_pages:
            try:
                page_report = {
                    "url": page_url,
                    "all_results": {},
                    "final_recommendation": {
                        "summary": "UI/UX recommendations categorized by service.",
                        "categories": {}
                    }
                }

                if apply_pagespeed:
                    pagespeed_result = uiux_analyzer.analyze_pagespeed(page_url)
                    page_report["all_results"]["pagespeed"] = pagespeed_result
                    if "recommendations" in pagespeed_result and pagespeed_result["recommendations"]:
                        page_report["final_recommendation"]["categories"]["pagespeed"] = pagespeed_result["recommendations"]

                if apply_accessibility:
                    data = uiux_analyzer.analyze_accessibility(page_url)
                    prompt = f"Analyze the accessibility of the URL: {data}. Provide a summary of the findings, make it in paragraph. Limit it to at most 30 words."
                    accessibility_result = uiux_analyzer.query_mistral(prompt)
                    page_report["all_results"]["accessibility"] = accessibility_result
                    if "recommendations" in accessibility_result and accessibility_result["recommendations"]:
                        page_report["final_recommendation"]["categories"]["accessibility"] = accessibility_result["recommendations"]

                if apply_security:
                    security_result = uiux_analyzer.analyze_ssllabs(page_url)
                    page_report["all_results"]["security"] = security_result
                    if "recommendations" in security_result and security_result["recommendations"]:
                        page_report["final_recommendation"]["categories"]["security"] = security_result["recommendations"]

                scan_results.append(page_report)

            except Exception as e:
                scan_results.append({
                    "url": page_url,
                    "error": f"Failed to analyze {page_url}: {str(e)}"
                })

        return Response({
            "total_pages_scanned": len(scan_results),
            "results": scan_results
        })

    def aggregate_results(self, results):
        categorized_recommendations = {
            'pagespeed': [],
            'accessibility': [],
            'security': []
        }

        for result in results:
            # Skip errored pages
            if 'error' in result:
                continue

            # Check each service result
            for service_name in ['pagespeed', 'accessibility', 'security']:
                if service_name in result:
                    service_result = result[service_name]
                    if isinstance(service_result, dict) and 'recommendations' in service_result:
                        recs = service_result['recommendations']
                        if recs:
                            categorized_recommendations[service_name].extend(recs)

        # Filter out empty categories
        categorized_recommendations = {
            k: v for k, v in categorized_recommendations.items() if v
        }

        if not categorized_recommendations:
            return {
                "summary": "No UI/UX feedback could be generated from the analysis.",
                "categories": {}
            }

        return {
            'summary': "UI/UX recommendations categorized by service.",
            'categories': categorized_recommendations
        }
