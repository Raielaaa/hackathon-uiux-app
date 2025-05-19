from django.urls import path
from .views import UIUXRecommendationAPIView, WebsiteFullScanAPIView

urlpatterns = [
    path("", UIUXRecommendationAPIView.as_view(), name='uiux-feedback'),
    path("full-scan/", WebsiteFullScanAPIView.as_view(), name='website-full-scan'),
]
