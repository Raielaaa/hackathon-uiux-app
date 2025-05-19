from rest_framework import serializers

class WebsiteURLSerializer(serializers.Serializer):
    url = serializers.URLField(required = True)
    is_accessibility_applied = serializers.BooleanField(default = True)
    is_pagespeed_applied = serializers.BooleanField(default = True)
    is_security_applied = serializers.BooleanField(default = True)