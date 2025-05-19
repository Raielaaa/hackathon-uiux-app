from rest_framework import generics
from rest_framework.response import Response
from urllib.parse import urlencode, urlparse
import requests
import time
from collections import Counter
from .serializers import WebsiteURLSerializer
from bs4 import BeautifulSoup
from urllib.parse import urljoin

PAGESPEED_API_KEY = "AIzaSyANm28tCwij2AaUN3eF43g98PVE5IWBKJE"
WAVE_API_KEY = "Ue4G4Int5398"

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
        try:
            response = self._request_with_retries('GET', url)
            html = response.text

            soup = BeautifulSoup(html, 'html.parser')

            # Basic checks
            images = soup.find_all('img')
            images_missing_alt = [img for img in images if not img.has_attr('alt') or not img['alt'].strip()]

            title_tag = soup.find('title')
            missing_title = title_tag is None or not title_tag.text.strip()

            # ARIA landmarks (e.g., role="banner", "navigation", "main", "contentinfo")
            landmarks = soup.find_all(attrs={"role": True})
            missing_landmarks = len(landmarks) == 0

            # Form elements without labels
            form_elements = soup.find_all(['input', 'select', 'textarea'])
            unlabeled_elements = []
            for el in form_elements:
                id_attr = el.get('id')
                if id_attr:
                    label = soup.find('label', attrs={'for': id_attr})
                    if not label:
                        unlabeled_elements.append(el)
                else:
                    # no id means can't be referenced by label
                    unlabeled_elements.append(el)

            issues = {
                'images_missing_alt': len(images_missing_alt),
                'missing_title': missing_title,
                'missing_landmarks': missing_landmarks,
                'unlabeled_form_elements': len(unlabeled_elements),
            }

            recommendations = []

            if issues['images_missing_alt'] > 0:
                recommendations.append(f"Found {issues['images_missing_alt']} images missing alt attributes. Add descriptive alt text for all images.")
            if issues['missing_title']:
                recommendations.append("Missing or empty <title> tag. Add a descriptive page title.")
            if issues['missing_landmarks']:
                recommendations.append("No ARIA landmark roles found. Use roles like 'banner', 'navigation', 'main', and 'contentinfo' for better navigation.")
            if issues['unlabeled_form_elements'] > 0:
                recommendations.append(f"Found {issues['unlabeled_form_elements']} form elements without associated labels. Ensure all form inputs have labels.")

            return {
                'accessibility_summary': issues,
                'recommendations': recommendations
            }

        except Exception as e:
            return {'error': f"Accessibility check error: {str(e)}"}

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
            accessibility_result = self.analyze_accessibility(url)
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

class WebsiteFullScanAPIView(generics.GenericAPIView):
    serializer_class = WebsiteURLSerializer

    def get_internal_links(self, base_url):
        try:
            response = requests.get(base_url, timeout = 30)
            soup = BeautifulSoup(response.content, "html.parser")
            base_domain = urlparse(base_url).netloc

            links = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                parsed = urlparse(href)

                if parsed.netloc and parsed.netloc != base_domain:
                    continue  # External link

                full_url = urljoin(base_url, href)
                if full_url.startswith(base_url):
                    links.add(full_url.split("#")[0])  # Remove fragment
            return list(links)
        except Exception as e:
            return []

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        base_url = serializer.validated_data['url']

        internal_pages = self.get_internal_links(base_url)
        if base_url not in internal_pages:
            internal_pages.insert(0, base_url)  # Include main page first

        analyzer = UIUXRecommendationAPIView()

        results = []
        for url in internal_pages:
            try:
                page_speed = analyzer.analyze_pagespeed(url)
                accessibility = analyzer.analyze_accessibility(url)
                security_result = analyzer.analyze_ssllabs(url)
                results.append({
                    "url": url,
                    "page_speed": page_speed,
                    "accessibility": accessibility,
                    "security": security_result
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "error": str(e)
                })

        return Response({
            "base_url": base_url,
            "total_pages_scanned": len(results),
            "pages": results
        })
