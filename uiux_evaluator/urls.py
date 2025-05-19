from django.urls import path
from .views import UIUXRecommendationAPIView

urlpatterns = [
    path("", UIUXRecommendationAPIView.as_view(), name='uiux-feedback'),
]
