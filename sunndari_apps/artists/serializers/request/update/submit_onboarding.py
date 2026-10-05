from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.submit_onboarding import SubmitOnboardingRequest


class SubmitOnboardingSerializer(serializers.Serializer):

    def create(self, validated_data) -> SubmitOnboardingRequest:
        return SubmitOnboardingRequest(**validated_data)
